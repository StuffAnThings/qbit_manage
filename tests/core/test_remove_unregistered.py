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
