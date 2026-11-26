"""First-run crashes from a fresh sample config (issue #1439)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from ruamel.yaml import YAML

from modules import config as config_mod
from modules import util as util_mod
from modules import webhooks as webhooks_mod
from modules.config import Config
from modules.config import validate_share_limit_action
from modules.util import Failed
from modules.util import check
from modules.webhooks import Webhooks

SAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yml.sample"


@pytest.fixture
def log(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(config_mod, "logger", mock)
    monkeypatch.setattr(webhooks_mod, "logger", mock)
    monkeypatch.setattr(util_mod, "logger", mock)
    return mock


def test_sample_config_has_no_duplicate_keys():
    yaml = YAML()
    yaml.allow_duplicate_keys = False
    with open(SAMPLE_CONFIG, encoding="utf-8") as handle:
        yaml.load(handle)


@pytest.mark.parametrize("raw", ["pause", "Pause", "PAUSE"])
def test_legacy_pause_maps_to_stop_with_warning(raw, log):
    assert validate_share_limit_action(raw, cleanup=False, group="g") == "Stop"
    log.warning.assert_called_once()


@pytest.mark.parametrize("exc", [requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout])
def test_webhook_network_error_is_logged_not_raised(exc, log):
    config = MagicMock()
    config.post.side_effect = exc("unreachable")
    hooks = Webhooks(config, {"error": ["https://mywebhookurl.com"]})
    hooks.error_hooks("boom", "Test")
    log.warning.assert_called_once()


def test_webhook_failed_is_logged_not_raised(log):
    hooks = Webhooks(MagicMock(), {"error": ["https://mywebhookurl.com"]})
    hooks.request_and_check = MagicMock(side_effect=Failed("bad webhook"))
    hooks.error_hooks("boom", "Test")
    log.warning.assert_called_once()


def _directory_config(tmp_path, torrents_dir):
    cfg = object.__new__(Config)
    cfg.data = {"directory": {"root_dir": str(tmp_path), "torrents_dir": str(torrents_dir)}}
    cfg.commands = {"tag_nohardlinks": False, "rem_orphaned": False}
    cfg.recyclebin = {"enabled": True, "save_torrents": True, "split_by_category": False}
    cfg.config_path = str(tmp_path / "config.yml")
    (tmp_path / "config.yml").write_text(f"directory:\n  root_dir: {tmp_path}\n", encoding="utf-8")
    cfg.util = check(cfg)
    cfg.notify = MagicMock()
    return cfg


def test_empty_torrents_dir_warns_and_continues(tmp_path, log):
    bt = tmp_path / ".BT_backup"
    bt.mkdir()
    cfg = _directory_config(tmp_path, bt)
    cfg.process_config_directories()
    assert cfg.torrents_dir is not None
    assert "does not contain any .torrents" in str(log.warning.call_args)


def test_missing_torrents_dir_warns_and_continues(tmp_path, log):
    cfg = _directory_config(tmp_path, tmp_path / "does-not-exist")
    cfg.process_config_directories()
    assert cfg.torrents_dir is None
    assert "does not exist" in str(log.print_line.call_args)


def test_file_torrents_dir_does_not_crash(tmp_path, log):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    cfg = _directory_config(tmp_path, not_a_dir)
    cfg.process_config_directories()
    assert cfg.torrents_dir is not None
