"""Tests for Category.change_categories.

Uses the make_category() bypass constructor so we can test individual methods
without triggering the eager __init__ work (category() + change_categories()).
"""

from __future__ import annotations

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category


def _make_qbt(torrents=None, config=None):
    cfg = config or FakeConfig()
    return FakeQbtManager(torrents=torrents or [], config=cfg)


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


# ── change_categories early-exit ──────────────────────────────────────────────


def test_change_categories_no_op_when_cat_change_empty():
    """If config.cat_change is empty/falsy, method returns immediately."""
    cfg = FakeConfig(cat_change={})
    qbt = _make_qbt(config=cfg)
    cat = make_category(qbt)
    # Should not raise and should not touch any torrents
    cat.change_categories()
    assert cat.stats == 0
    assert cat.torrents_updated == []


def test_change_categories_moves_matching_torrent():
    """Torrent in 'OldCat' moves to 'NewCat'."""
    t = FakeTorrent(category="OldCat", tags="")
    cfg = FakeConfig(cat_change={"OldCat": "NewCat"})
    qbt = _make_qbt(torrents=[t], config=cfg)
    cat = make_category(qbt)
    cat.change_categories()
    assert _calls_of(t, "set_category"), "set_category should have been called"
    assert t.category == "NewCat"
    assert cat.stats == 1
    assert t.name in cat.torrents_updated


def test_change_categories_leaves_non_matching_torrent_alone():
    """Torrent in a different category is untouched."""
    t = FakeTorrent(category="OtherCat", tags="")
    cfg = FakeConfig(cat_change={"OldCat": "NewCat"})
    qbt = _make_qbt(torrents=[t], config=cfg)
    cat = make_category(qbt)
    cat.change_categories()
    assert _calls_of(t, "set_category") == []
    assert cat.stats == 0


def test_change_categories_multiple_mappings():
    """Multiple cat_change entries each fire for their own category."""
    t1 = FakeTorrent(name="T1", hash="abc1", category="CatA", tags="")
    t2 = FakeTorrent(name="T2", hash="abc2", category="CatB", tags="")
    cfg = FakeConfig(cat_change={"CatA": "NewA", "CatB": "NewB"})
    qbt = _make_qbt(torrents=[t1, t2], config=cfg)
    cat = make_category(qbt)
    cat.change_categories()
    assert t1.category == "NewA"
    assert t2.category == "NewB"
    assert cat.stats == 2


def test_change_categories_dry_run_suppresses_set_category():
    """In dry-run mode set_category is NOT called on the torrent."""
    t = FakeTorrent(category="OldCat", tags="")
    cfg = FakeConfig(cat_change={"OldCat": "NewCat"}, dry_run=True)
    qbt = _make_qbt(torrents=[t], config=cfg)
    cat = make_category(qbt)
    cat.change_categories()
    assert _calls_of(t, "set_category") == []
    # stats and audit lists are still updated even in dry-run
    assert cat.stats == 1


def test_change_categories_notify_attr_populated():
    """After a category change the notify_attr list gains an entry."""
    t = FakeTorrent(category="OldCat", tags="")
    cfg = FakeConfig(cat_change={"OldCat": "NewCat"})
    qbt = _make_qbt(torrents=[t], config=cfg)
    cat = make_category(qbt)
    cat.change_categories()
    assert len(cat.notify_attr) == 1
    attr = cat.notify_attr[0]
    assert attr["function"] == "cat_update"
    assert attr["title"] == "Moving Categories"
    assert "NewCat" in attr["body"]


def test_change_categories_two_torrents_same_source_cat():
    """Two torrents in the same source category both get moved."""
    t1 = FakeTorrent(name="T1", hash="aaa1", category="OldCat", tags="")
    t2 = FakeTorrent(name="T2", hash="aaa2", category="OldCat", tags="")
    cfg = FakeConfig(cat_change={"OldCat": "NewCat"})
    qbt = _make_qbt(torrents=[t1, t2], config=cfg)
    cat = make_category(qbt)
    cat.change_categories()
    assert t1.category == "NewCat"
    assert t2.category == "NewCat"
    assert cat.stats == 2
