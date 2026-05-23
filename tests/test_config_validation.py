"""Unit tests for validate_config_keys() — Gap coverage per Copilot review.

Tests exercise the four gaps closed in feat/589-warn-unrecognized-config:
  Gap 1  — early invocation (structural; tested indirectly via validate_config_keys API)
  Gap 2  — webhooks.function sub-key validation
  Gap 3  — nohardlinks list shape (legacy form)
  Gap 4  — apprise / notifiarr / commands / qbt sub-key validation
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.util import Failed  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal Config stub — only the surface that validate_config_keys() needs
# ---------------------------------------------------------------------------


def _make_stub(data: dict) -> object:
    """Return a minimal Config-like object that can run validate_config_keys()."""

    class StubConfig:
        pass

    from modules import config as config_mod

    stub = StubConfig()
    stub.data = data
    stub.notify = MagicMock()  # silence actual webhook calls
    # Bind validate_config_keys as a bound method on stub
    stub.validate_config_keys = config_mod.Config.validate_config_keys.__get__(stub, StubConfig)
    return stub


def _valid_base() -> dict:
    """Minimal config data that passes validate_config_keys cleanly."""
    return {
        "qbt": {"host": "http://localhost:8080", "user": "admin", "pass": "secret"},
        "settings": {},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raises_failed(data: dict) -> Failed:
    stub = _make_stub(data)
    with pytest.raises(Failed) as exc_info:
        stub.validate_config_keys()
    return exc_info.value


def _passes(data: dict) -> None:
    stub = _make_stub(data)
    stub.validate_config_keys()  # must not raise


# ===========================================================================
# Gap 2 — webhooks.function sub-key validation
# ===========================================================================


class TestWebhooksFunctionKeys:
    def test_unknown_function_key_raises(self):
        data = _valid_base()
        data["webhooks"] = {
            "function": {"not_a_real_command": "http://example.com"},
        }
        err = _raises_failed(data)
        assert "not_a_real_command" in str(err)

    def test_all_known_function_keys_pass(self):
        data = _valid_base()
        data["webhooks"] = {
            "function": {
                "recheck": None,
                "cat_update": None,
                "tag_update": None,
                "rem_unregistered": None,
                "tag_tracker_error": None,
                "rem_orphaned": None,
                "tag_nohardlinks": None,
                "share_limits": None,
                "cleanup_dirs": None,
            },
        }
        _passes(data)

    def test_webhooks_top_level_unknown_key_raises(self):
        data = _valid_base()
        data["webhooks"] = {"bogus_top_key": "http://x.com"}
        err = _raises_failed(data)
        assert "bogus_top_key" in str(err)

    def test_webhooks_function_none_does_not_raise(self):
        data = _valid_base()
        data["webhooks"] = {"error": None, "run_start": None, "run_end": None, "function": None}
        _passes(data)

    def test_webhooks_absent_does_not_raise(self):
        _passes(_valid_base())


# ===========================================================================
# Gap 3 — nohardlinks list shape (legacy form)
# ===========================================================================


class TestNohardlinksListShape:
    def test_list_of_strings_passes(self):
        data = _valid_base()
        data["nohardlinks"] = ["movies", "tv"]
        _passes(data)

    def test_list_of_dicts_with_valid_keys_passes(self):
        data = _valid_base()
        data["nohardlinks"] = [{"movies": {"exclude_tags": ["noHL"], "ignore_root_dir": True}}]
        _passes(data)

    def test_list_of_dicts_with_unknown_key_raises(self):
        data = _valid_base()
        data["nohardlinks"] = [{"movies": {"unknown_key": True}}]
        err = _raises_failed(data)
        assert "unknown_key" in str(err)

    def test_dict_shape_still_works(self):
        data = _valid_base()
        data["nohardlinks"] = {"movies": {"exclude_tags": [], "ignore_root_dir": True}}
        _passes(data)

    def test_dict_shape_unknown_key_raises(self):
        data = _valid_base()
        data["nohardlinks"] = {"movies": {"not_valid": True}}
        err = _raises_failed(data)
        assert "not_valid" in str(err)


# ===========================================================================
# Gap 4a — apprise sub-key validation
# ===========================================================================


class TestAppriseKeys:
    def test_unknown_apprise_key_raises(self):
        data = _valid_base()
        data["apprise"] = {"api_url": "http://apprise", "notify_url": ["x"], "typo_key": "oops"}
        err = _raises_failed(data)
        assert "typo_key" in str(err)

    def test_known_apprise_keys_pass(self):
        data = _valid_base()
        data["apprise"] = {"api_url": "http://apprise", "notify_url": ["schema://x"]}
        _passes(data)

    def test_apprise_absent_does_not_raise(self):
        _passes(_valid_base())


# ===========================================================================
# Gap 4b — notifiarr sub-key validation
# ===========================================================================


class TestNotifiarrKeys:
    def test_unknown_notifiarr_key_raises(self):
        data = _valid_base()
        data["notifiarr"] = {"apikey": "abc123", "bad_key": "nope"}
        err = _raises_failed(data)
        assert "bad_key" in str(err)

    def test_known_notifiarr_keys_pass(self):
        data = _valid_base()
        data["notifiarr"] = {"apikey": "abc123", "instance": "myinstance"}
        _passes(data)

    def test_notifiarr_absent_does_not_raise(self):
        _passes(_valid_base())


# ===========================================================================
# Gap 4c — qbt sub-key validation
# ===========================================================================


class TestQbtKeys:
    def test_unknown_qbt_key_raises(self):
        data = _valid_base()
        data["qbt"]["extra_key"] = "whoops"
        err = _raises_failed(data)
        assert "extra_key" in str(err)

    def test_known_qbt_keys_pass(self):
        _passes(_valid_base())

    def test_qbt_absent_does_not_raise(self):
        data = {"settings": {}}
        _passes(data)


# ===========================================================================
# Gap 4d — commands sub-key validation
# ===========================================================================


class TestCommandsKeys:
    def test_unknown_commands_key_raises(self):
        data = _valid_base()
        data["commands"] = {"recheck": True, "ghost_command": True}
        err = _raises_failed(data)
        assert "ghost_command" in str(err)

    def test_all_known_commands_pass(self):
        data = _valid_base()
        data["commands"] = {
            "recheck": True,
            "cat_update": False,
            "tag_update": True,
            "rem_unregistered": False,
            "tag_tracker_error": True,
            "rem_orphaned": False,
            "tag_nohardlinks": True,
            "share_limits": False,
            "skip_cleanup": False,
            "skip_qb_version_check": False,
            "dry_run": False,
        }
        _passes(data)

    def test_commands_absent_does_not_raise(self):
        _passes(_valid_base())


# ===========================================================================
# Comprehensive happy-path — all known sections, all known keys
# ===========================================================================


class TestFullValidConfig:
    def test_complete_known_config_passes(self):
        data = {
            "qbt": {"host": "http://localhost:8080", "user": "admin", "pass": "secret"},
            "settings": {
                "force_auto_tmm": False,
                "tracker_error_tag": "issue",
                "nohardlinks_tag": "noHL",
                "stalled_tag": "stalledDL",
                "share_limits_tag": "~share_limit",
            },
            "directory": {"root_dir": "/data", "remote_dir": "/remote", "recycle_bin": "/recycle"},
            "apprise": {"api_url": "http://apprise", "notify_url": ["schema://x"]},
            "notifiarr": {"apikey": "k", "instance": "i"},
            "commands": {"recheck": True, "dry_run": False},
            "webhooks": {
                "error": None,
                "run_start": None,
                "run_end": None,
                "function": {
                    "recheck": None,
                    "cat_update": None,
                    "cleanup_dirs": None,
                },
            },
            "nohardlinks": ["movies", "tv"],
            "recyclebin": {"enabled": True, "empty_after_x_days": 7},
            "orphaned": {"empty_after_x_days": 14, "exclude_patterns": []},
            "share_limits": {
                "group1": {
                    "priority": 1,
                    "max_ratio": 2.0,
                    "cleanup": True,
                }
            },
        }
        _passes(data)
