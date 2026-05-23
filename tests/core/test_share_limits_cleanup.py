"""Tests for ShareLimits.cleanup_torrents_for_group.

Verifies tor_delete_recycle is dispatched correctly, that content-path
mismatches skip deletion, and that notification batching kicks in past
GROUP_NOTIFICATION_LIMIT.
"""

from __future__ import annotations

from collections import OrderedDict


def _seed_tdel_dict(sl, torrent, body="ratio>=max"):
    """Place a torrent into sl.tdel_dict the way update_share_limits_for_group would."""
    sl.tdel_dict[torrent.hash] = {
        "torrent": torrent,
        "content_path": torrent["content_path"].replace(sl.root_dir, sl.remote_dir),
        "body": body,
    }


def _seed_torrentinfo(sl, torrent, msg=("",), status=(2,)):
    sl.qbt.torrentinfo[torrent.name] = {"msg": list(msg), "status": list(status)}


def test_cleanup_deletes_torrent_and_dispatches_notification(share_limits_factory, torrent_factory, group_config_factory):
    t = torrent_factory(
        hash="a" * 40,
        name="A",
        content_path="/data/torrents/A",
        category="RadarrComplete",
    )
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
    )
    _seed_tdel_dict(sl, t)
    _seed_torrentinfo(sl, t)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    assert len(sl.qbt.tor_delete_recycle_calls) == 1
    delivered_torrent, attr = sl.qbt.tor_delete_recycle_calls[0]
    assert delivered_torrent is t
    assert attr["function"] == "cleanup_share_limits"
    assert attr["torrent_category"] == "RadarrComplete"


def test_cleanup_skips_when_content_path_changed(share_limits_factory, torrent_factory, group_config_factory):
    """If the torrent's content_path changed between assignment and cleanup
    (e.g. the user moved it), the deletion must be aborted."""
    t = torrent_factory(hash="a" * 40, name="A", content_path="/data/torrents/A")
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
    )
    # Stash mismatched path
    sl.tdel_dict[t.hash] = {
        "torrent": t,
        "content_path": "/data/torrents/SOMETHING_ELSE",
        "body": "ratio>=max",
    }
    _seed_torrentinfo(sl, t)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    assert sl.qbt.tor_delete_recycle_calls == []


def test_cleanup_with_cross_seed_working_keeps_contents(share_limits_factory, torrent_factory, group_config_factory, monkeypatch):
    """When cross-seed is present AND a peer's tracker is working, only the
    .torrent is deleted — content is preserved."""
    import os

    t = torrent_factory(hash="a" * 40, name="A", content_path="/data/torrents/A")
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
    )
    sl.qbt.cross_seed_map[t.hash] = True  # has_cross_seed → True
    _seed_tdel_dict(sl, t)
    _seed_torrentinfo(sl, t, msg=[""], status=[2])  # "" in msg → working
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    assert len(sl.qbt.tor_delete_recycle_calls) == 1
    _, attr = sl.qbt.tor_delete_recycle_calls[0]
    assert attr["torrents_deleted_and_contents"] is False
    assert sl.stats_deleted == 1


def test_cleanup_with_no_cross_seed_deletes_contents(share_limits_factory, torrent_factory, group_config_factory, monkeypatch):
    import os

    t = torrent_factory(hash="a" * 40, name="A", content_path="/data/torrents/A")
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
    )
    _seed_tdel_dict(sl, t)
    _seed_torrentinfo(sl, t, msg=["unregistered"], status=[4])
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    assert len(sl.qbt.tor_delete_recycle_calls) == 1
    _, attr = sl.qbt.tor_delete_recycle_calls[0]
    assert attr["torrents_deleted_and_contents"] is True
    assert sl.stats_deleted_contents == 1


def test_cleanup_batches_notifications_past_group_limit(share_limits_factory, torrent_factory, group_config_factory, monkeypatch):
    """With > GROUP_NOTIFICATION_LIMIT (10) torrents, individual notifications
    are suppressed and a single grouped notification is sent."""
    import os

    torrents = [torrent_factory(hash=f"{i:040x}", name=f"T{i}", content_path=f"/data/torrents/T{i}") for i in range(12)]
    sl = share_limits_factory(
        torrents=torrents,
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
    )
    for t in torrents:
        _seed_tdel_dict(sl, t)
        _seed_torrentinfo(sl, t, msg=["unregistered"], status=[4])
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    # 12 deletions
    assert len(sl.qbt.tor_delete_recycle_calls) == 12
    # One grouped notification (the "AND content files" branch — all torrents
    # took the no-cross-seed path).
    notifications = sl.config.notifications_sent
    assert len(notifications) == 1
    assert notifications[0]["torrents_deleted_and_contents"] is True
    assert set(notifications[0]["torrents"]) == {f"T{i}" for i in range(12)}


def test_cleanup_batches_notifications_for_torrent_only_path(
    share_limits_factory, torrent_factory, group_config_factory, monkeypatch
):
    """Batched notifications when only the 'torrent-only' deletion path fires
    (cross-seed present, working) — verifies the t_deleted batch branch."""
    import os

    torrents = [torrent_factory(hash=f"{i:040x}", name=f"T{i}", content_path=f"/data/torrents/T{i}") for i in range(12)]
    sl = share_limits_factory(
        torrents=torrents,
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
    )
    for t in torrents:
        _seed_tdel_dict(sl, t)
        _seed_torrentinfo(sl, t, msg=[""], status=[2])
        sl.qbt.cross_seed_map[t.hash] = True
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    notifications = sl.config.notifications_sent
    assert len(notifications) == 1
    assert notifications[0]["torrents_deleted_and_contents"] is False
    assert set(notifications[0]["torrents"]) == {f"T{i}" for i in range(12)}


def test_cleanup_dry_run_does_not_call_delete(share_limits_factory, torrent_factory, group_config_factory, monkeypatch):
    import os

    t = torrent_factory(hash="a" * 40, name="A", content_path="/data/torrents/A")
    sl = share_limits_factory(
        torrents=[t],
        share_limits_config=OrderedDict([("noHL", group_config_factory(priority=1.0, cleanup=True))]),
        config_overrides={"dry_run": True},
    )
    _seed_tdel_dict(sl, t)
    _seed_torrentinfo(sl, t)
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    sl.cleanup_torrents_for_group("noHL", 1.0)

    assert sl.qbt.tor_delete_recycle_calls == []
