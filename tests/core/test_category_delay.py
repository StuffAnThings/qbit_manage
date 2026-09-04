"""Tests for the delay_minutes branch in Category.change_categories().

Uses make_category() bypass so __init__ eager-work doesn't fire.
All completion_on values are set relative to real time() with deltas
large enough (>5 s) to be insensitive to clock skew.
"""

from __future__ import annotations

import time

import pytest

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category


def _now():
    return int(time.time())


def _make_cat(torrents, cat_change):
    cfg = FakeConfig(cat_change=cat_change)
    qbt = FakeQbtManager(torrents=torrents, config=cfg)
    return make_category(qbt)


def _set_calls(torrent):
    return [c for c in torrent.calls if c[0] == "set_category"]


# ── delay_minutes=0 fires regardless of completion_on ─────────────────────────


def test_delay_zero_fires_immediately():
    """delay_minutes=0 → category change fires regardless of how recent completion_on is."""
    t = FakeTorrent(
        name="Torrent.NAME.1",
        category="OldCat",
        # completed just 1 second ago — would be blocked by any positive delay
        completion_on=_now() - 1,
    )
    cat = _make_cat([t], {"OldCat": {"new_cat": "NewCat", "delay_minutes": 0}})
    cat.change_categories()
    assert _set_calls(t), "set_category must be called when delay_minutes=0"
    assert t.category == "NewCat"


# ── delay not yet elapsed → skipped ───────────────────────────────────────────


def test_delay_not_elapsed_skips_torrent():
    """delay_minutes=60 + completed 30 min ago → category change must be skipped."""
    t = FakeTorrent(
        name="Torrent.NAME.2",
        category="OldCat",
        completion_on=_now() - (30 * 60),  # 30 minutes ago
    )
    cat = _make_cat([t], {"OldCat": {"new_cat": "NewCat", "delay_minutes": 60}})
    cat.change_categories()
    assert _set_calls(t) == [], "set_category must NOT be called when delay has not elapsed"
    assert t.category == "OldCat"


# ── delay elapsed → fires ─────────────────────────────────────────────────────


def test_delay_elapsed_fires():
    """delay_minutes=60 + completed 120 min ago → category change must fire."""
    t = FakeTorrent(
        name="Torrent.NAME.3",
        category="OldCat",
        completion_on=_now() - (120 * 60),  # 120 minutes ago
    )
    cat = _make_cat([t], {"OldCat": {"new_cat": "NewCat", "delay_minutes": 60}})
    cat.change_categories()
    assert _set_calls(t), "set_category must be called when delay has elapsed"
    assert t.category == "NewCat"


# ── completion_on sentinel values (not yet completed) → skipped ───────────────


@pytest.mark.parametrize("completion_on", [0, -1])
def test_not_yet_completed_skips(completion_on):
    """delay_minutes=60 + completion_on in {0, -1} → torrent not yet complete, must skip."""
    t = FakeTorrent(
        name="Torrent.NAME.4",
        category="OldCat",
        completion_on=completion_on,
    )
    cat = _make_cat([t], {"OldCat": {"new_cat": "NewCat", "delay_minutes": 60}})
    cat.change_categories()
    assert _set_calls(t) == [], f"set_category must NOT be called when completion_on={completion_on}"
    assert t.category == "OldCat"


# ── boundary: elapsed == delay (inclusive) → fires ────────────────────────────


def test_delay_boundary_exactly_elapsed_fires():
    """delay_minutes=60 + completed exactly 60 min ago → boundary is inclusive, must fire."""
    # Use 60 min + 2 s buffer to avoid any sub-second race with clock advancing
    t = FakeTorrent(
        name="Torrent.NAME.5",
        category="OldCat",
        completion_on=_now() - (60 * 60) - 2,
    )
    cat = _make_cat([t], {"OldCat": {"new_cat": "NewCat", "delay_minutes": 60}})
    cat.change_categories()
    assert _set_calls(t), "set_category must be called at the boundary (elapsed >= delay)"
    assert t.category == "NewCat"
