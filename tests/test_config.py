"""Tests for modules.config.Config — pure validation logic.

Uses object.__new__ to bypass __init__ (which requires a real config file and
running qBittorrent instance) and exercises validate_required_sections() directly.
"""

from __future__ import annotations

import pytest

from modules.config import Config
from modules.util import Failed


def _make_config(data: dict) -> Config:
    """Construct a Config with minimal state, bypassing __init__."""
    cfg = object.__new__(Config)
    cfg.data = data
    cfg._notify_calls = []
    cfg.notify = lambda text, function=None, critical=True: cfg._notify_calls.append(text)
    return cfg


class TestValidateRequiredSections:
    """validate_required_sections() raises Failed when sections are missing/empty."""

    def test_valid_cat_section_passes(self):
        """A non-empty 'cat' section satisfies the validator."""
        cfg = _make_config({"cat": {"Movies": "/data/movies"}})
        # Must not raise
        cfg.validate_required_sections()

    def test_valid_tracker_section_passes(self):
        """A non-empty 'tracker' section satisfies the validator."""
        cfg = _make_config({"tracker": {"tracker1.example": {"tag": ["t1"]}}})
        cfg.validate_required_sections()

    def test_both_sections_present_and_non_empty_passes(self):
        """Both non-empty sections together satisfy the validator."""
        cfg = _make_config(
            {
                "cat": {"Movies": "/data/movies"},
                "tracker": {"tracker1.example": {"tag": ["t1"]}},
            }
        )
        cfg.validate_required_sections()

    def test_empty_cat_section_raises(self):
        """An empty 'cat' section raises Failed."""
        cfg = _make_config({"cat": {}})
        with pytest.raises(Failed, match="Category section"):
            cfg.validate_required_sections()

    def test_none_cat_section_raises(self):
        """A None 'cat' section raises Failed."""
        cfg = _make_config({"cat": None})
        with pytest.raises(Failed, match="Category section"):
            cfg.validate_required_sections()

    def test_empty_tracker_section_raises(self):
        """An empty 'tracker' section raises Failed."""
        cfg = _make_config({"tracker": {}})
        with pytest.raises(Failed, match="Tracker section"):
            cfg.validate_required_sections()

    def test_none_tracker_section_raises(self):
        """A None 'tracker' section raises Failed."""
        cfg = _make_config({"tracker": None})
        with pytest.raises(Failed, match="Tracker section"):
            cfg.validate_required_sections()

    def test_both_sections_missing_raises(self):
        """Neither 'cat' nor 'tracker' present raises Failed."""
        cfg = _make_config({})
        with pytest.raises(Failed, match="Both"):
            cfg.validate_required_sections()

    def test_notify_called_before_raise_on_empty_cat(self):
        """notify() is called before raising so webhooks fire."""
        cfg = _make_config({"cat": {}})
        with pytest.raises(Failed):
            cfg.validate_required_sections()
        assert len(cfg._notify_calls) == 1
        assert "Category section" in cfg._notify_calls[0]
