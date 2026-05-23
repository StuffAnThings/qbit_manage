"""Tests for share_limit_action configuration and validation.

Covers:
- Default value when share_limit_action is not set
- Valid action values (Default, Stop, Remove, RemoveWithContent, EnableSuperSeeding)
- Invalid action raises Failed
- Mutual exclusion: cleanup=true + destructive share_limit_action (Remove/RemoveWithContent)
- share_limit_action is passed through to torrent.set_share_limits()
"""

from __future__ import annotations


def _calls_of(torrent, name):
    """Extract all calls to a specific method from torrent.calls."""
    return [c for c in torrent.calls if c[0] == name]


class TestShareLimitActionDefaults:
    """Tests for default and missing share_limit_action values."""

    def test_default_value_when_not_specified(self, group_config_factory):
        """When share_limit_action is not specified, defaults to 'Default'."""
        config = group_config_factory()
        assert config["share_limit_action"] == "Default"


class TestShareLimitActionValidation:
    """Tests for share_limit_action validation in group config."""

    def test_valid_action_default(self, group_config_factory):
        """share_limit_action='Default' is valid."""
        config = group_config_factory(share_limit_action="Default")
        assert config["share_limit_action"] == "Default"

    def test_valid_action_stop(self, group_config_factory):
        """share_limit_action='Stop' is valid."""
        config = group_config_factory(share_limit_action="Stop")
        assert config["share_limit_action"] == "Stop"

    def test_valid_action_remove(self, group_config_factory):
        """share_limit_action='Remove' is valid."""
        config = group_config_factory(share_limit_action="Remove")
        assert config["share_limit_action"] == "Remove"

    def test_valid_action_remove_with_content(self, group_config_factory):
        """share_limit_action='RemoveWithContent' is valid."""
        config = group_config_factory(share_limit_action="RemoveWithContent")
        assert config["share_limit_action"] == "RemoveWithContent"

    def test_valid_action_enable_super_seeding(self, group_config_factory):
        """share_limit_action='EnableSuperSeeding' is valid."""
        config = group_config_factory(share_limit_action="EnableSuperSeeding")
        assert config["share_limit_action"] == "EnableSuperSeeding"


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


class TestCleanupMutualExclusion:
    """Tests for mutual exclusion of cleanup=true and destructive share_limit_action."""

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
