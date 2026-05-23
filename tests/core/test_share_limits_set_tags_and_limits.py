"""Tests for ShareLimits.set_limits (formerly set_tags_and_limits).

Covers tag application via update_share_limits_tag_for_torrent, upload-speed
limiting, share-limit application, short-circuit behavior when
min-seeding/min-seeds/last-active tags are present, and dry-run.
"""

from __future__ import annotations

import pytest


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


def test_no_limit_calls_set_share_limits_with_negative_ones(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory()
    sl.set_limits(t, max_ratio=-1, max_seeding_time=-1)
    assert len(_calls_of(t, "set_share_limits")) == 1
    call_kwargs = _calls_of(t, "set_share_limits")[0][1]
    assert call_kwargs["ratio_limit"] == -1
    assert call_kwargs["seeding_time_limit"] == -1
    assert call_kwargs["inactive_seeding_time_limit"] == -2


def test_global_limit_uses_minus_two(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory()
    sl.set_limits(t, max_ratio=-2, max_seeding_time=-2)
    call_kwargs = _calls_of(t, "set_share_limits")[0][1]
    assert call_kwargs["ratio_limit"] == -2
    assert call_kwargs["seeding_time_limit"] == -2


def test_hard_ratio_limit_applied(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)
    body = sl.set_limits(t, max_ratio=5.0, max_seeding_time=-1)
    assert any("Max Ratio = 5.0" in line for line in body)
    call_kwargs = _calls_of(t, "set_share_limits")[0][1]
    assert call_kwargs["ratio_limit"] == 5.0


def test_hard_seeding_time_limit_applied(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)
    body = sl.set_limits(t, max_ratio=-1, max_seeding_time=43200)
    assert any("Max Seed Time" in line for line in body)


def test_tag_applied(share_limits_factory, torrent_factory):
    """update_share_limits_tag_for_torrent applies the group_tag to the torrent."""
    sl = share_limits_factory()
    t = torrent_factory(tags="")
    sl.group_tag = "~share_limit_1.noHL"
    sl.update_share_limits_tag_for_torrent(t)
    add_tags = _calls_of(t, "add_tags")
    assert len(add_tags) == 1
    assert add_tags[0][1]["tags"] == "~share_limit_1.noHL"


def test_upload_limit_unlimited_translates_to_minus_one(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    # Torrent has 100 KiB/s set; switching to -1 (unlimited) should call set_upload_limit(-1).
    t = torrent_factory(up_limit=100 * 1024)
    sl.set_limits(t, max_ratio=-1, max_seeding_time=-1, limit_upload_speed=-1)
    ul_calls = _calls_of(t, "set_upload_limit")
    assert len(ul_calls) == 1
    assert ul_calls[0][1]["limit"] == -1


def test_upload_limit_positive_translates_to_bytes(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    t = torrent_factory(up_limit=0)  # currently unlimited
    sl.set_limits(t, max_ratio=-1, max_seeding_time=-1, limit_upload_speed=500)
    ul_calls = _calls_of(t, "set_upload_limit")
    assert len(ul_calls) == 1
    assert ul_calls[0][1]["limit"] == 500 * 1024


def test_upload_limit_unchanged_skips_call(share_limits_factory, torrent_factory):
    sl = share_limits_factory()
    # 500 KiB/s expressed in bytes/s. Production code reads it back as round(up_limit/1024) == 500.
    t = torrent_factory(up_limit=500 * 1024)
    sl.set_limits(t, max_ratio=-1, max_seeding_time=-1, limit_upload_speed=500)
    assert _calls_of(t, "set_upload_limit") == []


def test_dry_run_suppresses_all_qbit_mutations(share_limits_factory, torrent_factory):
    sl = share_limits_factory(config_overrides={"dry_run": True})
    t = torrent_factory()
    sl.group_tag = "~share_limit_1.x"
    sl.set_limits(t, max_ratio=5.0, max_seeding_time=-1, limit_upload_speed=100)
    sl.update_share_limits_tag_for_torrent(t)
    assert t.calls == [], "dry_run must not produce any qbit API calls"


@pytest.mark.parametrize(
    "blocking_tag_attr",
    [
        "min_seeding_time_tag",
        "min_num_seeds_tag",
        "last_active_tag",
    ],
)
def test_blocking_tag_short_circuits_set_share_limits(share_limits_factory, torrent_factory, blocking_tag_attr):
    """When the torrent already carries any 'not-ready-yet' tag, set_share_limits is NOT called."""
    sl = share_limits_factory()
    tag = getattr(sl, blocking_tag_attr)
    t = torrent_factory(tags=tag)
    result = sl.set_limits(t, max_ratio=5.0, max_seeding_time=43200)
    assert result == []
    assert _calls_of(t, "set_share_limits") == []
