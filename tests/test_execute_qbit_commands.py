"""execute_qbit_commands must let config-fatal errors reach the caller and keep swallowing the rest."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.util import InvalidCategoryConfig
from modules.util import UnsupportedVersion
from modules.util import execute_qbit_commands


@pytest.mark.parametrize("exc_cls", [InvalidCategoryConfig, UnsupportedVersion])
def test_propagates_config_fatal_errors(monkeypatch, exc_cls):
    monkeypatch.setattr("modules.core.category.Category", MagicMock(side_effect=exc_cls("bad config")))

    with pytest.raises(exc_cls):
        execute_qbit_commands(MagicMock(), {"cat_update": True}, {})


def test_still_swallows_other_errors(monkeypatch):
    monkeypatch.setattr("modules.core.category.Category", MagicMock(side_effect=ValueError("boom")))
    monkeypatch.setattr("modules.qbit_error_handler.logger", MagicMock())
    stats = {}

    execute_qbit_commands(MagicMock(), {"cat_update": True}, stats)

    assert "cat_update" not in stats["executed_commands"]
