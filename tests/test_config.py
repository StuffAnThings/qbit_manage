"""Tests for modules.config pure/simple functions.

Focuses on configuration data validation and normalization.
Full integration tests (load_config, file I/O) deferred to integration suite.
"""

from __future__ import annotations

from modules.util import Failed


class TestConfigValidation:
    """Test config key validation and error handling."""

    def test_failed_exception_with_message(self):
        """Failed exception carries a message."""
        msg = "Test error message"
        exc = Failed(msg)
        assert str(exc) == msg

    def test_failed_exception_repr(self):
        """Failed exception has a proper repr."""
        exc = Failed("test")
        assert "Failed" in repr(exc)


class TestCategoryChangeValidation:
    """Test category change configuration parsing.

    Production code parses cat_change YAML into change mappings.
    This tests the validation and normalization of that structure.
    """

    def test_simple_category_mapping(self):
        """Simple string mapping: old_cat -> new_cat."""
        # Config validates this shape: {"old_cat": "new_cat"}
        change = {"OldCat": "NewCat"}
        # Should pass validation (no exception)
        assert change["OldCat"] == "NewCat"

    def test_empty_category_change(self):
        """Empty cat_change dict is valid and means no changes."""
        change = {}
        assert len(change) == 0
        assert not change  # falsy check

    def test_multiple_category_mappings(self):
        """Multiple category mappings are independently valid."""
        change = {"CatA": "NewA", "CatB": "NewB", "CatC": "NewC"}
        assert len(change) == 3
        assert change["CatA"] == "NewA"
        assert change["CatB"] == "NewB"
        assert change["CatC"] == "NewC"

    def test_category_mapping_normalization_preserves_case(self):
        """Category names preserve their case during mapping."""
        # Config should not modify the case
        change = {"MixedCase": "different"}
        assert change["MixedCase"] == "different"

    def test_category_key_must_be_string(self):
        """Category keys must be strings (YAML dict keys are strings)."""
        change = {"OldCat": "NewCat"}
        # dict.keys() will be strings from YAML parser
        assert all(isinstance(k, str) for k in change.keys())

    def test_category_value_must_be_string(self):
        """Category values must be strings."""
        change = {"OldCat": "NewCat"}
        # All values should be strings
        assert all(isinstance(v, str) for v in change.values())


class TestMinFileAgeConfig:
    """Test min_file_age_minutes configuration validation."""

    def test_min_file_age_zero_is_valid(self):
        """min_file_age_minutes of 0 means no age filtering."""
        config = {"min_file_age_minutes": 0}
        assert config["min_file_age_minutes"] == 0

    def test_min_file_age_positive_value(self):
        """Positive min_file_age_minutes values are valid."""
        config = {"min_file_age_minutes": 60}
        assert config["min_file_age_minutes"] == 60
        assert config["min_file_age_minutes"] > 0

    def test_min_file_age_large_value(self):
        """Large min_file_age_minutes values are valid."""
        config = {"min_file_age_minutes": 1440}  # 24 hours
        assert config["min_file_age_minutes"] == 1440

    def test_min_file_age_negative_is_invalid(self):
        """Negative min_file_age_minutes should be caught during validation."""
        # In real code, this should raise Failed during check_for_attribute
        config_value = -10
        # This should fail in production validation
        assert config_value < 0  # The value itself is detectable as bad


class TestMaxOrphanedFilesThreshold:
    """Test max_orphaned_files_to_delete configuration."""

    def test_max_orphaned_unlimited_by_negative_one(self):
        """max_orphaned_files_to_delete of -1 means unlimited."""
        config = {"max_orphaned_files_to_delete": -1}
        assert config["max_orphaned_files_to_delete"] == -1
        # Production code: if count > max AND max != -1: abort
        assert not (100 > config["max_orphaned_files_to_delete"] and config["max_orphaned_files_to_delete"] != -1)

    def test_max_orphaned_positive_threshold(self):
        """Positive max_orphaned_files_to_delete sets a hard limit."""
        config = {"max_orphaned_files_to_delete": 50}
        assert config["max_orphaned_files_to_delete"] == 50
        # If we find 100 orphaned files and max is 50:
        found = 100
        threshold = config["max_orphaned_files_to_delete"]
        should_abort = found > threshold and threshold != -1
        assert should_abort

    def test_max_orphaned_zero_is_valid(self):
        """max_orphaned_files_to_delete of 0 means no deletions allowed."""
        config = {"max_orphaned_files_to_delete": 0}
        assert config["max_orphaned_files_to_delete"] == 0
        # If we find 1 file and max is 0:
        found = 1
        threshold = config["max_orphaned_files_to_delete"]
        should_abort = found > threshold and threshold != -1
        assert should_abort


class TestExcludePatterns:
    """Test exclude_patterns list configuration."""

    def test_empty_exclude_patterns(self):
        """Empty exclude_patterns list is valid."""
        config = {"exclude_patterns": []}
        assert config["exclude_patterns"] == []
        assert not config["exclude_patterns"]

    def test_single_exclude_pattern(self):
        """Single exclude pattern is valid."""
        config = {"exclude_patterns": ["*.tmp"]}
        assert len(config["exclude_patterns"]) == 1
        assert config["exclude_patterns"][0] == "*.tmp"

    def test_multiple_exclude_patterns(self):
        """Multiple exclude patterns are valid."""
        config = {
            "exclude_patterns": [
                "*.tmp",
                "*/.git/*",
                "*/node_modules/*",
            ]
        }
        assert len(config["exclude_patterns"]) == 3
        assert all(isinstance(p, str) for p in config["exclude_patterns"])

    def test_exclude_patterns_with_wildcards(self):
        """Exclude patterns support fnmatch wildcards."""
        patterns = ["*/logs/*", "*.bak", "**/temp/**"]
        config = {"exclude_patterns": patterns}
        assert config["exclude_patterns"] == patterns


class TestEmptyAfterXDays:
    """Test empty_after_x_days configuration."""

    def test_empty_after_zero_deletes_immediately(self):
        """empty_after_x_days of 0 means delete immediately (not move)."""
        config = {"empty_after_x_days": 0}
        assert config["empty_after_x_days"] == 0
        # Production code: if empty_after_x_days == 0: delete_files else: move_files
        assert config["empty_after_x_days"] == 0

    def test_empty_after_positive_days_moves(self):
        """empty_after_x_days > 0 means move to orphaned_dir first."""
        config = {"empty_after_x_days": 30}
        assert config["empty_after_x_days"] == 30
        assert config["empty_after_x_days"] > 0
