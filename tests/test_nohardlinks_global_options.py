"""Unit tests for nohardlinks global_options merge behavior.

These tests call ``Config.process_config_nohardlinks()`` directly via
``object.__new__(Config)`` + attribute injection, mirroring the
``make_share_limits()`` pattern in factories.py.  Every assertion is tied to
production code output — none of them are tautological self-assignment checks.
"""

from __future__ import annotations

import pytest

from modules.config import Config
from modules.util import Failed

# ---------------------------------------------------------------------------
# Helper — minimal Config skeleton that satisfies process_config_nohardlinks
# ---------------------------------------------------------------------------


def _make_config(nohardlinks_data, *, tag_nohardlinks=True):
    """Return a Config instance wired for process_config_nohardlinks().

    ``nohardlinks_data`` is the value that would sit under the ``nohardlinks``
    key in config.yml.  ``tag_nohardlinks`` controls whether the command flag
    is enabled (default True so the nohardlinks branch is exercised).
    """
    cfg = object.__new__(Config)
    cfg.data = {"nohardlinks": nohardlinks_data}
    cfg.commands = {"tag_nohardlinks": tag_nohardlinks}
    cfg.notify_calls = []
    cfg.notify = lambda err, func, *a, **kw: cfg.notify_calls.append((err, func))
    return cfg


# ---------------------------------------------------------------------------
# Order-preserving merge tests
# ---------------------------------------------------------------------------


class TestExcludeTagsMerge:
    def test_global_and_per_cat_no_overlap(self):
        """global=[a,b] + per_cat=[c] → [a,b,c], global tags appear first."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": ["a", "b"]},
                "cat1": {"exclude_tags": ["c"]},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["exclude_tags"] == ["a", "b", "c"]

    def test_global_and_per_cat_with_overlap(self):
        """global=[a,b] + per_cat=[b,c] → [a,b,c], no duplicates, global-first."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": ["a", "b"]},
                "cat1": {"exclude_tags": ["b", "c"]},
            }
        )
        cfg.process_config_nohardlinks()
        result = cfg.nohardlinks["cat1"]["exclude_tags"]
        assert result == ["a", "b", "c"], f"Expected ['a','b','c'], got {result}"

    def test_order_is_deterministic_global_first(self):
        """Merge order: global tags always precede any extra per-cat tags."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": ["z", "y"]},
                "cat1": {"exclude_tags": ["x", "y"]},
            }
        )
        cfg.process_config_nohardlinks()
        result = cfg.nohardlinks["cat1"]["exclude_tags"]
        # z and y come from global, x is the only addition from per-cat
        assert result[0] == "z"
        assert result[1] == "y"
        assert result[2] == "x"
        assert len(result) == 3

    def test_per_cat_no_exclude_tags_inherits_global(self):
        """Category without exclude_tags gets global's list as-is."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": ["g1", "g2"]},
                "cat1": {"ignore_root_dir": True},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["exclude_tags"] == ["g1", "g2"]

    def test_empty_global_per_cat_specified(self):
        """No global_options → per-cat exclude_tags used as-is."""
        cfg = _make_config({"cat1": {"exclude_tags": ["only"]}})
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["exclude_tags"] == ["only"]

    def test_both_empty(self):
        """Both global and per-cat empty → empty list."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": []},
                "cat1": {"exclude_tags": []},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["exclude_tags"] == []

    def test_multiple_categories_each_merged_independently(self):
        """Each category gets its own independent merge; no cross-category bleed."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": ["global"]},
                "cat1": {"exclude_tags": ["only_cat1"]},
                "cat2": {"exclude_tags": ["only_cat2"]},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["exclude_tags"] == ["global", "only_cat1"]
        assert cfg.nohardlinks["cat2"]["exclude_tags"] == ["global", "only_cat2"]


# ---------------------------------------------------------------------------
# ignore_root_dir override
# ---------------------------------------------------------------------------


class TestIgnoreRootDirOverride:
    def test_per_cat_false_beats_global_true(self):
        """Per-category ignore_root_dir=False overrides global default of True."""
        cfg = _make_config(
            {
                "global_options": {"ignore_root_dir": True},
                "cat1": {"ignore_root_dir": False},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["ignore_root_dir"] is False

    def test_per_cat_true_beats_global_false(self):
        """Per-category ignore_root_dir=True overrides global=False."""
        cfg = _make_config(
            {
                "global_options": {"ignore_root_dir": False},
                "cat1": {"ignore_root_dir": True},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["ignore_root_dir"] is True

    def test_no_per_cat_inherits_global_ignore_root_dir(self):
        """Category omitting ignore_root_dir inherits global value."""
        cfg = _make_config(
            {
                "global_options": {"ignore_root_dir": False},
                "cat1": {},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["ignore_root_dir"] is False


# ---------------------------------------------------------------------------
# global_options type validation (Bug 1)
# ---------------------------------------------------------------------------


class TestGlobalOptionsTypeValidation:
    def test_global_options_as_string_raises_failed(self):
        """global_options: 'yes please' (string) must raise Failed."""
        cfg = _make_config(
            {
                "global_options": "yes please",
                "cat1": {},
            }
        )
        with pytest.raises(Failed, match="global_options must be a dict"):
            cfg.process_config_nohardlinks()

    def test_global_options_as_list_raises_failed(self):
        """global_options: [a, b] (list) must raise Failed."""
        cfg = _make_config(
            {
                "global_options": ["a", "b"],
                "cat1": {},
            }
        )
        with pytest.raises(Failed, match="global_options must be a dict"):
            cfg.process_config_nohardlinks()

    def test_global_options_as_int_raises_failed(self):
        """global_options: 42 (int) must raise Failed."""
        cfg = _make_config(
            {
                "global_options": 42,
                "cat1": {},
            }
        )
        with pytest.raises(Failed, match="global_options must be a dict"):
            cfg.process_config_nohardlinks()


# ---------------------------------------------------------------------------
# Per-category exclude_tags type validation (pre-existing, kept real)
# ---------------------------------------------------------------------------


class TestPerCatExcludeTagsTypeValidation:
    def test_exclude_tags_as_string_raises_failed(self):
        """Per-category exclude_tags as string must raise Failed."""
        cfg = _make_config({"cat1": {"exclude_tags": "not-a-list"}})
        with pytest.raises(Failed, match="exclude_tags must be a list"):
            cfg.process_config_nohardlinks()


# ---------------------------------------------------------------------------
# Bug 1 — outer nohardlinks type validation
# ---------------------------------------------------------------------------


class TestOuterNohardlinksTypeValidation:
    def test_nohardlinks_as_int_raises_failed(self):
        """nohardlinks: 42 (int) must raise Failed before any iteration."""
        cfg = _make_config(42)
        with pytest.raises(Failed, match="nohardlinks must be a dict"):
            cfg.process_config_nohardlinks()
        # nohardlinks dict must NOT be populated with garbage
        assert cfg.nohardlinks is None or cfg.nohardlinks == {}

    def test_nohardlinks_as_string_raises_failed(self):
        """nohardlinks: 'movies' (string) must raise Failed, not iterate characters."""
        cfg = _make_config("movies-completed")
        with pytest.raises(Failed, match="nohardlinks must be a dict"):
            cfg.process_config_nohardlinks()

    def test_nohardlinks_as_bool_raises_failed(self):
        """nohardlinks: True (bool) must raise Failed."""
        cfg = _make_config(True)
        with pytest.raises(Failed, match="nohardlinks must be a dict"):
            cfg.process_config_nohardlinks()

    def test_nohardlinks_as_dict_is_valid(self):
        """nohardlinks: {cat1: {}} (dict) must not raise."""
        cfg = _make_config({"cat1": {}})
        cfg.process_config_nohardlinks()
        assert "cat1" in cfg.nohardlinks

    def test_nohardlinks_as_list_is_valid(self):
        """nohardlinks: [cat1] (list of strings) must not raise."""
        cfg = _make_config(["movies-completed"])
        cfg.process_config_nohardlinks()
        assert "movies-completed" in cfg.nohardlinks


# ---------------------------------------------------------------------------
# Bug 2 — global_options.exclude_tags type validation
# ---------------------------------------------------------------------------


class TestGlobalExcludeTagsTypeValidation:
    def test_global_exclude_tags_as_string_raises_failed(self):
        """global_options: {exclude_tags: 'tag1'} (string) must raise Failed."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": "tag1"},
                "cat1": {},
            }
        )
        with pytest.raises(Failed, match="exclude_tags must be a list"):
            cfg.process_config_nohardlinks()

    def test_global_exclude_tags_as_int_raises_failed(self):
        """global_options: {exclude_tags: 99} (int) must raise Failed."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": 99},
                "cat1": {},
            }
        )
        with pytest.raises(Failed, match="exclude_tags must be a list"):
            cfg.process_config_nohardlinks()

    def test_global_exclude_tags_as_list_is_valid(self):
        """global_options: {exclude_tags: ['tag1']} (list) must not raise."""
        cfg = _make_config(
            {
                "global_options": {"exclude_tags": ["tag1"]},
                "cat1": {},
            }
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["cat1"]["exclude_tags"] == ["tag1"]


# ---------------------------------------------------------------------------
# Bug 3 — legacy list-form inherits global_options
# ---------------------------------------------------------------------------


class TestLegacyListInheritsGlobalOptions:
    def test_list_of_strings_inherits_global_exclude_tags(self):
        """Legacy list-of-strings entries must inherit global_options exclude_tags."""
        cfg = _make_config(
            [
                {"global_options": {"exclude_tags": ["tracker1.example", "tracker2.example"]}},
                "movies-completed",
                "series-completed",
            ]
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["movies-completed"]["exclude_tags"] == ["tracker1.example", "tracker2.example"]
        assert cfg.nohardlinks["series-completed"]["exclude_tags"] == ["tracker1.example", "tracker2.example"]
        # global_options itself must NOT become a category key
        assert "global_options" not in cfg.nohardlinks

    def test_list_of_strings_inherits_global_ignore_root_dir(self):
        """Legacy list-of-strings entries must inherit global_options ignore_root_dir."""
        cfg = _make_config(
            [
                {"global_options": {"ignore_root_dir": False}},
                "tv-series",
            ]
        )
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["tv-series"]["ignore_root_dir"] is False

    def test_list_of_strings_no_global_options_uses_defaults(self):
        """Legacy list-of-strings without global_options gets default values."""
        cfg = _make_config(["movies-completed"])
        cfg.process_config_nohardlinks()
        assert cfg.nohardlinks["movies-completed"]["exclude_tags"] == []
        assert cfg.nohardlinks["movies-completed"]["ignore_root_dir"] is True

    def test_list_of_dicts_inherits_global_exclude_tags(self):
        """Legacy list-of-dicts entries must inherit global_options exclude_tags."""
        cfg = _make_config(
            [
                {"global_options": {"exclude_tags": ["global-tag"]}},
                {"Tv.Series": {"exclude_tags": ["local-tag"]}},
            ]
        )
        cfg.process_config_nohardlinks()
        result = cfg.nohardlinks["Tv.Series"]["exclude_tags"]
        # global-tag comes first, local-tag appended
        assert result == ["global-tag", "local-tag"], f"Expected ['global-tag', 'local-tag'], got {result}"
        assert "global_options" not in cfg.nohardlinks

    def test_list_of_dicts_inherits_global_ignore_root_dir(self):
        """Legacy list-of-dicts entries inherit global ignore_root_dir unless overridden."""
        cfg = _make_config(
            [
                {"global_options": {"ignore_root_dir": False}},
                {"Tv.Series": {}},
                {"Movies": {"ignore_root_dir": True}},
            ]
        )
        cfg.process_config_nohardlinks()
        # Tv.Series has no override → inherits global False
        assert cfg.nohardlinks["Tv.Series"]["ignore_root_dir"] is False
        # Movies explicitly sets True → overrides global False
        assert cfg.nohardlinks["Movies"]["ignore_root_dir"] is True
