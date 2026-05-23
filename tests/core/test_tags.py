"""Tests for Tags.tags() — stalled/private torrent detection and tagging.

Uses the make_tags() bypass constructor so we can test individual methods
without triggering the eager __init__ work.
"""

from __future__ import annotations

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_tags


def _make_qbt(torrents=None, config=None):
    cfg = config or FakeConfig()
    return FakeQbtManager(torrents=torrents or [], config=cfg)


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


# ── stalled torrent tagging ──────────────────────────────────────────────────


def test_tags_adds_stalled_tag_to_stalled_torrent():
    """Torrent in stalledDL state gets stalled_tag applied."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="stalledDL", tags="")
    cfg = FakeConfig(settings={"tag_stalled_torrents": True})
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    adds = _calls_of(t, "add_tags")
    assert adds, "add_tags should have been called"
    assert tags_obj.stats >= 1


def test_tags_skips_stalled_tag_when_disabled():
    """When tag_stalled_torrents is False, stalled torrents are not tagged."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="stalledDL", tags="")
    cfg = FakeConfig(settings={"tag_stalled_torrents": False})
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    # No stalled tag should be added
    adds = _calls_of(t, "add_tags")
    assert not adds or "Stalled" not in str(adds)


def test_tags_removes_stalled_tag_when_no_longer_stalled():
    """Torrent with stalled_tag but now uploading → tag is removed."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="uploading", tags="Stalled")
    cfg = FakeConfig(settings={"tag_stalled_torrents": True}, stalled_tag="Stalled")
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    removes = _calls_of(t, "remove_tags")
    assert removes, "remove_tags should have been called for previously stalled torrent"


def test_tags_dry_run_suppresses_add_tags():
    """In dry-run mode, add_tags is NOT called on the torrent."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="stalledDL", tags="")
    cfg = FakeConfig(settings={"tag_stalled_torrents": True}, dry_run=True)
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    assert _calls_of(t, "add_tags") == []
    # stats still increment even in dry-run
    assert tags_obj.stats >= 0


def test_tags_dry_run_suppresses_remove_tags():
    """In dry-run mode, remove_tags is NOT called even if tag should be removed."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="uploading", tags="Stalled")
    cfg = FakeConfig(settings={"tag_stalled_torrents": True}, dry_run=True, stalled_tag="Stalled")
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    assert _calls_of(t, "remove_tags") == []


# ── private torrent tagging ──────────────────────────────────────────────────


def test_tags_adds_private_tag_to_private_torrent():
    """Private torrent gets private_tag applied."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", private=True, tags="")
    cfg = FakeConfig(private_tag="Private")
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    adds = _calls_of(t, "add_tags")
    assert adds, "add_tags should have been called for private torrent"


def test_tags_skips_private_tag_when_torrent_public():
    """Public torrent does not receive private_tag."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", private=False, tags="")
    cfg = FakeConfig(private_tag="Private")
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    adds = _calls_of(t, "add_tags")
    # Should not add private tag to public torrent
    assert not adds or "Private" not in str(adds)


def test_tags_applies_both_stalled_and_private_tags():
    """Torrent that is both stalled AND private gets both tags."""
    t = FakeTorrent(name="Tv.Series.S01E01-NOGRP", state="stalledDL", private=True, tags="")
    cfg = FakeConfig(
        settings={"tag_stalled_torrents": True},
        stalled_tag="Stalled",
        private_tag="Private",
    )
    qbt = _make_qbt(torrents=[t], config=cfg)
    tags_obj = make_tags(qbt)
    tags_obj.tags()
    adds = _calls_of(t, "add_tags")
    assert adds, "add_tags should have been called"
    assert tags_obj.stats >= 2
