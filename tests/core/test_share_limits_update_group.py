"""Tests for ShareLimits.update_share_limits_for_group — orchestration logic.

Verifies that tags + limits are applied to torrents that need them, that
already-correctly-configured torrents are skipped, and that cleanup-eligible
torrents are queued into tdel_dict.
"""

from __future__ import annotations

from collections import OrderedDict


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


def _has_call(torrent, name):
    return any(c[0] == name for c in torrent.calls)


def test_new_torrent_gets_tagged_and_limited(share_limits_factory, torrent_factory, group_config_factory):
    group_cfg = group_config_factory(
        priority=1.0,
        max_ratio=5.0,
        max_seeding_time=43200,
    )
    t = torrent_factory(hash="a" * 40, tags="", max_ratio=-1.0, max_seeding_time=-1)
    group_cfg["torrents"] = [t]
    share_limits = OrderedDict([("noHL", group_cfg)])
    sl = share_limits_factory(torrents=[t], share_limits_config=share_limits)

    sl.update_share_limits_for_group("noHL", group_cfg, [t])

    assert _has_call(t, "add_tags")
    add_tag = _calls_of(t, "add_tags")[0][1]["tags"]
    assert add_tag == "~share_limit_1.0.noHL"
    assert _has_call(t, "set_share_limits")
    assert t.name in sl.torrents_updated
    assert sl.stats_tagged == 1


def test_torrent_already_correctly_tagged_is_skipped(share_limits_factory, torrent_factory, group_config_factory):
    """A torrent whose ratio_limit/seeding_time_limit/up_limit/tag all match
    the group config should not have its share limits updated.

    Note: production code compares group_config["max_ratio"] against
    torrent.ratio_limit (the per-torrent qBittorrent limit field), NOT against
    torrent.max_ratio (which is the global max-ratio preference copy).

    The group tag is always re-applied by update_share_limits_tag_for_torrent
    (remove old + add new) even when limits are already correct — that is
    expected behavior. What MUST NOT happen is set_share_limits being called
    (i.e. the limits themselves do not get re-written) and the torrent must
    not appear in torrents_updated.
    """
    group_cfg = group_config_factory(
        priority=1.0,
        max_ratio=5.0,
        max_seeding_time=43200,
        limit_upload_speed=-1,
    )
    expected_tag = "~share_limit_1.0.noHL"
    t = torrent_factory(
        hash="a" * 40,
        tags=expected_tag,
        # ratio_limit / seeding_time_limit are the per-torrent limit fields that
        # production code uses to decide whether limits need updating.
        ratio_limit=5.0,
        seeding_time_limit=43200,
        up_limit=0,
        ratio=0.1,
        seeding_time=10,
    )
    group_cfg["torrents"] = [t]
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_cfg)]),
    )

    sl.update_share_limits_for_group("noHL", group_cfg, [t])

    # share limits must NOT be rewritten when already matching
    assert _calls_of(t, "set_share_limits") == []
    # torrent must not be counted as "updated" (i.e. _should_update_torrent returned False)
    assert t.name not in sl.torrents_updated


def test_add_group_to_tag_false_skips_tagging(share_limits_factory, torrent_factory, group_config_factory):
    group_cfg = group_config_factory(
        priority=1.0,
        max_ratio=5.0,
        max_seeding_time=-1,
        add_group_to_tag=False,
    )
    t = torrent_factory(hash="a" * 40, tags="", max_ratio=-1.0)
    group_cfg["torrents"] = [t]
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_cfg)]),
    )

    sl.update_share_limits_for_group("noHL", group_cfg, [t])

    assert _calls_of(t, "add_tags") == []
    # set_share_limits still happens — only the group tag is suppressed
    assert _has_call(t, "set_share_limits")


def test_enable_group_upload_speed_divides_across_torrents(share_limits_factory, torrent_factory, group_config_factory):
    """1000 KiB/s split across 4 torrents → 250 KiB/s each."""
    group_cfg = group_config_factory(
        priority=1.0,
        max_ratio=-1.0,
        max_seeding_time=-1,
        limit_upload_speed=1000,
        enable_group_upload_speed=True,
    )
    torrents = [torrent_factory(hash=f"{i:040x}", up_limit=0, tags="") for i in range(4)]
    group_cfg["torrents"] = list(torrents)
    sl = share_limits_factory(
        torrents=torrents,
        share_limits_config=OrderedDict([("noHL", group_cfg)]),
    )

    sl.update_share_limits_for_group("noHL", group_cfg, torrents)

    # Each torrent should have been called with 250 * 1024 bytes/sec
    for t in torrents:
        ul = _calls_of(t, "set_upload_limit")
        assert ul, f"set_upload_limit not called on {t.name}"
        assert ul[0][1]["limit"] == 250 * 1024


def test_cleanup_eligible_torrents_queued_into_tdel_dict(share_limits_factory, torrent_factory, group_config_factory):
    """When cleanup=True and the torrent meets the ratio limit, it lands in tdel_dict."""
    group_cfg = group_config_factory(
        priority=1.0,
        max_ratio=2.0,
        max_seeding_time=-1,
        cleanup=True,
        min_seeding_time=0,
    )
    t = torrent_factory(
        hash="a" * 40,
        tags="",
        ratio=3.0,  # over the limit
        seeding_time=99999,
        max_ratio=-1.0,
    )
    group_cfg["torrents"] = [t]
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_cfg)]),
    )

    sl.update_share_limits_for_group("noHL", group_cfg, [t])

    assert t.hash in sl.tdel_dict
    assert sl.tdel_dict[t.hash]["torrent"] is t
    assert sl.tdel_dict[t.hash]["body"]  # non-empty body string


def test_cleanup_skips_torrents_under_limit(share_limits_factory, torrent_factory, group_config_factory):
    group_cfg = group_config_factory(
        priority=1.0,
        max_ratio=2.0,
        max_seeding_time=-1,
        cleanup=True,
    )
    t = torrent_factory(hash="a" * 40, tags="", ratio=0.5)
    group_cfg["torrents"] = [t]
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_cfg)]),
    )

    sl.update_share_limits_for_group("noHL", group_cfg, [t])

    assert sl.tdel_dict == {}


def test_multiple_share_limit_tags_triggers_retag(share_limits_factory, torrent_factory, group_config_factory):
    """If a torrent has multiple ~share_limit_* tags (legacy state from a
    prior bug or manual edit), the group should still drive a re-tag."""
    group_cfg = group_config_factory(priority=1.0, max_ratio=-1, max_seeding_time=-1)
    expected_tag = "~share_limit_1.0.noHL"
    # Has the current group's expected tag PLUS a stray one — production code
    # should detect the duplicate and re-tag.
    t = torrent_factory(
        hash="a" * 40,
        tags=f"{expected_tag}, ~share_limit_99.old",
        max_ratio=-1.0,
        max_seeding_time=-1,
    )
    group_cfg["torrents"] = [t]
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_cfg)]),
    )

    sl.update_share_limits_for_group("noHL", group_cfg, [t])

    # remove_tags called to strip the legacy share_limit tags, then add_tags re-applies
    assert _has_call(t, "remove_tags")
    assert _has_call(t, "add_tags")
