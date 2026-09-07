"""Tests for RemoveUnregistered module.

Tests cover:
- check_for_unregistered_torrents_in_bhd() — BHD-specific detection
- is_within_grace() — grace period bypass logic
- check_max_limit_and_delete() — deletion rate limiting
- remove_previous_errors() — untag recovery
- Tracker status detection (WORKING, NOT_WORKING, UNREGISTERED, TRACKER_DOWN)
- Dry-run suppression
- Cross-seed safety (don't delete content when sibling torrent exists)
"""

from __future__ import annotations

import time
from unittest.mock import patch

from modules.core.remove_unregistered import BHD_TRACKER_DOMAIN
from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import _Tracker
from tests.factories import make_remove_unregistered

# Tracker URLs used by tests. Generic .example domains for the non-special
# tracker path. The BHD-specific path requires the literal domain that
# production matches against — imported by symbol so this test file never
# spells out the real tracker name in source.
_GENERIC_TRACKER_URL = "http://tracker1.example/announce"
_BHD_TRACKER_URL = f"http://{BHD_TRACKER_DOMAIN}/announce"


def _make_qbt(torrents=None, config=None, torrentinfo=None):
    """Helper to construct FakeQbtManager for remove_unregistered tests."""
    cfg = config or FakeConfig()
    return FakeQbtManager(torrents=torrents or [], config=cfg, torrentinfo=torrentinfo or {})


def _calls_of(torrent, name):
    """Extract all calls of a given name from torrent.calls."""
    return [c for c in torrent.calls if c[0] == name]


# ── is_within_grace ──────────────────────────────────────────────────────────


def test_is_within_grace_when_grace_disabled():
    """Grace is disabled (0 or None), should return (False, 0.0)."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    t = FakeTorrent(added_on=int(time.time()) - 100)
    is_grace, age = ru.is_within_grace(t)
    assert is_grace is False
    assert age == 0.0


def test_is_within_grace_when_torrent_within_window():
    """Torrent added recently (< grace window), should return (True, age_minutes)."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 60})
    qbt = _make_qbt(config=cfg)
    ru = make_remove_unregistered(qbt)
    # Torrent added 30 minutes ago
    added_on = int(time.time()) - 30 * 60
    t = FakeTorrent(added_on=added_on)
    is_grace, age = ru.is_within_grace(t)
    assert is_grace is True
    assert 29 < age < 31


def test_is_within_grace_when_torrent_outside_window():
    """Torrent older than grace window, should return (False, age_minutes)."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 30})
    qbt = _make_qbt(config=cfg)
    ru = make_remove_unregistered(qbt)
    # Torrent added 60 minutes ago
    added_on = int(time.time()) - 60 * 60
    t = FakeTorrent(added_on=added_on)
    is_grace, age = ru.is_within_grace(t)
    assert is_grace is False
    assert 59 < age < 61


def test_is_within_grace_no_added_on_field():
    """Torrent has no added_on attribute, should return (False, 0.0)."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    t = FakeTorrent()
    delattr(t, "added_on")
    is_grace, age = ru.is_within_grace(t)
    assert is_grace is False
    assert age == 0.0


def test_is_within_grace_invalid_added_on_value():
    """Torrent has non-numeric added_on, should return (False, 0.0)."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    t = FakeTorrent(added_on="not_a_timestamp")
    is_grace, age = ru.is_within_grace(t)
    assert is_grace is False
    assert age == 0.0


# ── check_for_unregistered_torrents_in_bhd ──────────────────────────────────


def test_bhd_check_detects_unregistered_in_bhd_tracker():
    """BHD tracker with a BHD deletion reason is detected."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    tracker = {"url": _BHD_TRACKER_URL}
    # BHD deletion reason from TorrentMessages.UNREGISTERED_MSGS_BHD
    msg_up = "TRUMPED"
    result = ru.check_for_unregistered_torrents_in_bhd(tracker, msg_up, "hash123")
    assert result is True


def test_bhd_check_with_colon_in_message():
    """Message with colon suffix (e.g. 'TRUMPED: Internal: ...') is stripped."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    tracker = {"url": _BHD_TRACKER_URL}
    # Real-world BHD TRUMPED messages embed a link to the duplicating torrent;
    # the colon-suffix path is the codepath under test, the URL itself is illustrative.
    msg_up = "TRUMPED: Internal: https://example.com/torrent/12345"
    result = ru.check_for_unregistered_torrents_in_bhd(tracker, msg_up, "hash123")
    assert result is True


def test_bhd_check_non_bhd_tracker_returns_false():
    """Non-BHD tracker always returns False."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    tracker = {"url": "http://tracker1.example/announce"}
    msg_up = "UNREGISTERED"
    result = ru.check_for_unregistered_torrents_in_bhd(tracker, msg_up, "hash123")
    assert result is False


def test_bhd_check_bhd_tracker_invalid_message():
    """BHD tracker with non-unregistered message returns False."""
    qbt = _make_qbt()
    ru = make_remove_unregistered(qbt)
    tracker = {"url": _BHD_TRACKER_URL}
    msg_up = "TRACKER_DOWN"
    result = ru.check_for_unregistered_torrents_in_bhd(tracker, msg_up, "hash123")
    assert result is False


# ── check_max_limit_and_delete ───────────────────────────────────────────────


def test_max_limit_disabled_allows_deletion():
    """When max_torrents=0 (disabled), deletion proceeds."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_max_torrents": 0})
    qbt = _make_qbt(config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = "UNREGISTERED"
    ru.t_status = [3]
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1")
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}
    # Should call del_unregistered
    with patch.object(ru, "del_unregistered") as mock_del:
        ru.check_max_limit_and_delete("UNREGISTERED", tracker, t)
        assert mock_del.called


def test_max_limit_not_reached_allows_deletion():
    """When tracker deletion count < max_torrents, deletion proceeds."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_max_torrents": 5})
    qbt = _make_qbt(config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = "UNREGISTERED"
    ru.t_status = [3]
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1")
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}
    with patch.object(ru, "del_unregistered") as mock_del:
        ru.check_max_limit_and_delete("UNREGISTERED", tracker, t)
        assert mock_del.called
        assert ru.tracker_del_count["tracker1.example"] == 1


def test_max_limit_reached_skips_deletion():
    """When tracker deletion count >= max_torrents, deletion is skipped."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_max_torrents": 2})
    qbt = _make_qbt(config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.tracker_del_count["tracker1.example"] = 2  # Already at limit
    ru.t_name = "Torrent.NAME.2"
    ru.t_cat = "Test"
    ru.t_msg = "UNREGISTERED"
    ru.t_status = [3]
    t = FakeTorrent(name="Torrent.NAME.2", hash="hash2")
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}
    with patch.object(ru, "del_unregistered") as mock_del:
        ru.check_max_limit_and_delete("UNREGISTERED", tracker, t)
        assert not mock_del.called
        # Count should not increment
        assert ru.tracker_del_count["tracker1.example"] == 2


# ── remove_previous_errors ───────────────────────────────────────────────────


def test_remove_previous_errors_untagged_working_torrent():
    """A torrent with error tag but now-working tracker gets untagged."""
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t = FakeTorrent(
        name="Torrent.NAME.1",
        hash="hash1",
        tags="TrackerError",
        trackers=[_Tracker(url="http://tracker1.example/announce", status=2)],
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)

    ru.remove_previous_errors()

    # Should call remove_tags
    assert any(c[0] == "remove_tags" for c in t.calls)
    assert "TrackerError" not in t.tags
    assert ru.stats_untagged == 1


def test_remove_previous_errors_dry_run_suppresses_remove_tags():
    """In dry-run mode, remove_tags is NOT called."""
    cfg = FakeConfig(
        settings={**FakeConfig().settings},
        dry_run=True,
    )
    t = FakeTorrent(
        name="Torrent.NAME.1",
        hash="hash1",
        tags="TrackerError",
        trackers=[_Tracker(url="http://tracker1.example/announce", status=2)],
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)

    ru.remove_previous_errors()

    # Should NOT call remove_tags
    assert not any(c[0] == "remove_tags" for c in t.calls)
    # But should still increment stats
    assert ru.stats_untagged == 1


def test_remove_previous_errors_untagged_even_with_broken_tracker():
    """Torrent with error tag gets untagged regardless of tracker status.

    remove_previous_errors() iterates torrentvalid only.  We explicitly place
    the torrent there (via the torrentvalid kwarg) to show that belonging to
    torrentvalid — not tracker health — is what drives un-tagging.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t = FakeTorrent(
        name="Torrent.NAME.1",
        hash="hash1",
        tags="TrackerError",
        trackers=[_Tracker(url="http://tracker1.example/announce", status=4)],  # NOT_WORKING
    )
    # Explicitly place t in torrentvalid so the test doesn't rely on the
    # "everything is in everything" default that issue #4 fixed.
    qbt = _make_qbt(torrents=[t], config=cfg)
    qbt._torrentvalid_override = [t]
    ru = make_remove_unregistered(qbt)

    ru.remove_previous_errors()

    # Torrent in torrentvalid gets untagged regardless of tracker status
    assert any(c[0] == "remove_tags" for c in t.calls)
    assert ru.stats_untagged == 1


def test_remove_previous_errors_filters_by_hashes():
    """When hashes are specified, only those torrents are processed."""
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t1 = FakeTorrent(
        name="Torrent.NAME.1",
        hash="hash1",
        tags="TrackerError",
        trackers=[_Tracker(url="http://tracker1.example/announce", status=2)],
    )
    t2 = FakeTorrent(
        name="Torrent.NAME.2",
        hash="hash2",
        tags="TrackerError",
        trackers=[_Tracker(url="http://tracker1.example/announce", status=2)],
    )
    qbt = _make_qbt(torrents=[t1, t2], config=cfg)
    ru = make_remove_unregistered(qbt, hashes=["hash1"])

    ru.remove_previous_errors()

    # Only t1 should be processed
    assert ru.stats_untagged == 1


# ── del_unregistered (cross-seed detection) ──────────────────────────────────


def test_del_unregistered_cross_seed_with_working_tracker():
    """Cross-seed with working tracker on sibling → only .torrent deleted."""
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1", category="Test")
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.qbt.cross_seed_map[t.hash] = True
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = ["UNREGISTERED"]
    ru.t_status = [2]  # working → matches 2 in self.t_status
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}

    ru.del_unregistered("UNREGISTERED", tracker, t)

    # Should NOT delete content
    assert ru.stats_deleted == 1
    assert ru.stats_deleted_contents == 0
    assert len(ru.qbt.tor_delete_recycle_calls) == 1
    _, attr = ru.qbt.tor_delete_recycle_calls[0]
    assert attr["torrents_deleted_and_contents"] is False


def test_del_unregistered_cross_seed_all_broken():
    """Cross-seed with all trackers broken → .torrent AND content deleted.

    The code checks `"" in self.t_msg or 2 in self.t_status`. If neither
    condition is true (all trackers broken, no empty string in msg),
    content is deleted.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1", category="Test")
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.qbt.cross_seed_map[t.hash] = True
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = ["UNREGISTERED"]  # list, no empty strings
    ru.t_status = [4]  # NOT_WORKING, not 2 (WORKING)
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}

    ru.del_unregistered("UNREGISTERED", tracker, t)

    # Should delete content
    assert ru.stats_deleted_contents == 1
    assert len(ru.qbt.tor_delete_recycle_calls) == 1
    _, attr = ru.qbt.tor_delete_recycle_calls[0]
    assert attr["torrents_deleted_and_contents"] is True


def test_del_unregistered_no_cross_seed_deletes_content():
    """No cross-seed → always delete .torrent AND content."""
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1", category="Test")
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.qbt.cross_seed_map[t.hash] = False
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = ["UNREGISTERED"]
    ru.t_status = [2]  # working
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}

    ru.del_unregistered("UNREGISTERED", tracker, t)

    # Should delete content
    assert ru.stats_deleted_contents == 1
    assert len(ru.qbt.tor_delete_recycle_calls) == 1
    _, attr = ru.qbt.tor_delete_recycle_calls[0]
    assert attr["torrents_deleted_and_contents"] is True


def test_del_unregistered_dry_run_suppresses_delete():
    """In dry-run mode, tor_delete_recycle is NOT called."""
    cfg = FakeConfig(settings={**FakeConfig().settings}, dry_run=True)
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1", category="Test")
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = ["UNREGISTERED"]
    ru.t_status = [4]
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}

    ru.del_unregistered("UNREGISTERED", tracker, t)

    # Should NOT call tor_delete_recycle
    assert len(ru.qbt.tor_delete_recycle_calls) == 0
    # But should still increment stats
    assert ru.stats_deleted_contents == 1


# ── tag_tracker_error (error tagging) ────────────────────────────────────────


def test_tag_tracker_error_adds_tag():
    """Torrent with tracker error gets the error tag added."""
    cfg = FakeConfig(settings={**FakeConfig().settings})
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1", category="Test", tags="")
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}

    ru.tag_tracker_error("TRACKER_DOWN", tracker, t)

    assert any(c[0] == "add_tags" for c in t.calls)
    assert ru.stats_tagged == 1


def test_tag_tracker_error_dry_run_suppresses_add_tags():
    """In dry-run mode, add_tags is NOT called."""
    cfg = FakeConfig(settings={**FakeConfig().settings}, dry_run=True)
    t = FakeTorrent(name="Torrent.NAME.1", hash="hash1", category="Test", tags="")
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    tracker = {"url": "tracker1.example", "tag": [], "notifiarr": None}

    ru.tag_tracker_error("TRACKER_DOWN", tracker, t)

    # Should NOT call add_tags
    assert not any(c[0] == "add_tags" for c in t.calls)
    # But should still increment stats
    assert ru.stats_tagged == 1


# ── Integration-style scenarios ──────────────────────────────────────────────


def test_full_flow_remove_unregistered_no_cross_seed():
    """Full flow: unregistered torrent with no cross-seed is deleted with content."""
    cfg = FakeConfig(
        settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0},
        commands={"rem_unregistered": True, "tag_tracker_error": False},
    )
    t = FakeTorrent(
        name="Torrent.NAME.1",
        hash="hash1",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://tracker1.example/announce", status=4, msg="UNREGISTERED")],
    )
    qbt = _make_qbt(torrents=[t], config=cfg, torrentinfo={"Torrent.NAME.1": {"msg": ["UNREGISTERED"], "status": [4]}})
    ru = make_remove_unregistered(qbt)
    ru.t_name = "Torrent.NAME.1"
    ru.t_cat = "Test"
    ru.t_msg = "UNREGISTERED"
    ru.t_status = [4]

    with patch.object(ru, "del_unregistered") as mock_del:
        ru.check_max_limit_and_delete("UNREGISTERED", {"url": "tracker1.example", "tag": [], "notifiarr": None}, t)
        assert mock_del.called


def _make_issue_qbt(torrent, *, config):
    """Build a FakeQbtManager where *torrent* is the sole torrentissue entry.

    process_torrent_issues() reads Category/msg/status out of torrentinfo keyed by
    name, so mirror the torrent's own trackers into that structure.
    """
    torrentinfo = {
        torrent.name: {
            "Category": torrent.category,
            "msg": [(t.msg or "").upper() for t in torrent.trackers],
            "status": [t.status for t in torrent.trackers],
        }
    }
    return _make_qbt(torrents=[torrent], config=config, torrentinfo=torrentinfo)


# ── process_torrent_issues (multi-tracker detection) ─────────────────────────


def test_process_issues_detects_unregistered_when_not_last_tracker():
    """Unregistered tracker anywhere in the list is detected, not just the last one.

    Regression for #1358: a torrent whose unregistered tracker is followed by
    another failing tracker was previously missed because only the last tracker
    was evaluated.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    t = FakeTorrent(
        name="Sugar.2024.S01",
        hash="hashsugar",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=4, msg="some other tracker error"),
            _Tracker(url="http://b.example/announce", status=4, msg="err: unregistered torrent"),
        ],
    )
    cfg.commands["tag_tracker_error"] = False
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert "UNREGISTERED" in mock_del.call_args[0][0].upper()
    assert not qbt.config.notify_calls  # no swallowed exception


def test_process_issues_none_msg_earlier_tracker_still_detects():
    """A failing tracker with a None message before an unregistered one must not
    abort detection or crash. Regression for #1358 None-msg handling."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.NoneMsg",
        hash="hnonemsg",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=4, msg=None),
            _Tracker(url="http://b.example/announce", status=4, msg="err: unregistered torrent"),
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert "UNREGISTERED" in mock_del.call_args[0][0].upper()
    assert not qbt.config.notify_calls  # no swallowed exception


def test_process_issues_single_unregistered_still_deletes():
    """The basic single-tracker unregistered case still triggers deletion."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.Single",
        hash="hsingle",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert not qbt.config.notify_calls


def test_process_issues_deletes_despite_host_not_found_sibling():
    """Reporter's exact case: 'Host not found' + 'unregistered' still deletes.

    A permanent authoritative DNS failure is not a temporary outage, so it must
    not defer the removal.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.HostNotFound",
        hash="hhnf",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=4, msg="Host not found (authoritative)"),
            _Tracker(url="http://b.example/announce", status=4, msg="err: unregistered torrent"),
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert not qbt.config.notify_calls


def test_process_issues_deletes_when_sibling_tracker_times_out():
    """A failed sibling tracker (e.g. timed out) does not block detection.

    A single-snapshot message cannot distinguish a temporary outage from a
    permanently-dead host, so message-based reachability is NOT used to defer.
    The opt-in dwell timer (rem_unregistered_confirm_minutes) is the mechanism
    that protects against transient false-unregistered.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.Timeout",
        hash="htimeout",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=4, msg="Connection timed out"),
            _Tracker(url="http://b.example/announce", status=4, msg="Unregistered torrent"),
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert not qbt.config.notify_calls


def test_process_issues_defers_when_tracker_still_updating():
    """A tracker still UPDATING is inconclusive, so removal is deferred."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.Updating",
        hash="hupdating",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=3, msg=""),  # UPDATING
            _Tracker(url="http://b.example/announce", status=4, msg="Unregistered torrent"),
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert not mock_del.called
    assert not qbt.config.notify_calls


def test_process_issues_skips_when_any_tracker_working():
    """A working tracker means the torrent is alive; never removed."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.Working",
        hash="hworking",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=2, msg=""),  # WORKING
            _Tracker(url="http://b.example/announce", status=4, msg="Unregistered torrent"),
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert not mock_del.called
    assert not qbt.config.notify_calls


def test_process_issues_bhd_scan_defers_get_tags_until_match():
    """get_tags() is only called once, for the matched tracker.

    A non-BHD, non-unregistered failing tracker scanned before the BHD match
    must not trigger a get_tags() lookup of its own.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.BhdScan",
        hash="hbhdscan",
        category="Test",
        added_on=int(time.time()) - 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=4, msg="Connection timed out"),
            _Tracker(url=_BHD_TRACKER_URL, status=4, msg="Dead"),
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with (
        patch.object(ru, "check_max_limit_and_delete") as mock_del,
        patch.object(qbt, "get_tags", wraps=qbt.get_tags) as mock_get_tags,
    ):
        ru.process_torrent_issues()

    assert mock_del.called
    assert mock_get_tags.call_count == 1


# ── dwell-timer confirmation (rem_unregistered_confirm_minutes) ───────────────


def _confirm_cfg():
    cfg = FakeConfig(
        settings={
            **FakeConfig().settings,
            "rem_unregistered_grace_minutes": 0,
            "rem_unregistered_confirm_minutes": 60,
        }
    )
    cfg.commands["tag_tracker_error"] = False
    return cfg


def test_confirm_first_sighting_flags_and_does_not_delete():
    """First time seen unregistered: stamp a timestamped flag, do not remove."""
    cfg = _confirm_cfg()
    t = FakeTorrent(
        name="T.Confirm1",
        hash="hc1",
        category="Test",
        tags="",
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert not mock_del.called
    add_tag_calls = [c for c in t.calls if c[0] == "add_tags"]
    assert any(str(c[1].get("tags", "")).startswith("unregisteredCheck_") for c in add_tag_calls)
    assert not qbt.config.notify_calls


def test_confirm_deletes_after_dwell_elapsed():
    """Flagged long enough ago (> confirm_minutes) and still unregistered → removed."""
    cfg = _confirm_cfg()
    flagged_at = int(time.time()) - 2 * 3600  # 2h ago, well past the 60 min window
    t = FakeTorrent(
        name="T.Confirm2",
        hash="hc2",
        category="Test",
        tags=f"unregisteredCheck_{flagged_at}",
        added_on=int(time.time()) - 3 * 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert not qbt.config.notify_calls


def test_confirm_waits_when_dwell_not_elapsed():
    """Flagged only recently (< confirm_minutes) → still waits, no new flag, no delete.

    This is the case bare 'seen twice' got wrong: a fast scheduler must not delete
    before the tracker has had time to re-announce.
    """
    cfg = _confirm_cfg()
    flagged_at = int(time.time()) - 120  # 2 min ago, under the 60 min window
    t = FakeTorrent(
        name="T.Confirm3",
        hash="hc3",
        category="Test",
        tags=f"unregisteredCheck_{flagged_at}",
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert not mock_del.called
    assert not any(c[0] == "add_tags" for c in t.calls)  # already flagged; no duplicate stamp


def test_confirm_malformed_marker_does_not_short_circuit_delete():
    """A prefix-sharing tag with no valid timestamp must not bypass the dwell.

    Fail-safe: an unparseable marker is ignored, so the torrent is treated as a
    first sighting (fresh stamp, no removal) rather than deleted immediately.
    """
    cfg = _confirm_cfg()
    t = FakeTorrent(
        name="T.Malformed",
        hash="hmal",
        category="Test",
        tags="unregisteredCheck_manual",  # hand-edited / foreign, no epoch
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert not mock_del.called
    add_tag_calls = [c for c in t.calls if c[0] == "add_tags"]
    assert any(str(c[1].get("tags", "")).startswith("unregisteredCheck_") for c in add_tag_calls)


def test_confirm_off_deletes_on_first_run():
    """Default (confirm_minutes=0) preserves immediate removal."""
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 0})
    cfg.commands["tag_tracker_error"] = False
    t = FakeTorrent(
        name="T.NoConfirm",
        hash="hnc",
        category="Test",
        tags="",
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()

    assert mock_del.called
    assert not any(c[0] == "add_tags" for c in t.calls)  # no flag written when off


def test_confirm_clears_flag_when_no_longer_unregistered():
    """A flagged torrent that recovers to a non-unregistered error loses its flag."""
    cfg = _confirm_cfg()
    flagged_at = int(time.time()) - 120
    marker = f"unregisteredCheck_{flagged_at}"
    t = FakeTorrent(
        name="T.Recover",
        hash="hrec",
        category="Test",
        tags=marker,
        added_on=int(time.time()) - 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="some transient tracker error")],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()
        ru.clear_stale_pending_markers()

    assert not mock_del.called
    remove_calls = [c for c in t.calls if c[0] == "remove_tags"]
    assert any(c[1].get("tags") == marker for c in remove_calls)


def test_confirm_clears_flag_on_working_tracker():
    """The stale-marker sweep strips the pending flag once a tracker works again."""
    cfg = _confirm_cfg()
    marker = f"unregisteredCheck_{int(time.time()) - 120}"
    t = FakeTorrent(
        name="T.WorkingAgain",
        hash="hwork",
        category="Test",
        tags=marker,
        trackers=[_Tracker(url="http://a.example/announce", status=2)],  # WORKING
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    qbt._torrentvalid_override = [t]
    ru = make_remove_unregistered(qbt)

    ru.remove_previous_errors()
    ru.clear_stale_pending_markers()

    remove_calls = [c for c in t.calls if c[0] == "remove_tags"]
    assert any(c[1].get("tags") == marker for c in remove_calls)


def test_confirm_clears_stale_flag_when_disabled():
    """A stale pending-removal marker is cleared even with confirm_minutes back to 0.

    Regression: cleanup was gated on confirm_minutes being truthy, so disabling
    the feature after it had already tagged a torrent stranded that marker. The
    sweep clears markers independent of the confirm_minutes setting.
    """
    cfg = FakeConfig(settings={**FakeConfig().settings, "rem_unregistered_confirm_minutes": 0})
    marker = f"unregisteredCheck_{int(time.time()) - 120}"
    t = FakeTorrent(
        name="T.StaleDisabled",
        hash="hstaledisabled",
        category="Test",
        tags=marker,
        trackers=[_Tracker(url="http://a.example/announce", status=2)],  # WORKING
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    qbt._torrentvalid_override = [t]
    ru = make_remove_unregistered(qbt)

    ru.remove_previous_errors()
    ru.clear_stale_pending_markers()

    remove_calls = [c for c in t.calls if c[0] == "remove_tags"]
    assert any(c[1].get("tags") == marker for c in remove_calls)


def test_sweep_clears_marker_on_inconclusive_neither_bucket():
    """A marked torrent whose snapshot is all-UPDATING lands in neither torrentissue
    nor torrentvalid; the sweep still clears its stale marker."""
    cfg = _confirm_cfg()
    marker = f"unregisteredCheck_{int(time.time()) - 120 * 60}"
    t = FakeTorrent(
        name="T.Inconclusive",
        hash="hincon",
        category="Test",
        tags=marker,
        added_on=int(time.time()) - 24 * 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=3, msg="")],  # UPDATING
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    qbt._torrentissue_override = []  # inconclusive -> classified into neither list
    qbt._torrentvalid_override = []
    ru = make_remove_unregistered(qbt)

    ru.process_torrent_issues()
    ru.clear_stale_pending_markers()

    remove_calls = [c for c in t.calls if c[0] == "remove_tags"]
    assert any(c[1].get("tags") == marker for c in remove_calls)


def test_sweep_clears_marker_on_mixed_tracker_early_return():
    """A torrentissue torrent with an UPDATING sibling tracker hits the inconclusive
    early-return in process_torrent_issues; the sweep clears its stale marker so the
    dwell restarts instead of counting the interruption toward the deadline."""
    cfg = _confirm_cfg()
    marker = f"unregisteredCheck_{int(time.time()) - 120 * 60}"
    t = FakeTorrent(
        name="T.Mixed",
        hash="hmixed",
        category="Test",
        tags=marker,
        added_on=int(time.time()) - 24 * 3600,
        trackers=[
            _Tracker(url="http://a.example/announce", status=3, msg=""),  # UPDATING
            _Tracker(url="http://b.example/announce", status=4, msg="Unregistered torrent"),  # NOT_WORKING
        ],
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()
        ru.clear_stale_pending_markers()

    assert not mock_del.called  # inconclusive: not deleted this run
    remove_calls = [c for c in t.calls if c[0] == "remove_tags"]
    assert any(c[1].get("tags") == marker for c in remove_calls)


def test_sweep_keeps_marker_when_still_unregistered():
    """A torrent reconfirmed unregistered this run keeps its dwell marker (not swept)."""
    cfg = _confirm_cfg()
    marker = f"unregisteredCheck_{int(time.time()) - 30 * 60}"  # dwell not yet elapsed (60 min)
    t = FakeTorrent(
        name="T.StillUnreg",
        hash="hstill",
        category="Test",
        tags=marker,
        added_on=int(time.time()) - 24 * 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")],  # NOT_WORKING
    )
    qbt = _make_issue_qbt(t, config=cfg)
    qbt._torrentissue_override = [t]
    ru = make_remove_unregistered(qbt)

    with patch.object(ru, "check_max_limit_and_delete") as mock_del:
        ru.process_torrent_issues()
        ru.clear_stale_pending_markers()

    assert not mock_del.called  # dwell not elapsed
    remove_calls = [c for c in t.calls if c[0] == "remove_tags"]
    assert not any(c[1].get("tags") == marker for c in remove_calls)  # marker preserved


def test_inconclusive_state_resets_dwell_no_immediate_delete():
    """Regression: unregistered -> updating -> unregistered must NOT delete on the
    second sighting. The inconclusive snapshot clears the marker so the dwell timer
    restarts rather than counting wall-clock across the interruption."""
    cfg = _confirm_cfg()  # confirm_minutes = 60
    # Marker old enough that, if it survived, the dwell would read as elapsed.
    stale = int(time.time()) - 120 * 60
    t = FakeTorrent(
        name="T.Flap",
        hash="hflap",
        category="Test",
        tags=f"unregisteredCheck_{stale}",
        added_on=int(time.time()) - 24 * 3600,
        trackers=[_Tracker(url="http://a.example/announce", status=3, msg="")],  # UPDATING
    )

    # Run 1: inconclusive snapshot -> neither bucket -> sweep clears the stale marker.
    qbt1 = _make_qbt(torrents=[t], config=cfg)
    qbt1._torrentissue_override = []
    qbt1._torrentvalid_override = []
    ru1 = make_remove_unregistered(qbt1)
    ru1.process_torrent_issues()
    ru1.clear_stale_pending_markers()
    assert not any(tag.startswith("unregisteredCheck_") for tag in (t.tags or "").split(", ") if tag)

    # Run 2: unregistered again. With the marker cleared this is a fresh first
    # sighting, so it is re-flagged and NOT deleted despite the original deadline.
    t.trackers = [_Tracker(url="http://a.example/announce", status=4, msg="Unregistered torrent")]
    qbt2 = _make_issue_qbt(t, config=cfg)
    qbt2._torrentissue_override = [t]
    ru2 = make_remove_unregistered(qbt2)
    with patch.object(ru2, "check_max_limit_and_delete") as mock_del:
        ru2.process_torrent_issues()
        ru2.clear_stale_pending_markers()

    assert not mock_del.called  # NOT deleted immediately
    add_calls = [c for c in t.calls if c[0] == "add_tags"]
    assert any(str(c[1].get("tags", "")).startswith("unregisteredCheck_") for c in add_calls)  # re-flagged


def test_grace_period_blocks_deletion():
    """Grace period prevents deletion of recently added torrent."""
    cfg = FakeConfig(
        settings={**FakeConfig().settings, "rem_unregistered_grace_minutes": 60},
        commands={"rem_unregistered": True},
    )
    t = FakeTorrent(
        name="Torrent.NAME.1",
        hash="hash1",
        category="Test",
        added_on=int(time.time()) - 300,  # 5 minutes ago
        trackers=[_Tracker(url="http://tracker1.example/announce", status=4, msg="UNREGISTERED")],
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    ru = make_remove_unregistered(qbt)

    skip, age = ru.is_within_grace(t)
    assert skip is True
    assert 4 < age < 6
