"""Tests for TagNoHardLinks tagging path.

Uses the make_tag_nohardlinks() bypass constructor and injects a fake
check_hardlinks object so no real filesystem access occurs.
"""

from __future__ import annotations

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_tag_nohardlinks

# ── helpers ───────────────────────────────────────────────────────────────────


class _FakeCheckHardLinks:
    """Stand-in for util.CheckHardLinks — controls nohardlink() return value."""

    def __init__(self, has_nohardlinks: bool = True):
        self._has = has_nohardlinks

    def nohardlink(self, file, notify, ignore_root_dir):
        return self._has


def _tracker():
    return {"tag": [], "cat": "", "notifiarr": None, "url": "http://tracker1.example/announce"}


def _make_qbt(torrents=None, nohardlinks=None, nohardlinks_tag="noHL", dry_run=False):
    cfg = FakeConfig(
        nohardlinks=nohardlinks or {"Movies": {}},
        nohardlinks_tag=nohardlinks_tag,
        dry_run=dry_run,
    )
    return FakeQbtManager(torrents=torrents or [], config=cfg)


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


# ── add_tag_no_hl ─────────────────────────────────────────────────────────────


def test_add_tag_no_hl_adds_tag_to_torrent():
    """add_tag_no_hl() should call torrent.add_tags with the nohardlinks_tag."""
    t = FakeTorrent(category="Movies", tags="")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)
    tnhl.add_tag_no_hl(torrent=t, tracker=_tracker(), category="Movies")
    adds = _calls_of(t, "add_tags")
    assert adds, "add_tags should have been called"
    assert adds[0][1]["tags"] == "noHL"
    assert tnhl.stats_tagged == 1


def test_add_tag_no_hl_dry_run_suppresses_mutation():
    """In dry-run mode, add_tags is NOT called on the torrent."""
    t = FakeTorrent(category="Movies", tags="")
    qbt = _make_qbt(torrents=[t], dry_run=True)
    tnhl = make_tag_nohardlinks(qbt)
    tnhl.add_tag_no_hl(torrent=t, tracker=_tracker(), category="Movies")
    assert _calls_of(t, "add_tags") == []
    # stats still increment even in dry-run
    assert tnhl.stats_tagged == 1


def test_add_tag_no_hl_appends_to_notify_lists():
    """add_tag_no_hl() populates torrents_updated_tagged and notify_attr_tagged."""
    t = FakeTorrent(name="MyMovie", hash="abc1", category="Movies", tags="")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)
    tnhl.add_tag_no_hl(torrent=t, tracker=_tracker(), category="Movies")
    assert "MyMovie" in tnhl.torrents_updated_tagged
    assert len(tnhl.notify_attr_tagged) == 1
    assert tnhl.notify_attr_tagged[0]["function"] == "tag_nohardlinks"


# ── check_previous_nohardlinks_tagged_torrents ────────────────────────────────


def test_check_previous_untags_when_hardlinks_found():
    """Torrent previously tagged noHL but now has hardlinks → tag removed."""
    t = FakeTorrent(category="Movies", tags="noHL")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)
    # has_nohardlinks=False means hardlinks HAVE been found (tag should be removed)
    tnhl.check_previous_nohardlinks_tagged_torrents(has_nohardlinks=False, torrent=t, tracker=_tracker(), category="Movies")
    removes = _calls_of(t, "remove_tags")
    assert removes, "remove_tags should have been called"
    assert tnhl.stats_untagged == 1


def test_check_previous_no_untag_when_still_no_hardlinks():
    """Torrent tagged noHL and still has no hardlinks → tag is not removed."""
    t = FakeTorrent(category="Movies", tags="noHL")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)
    tnhl.check_previous_nohardlinks_tagged_torrents(has_nohardlinks=True, torrent=t, tracker=_tracker(), category="Movies")
    assert _calls_of(t, "remove_tags") == []
    assert tnhl.stats_untagged == 0


def test_check_previous_no_untag_when_tag_not_present():
    """Torrent has hardlinks but was never tagged → no remove call."""
    t = FakeTorrent(category="Movies", tags="")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)
    tnhl.check_previous_nohardlinks_tagged_torrents(has_nohardlinks=False, torrent=t, tracker=_tracker(), category="Movies")
    assert _calls_of(t, "remove_tags") == []
    assert tnhl.stats_untagged == 0


def test_check_previous_dry_run_suppresses_remove():
    """In dry-run mode remove_tags is NOT called even when tag should be removed."""
    t = FakeTorrent(category="Movies", tags="noHL")
    qbt = _make_qbt(torrents=[t], dry_run=True)
    tnhl = make_tag_nohardlinks(qbt)
    tnhl.check_previous_nohardlinks_tagged_torrents(has_nohardlinks=False, torrent=t, tracker=_tracker(), category="Movies")
    assert _calls_of(t, "remove_tags") == []
    assert tnhl.stats_untagged == 1


# ── _process_torrent_for_nohardlinks ─────────────────────────────────────────


def test_process_torrent_tags_when_no_hardlinks(monkeypatch):
    """_process_torrent_for_nohardlinks tags torrent when nohardlink() returns True."""
    t = FakeTorrent(category="Movies", tags="")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)

    fake_hl = _FakeCheckHardLinks(has_nohardlinks=True)
    tnhl._process_torrent_for_nohardlinks(
        torrent=t,
        check_hardlinks=fake_hl,
        ignore_root_dir=True,
        exclude_tags=[],
        category="Movies",
    )
    adds = _calls_of(t, "add_tags")
    assert adds and adds[0][1]["tags"] == "noHL"


def test_process_torrent_does_not_retag_if_already_tagged(monkeypatch):
    """Torrent already has noHL tag → add_tags is NOT called again."""
    t = FakeTorrent(category="Movies", tags="noHL")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)

    fake_hl = _FakeCheckHardLinks(has_nohardlinks=True)
    tnhl._process_torrent_for_nohardlinks(
        torrent=t,
        check_hardlinks=fake_hl,
        ignore_root_dir=True,
        exclude_tags=[],
        category="Movies",
    )
    assert _calls_of(t, "add_tags") == []
    assert tnhl.stats_tagged == 0


def test_process_torrent_skips_excluded_tag(monkeypatch):
    """Torrent with an exclude_tag is skipped entirely."""
    t = FakeTorrent(category="Movies", tags="skip-me")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)

    fake_hl = _FakeCheckHardLinks(has_nohardlinks=True)
    tnhl._process_torrent_for_nohardlinks(
        torrent=t,
        check_hardlinks=fake_hl,
        ignore_root_dir=True,
        exclude_tags=["skip-me"],
        category="Movies",
    )
    assert _calls_of(t, "add_tags") == []
    assert _calls_of(t, "remove_tags") == []


def test_process_torrent_removes_tag_when_hardlinks_appear(monkeypatch):
    """nohardlink() returns False (has hardlinks) → existing noHL tag removed."""
    t = FakeTorrent(category="Movies", tags="noHL")
    qbt = _make_qbt(torrents=[t])
    tnhl = make_tag_nohardlinks(qbt)

    fake_hl = _FakeCheckHardLinks(has_nohardlinks=False)
    tnhl._process_torrent_for_nohardlinks(
        torrent=t,
        check_hardlinks=fake_hl,
        ignore_root_dir=True,
        exclude_tags=[],
        category="Movies",
    )
    removes = _calls_of(t, "remove_tags")
    assert removes and removes[0][1]["tags"] == "noHL"
    assert tnhl.stats_untagged == 1
