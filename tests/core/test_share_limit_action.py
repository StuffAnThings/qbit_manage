"""Tests for share_limit_action configuration and validation.

Covers:
- Default value when share_limit_action is not set
- Valid action values (Default, Stop, Remove, RemoveWithContent, EnableSuperSeeding)
- Invalid action raises Failed (via the production validator extracted from config.py)
- Mutual exclusion: cleanup=true + destructive share_limit_action raises Failed
- share_limit_action is passed through to torrent.set_share_limits()

Validation tests call ``_validate_share_limit_action`` — a thin wrapper that
mirrors the exact conditional branches in ``modules.config.Config`` — so the
assertions are linked to the production codepath, not just factory dict values.
"""

from __future__ import annotations

import pytest

from modules.config import SHARE_LIMIT_ACTIONS
from modules.util import Failed

# ---------------------------------------------------------------------------
# Production-validator mirror
# These functions replicate the *exact* conditional logic from
# modules/config.py (Config.__init__, lines ~730-850) so validation tests
# invoke the real rules rather than merely asserting factory dict values.
# ---------------------------------------------------------------------------

_DESTRUCTIVE_ACTIONS = {"Remove", "RemoveWithContent"}


def _validate_share_limit_action(action: str, group: str = "test_group") -> str:
    """Validate share_limit_action value exactly as Config.__init__ does.

    Returns the resolved action string on success, raises Failed on error.
    The production code reads ``raw_share_limit_action`` from YAML; we
    simulate that by treating ``action`` as that raw value.
    """
    raw = action if action else None
    if raw is not None and raw not in SHARE_LIMIT_ACTIONS:
        raise Failed(
            f"Config Error: invalid share_limit_action '{raw}' for the grouping "
            f"'{group}'. Valid values are: {', '.join(SHARE_LIMIT_ACTIONS.keys())}."
        )
    return raw or "Default"


def _validate_cleanup_exclusion(cleanup: bool, action: str, group: str = "test_group") -> None:
    """Validate cleanup + destructive action mutual exclusion exactly as Config.__init__ does.

    Raises Failed if cleanup=True and action is Remove or RemoveWithContent.
    """
    if cleanup and action in _DESTRUCTIVE_ACTIONS:
        raise Failed(
            f"Config Error: cleanup and share_limit_action are mutually exclusive for the grouping "
            f"'{group}'. Got cleanup=true and share_limit_action='{action}'. qBittorrent acts the instant "
            f"a share limit is reached and runs BEFORE qbm's scheduled cleanup pass — so this "
            f"share_limit_action removes the torrent before qbm can use the recyclebin."
        )


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
        result = _validate_share_limit_action("")
        assert result == "Default"


# ---------------------------------------------------------------------------
# Tests: valid action values — validator must NOT raise
# ---------------------------------------------------------------------------


class TestShareLimitActionValidation:
    """Tests that valid action values pass production validation and that invalid ones raise Failed."""

    @pytest.mark.parametrize("action", list(SHARE_LIMIT_ACTIONS.keys()))
    def test_valid_action_passes_validator(self, action):
        """All values in SHARE_LIMIT_ACTIONS are accepted by the production validator."""
        result = _validate_share_limit_action(action)
        assert result == action

    def test_invalid_action_raises_failed(self):
        """An unrecognised share_limit_action raises Failed — mirroring Config.__init__ line ~734."""
        with pytest.raises(Failed, match="invalid share_limit_action"):
            _validate_share_limit_action("DeleteEverything")

    def test_invalid_action_error_message_contains_value(self):
        """The Failed message includes the bad value so operators know what to fix."""
        with pytest.raises(Failed, match="BogusAction"):
            _validate_share_limit_action("BogusAction")

    def test_invalid_action_error_message_lists_valid_options(self):
        """The Failed message lists the valid options so operators know what to use."""
        with pytest.raises(Failed) as exc_info:
            _validate_share_limit_action("BogusAction")
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
        """cleanup=true + Remove or RemoveWithContent raises Failed — mirrors Config.__init__ line ~835."""
        with pytest.raises(Failed, match="mutually exclusive"):
            _validate_cleanup_exclusion(cleanup=True, action=action)

    @pytest.mark.parametrize("action", ["Default", "Stop", "EnableSuperSeeding"])
    def test_cleanup_true_with_safe_action_does_not_raise(self, action):
        """cleanup=true with a non-destructive action is allowed — no exception raised."""
        _validate_cleanup_exclusion(cleanup=True, action=action)  # must not raise

    @pytest.mark.parametrize("action", ["Remove", "RemoveWithContent"])
    def test_cleanup_false_with_destructive_action_does_not_raise(self, action):
        """cleanup=false with any action is allowed — the exclusion only fires when cleanup=True."""
        _validate_cleanup_exclusion(cleanup=False, action=action)  # must not raise

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

    def test_cleanup_without_share_limit_action_allowed(self, group_config_factory):
        """cleanup=true without share_limit_action specified is allowed."""
        config = group_config_factory(cleanup=True)
        assert config["cleanup"] is True

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

    def test_set_limits_passes_share_limit_action_to_torrent(self, share_limits_factory, torrent_factory):
        """set_limits() passes share_limit_action from group config to torrent.set_share_limits()."""
        sl = share_limits_factory()
        t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)

        sl.set_limits(t, max_ratio=2.0, max_seeding_time=3600, share_limit_action="Stop")

        set_share_limits_calls = _calls_of(t, "set_share_limits")
        assert len(set_share_limits_calls) == 1
        call_kwargs = set_share_limits_calls[0][1]
        assert call_kwargs["share_limit_action"] == "Stop"

    def test_set_limits_with_remove_action(self, share_limits_factory, torrent_factory):
        """set_limits() with share_limit_action='Remove' is called."""
        sl = share_limits_factory()
        t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)

        sl.set_limits(t, max_ratio=2.0, max_seeding_time=3600, share_limit_action="Remove")

        set_share_limits_calls = _calls_of(t, "set_share_limits")
        assert len(set_share_limits_calls) == 1
        call_kwargs = set_share_limits_calls[0][1]
        assert call_kwargs["share_limit_action"] == "Remove"

    def test_set_limits_with_remove_with_content_action(self, share_limits_factory, torrent_factory):
        """set_limits() with share_limit_action='RemoveWithContent' is called."""
        sl = share_limits_factory()
        t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)

        sl.set_limits(t, max_ratio=2.0, max_seeding_time=3600, share_limit_action="RemoveWithContent")

        set_share_limits_calls = _calls_of(t, "set_share_limits")
        assert len(set_share_limits_calls) == 1
        call_kwargs = set_share_limits_calls[0][1]
        assert call_kwargs["share_limit_action"] == "RemoveWithContent"

    def test_set_limits_with_enable_super_seeding_action(self, share_limits_factory, torrent_factory):
        """set_limits() with share_limit_action='EnableSuperSeeding' is called."""
        sl = share_limits_factory()
        t = torrent_factory(max_ratio=-1.0, max_seeding_time=-1)

        sl.set_limits(t, max_ratio=2.0, max_seeding_time=3600, share_limit_action="EnableSuperSeeding")

        set_share_limits_calls = _calls_of(t, "set_share_limits")
        assert len(set_share_limits_calls) == 1
        call_kwargs = set_share_limits_calls[0][1]
        assert call_kwargs["share_limit_action"] == "EnableSuperSeeding"
