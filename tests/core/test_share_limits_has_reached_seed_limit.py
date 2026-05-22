"""Tests for ShareLimits.has_reached_seed_limit — the deletion-eligibility logic.

This is the most regression-sensitive code in share_limits.py. The matrix
covers min_num_seeds, last_active, max_ratio (hard + global), max_seeding_time
(hard + global), min_seeding_time crossover, dry_run, and resume_torrent.
"""

from __future__ import annotations

from modules.core import share_limits as share_limits_mod


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


def _has_call(torrent, name):
    return any(c[0] == name for c in torrent.calls)


def _seed_limit(sl, torrent, **overrides):
    """Invoke ShareLimits.has_reached_seed_limit with sensible defaults.

    Unpacks the (body, exclusion_tag_added) tuple and returns body only,
    so callers can assert on the body value directly.
    """
    kwargs = {
        "torrent": torrent,
        "max_ratio": -1,
        "max_seeding_time": -1,
        "max_last_active": -1,
        "min_seeding_time": 0,
        "min_num_seeds": 0,
        "min_last_active": 0,
        "resume_torrent": True,
        "tracker": "http://tracker1.example/announce",
        "reset_upload_speed_on_unmet_minimums": True,
    }
    kwargs.update(overrides)
    body, _exclusion_tag_added = sl.has_reached_seed_limit(**kwargs)
    return body


# ---- min_num_seeds ----------------------------------------------------------


def test_min_num_seeds_zero_never_gates(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0)
    assert _seed_limit(sl, t, min_num_seeds=0) is False
    assert _calls_of(t, "add_tags") == []


def test_min_num_seeds_met_clears_existing_tag(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(num_complete=10, tags=sl.min_num_seeds_tag)
    _seed_limit(sl, t, min_num_seeds=5)
    assert _has_call(t, "remove_tags")


def test_min_num_seeds_not_met_adds_tag_and_clears_limits(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(num_complete=2, tags="")
    result = _seed_limit(sl, t, min_num_seeds=5)
    assert result == ""  # NOT eligible for deletion
    add_tag = _calls_of(t, "add_tags")
    assert add_tag and add_tag[0][1]["tags"] == sl.min_num_seeds_tag
    set_limits = _calls_of(t, "set_share_limits")
    assert set_limits and set_limits[0][1]["ratio_limit"] == -1
    assert set_limits[0][1]["seeding_time_limit"] == -1
    assert set_limits[0][1]["inactive_seeding_time_limit"] == -1
    assert _has_call(t, "resume")


def test_min_num_seeds_not_met_with_tag_already_present_skips_remediation(share_limits_factory, torrent_factory):
    """If the warning tag is already on the torrent, we don't re-tag / re-resume."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=2, tags=sl.min_num_seeds_tag)
    result = _seed_limit(sl, t, min_num_seeds=5)
    assert result == ""
    assert _calls_of(t, "add_tags") == []
    assert _calls_of(t, "set_share_limits") == []
    assert _calls_of(t, "resume") == []


def test_min_num_seeds_no_resume_when_resume_torrent_false(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(num_complete=2, tags="")
    _seed_limit(sl, t, min_num_seeds=5, resume_torrent=False)
    assert _calls_of(t, "resume") == []


# ---- last_active ------------------------------------------------------------


def test_last_active_met_returns_false_after_gating(share_limits_factory, torrent_factory, monkeypatch):
    """last_active threshold met → continues past this gate (returns False because no other
    deletion criteria match, but no warning tag is added)."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    # 7200s inactive = 120 min, last_active threshold 60 → met
    t = torrent_factory(last_activity=1_000_000 - 7200, tags="")
    result = _seed_limit(sl, t, min_last_active=60)
    assert result is False
    assert _calls_of(t, "add_tags") == []


def test_last_active_met_clears_existing_tag(share_limits_factory, torrent_factory, monkeypatch):
    """If the last_active warning tag was previously applied and the threshold
    is now met, the tag is removed."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    t = torrent_factory(last_activity=1_000_000 - 7200, tags=sl.last_active_tag)
    _seed_limit(sl, t, min_last_active=60)
    removes = _calls_of(t, "remove_tags")
    assert removes and removes[0][1]["tags"] == sl.last_active_tag


def test_global_max_seeding_time_disabled_falls_through(share_limits_factory, torrent_factory):
    sl = share_limits_factory(
        qbt_overrides={
            "global_max_seeding_time_enabled": False,
            "global_max_seeding_time": 60,
        }
    )
    t = torrent_factory(seeding_time=7200, ratio=0.1, tags="")
    result = _seed_limit(sl, t, max_seeding_time=-2)
    assert result is False


def test_last_active_not_met_adds_warning_tag(share_limits_factory, torrent_factory, monkeypatch):
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    # Only 1 min idle, threshold 60 → not met
    t = torrent_factory(last_activity=1_000_000 - 60, tags="")
    result = _seed_limit(sl, t, min_last_active=60)
    assert result == ""
    add = _calls_of(t, "add_tags")
    assert add and add[0][1]["tags"] == sl.last_active_tag
    assert _has_call(t, "set_share_limits")
    assert _has_call(t, "resume")


# ---- max_ratio (hard) -------------------------------------------------------


def test_ratio_met_and_min_seeding_time_met_returns_body(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    # ratio 2.5 >= 2.0 AND seeding_time 120min (in s = 7200) >= min 60min
    t = torrent_factory(ratio=2.5, seeding_time=7200, tags="")
    result = _seed_limit(sl, t, max_ratio=2.0, min_seeding_time=60)
    assert result, "expected a non-empty body indicating deletion eligibility"
    assert "Ratio vs Max Ratio" in result


def test_ratio_met_but_min_seeding_time_not_met_tags_and_clears(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    # ratio 2.5 >= 2.0 BUT seeding_time 30min (1800s) < min 60min → tag + clear
    t = torrent_factory(ratio=2.5, seeding_time=1800, tags="")
    result = _seed_limit(sl, t, max_ratio=2.0, min_seeding_time=60)
    assert result is False
    add = _calls_of(t, "add_tags")
    assert add and add[0][1]["tags"] == sl.min_seeding_time_tag
    set_limits = _calls_of(t, "set_share_limits")
    assert set_limits and set_limits[0][1]["ratio_limit"] == -1


def test_ratio_not_met_no_action(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(ratio=1.0, seeding_time=99999, tags="")
    result = _seed_limit(sl, t, max_ratio=2.0)
    assert result is False
    assert _calls_of(t, "add_tags") == []


def test_crossover_min_seeding_time_tag_removed_when_now_met(share_limits_factory, torrent_factory):
    """Torrent previously had MinSeedTimeNotReached tag; now seeding_time is enough
    AND ratio is met → tag is removed and deletion body is returned."""
    sl = share_limits_factory()
    t = torrent_factory(
        ratio=2.5,
        seeding_time=7200,  # 120 min, >= 60 min threshold
        tags=sl.min_seeding_time_tag,
    )
    result = _seed_limit(sl, t, max_ratio=2.0, min_seeding_time=60)
    assert result  # deletion-eligible
    remove = _calls_of(t, "remove_tags")
    assert remove and remove[0][1]["tags"] == sl.min_seeding_time_tag


# ---- max_ratio = -2 (global) ------------------------------------------------


def test_global_ratio_enabled_and_met(share_limits_factory, torrent_factory):
    sl = share_limits_factory(qbt_overrides={"global_max_ratio_enabled": True, "global_max_ratio": 2.0})
    t = torrent_factory(ratio=3.0, seeding_time=99999, tags="")
    result = _seed_limit(sl, t, max_ratio=-2, min_seeding_time=0)
    assert result
    assert "Global Max Ratio" in result


def test_global_ratio_disabled_falls_through(share_limits_factory, torrent_factory):
    sl = share_limits_factory(qbt_overrides={"global_max_ratio_enabled": False, "global_max_ratio": 2.0})
    t = torrent_factory(ratio=3.0, tags="")
    result = _seed_limit(sl, t, max_ratio=-2)
    assert result is False


# ---- max_seeding_time -------------------------------------------------------


def test_max_seeding_time_met_returns_body(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    # seeding_time 7200s = 120min, threshold 60 min → met
    t = torrent_factory(seeding_time=7200, ratio=0.1, tags="")
    result = _seed_limit(sl, t, max_seeding_time=60, min_seeding_time=0)
    assert result
    assert "Seeding Time vs Max Seed Time" in result


def test_max_seeding_time_not_met_no_action(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(seeding_time=600, ratio=0.1, tags="")
    result = _seed_limit(sl, t, max_seeding_time=60)
    assert result is False
    assert _calls_of(t, "add_tags") == []


def test_global_max_seeding_time(share_limits_factory, torrent_factory):
    sl = share_limits_factory(
        qbt_overrides={
            "global_max_seeding_time_enabled": True,
            "global_max_seeding_time": 60,
        }
    )
    t = torrent_factory(seeding_time=7200, ratio=0.1, tags="")
    result = _seed_limit(sl, t, max_seeding_time=-2)
    assert result


# ---- dry_run ----------------------------------------------------------------


def test_dry_run_suppresses_all_qbit_mutations_in_seed_limit_path(share_limits_factory, torrent_factory):
    sl = share_limits_factory(config_overrides={"dry_run": True})
    t = torrent_factory(num_complete=0, tags="")
    _seed_limit(sl, t, min_num_seeds=5)
    assert t.calls == []


# ---- max_last_active --------------------------------------------------------


def test_max_last_active_met_returns_body(share_limits_factory, torrent_factory, monkeypatch):
    """inactive_time >= max_last_active AND min_last_active met → deletion eligible."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    # 7200s idle = 120 min, max_last_active=60, min_last_active=0 (always met)
    t = torrent_factory(last_activity=1_000_000 - 7200, tags="")
    result = _seed_limit(sl, t, max_last_active=60, min_last_active=0)
    assert result, "expected a non-empty body indicating deletion eligibility"
    assert "Inactive Time vs Max Last Active Time" in result


def test_max_last_active_not_met_does_not_return_body(share_limits_factory, torrent_factory, monkeypatch):
    """inactive_time < max_last_active → NOT eligible for deletion."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    # only 5 min idle, max_last_active=60
    t = torrent_factory(last_activity=1_000_000 - 300, tags="")
    result = _seed_limit(sl, t, max_last_active=60, min_last_active=0)
    assert result is False


def test_max_last_active_minus_one_skips_check(share_limits_factory, torrent_factory, monkeypatch):
    """max_last_active=-1 (disabled) → gate is never applied."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    t = torrent_factory(last_activity=0, tags="")  # maximally old
    result = _seed_limit(sl, t, max_last_active=-1, min_last_active=0)
    assert result is False


def test_max_last_active_met_clears_last_active_tag(share_limits_factory, torrent_factory, monkeypatch):
    """When max_last_active is met and a warning tag exists, it is removed."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    t = torrent_factory(last_activity=1_000_000 - 7200, tags=sl.last_active_tag)
    _seed_limit(sl, t, max_last_active=60, min_last_active=0)
    removes = _calls_of(t, "remove_tags")
    # last_active_tag should be cleared because min_last_active is also met
    assert removes


# ---- reset_upload_speed_on_unmet_minimums -----------------------------------


def test_reset_upload_speed_on_unmet_minimums_true_resets_speed(share_limits_factory, torrent_factory):
    """When flag is True and min_num_seeds not met, upload speed is reset."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0, tags="", up_limit=1024)
    _seed_limit(sl, t, min_num_seeds=5, reset_upload_speed_on_unmet_minimums=True)
    set_ul = _calls_of(t, "set_upload_limit")
    assert set_ul, "set_upload_limit should be called when flag is True"
    assert set_ul[0][1]["limit"] == -1


def test_reset_upload_speed_on_unmet_minimums_false_does_not_reset(share_limits_factory, torrent_factory):
    """When flag is False and min_num_seeds not met, upload speed is NOT reset."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0, tags="", up_limit=1024)
    _seed_limit(sl, t, min_num_seeds=5, reset_upload_speed_on_unmet_minimums=False)
    assert _calls_of(t, "set_upload_limit") == []


def test_reset_upload_speed_false_still_adds_tag(share_limits_factory, torrent_factory):
    """Even with reset_upload_speed_on_unmet_minimums=False the warning tag is added."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0, tags="")
    _seed_limit(sl, t, min_num_seeds=5, reset_upload_speed_on_unmet_minimums=False)
    add_tag = _calls_of(t, "add_tags")
    assert add_tag and add_tag[0][1]["tags"] == sl.min_num_seeds_tag


# ---- empty tracker URL short-circuit ----------------------------------------


def test_empty_tracker_url_does_not_crash(share_limits_factory, torrent_factory):
    """Passing tracker='' should not raise — the method accepts any string."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=10, ratio=5.0, seeding_time=99999, tags="")
    # Provide a concrete max_ratio so the deletion body is hit with no tracker needed
    result = _seed_limit(sl, t, max_ratio=2.0, tracker="")
    assert result  # still reaches the ratio gate


# ---- multiple gating tags simultaneously ------------------------------------


def test_both_min_tags_present_both_removed_when_met(share_limits_factory, torrent_factory):
    """Torrent had both MinSeedTimeNotReached and MinSeedsNotMet; when both gates
    are now satisfied both tags are removed before the deletion body is returned."""
    sl = share_limits_factory()
    combined_tags = f"{sl.min_seeding_time_tag}, {sl.min_num_seeds_tag}"
    t = torrent_factory(
        ratio=3.0,
        seeding_time=7200,  # 120 min >= 60 min threshold
        num_complete=10,
        tags=combined_tags,
    )
    result = _seed_limit(sl, t, max_ratio=2.0, min_seeding_time=60, min_num_seeds=5)
    assert result  # deletion-eligible
    removed_tags = [c[1]["tags"] for c in _calls_of(t, "remove_tags")]
    # min_seeding_time_tag is removed inside _has_reached_min_seeding_time_limit
    # min_num_seeds_tag is removed inside _is_less_than_min_num_seeds
    assert sl.min_seeding_time_tag in removed_tags


def test_min_num_seeds_and_min_seeding_time_not_met_only_seeds_tag_added(share_limits_factory, torrent_factory):
    """When min_num_seeds is not met, the method short-circuits before touching
    min_seeding_time — only the seeds tag is added, not the seeding-time tag."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0, seeding_time=100, ratio=5.0, tags="")
    _seed_limit(sl, t, min_num_seeds=5, min_seeding_time=60, max_ratio=2.0)
    added = [c[1]["tags"] for c in _calls_of(t, "add_tags")]
    assert sl.min_num_seeds_tag in added
    assert sl.min_seeding_time_tag not in added


# ---- exclusion_tag_added tuple element ----------------------------------------


def test_exclusion_tag_added_true_when_tag_applied(share_limits_factory, torrent_factory):
    """When a gating tag is newly added, the second tuple element is True."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0, tags="")
    _body, exclusion_tag_added = sl.has_reached_seed_limit(
        torrent=t,
        max_ratio=-1,
        max_seeding_time=-1,
        max_last_active=-1,
        min_seeding_time=0,
        min_num_seeds=5,
        min_last_active=0,
        resume_torrent=True,
        tracker="http://tracker1.example/announce",
        reset_upload_speed_on_unmet_minimums=True,
    )
    assert exclusion_tag_added is True


def test_exclusion_tag_added_false_when_no_gate_fires(share_limits_factory, torrent_factory):
    """When no gating tag is applied, the second tuple element is False."""
    sl = share_limits_factory()
    t = torrent_factory(ratio=1.0, seeding_time=99999, tags="")
    _body, exclusion_tag_added = sl.has_reached_seed_limit(
        torrent=t,
        max_ratio=2.0,
        max_seeding_time=-1,
        max_last_active=-1,
        min_seeding_time=0,
        min_num_seeds=0,
        min_last_active=0,
        resume_torrent=True,
        tracker="http://tracker1.example/announce",
        reset_upload_speed_on_unmet_minimums=True,
    )
    assert exclusion_tag_added is False


def test_exclusion_tag_added_false_when_deletion_eligible(share_limits_factory, torrent_factory):
    """When deletion criteria are met (no gating tag added), exclusion_tag_added is False."""
    sl = share_limits_factory()
    t = torrent_factory(ratio=3.0, seeding_time=7200, tags="")
    _body, exclusion_tag_added = sl.has_reached_seed_limit(
        torrent=t,
        max_ratio=2.0,
        max_seeding_time=-1,
        max_last_active=-1,
        min_seeding_time=60,
        min_num_seeds=0,
        min_last_active=0,
        resume_torrent=True,
        tracker="http://tracker1.example/announce",
        reset_upload_speed_on_unmet_minimums=True,
    )
    assert exclusion_tag_added is False


def test_exclusion_tag_added_false_when_tag_already_present(share_limits_factory, torrent_factory):
    """When the gating tag is ALREADY on the torrent, _add_tag_and_reset_limits
    does not set exclusion_tag_added=True (the tag was not newly added)."""
    sl = share_limits_factory()
    t = torrent_factory(num_complete=0, tags=sl.min_num_seeds_tag)
    _body, exclusion_tag_added = sl.has_reached_seed_limit(
        torrent=t,
        max_ratio=-1,
        max_seeding_time=-1,
        max_last_active=-1,
        min_seeding_time=0,
        min_num_seeds=5,
        min_last_active=0,
        resume_torrent=True,
        tracker="http://tracker1.example/announce",
        reset_upload_speed_on_unmet_minimums=True,
    )
    assert exclusion_tag_added is False


def test_exclusion_tag_added_true_for_last_active_gate(share_limits_factory, torrent_factory, monkeypatch):
    """exclusion_tag_added is True when the last_active warning tag is newly applied."""
    sl = share_limits_factory()
    monkeypatch.setattr(share_limits_mod, "time", lambda: 1_000_000)
    # 1 min idle, threshold 60 → not met
    t = torrent_factory(last_activity=1_000_000 - 60, tags="")
    _body, exclusion_tag_added = sl.has_reached_seed_limit(
        torrent=t,
        max_ratio=-1,
        max_seeding_time=-1,
        max_last_active=-1,
        min_seeding_time=0,
        min_num_seeds=0,
        min_last_active=60,
        resume_torrent=True,
        tracker="http://tracker1.example/announce",
        reset_upload_speed_on_unmet_minimums=True,
    )
    assert exclusion_tag_added is True
