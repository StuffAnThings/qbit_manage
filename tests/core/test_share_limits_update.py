"""End-to-end smoke tests for ShareLimits.update_share_limits — the top-level
entrypoint that ties grouping, limit application, and cleanup together."""

from __future__ import annotations

from collections import OrderedDict


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


def _has_call(torrent, name):
    return any(c[0] == name for c in torrent.calls)


def test_update_share_limits_end_to_end_tags_and_cleans(share_limits_factory, torrent_factory, group_config_factory):
    """Three torrents: one matches noHL group (gets tagged + limited),
    one matches cross-seed group (cleanup-eligible → tdel_dict + delete),
    one falls through to default (no-op)."""

    t_noHL = torrent_factory(
        hash="a" * 40,
        name="A",
        tags="noHL",
        max_ratio=-1.0,
        max_seeding_time=-1,
        content_path="/data/torrents/A",
    )
    t_cross = torrent_factory(
        hash="b" * 40,
        name="B",
        tags="cross-seed",
        ratio=10.0,
        seeding_time=99999,
        max_ratio=-1.0,
        content_path="/data/torrents/B",
    )
    t_default = torrent_factory(
        hash="c" * 40,
        name="C",
        tags="random",
        max_ratio=-1.0,
        max_seeding_time=-1,
        content_path="/data/torrents/C",
    )

    share_limits = OrderedDict(
        [
            (
                "noHL",
                group_config_factory(
                    priority=1.0,
                    include_all_tags=["noHL"],
                    max_ratio=5.0,
                    max_seeding_time=43200,
                ),
            ),
            (
                "cross-seed",
                group_config_factory(
                    priority=2.0,
                    include_all_tags=["cross-seed"],
                    max_ratio=2.0,
                    cleanup=True,
                ),
            ),
            ("default", group_config_factory(priority=999.0)),
        ]
    )

    sl = share_limits_factory(
        torrents=[t_noHL, t_cross, t_default],
        share_limits_config=share_limits,
    )
    # cleanup_torrents_for_group inspects torrentinfo and the filesystem
    sl.qbt.torrentinfo = {
        "A": {"msg": [""], "status": [2]},
        "B": {"msg": ["unregistered"], "status": [4]},
        "C": {"msg": [""], "status": [2]},
    }
    import unittest.mock as mock

    with mock.patch("os.path.exists", return_value=True):
        sl.update_share_limits()

    # noHL: tagged + limited, not deleted
    assert _has_call(t_noHL, "add_tags")
    assert _has_call(t_noHL, "set_share_limits")
    assert all(t_noHL is not c[0] for c in sl.qbt.tor_delete_recycle_calls)
    # cross-seed: deleted via tor_delete_recycle (the only delete this run)
    assert len(sl.qbt.tor_delete_recycle_calls) == 1
    deleted_torrent, _ = sl.qbt.tor_delete_recycle_calls[0]
    assert deleted_torrent is t_cross
    # default group: tagged with the default group's marker but not deleted
    default_tag_calls = [c for c in _calls_of(t_default, "add_tags") if "default" in c[1]["tags"]]
    assert default_tag_calls, "default group should still tag matching torrents"
    assert all(t_default is not c[0] for c in sl.qbt.tor_delete_recycle_calls)
