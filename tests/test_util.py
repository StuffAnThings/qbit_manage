"""Tests for pure-function helpers in modules/util.py.

No conftest dependency needed — these functions are stateless and have no I/O.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.util import format_stats_summary
from modules.util import get_list
from modules.util import guess_branch
from modules.util import is_tag_in_torrent
from modules.util import list_in_text
from modules.util import parse_version
from modules.util import trunc_val

# ── get_list ─────────────────────────────────────────────────────────────────


class TestGetList:
    def test_none_returns_none(self):
        assert get_list(None) is None

    def test_list_passthrough(self):
        assert get_list(["a", "b"]) == ["a", "b"]

    def test_list_lower(self):
        assert get_list(["Foo", " BAR "], lower=True) == ["foo", "bar"]

    def test_list_upper(self):
        assert get_list(["foo", " bar "], upper=True) == ["FOO", "BAR"]

    def test_dict_wraps_in_list(self):
        d = {"key": "val"}
        assert get_list(d) == [d]

    def test_string_split_on_comma(self):
        assert get_list("a,b,c") == ["a", "b", "c"]

    def test_string_split_strips_whitespace(self):
        assert get_list("a , b , c") == ["a", "b", "c"]

    def test_string_lower(self):
        assert get_list("Foo,BAR", lower=True) == ["foo", "bar"]

    def test_string_upper(self):
        assert get_list("foo,bar", upper=True) == ["FOO", "BAR"]

    def test_string_no_split(self):
        # split=False → returns the entire string as a single-element list
        assert get_list("a,b,c", split=False) == ["a,b,c"]

    def test_int_list_valid(self):
        assert get_list("1,2,3", int_list=True) == [1, 2, 3]

    def test_int_list_invalid_returns_empty(self):
        assert get_list("a,b,c", int_list=True) == []

    def test_empty_string_split(self):
        # "".split(",") → [""], so result is [""]
        assert get_list("") == [""]

    def test_integer_input_converted_to_string(self):
        # Integers are converted via str() before splitting
        assert get_list(42) == ["42"]


# ── is_tag_in_torrent ─────────────────────────────────────────────────────────


class TestIsTagInTorrent:
    def test_exact_match_string_found(self):
        assert is_tag_in_torrent("foo", "foo, bar") is True

    def test_exact_match_string_not_found(self):
        assert is_tag_in_torrent("baz", "foo, bar") is False

    def test_exact_match_list_input_all_present(self):
        assert is_tag_in_torrent(["foo", "bar"], "foo, bar, baz") is True

    def test_exact_match_list_input_one_missing(self):
        assert is_tag_in_torrent(["foo", "missing"], "foo, bar") is False

    def test_substring_match_string_found(self):
        # "foo" is a substring of "foobar"
        result = is_tag_in_torrent("foo", "foobar, baz", exact=False)
        assert "foobar" in result

    def test_substring_match_string_not_found(self):
        result = is_tag_in_torrent("xyz", "foo, bar", exact=False)
        assert result == []

    def test_substring_match_list_found(self):
        result = is_tag_in_torrent(["foo", "ba"], "foobar, baz", exact=False)
        # "foobar" matches "foo"; "baz" matches "ba"
        assert "foobar" in result
        assert "baz" in result

    def test_empty_string_tag_exact(self):
        # empty string is in the split list → True
        assert is_tag_in_torrent("", "") is True

    def test_exact_match_with_list_tags_exact_false(self):
        # substring match is case-sensitive; "Min" is in "MinSeedTimeNotReached"
        result = is_tag_in_torrent(["Min"], "MinSeedTimeNotReached", exact=False)
        assert "MinSeedTimeNotReached" in result


# ── list_in_text ──────────────────────────────────────────────────────────────


class TestListInText:
    def test_single_word_found_any(self):
        assert list_in_text("hello world", {"hello"}) is True

    def test_single_word_not_found_any(self):
        assert list_in_text("hello world", {"missing"}) is False

    def test_phrase_with_space_found(self):
        # Words with spaces use `in` (substring) not word-equality
        assert list_in_text("hello world", {"hello world"}) is True

    def test_phrase_not_found(self):
        assert list_in_text("hello world", {"foo bar"}) is False

    def test_match_all_all_present(self):
        assert list_in_text("hello world", {"hello", "world"}, match_all=True) is True

    def test_match_all_phrase_both_present(self):
        # Both phrases present in text
        assert list_in_text("hello world foo bar", {"hello world", "foo bar"}, match_all=True) is True

    def test_match_all_empty_search_set(self):
        # Empty set — all() of empty iterable is vacuously True, short-circuits to True
        assert list_in_text("hello world", set(), match_all=True) is True

    def test_match_all_missing_word(self):
        # 'foo' does not contain 'hello' or 'world' — must return False (regression for vacuous-truth bug)
        assert list_in_text("foo", {"hello", "world"}, match_all=True) is False

    def test_match_all_partial_words_missing(self):
        # Only one of the required words is present — must return False
        assert list_in_text("hello foo", {"hello", "world"}, match_all=True) is False

    def test_list_input_converted(self):
        # accepts list too
        assert list_in_text("hello world", ["hello"]) is True

    def test_empty_search_list_returns_false(self):
        # empty set — no element found
        assert list_in_text("hello world", set()) is False


# ── trunc_val ─────────────────────────────────────────────────────────────────


class TestTruncVal:
    def test_default_num_3(self):
        url = "http://tracker.example.com/announce/SECRET"
        result = trunc_val(url, "/")
        # joins first 3 parts: "http:" + "" + "tracker.example.com"
        assert result == "http://tracker.example.com"

    def test_num_2(self):
        result = trunc_val("a/b/c/d", "/", num=2)
        assert result == "a/b"

    def test_num_1(self):
        result = trunc_val("a/b/c", "/", num=1)
        assert result == "a"

    def test_delimiter_not_in_string(self):
        # No "/" → split returns ["hello"], [:3] is still ["hello"]
        result = trunc_val("hello", "/")
        assert result == "hello"

    def test_empty_string(self):
        result = trunc_val("", "/")
        assert result == ""

    def test_custom_delimiter(self):
        result = trunc_val("a:b:c:d", ":", num=2)
        assert result == "a:b"


# ── parse_version ─────────────────────────────────────────────────────────────


class TestParseVersion:
    def test_master_version_no_build(self):
        full, base, build = parse_version("4.1.2")
        assert full == "4.1.2"
        assert base == "4.1.2"
        assert build == 0

    def test_develop_version_with_build(self):
        full, base, build = parse_version("4.1.2-develop10", text="develop")
        assert full == "4.1.2-develop10"
        assert base == "4.1.2"
        assert build == 10

    def test_text_substitution(self):
        # the text param replaces the literal "develop" in the version string
        full, base, build = parse_version("4.0.0-develop5", text="develop")
        assert build == 5

    def test_zero_build_number(self):
        full, base, build = parse_version("4.1.0-develop0", text="develop")
        assert build == 0

    def test_custom_text_label(self):
        full, base, build = parse_version("1.2.3-beta7", text="beta")
        assert base == "1.2.3"
        assert build == 7


# ── guess_branch ──────────────────────────────────────────────────────────────


class TestGuessBranch:
    def test_git_branch_takes_priority(self):
        # If git_branch is set, always return it regardless of other args
        assert guess_branch(("1.0.0", "1.0.0", 0), "develop", "my-branch") == "my-branch"

    def test_env_version_develop_returns_develop(self):
        # No git_branch, env_version is "develop"
        result = guess_branch(("1.0.0", "1.0.0", 0), "develop", None)
        assert result == "develop"

    def test_master_branch_when_build_zero(self):
        # No git_branch, not develop, build=0 → "master"
        result = guess_branch(("1.0.0", "1.0.0", 0), "master", None)
        assert result == "master"


# ── format_stats_summary ──────────────────────────────────────────────────────


class TestFormatStatsSummary:
    """format_stats_summary needs a tiny fake config with tracker_error_tag / nohardlinks_tag."""

    class _FakeCfg:
        tracker_error_tag = "TrackerError"
        nohardlinks_tag = "NoHL"

    cfg = _FakeCfg()

    def test_empty_stats_returns_empty_list(self):
        assert format_stats_summary({}, self.cfg) == []

    def test_zero_values_omitted(self):
        stats = {"tagged": 0, "deleted": 0}
        assert format_stats_summary(stats, self.cfg) == []

    def test_tagged_shows_in_output(self):
        lines = format_stats_summary({"tagged": 3}, self.cfg)
        assert len(lines) == 1
        assert "3" in lines[0]

    def test_tagged_tracker_error_uses_config_tag(self):
        lines = format_stats_summary({"tagged_tracker_error": 2}, self.cfg)
        assert any("TrackerError" in line for line in lines)

    def test_untagged_tracker_error_uses_config_tag(self):
        lines = format_stats_summary({"untagged_tracker_error": 1}, self.cfg)
        assert any("TrackerError" in line for line in lines)

    def test_tagged_nohl_uses_config_tag(self):
        lines = format_stats_summary({"tagged_noHL": 5}, self.cfg)
        assert any("NoHL" in line for line in lines)

    def test_untagged_nohl_uses_config_tag(self):
        lines = format_stats_summary({"untagged_noHL": 1}, self.cfg)
        assert any("NoHL" in line for line in lines)

    def test_rem_unreg_display_key(self):
        lines = format_stats_summary({"rem_unreg": 2}, self.cfg)
        assert any("Unregistered Torrents Removed" in line for line in lines)

    def test_deleted_contents_display_key(self):
        lines = format_stats_summary({"deleted_contents": 1}, self.cfg)
        assert any("Contents Deleted" in line for line in lines)

    def test_executed_commands_listed(self):
        lines = format_stats_summary({"executed_commands": ["share_limits", "category"]}, self.cfg)
        assert any("Executed Commands" in line for line in lines)
        assert any("share_limits" in line for line in lines)

    def test_executed_commands_empty_not_shown(self):
        lines = format_stats_summary({"executed_commands": []}, self.cfg)
        assert lines == []

    def test_multiple_stats_all_output(self):
        stats = {"tagged": 1, "deleted": 2, "categorized": 3}
        lines = format_stats_summary(stats, self.cfg)
        assert len(lines) == 3

    def test_config_without_tracker_error_tag_attr(self):
        """Config without tracker_error_tag falls back to generic title-cased key."""

        class _MinimalCfg:
            pass

        lines = format_stats_summary({"tagged_tracker_error": 1}, _MinimalCfg())
        assert len(lines) == 1
        # Shouldn't crash; falls back to title-cased key
        assert "1" in lines[0]

    def test_updated_share_limits_display_key(self):
        lines = format_stats_summary({"updated_share_limits": 4}, self.cfg)
        assert any("Share Limits Updated" in line for line in lines)

    def test_float_stat_shown(self):
        lines = format_stats_summary({"ratio": 1.5}, self.cfg)
        assert len(lines) == 1
