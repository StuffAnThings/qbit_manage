"""Regression tests for WebAPI.validate_config with an unsupported qBittorrent version."""

import asyncio
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from modules.qbittorrent import Qbt
from modules.web_api import ConfigRequest
from modules.web_api import WebAPI
from tests.test_qbittorrent import make_qbt_client
from tests.test_qbittorrent import make_qbt_config

PARAMS = {"host": "localhost:8080", "username": None, "password": None, "api_key": "key"}


@pytest.fixture
def api(tmp_path):
    (tmp_path / "config.yml").write_text("qbt:\n  host: localhost:8080\n")
    web_api = object.__new__(WebAPI)
    object.__setattr__(web_api, "config_path", tmp_path.resolve())
    object.__setattr__(web_api, "default_dir", str(tmp_path))
    object.__setattr__(web_api, "args", {"skip_qb_version_check": False})
    return web_api


def validate(api, data):
    return asyncio.run(api.validate_config("config.yml", ConfigRequest(data=data)))


@patch("modules.qbittorrent.Version.is_app_version_supported", return_value=False)
@patch("modules.qbittorrent.Qbt.get_torrents", return_value=[])
@patch("modules.qbittorrent.Client")
@patch("modules.qbittorrent.logger.print_line", create=True)
@patch("modules.qbittorrent.logger.secret", create=True)
def test_validate_returns_error_for_unsupported_version(_secret, _print_line, mock_client, _torrents, _supported, api):
    mock_client.return_value = make_qbt_client()

    def build_config(default_dir, args):
        Qbt(make_qbt_config(), PARAMS)

    with patch("modules.web_api.Config", side_effect=build_config):
        response = validate(api, {"qbt": {"host": "localhost:8080"}})

    assert response.valid is False
    assert "only compatible with" in response.errors[0]


def test_validate_honors_skip_version_check_from_config_commands(api):
    seen = {}

    def capture(default_dir, args):
        seen.update(args)
        return MagicMock()

    with patch("modules.web_api.Config", side_effect=capture):
        response = validate(api, {"qbt": {"host": "localhost:8080"}, "commands": {"skip_qb_version_check": True}})

    assert response.valid is True
    assert seen["skip_qb_version_check"] is True
