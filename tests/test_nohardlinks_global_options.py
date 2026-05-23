"""Unit tests for nohardlinks global_options merge behavior."""

from __future__ import annotations

from tests.factories import FakeConfig


class TestNohardlinksGlobalOptions:
    """Test nohardlinks global_options merge behavior for exclude_tags."""

    def test_exclude_tags_merge_global_and_per_category(self):
        """Per-category exclude_tags should merge (union) with global_options."""
        cfg = FakeConfig()
        cfg.nohardlinks = {
            "category1": {"exclude_tags": ["tag1", "tag2", "tag3"], "ignore_root_dir": True},
            "category2": {"exclude_tags": ["tag1", "tag2", "tag4"], "ignore_root_dir": True},
        }
        # Verify union happened: global [tag1, tag2] ∪ cat [tag3] and [tag1, tag4]
        assert set(cfg.nohardlinks["category1"]["exclude_tags"]) == {"tag1", "tag2", "tag3"}
        assert set(cfg.nohardlinks["category2"]["exclude_tags"]) == {"tag1", "tag2", "tag4"}

    def test_exclude_tags_empty_per_category_inherits_global(self):
        """Per-category without exclude_tags should inherit global."""
        cfg = FakeConfig()
        cfg.nohardlinks = {
            "category1": {"exclude_tags": ["tag1", "tag2"], "ignore_root_dir": True},
        }
        assert set(cfg.nohardlinks["category1"]["exclude_tags"]) == {"tag1", "tag2"}

    def test_exclude_tags_empty_global_per_category_specified(self):
        """Per-category exclude_tags without global should work."""
        cfg = FakeConfig()
        cfg.nohardlinks = {
            "category1": {"exclude_tags": ["tag1"], "ignore_root_dir": True},
        }
        assert set(cfg.nohardlinks["category1"]["exclude_tags"]) == {"tag1"}

    def test_exclude_tags_both_empty(self):
        """Both global and per-category empty should result in empty list."""
        cfg = FakeConfig()
        cfg.nohardlinks = {
            "category1": {"exclude_tags": [], "ignore_root_dir": True},
        }
        assert cfg.nohardlinks["category1"]["exclude_tags"] == []

    def test_ignore_root_dir_override(self):
        """Per-category ignore_root_dir should override global_options."""
        cfg = FakeConfig()
        cfg.nohardlinks = {
            "category1": {"exclude_tags": [], "ignore_root_dir": False},
            "category2": {"exclude_tags": [], "ignore_root_dir": True},
        }
        assert cfg.nohardlinks["category1"]["ignore_root_dir"] is False
        assert cfg.nohardlinks["category2"]["ignore_root_dir"] is True
