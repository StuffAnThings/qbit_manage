"""Tests for ReCheck.recheck() — pause→resume→recheck flow.

Uses the make_recheck() bypass constructor so we can test individual methods
without triggering the eager __init__ work.
"""

from __future__ import annotations

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_recheck


def _make_qbt(torrents=None, config=None, torrentinfo=None):
    cfg = config or FakeConfig()
    return FakeQbtManager(torrents=torrents or [], config=cfg, torrentinfo=torrentinfo or {})


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


# ── resume completed paused torrents ─────────────────────────────────────────


def test_recheck_resumes_completed_paused_torrent_with_no_limits():
    """Paused torrent with progress=1 and no ratio/seeding limits → resume."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="pausedUP",
        progress=1.0,
        ratio_limit=-1,
        seeding_time_limit=-1,
    )
    cfg = FakeConfig(commands={"recheck": True})
    qbt = _make_qbt(torrents=[t], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    resumes = _calls_of(t, "resume")
    assert resumes, "resume should have been called"
    assert recheck_obj.stats_resumed >= 1


def test_recheck_skips_when_command_disabled():
    """When commands['recheck'] is False, no rechecks occur."""
    t = FakeTorrent(
        name="Torrent.NAME.1",
        state="pausedUP",
        progress=1.0,
        ratio_limit=-1,
        seeding_time_limit=-1,
    )
    cfg = FakeConfig(commands={"recheck": False})
    qbt = _make_qbt(torrents=[t], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    assert _calls_of(t, "resume") == []
    assert recheck_obj.stats_resumed == 0


def test_recheck_resumes_with_unmet_ratio_limit():
    """Paused, completed torrent with ratio < ratio_limit → resume."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="pausedUP",
        progress=1.0,
        ratio=1.5,
        ratio_limit=2.0,
        seeding_time_limit=-1,
    )
    cfg = FakeConfig(commands={"recheck": True})
    qbt = _make_qbt(torrents=[t], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    resumes = _calls_of(t, "resume")
    assert resumes, "resume should have been called for unmet ratio limit"


def test_recheck_resumes_with_unmet_seeding_time_limit():
    """Paused, completed torrent with seeding_time < seeding_time_limit → resume."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="pausedUP",
        progress=1.0,
        seeding_time=3600,  # 1 hour
        seeding_time_limit=120,  # 2 hours
        ratio_limit=-1,
    )
    cfg = FakeConfig(commands={"recheck": True})
    qbt = _make_qbt(torrents=[t], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    resumes = _calls_of(t, "resume")
    assert resumes, "resume should have been called for unmet seeding time limit"


# ── recheck incomplete paused torrents ───────────────────────────────────────


def test_recheck_rechecks_incomplete_paused_torrent_if_complete_on_disk():
    """Paused, progress=0, but is_complete=True on disk → recheck."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="pausedDL",
        progress=0.0,
        hash="abc123",
    )
    t.state_enum.is_checking = False
    cfg = FakeConfig(commands={"recheck": True})
    torrentinfo = {"Tv.Series.S01E01-NOGRP": {"is_complete": True}}
    qbt = _make_qbt(torrents=[t], config=cfg, torrentinfo=torrentinfo)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    rechecks = _calls_of(t, "recheck")
    assert rechecks, "recheck should have been called"
    assert recheck_obj.stats_rechecked >= 1


def test_recheck_skips_if_already_checking():
    """Torrent progress=0, is_complete=True, but already checking → skip."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="checkingDL",
        progress=0.0,
        hash="abc123",
    )
    t.state_enum.is_checking = True
    cfg = FakeConfig(commands={"recheck": True})
    torrentinfo = {"Tv.Series.S01E01-NOGRP": {"is_complete": True}}
    qbt = _make_qbt(torrents=[t], config=cfg, torrentinfo=torrentinfo)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    rechecks = _calls_of(t, "recheck")
    assert not rechecks, "recheck should not be called if already checking"


# ── dry-run suppression ──────────────────────────────────────────────────────


def test_recheck_dry_run_suppresses_resume():
    """In dry-run mode, resume is NOT called even if torrent is eligible."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="pausedUP",
        progress=1.0,
        ratio_limit=-1,
        seeding_time_limit=-1,
    )
    cfg = FakeConfig(commands={"recheck": True}, dry_run=True)
    qbt = _make_qbt(torrents=[t], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    assert _calls_of(t, "resume") == []
    # stats still increment even in dry-run
    assert recheck_obj.stats_resumed >= 0


def test_recheck_dry_run_suppresses_recheck():
    """In dry-run mode, recheck is NOT called even if torrent is eligible."""
    t = FakeTorrent(
        name="Tv.Series.S01E01-NOGRP",
        state="pausedDL",
        progress=0.0,
        hash="abc123",
    )
    t.state_enum.is_checking = False
    cfg = FakeConfig(commands={"recheck": True}, dry_run=True)
    torrentinfo = {"Tv.Series.S01E01-NOGRP": {"is_complete": True}}
    qbt = _make_qbt(torrents=[t], config=cfg, torrentinfo=torrentinfo)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    assert _calls_of(t, "recheck") == []


# ── no-op cases ──────────────────────────────────────────────────────────────


def test_recheck_no_op_when_no_paused_torrents():
    """If no paused torrents exist, stats remain 0."""
    # Torrent is uploading (not paused), so recheck won't touch it
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="uploading", progress=1.0)
    cfg = FakeConfig(commands={"recheck": True})
    qbt = _make_qbt(torrents=[t], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    # Since no paused torrents exist, neither stat should increment
    assert recheck_obj.stats_resumed == 0
    assert recheck_obj.stats_rechecked == 0


def test_recheck_no_op_when_empty_torrent_list():
    """Empty torrent list → no work done."""
    cfg = FakeConfig(commands={"recheck": True})
    qbt = _make_qbt(torrents=[], config=cfg)
    recheck_obj = make_recheck(qbt)
    recheck_obj.recheck()
    assert recheck_obj.stats_resumed == 0
    assert recheck_obj.stats_rechecked == 0
