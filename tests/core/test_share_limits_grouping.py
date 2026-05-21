"""Tests for tag/category filtering and priority-based group assignment.

Covers: check_tags, check_category, get_share_limit_group, assign_torrents_to_group.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest

# ---- check_tags truth table -------------------------------------------------


@pytest.mark.parametrize(
    "tags, include_all, include_any, exclude_all, exclude_any, expected",
    [
        # No filters: always matches
        (["a"], None, None, None, None, True),
        ([], None, None, None, None, True),
        # include_all_tags: every required tag must be present
        (["a", "b"], ["a", "b"], None, None, None, True),
        (["a"], ["a", "b"], None, None, None, False),
        (["a", "b", "c"], ["a", "b"], None, None, None, True),
        # include_any_tags: at least one required tag must be present
        (["a"], None, ["a", "b"], None, None, True),
        (["b"], None, ["a", "b"], None, None, True),
        (["c"], None, ["a", "b"], None, None, False),
        # exclude_all_tags: ALL must be present to exclude
        (["a", "b"], None, None, ["a", "b"], None, False),
        (["a"], None, None, ["a", "b"], None, True),
        # exclude_any_tags: ANY presence excludes
        (["a"], None, None, None, ["a", "b"], False),
        (["c"], None, None, None, ["a", "b"], True),
        # Mixed include/exclude
        (["a", "b"], ["a"], None, None, ["x"], True),
        (["a", "x"], ["a"], None, None, ["x"], False),
    ],
)
def test_check_tags(share_limits_factory, tags, include_all, include_any, exclude_all, exclude_any, expected):
    sl = share_limits_factory()
    assert (
        sl.check_tags(
            tags,
            include_all_tags=include_all,
            include_any_tags=include_any,
            exclude_all_tags=exclude_all,
            exclude_any_tags=exclude_any,
        )
        is expected
    )


@pytest.mark.parametrize(
    "category, categories, expected",
    [
        ("RadarrComplete", None, True),  # empty filter matches all
        ("RadarrComplete", [], True),
        ("RadarrComplete", ["RadarrComplete"], True),
        ("RadarrComplete", ["SonarrComplete"], False),
        ("RadarrComplete", ["SonarrComplete", "RadarrComplete"], True),
        ("", ["RadarrComplete"], False),
    ],
)
def test_check_category(share_limits_factory, category, categories, expected):
    sl = share_limits_factory()
    assert sl.check_category(category, categories) is expected


# ---- get_share_limit_group --------------------------------------------------


def _build_priority_config(group_config_factory):
    """Two-group config: noHL wins at priority 1, default at 999."""
    return OrderedDict(
        [
            ("noHL", group_config_factory(priority=1.0, include_all_tags=["noHL"])),
            ("cross-seed", group_config_factory(priority=2.0, include_all_tags=["cross-seed"])),
            ("default", group_config_factory(priority=999.0)),
        ]
    )


def test_get_share_limit_group_first_priority_wins(share_limits_factory, group_config_factory):
    cfg = _build_priority_config(group_config_factory)
    sl = share_limits_factory(share_limits_config=cfg)
    # Torrent has BOTH noHL and cross-seed tags. Highest priority (lowest number) wins.
    assert sl.get_share_limit_group(["noHL", "cross-seed"], "") == "noHL"


def test_get_share_limit_group_falls_through_to_default(share_limits_factory, group_config_factory):
    cfg = _build_priority_config(group_config_factory)
    sl = share_limits_factory(share_limits_config=cfg)
    assert sl.get_share_limit_group(["something-else"], "") == "default"


def test_get_share_limit_group_returns_none_when_no_default(share_limits_factory, group_config_factory):
    cfg = OrderedDict(
        [
            ("noHL", group_config_factory(priority=1.0, include_all_tags=["noHL"])),
        ]
    )
    sl = share_limits_factory(share_limits_config=cfg)
    assert sl.get_share_limit_group(["other"], "") is None


def test_get_share_limit_group_respects_category(share_limits_factory, group_config_factory):
    cfg = OrderedDict(
        [
            ("movies", group_config_factory(priority=1.0, categories=["RadarrComplete"])),
            ("default", group_config_factory(priority=999.0)),
        ]
    )
    sl = share_limits_factory(share_limits_config=cfg)
    assert sl.get_share_limit_group([], "RadarrComplete") == "movies"
    assert sl.get_share_limit_group([], "SonarrComplete") == "default"


# ---- assign_torrents_to_group -----------------------------------------------


def test_assign_torrents_to_group_uses_priority_order(share_limits_factory, torrent_factory, group_config_factory):
    cfg = _build_priority_config(group_config_factory)
    t_noHL = torrent_factory(name="A", hash="a" * 40, tags="noHL")
    t_cross = torrent_factory(name="B", hash="b" * 40, tags="cross-seed")
    t_both = torrent_factory(name="C", hash="c" * 40, tags="noHL, cross-seed")
    t_other = torrent_factory(name="D", hash="d" * 40, tags="random")

    sl = share_limits_factory(share_limits_config=cfg)
    sl.assign_torrents_to_group([t_noHL, t_cross, t_both, t_other])

    assert [t.name for t in cfg["noHL"]["torrents"]] == ["A", "C"]
    assert [t.name for t in cfg["cross-seed"]["torrents"]] == ["B"]
    assert [t.name for t in cfg["default"]["torrents"]] == ["D"]


def test_assign_torrents_unmatched_dropped_when_no_default(share_limits_factory, torrent_factory, group_config_factory):
    cfg = OrderedDict(
        [
            ("noHL", group_config_factory(priority=1.0, include_all_tags=["noHL"])),
        ]
    )
    t = torrent_factory(name="X", hash="0" * 40, tags="random")
    sl = share_limits_factory(share_limits_config=cfg)
    sl.assign_torrents_to_group([t])
    assert cfg["noHL"]["torrents"] == []
