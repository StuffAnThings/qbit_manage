"""Tests for share_limit_action configuration and validation.

Covers:
- Default value when share_limit_action is not set
- Valid action values (Default, Stop, Remove, RemoveWithContent, EnableSuperSeeding)
- Invalid action raises Failed (via the production validator from config.py)
- Mutual exclusion: cleanup=true + destructive share_limit_action raises Failed
- share_limit_action is passed through to torrent.set_share_limits()

Validation tests import the same ``validate_share_limit_action`` function
Config.__init__ calls, so any drift in the production validation rules will
surface immediately in these tests rather than passing against a stale local
mirror.
"""

from __future__ import annotations

import pytest

from modules.config import SHARE_LIMIT_ACTIONS
from modules.config import validate_share_limit_action
from modules.util import Failed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calls_of(torrent, name):
    """Extract all calls to a specific method from torrent.calls."""
    return [c for c in torrent.calls if c[0] == name]


# ---------------------------------------------------------------------------
# Tests: default / missing
# ---------------------------------------------------------------------------


class TestShareLimitActionDefaults:
    """Tests for default and missing share_limit_action values."""

    def test_default_value_when_not_specified(self, group_config_factory):
        """When share_limit_action is not specified, defaults to 'Default'."""
        config = group_config_factory()
        assert config["share_limit_action"] == "Default"

    def test_validator_returns_default_for_empty_value(self):
        """Production validator resolves missing/falsy action to 'Default' without raising."""
        result = validate_share_limit_action(None, cleanup=False, group="test_group")
        assert result == "Default"


# ---------------------------------------------------------------------------
# Tests: valid action values — validator must NOT raise
# ---------------------------------------------------------------------------


class TestShareLimitActionValidation:
    """Tests that valid action values pass production validation and that invalid ones raise Failed."""

    @pytest.mark.parametrize("action", list(SHARE_LIMIT_ACTIONS.keys()))
    def test_valid_action_passes_validator(self, action):
        """All values in SHARE_LIMIT_ACTIONS are accepted by the production validator.

        cleanup=False so the cleanup-combo branch in the merged validator never fires,
        regardless of which action we're checking — keeps this parametrize focused on
        the enum-membership check."""
        result = validate_share_limit_action(action, cleanup=False, group="test_group")
        assert result == action

    def test_invalid_action_raises_failed(self):
        """An unrecognised share_limit_action raises Failed — mirroring the validator in Config's share-limits processing."""
        with pytest.raises(Failed, match="invalid share_limit_action"):
            validate_share_limit_action("DeleteEverything", cleanup=False, group="test_group")

    def test_invalid_action_error_message_contains_value(self):
        """The Failed message includes the bad value so operators know what to fix."""
        with pytest.raises(Failed, match="BogusAction"):
            validate_share_limit_action("BogusAction", cleanup=False, group="test_group")

    def test_invalid_action_error_message_lists_valid_options(self):
        """The Failed message lists the valid options so operators know what to use."""
        with pytest.raises(Failed) as exc_info:
            validate_share_limit_action("BogusAction", cleanup=False, group="test_group")
        err = str(exc_info.value)
        for valid in SHARE_LIMIT_ACTIONS:
            assert valid in err


# ---------------------------------------------------------------------------
# Tests: cleanup + destructive action mutual exclusion
# ---------------------------------------------------------------------------


class TestCleanupMutualExclusion:
    """Tests for cleanup=true + destructive share_limit_action validation."""

    @pytest.mark.parametrize("action", ["Remove", "RemoveWithContent"])
    def test_cleanup_true_with_destructive_action_raises_failed(self, action):
        """cleanup=true + Remove/RemoveWithContent raises Failed via the merged
        validate_share_limit_action validator in Config's share-limits processing."""
        with pytest.raises(Failed, match="mutually exclusive"):
            validate_share_limit_action(action, cleanup=True, group="test_group")

    @pytest.mark.parametrize("action", ["Default", "Stop", "EnableSuperSeeding"])
    def test_cleanup_true_with_safe_action_does_not_raise(self, action):
        """cleanup=true with a non-destructive action is allowed — returns the resolved action."""
        result = validate_share_limit_action(action, cleanup=True, group="test_group")
        assert result == action

    @pytest.mark.parametrize("action", ["Remove", "RemoveWithContent"])
    def test_cleanup_false_with_destructive_action_does_not_raise(self, action):
        """cleanup=false with any action is allowed — the exclusion only fires when cleanup=True."""
        result = validate_share_limit_action(action, cleanup=False, group="test_group")
        assert result == action

    def test_cleanup_with_default_action_allowed(self, group_config_factory):
        """cleanup=true with share_limit_action='Default' is allowed (Default is safe)."""
        config = group_config_factory(cleanup=True, share_limit_action="Default")
        assert config["cleanup"] is True
        assert config["share_limit_action"] == "Default"

    def test_cleanup_with_stop_action_allowed(self, group_config_factory):
        """cleanup=true with share_limit_action='Stop' is allowed (Stop is safe)."""
        config = group_config_factory(cleanup=True, share_limit_action="Stop")
        assert config["cleanup"] is True
        assert config["share_limit_action"] == "Stop"

    def test_cleanup_without_share_limit_action_allowed(self):
        """cleanup=true with share_limit_action unset (None from YAML) resolves
        to 'Default' and does not raise the mutual-exclusion check.

        Exercises the missing-value path directly through the production
        validator instead of relying on the factory's defaulted dict (which
        always includes 'Default' explicitly and would test the wrong thing)."""
        result = validate_share_limit_action(None, cleanup=True, group="test_group")
        assert result == "Default"

    def test_cleanup_false_with_any_action_allowed(self, group_config_factory):
        """cleanup=false with any share_limit_action is allowed."""
        for action in ["Default", "Stop", "Remove", "RemoveWithContent", "EnableSuperSeeding"]:
            config = group_config_factory(cleanup=False, share_limit_action=action)
            assert config["cleanup"] is False
            assert config["share_limit_action"] == action


# ---------------------------------------------------------------------------
# Tests: passthrough to torrent.set_share_limits()
# ---------------------------------------------------------------------------


class TestShareLimitActionPassthrough:
    """Tests that share_limit_action is passed through to torrent.set_share_limits()."""

    @pytest.mark.parametrize("action", ["Stop", "Remove", "RemoveWithContent", "EnableSuperSeeding", "Default"])
    def test_set_limits_passes_share_limit_action_to_torrent(self, share_limits_factory, torrent_factory, action):
        """set_limits() passes each valid share_limit_action to torrent.set_share_limits()."""
        sl = share_limits_factory()
        t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)

        sl.set_limits(t, max_ratio=2.0, max_seeding_time=3600, share_limit_action=action)

        set_share_limits_calls = _calls_of(t, "set_share_limits")
        assert len(set_share_limits_calls) == 1
        call_kwargs = set_share_limits_calls[0][1]
        assert call_kwargs["share_limit_action"] == action
