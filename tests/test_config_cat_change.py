"""Tests for cat_change config validation in modules/config.py."""

import pytest

from modules.config import Config
from modules.util import Failed
from tests.factories import _FakeWebhooksFactory


class _TestConfig(Config):
    """Minimal Config subclass that overrides notify() to avoid webhook calls."""

    def __init__(self, cat_change_value):
        self.data = {"cat_change": cat_change_value} if cat_change_value is not None else {}
        self.webhooks_factory = _FakeWebhooksFactory()
        self.notify_calls = []

    def notify(self, err, function, *args, **kwargs):
        """Override notify to avoid trying to call webhooks."""
        self.notify_calls.append((err, function))


def make_config_with_cat_change(cat_change_value):
    """Create a Config instance with a specific cat_change value for testing."""
    return _TestConfig(cat_change_value)


def test_cat_change_none_returns_empty_dict():
    """cat_change: None or missing returns {}."""
    config = make_config_with_cat_change(None)
    result = config._process_cat_change()
    assert result == {}


def test_cat_change_empty_dict_returns_empty_dict():
    """cat_change: {} returns {}."""
    config = make_config_with_cat_change({})
    result = config._process_cat_change()
    assert result == {}


def test_cat_change_empty_list_raises_failed():
    """cat_change: [] is a non-dict type and must raise Failed, not silently return {}."""
    config = make_config_with_cat_change([])
    with pytest.raises(Failed, match="cat_change must be a mapping"):
        config._process_cat_change()


def test_cat_change_string_raises_failed():
    """cat_change: "string" raises Failed with type error."""
    config = make_config_with_cat_change("invalid")
    with pytest.raises(Failed, match="cat_change must be a mapping"):
        config._process_cat_change()


def test_cat_change_integer_raises_failed():
    """cat_change: 42 raises Failed with type error."""
    config = make_config_with_cat_change(42)
    with pytest.raises(Failed, match="cat_change must be a mapping"):
        config._process_cat_change()


def test_cat_change_value_list_raises_failed():
    """cat_change entry with list value raises Failed."""
    config = make_config_with_cat_change({"old_cat": ["invalid", "list"]})
    with pytest.raises(Failed, match="invalid type"):
        config._process_cat_change()


def test_cat_change_value_integer_raises_failed():
    """cat_change entry with integer value raises Failed."""
    config = make_config_with_cat_change({"old_cat": 42})
    with pytest.raises(Failed, match="invalid type"):
        config._process_cat_change()


def test_cat_change_value_none_raises_failed():
    """cat_change entry with None value raises Failed."""
    config = make_config_with_cat_change({"old_cat": None})
    with pytest.raises(Failed, match="invalid type"):
        config._process_cat_change()


def test_cat_change_simple_format_string():
    """cat_change: {old: new} normalizes to extended format."""
    config = make_config_with_cat_change({"old_cat": "new_cat"})
    result = config._process_cat_change()
    assert result == {"old_cat": {"new_cat": "new_cat", "delay_minutes": 0}}


def test_cat_change_extended_format_with_delay():
    """cat_change: {old: {new_cat: name, delay_minutes: N}} works correctly."""
    config = make_config_with_cat_change({"old_cat": {"new_cat": "new_cat", "delay_minutes": 30}})
    result = config._process_cat_change()
    assert result == {"old_cat": {"new_cat": "new_cat", "delay_minutes": 30}}


def test_cat_change_extended_format_without_delay():
    """cat_change: {old: {new_cat: name}} defaults delay to 0."""
    config = make_config_with_cat_change({"old_cat": {"new_cat": "new_cat"}})
    result = config._process_cat_change()
    assert result == {"old_cat": {"new_cat": "new_cat", "delay_minutes": 0}}


def test_cat_change_extended_format_missing_new_cat():
    """cat_change entry without new_cat raises Failed."""
    config = make_config_with_cat_change({"old_cat": {"delay_minutes": 30}})
    with pytest.raises(Failed, match="missing required 'new_cat' key"):
        config._process_cat_change()


def test_cat_change_extended_format_invalid_delay():
    """cat_change entry with invalid delay_minutes raises Failed."""
    config = make_config_with_cat_change({"old_cat": {"new_cat": "new_cat", "delay_minutes": -1}})
    with pytest.raises(Failed, match="invalid delay_minutes"):
        config._process_cat_change()


def test_cat_change_extended_format_delay_float():
    """cat_change entry with float delay_minutes is accepted and converted."""
    config = make_config_with_cat_change({"old_cat": {"new_cat": "new_cat", "delay_minutes": 30.5}})
    result = config._process_cat_change()
    assert result == {"old_cat": {"new_cat": "new_cat", "delay_minutes": 30}}


def test_cat_change_zero_raises_failed():
    """cat_change: 0 is falsy but non-dict — must raise Failed, not silently return {}."""
    config = make_config_with_cat_change(0)
    with pytest.raises(Failed, match="cat_change must be a mapping"):
        config._process_cat_change()


def test_cat_change_false_raises_failed():
    """cat_change: False is falsy but non-dict — must raise Failed, not silently return {}."""
    config = make_config_with_cat_change(False)
    with pytest.raises(Failed, match="cat_change must be a mapping"):
        config._process_cat_change()


def test_cat_change_empty_string_raises_failed():
    """cat_change: "" is falsy but non-dict — must raise Failed, not silently return {}."""
    config = make_config_with_cat_change("")
    with pytest.raises(Failed, match="cat_change must be a mapping"):
        config._process_cat_change()


def test_cat_change_delay_minutes_true_raises_failed():
    """delay_minutes: True must raise Failed — bool must not silently coerce to 1."""
    config = make_config_with_cat_change({"OldCat": {"new_cat": "NewCat", "delay_minutes": True}})
    with pytest.raises(Failed, match="invalid delay_minutes"):
        config._process_cat_change()


def test_cat_change_delay_minutes_false_raises_failed():
    """delay_minutes: False must raise Failed — bool must not silently coerce to 0."""
    config = make_config_with_cat_change({"OldCat": {"new_cat": "NewCat", "delay_minutes": False}})
    with pytest.raises(Failed, match="invalid delay_minutes"):
        config._process_cat_change()


def test_cat_change_multiple_entries():
    """cat_change with multiple entries processes all correctly."""
    config = make_config_with_cat_change(
        {
            "old1": "new1",
            "old2": {"new_cat": "new2", "delay_minutes": 60},
        }
    )
    result = config._process_cat_change()
    assert result == {
        "old1": {"new_cat": "new1", "delay_minutes": 0},
        "old2": {"new_cat": "new2", "delay_minutes": 60},
    }
