"""Regression tests for Web API log-file access."""

import asyncio

import pytest
from fastapi import HTTPException

from modules.web_api import WebAPI


@pytest.fixture
def log_api(tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir()
    api = object.__new__(WebAPI)
    object.__setattr__(api, "logs_path", logs_path)
    return api


def get_logs(api, *, limit=None, log_filename=None):
    return asyncio.run(api.get_logs(limit=limit, log_filename=log_filename))


def list_log_files(api):
    return asyncio.run(api.list_log_files())


@pytest.mark.parametrize(
    "filename",
    ["../outside.log", "/tmp/outside.log", r"..\outside.log", "activity.txt", "activity.log.backup"],
)
def test_get_logs_rejects_invalid_filename(log_api, filename):
    with pytest.raises(HTTPException) as exc_info:
        get_logs(log_api, log_filename=filename)

    assert exc_info.value.status_code == 400


def test_get_logs_rejects_symlink_escape(log_api, tmp_path):
    outside_log = tmp_path / "outside.log"
    outside_log.write_text("secret\n", encoding="utf-8")
    (log_api.logs_path / "linked.log").symlink_to(outside_log)

    with pytest.raises(HTTPException) as exc_info:
        get_logs(log_api, log_filename="linked.log")

    assert exc_info.value.status_code == 400


def test_get_logs_returns_404_for_missing_log(log_api):
    with pytest.raises(HTTPException) as exc_info:
        get_logs(log_api, log_filename="missing.log")

    assert exc_info.value.status_code == 404


def test_get_logs_reads_rotated_log_and_preserves_limit_order(log_api):
    (log_api.logs_path / "activity.2.log").write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = get_logs(log_api, limit=2, log_filename="activity.2.log")

    assert result == {"logs": ["two", "three"]}


def test_list_log_files_includes_rotations_in_natural_order(log_api):
    for filename in ["activity.10.log", "activity.log.2", "activity.log", "other.1.log"]:
        (log_api.logs_path / filename).touch()
    (log_api.logs_path / "ignored.txt").touch()
    (log_api.logs_path / "activity.log.backup").touch()

    result = list_log_files(log_api)

    assert result == {"log_files": ["activity.log", "activity.log.2", "activity.10.log", "other.1.log"]}


def test_list_log_files_excludes_symlink_escape(log_api, tmp_path):
    outside_log = tmp_path / "outside.log"
    outside_log.touch()
    (log_api.logs_path / "linked.log").symlink_to(outside_log)
    (log_api.logs_path / "inside.log").touch()

    assert list_log_files(log_api) == {"log_files": ["inside.log"]}
