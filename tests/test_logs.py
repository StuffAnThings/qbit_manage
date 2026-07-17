"""Tests for modules/logs.py — JSON log format mode."""

import inspect
import io
import json
import logging
import sys
from logging.handlers import RotatingFileHandler

import pytest

import modules.logs as logs_module
from modules.logs import JsonFormatter
from modules.logs import MyLogger
from modules.logs import canonical_log_name
from modules.logs import migrate_log_directory
from modules.logs import migrate_rotated_logs
from modules.logs import rotated_log_name


def _make_record(msg="test message", level=logging.INFO, exc_info=None):
    """Create a minimal LogRecord for formatter tests."""
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname="/some/path/module.py",
        lineno=42,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


def _make_logger(tmp_path, log_format="json"):
    name = f"test-logs-{tmp_path.name}"
    return MyLogger(name, "test.txt", "INFO", str(tmp_path), 100, "=", True, 10, 5, log_format=log_format)


def _capture_stream():
    sio = io.StringIO()
    handler = logging.StreamHandler(sio)
    handler.setFormatter(JsonFormatter())
    return handler, sio


class TestJsonFormatter:
    def test_basic_fields(self):
        record = _make_record("hello world", logging.INFO)
        formatter = JsonFormatter()
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello world"
        assert "timestamp" in parsed
        assert "logger" in parsed
        assert "source" in parsed
        assert parsed["source"].endswith(":42")

    def test_level_has_no_brackets(self):
        record = _make_record("msg", logging.WARNING)
        formatter = JsonFormatter()
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"
        assert "[" not in parsed["level"]
        assert "]" not in parsed["level"]

    def test_exc_info_included(self):
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = _make_record("oops", logging.ERROR, exc_info=exc_info)
        formatter = JsonFormatter()
        parsed = json.loads(formatter.format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]

    def test_no_exc_info_when_none(self):
        record = _make_record("fine")
        formatter = JsonFormatter()
        parsed = json.loads(formatter.format(record))
        assert "exc_info" not in parsed


class TestMyLoggerJsonMode:
    def test_default_stream_handler_emits_json(self, tmp_path):
        """The init StreamHandler must emit JSON in json mode (production default)."""
        logger = _make_logger(tmp_path)
        sio = io.StringIO()
        for handler in logger._logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                handler.stream = sio
        expected_line = inspect.currentframe().f_lineno + 1
        logger.info("from default handler")
        parsed = json.loads(sio.getvalue().strip())
        assert parsed["message"] == "from default handler"
        assert parsed["level"] == "INFO"
        assert parsed["source"].endswith(f"test_logs.py:{expected_line}")

    def test_source_field_uses_caller_pathname(self, tmp_path):
        """JSON source must reflect the real caller, not a mangled func/pathname tuple."""
        logger = _make_logger(tmp_path)
        handler, sio = _capture_stream()
        logger._logger.addHandler(handler)
        logger.info("caller line")
        parsed = json.loads(sio.getvalue().strip())
        assert parsed["source"].startswith("test_logs.py:")

    def test_multiline_message_is_single_json_record(self, tmp_path):
        logger = _make_logger(tmp_path)
        sio = io.StringIO()
        for handler in logger._logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                handler.stream = sio
        logger.info("line one\nline two")
        lines = [line for line in sio.getvalue().splitlines() if line.strip()]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["message"] == "line one\nline two"

    def test_info_emits_valid_json(self, tmp_path):
        logger = _make_logger(tmp_path)
        handler, sio = _capture_stream()
        logger._logger.addHandler(handler)
        logger.info("hello world")
        output = sio.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"

    def test_separator_no_border_art(self, tmp_path):
        logger = _make_logger(tmp_path)
        handler, sio = _capture_stream()
        logger._logger.addHandler(handler)
        logger.separator("Section")
        output = sio.getvalue().strip()
        assert output, "separator should emit at least one line in json mode"
        for line in output.splitlines():
            parsed = json.loads(line)
            assert "=====" not in parsed["message"]

    def test_secret_redacted_in_json(self, tmp_path):
        logger = _make_logger(tmp_path)
        handler, sio = _capture_stream()
        logger._logger.addHandler(handler)
        logger.secret("s3cr3t")
        logger.info("token s3cr3t here")
        output = sio.getvalue().strip()
        parsed = json.loads(output)
        assert "s3cr3t" not in parsed["message"]
        assert "(redacted)" in parsed["message"]


def test_rotated_log_name_keeps_log_suffix():
    assert rotated_log_name("/config/logs/qbit_manage.txt.3") == "/config/logs/qbit_manage.3.txt"


def test_canonical_log_name_always_uses_txt_extension():
    assert canonical_log_name("/config/logs/qbit_manage.log") == "/config/logs/qbit_manage.txt"
    assert canonical_log_name("/config/logs/custom") == "/config/logs/custom.txt"


def test_rotating_handler_uses_suffix_preserving_name(tmp_path):
    log_path = tmp_path / "qbit_manage.txt"
    log_path.write_text("first\n", encoding="utf-8")
    handler = RotatingFileHandler(log_path, maxBytes=1, backupCount=2, encoding="utf-8")
    handler.namer = rotated_log_name

    try:
        handler.doRollover()
    finally:
        handler.close()

    assert (tmp_path / "qbit_manage.1.txt").read_text(encoding="utf-8") == "first\n"
    assert not (tmp_path / "qbit_manage.txt.1").exists()


def test_migrate_rotated_logs_renames_legacy_archives(tmp_path):
    log_path = tmp_path / "qbit_manage.txt"
    (tmp_path / "qbit_manage.log").write_text("active\n", encoding="utf-8")
    (tmp_path / "qbit_manage.log.1").write_text("newer\n", encoding="utf-8")
    (tmp_path / "qbit_manage.2.log").write_text("older\n", encoding="utf-8")

    migrate_rotated_logs(str(log_path), backup_count=2)

    assert log_path.read_text(encoding="utf-8") == "active\n"
    assert (tmp_path / "qbit_manage.1.txt").read_text(encoding="utf-8") == "newer\n"
    assert (tmp_path / "qbit_manage.2.txt").read_text(encoding="utf-8") == "older\n"
    assert not (tmp_path / "qbit_manage.log").exists()
    assert not (tmp_path / "qbit_manage.log.1").exists()
    assert not (tmp_path / "qbit_manage.2.log").exists()


def test_migrate_rotated_logs_moves_collision_to_next_txt_archive(tmp_path):
    log_path = tmp_path / "qbit_manage.txt"
    legacy_path = tmp_path / "qbit_manage.log.1"
    canonical_path = tmp_path / "qbit_manage.1.txt"
    legacy_path.write_text("legacy\n", encoding="utf-8")
    canonical_path.write_text("canonical\n", encoding="utf-8")

    migrate_rotated_logs(str(log_path), backup_count=2)

    assert canonical_path.read_text(encoding="utf-8") == "canonical\n"
    assert (tmp_path / "qbit_manage.2.txt").read_text(encoding="utf-8") == "legacy\n"
    assert not legacy_path.exists()


def test_migrate_rotated_logs_cleans_all_legacy_names_despite_collisions(tmp_path):
    log_path = tmp_path / "qbit_manage.txt"
    log_path.write_text("canonical active\n", encoding="utf-8")
    (tmp_path / "qbit_manage.1.txt").write_text("canonical archive\n", encoding="utf-8")
    (tmp_path / "qbit_manage.log").write_text("legacy active\n", encoding="utf-8")
    (tmp_path / "qbit_manage.log.1").write_text("suffix archive\n", encoding="utf-8")
    (tmp_path / "qbit_manage.1.log").write_text("prefix archive\n", encoding="utf-8")
    (tmp_path / "qbit_manage.txt.8").write_text("old txt rotation\n", encoding="utf-8")

    migrate_rotated_logs(str(log_path), backup_count=5)

    txt_logs = sorted(path.name for path in tmp_path.iterdir())
    assert txt_logs == [
        "qbit_manage.1.txt",
        "qbit_manage.2.txt",
        "qbit_manage.3.txt",
        "qbit_manage.4.txt",
        "qbit_manage.5.txt",
        "qbit_manage.txt",
    ]
    assert {path.read_text(encoding="utf-8") for path in tmp_path.iterdir()} == {
        "canonical active\n",
        "canonical archive\n",
        "legacy active\n",
        "suffix archive\n",
        "prefix archive\n",
        "old txt rotation\n",
    }


def test_migrate_rotated_logs_preserves_order_within_retention(tmp_path):
    log_path = tmp_path / "qbit_manage.txt"
    log_path.write_text("current\n", encoding="utf-8")
    for rotation in range(1, 6):
        (tmp_path / f"qbit_manage.{rotation}.txt").write_text(f"archive {rotation}\n", encoding="utf-8")
    (tmp_path / "qbit_manage.log").write_text("legacy active\n", encoding="utf-8")

    migrate_rotated_logs(str(log_path), backup_count=5)

    assert (tmp_path / "qbit_manage.1.txt").read_text(encoding="utf-8") == "legacy active\n"
    assert (tmp_path / "qbit_manage.2.txt").read_text(encoding="utf-8") == "archive 1\n"
    assert (tmp_path / "qbit_manage.5.txt").read_text(encoding="utf-8") == "archive 5\narchive 4\n"
    assert not (tmp_path / "qbit_manage.6.txt").exists()


def test_migrate_log_directory_converts_inactive_stems(tmp_path):
    (tmp_path / "qbit_manage.log").write_text("main\n", encoding="utf-8")
    (tmp_path / "retired-config.log").write_text("retired\n", encoding="utf-8")
    (tmp_path / "retired-config.log.1").write_text("retired archive\n", encoding="utf-8")

    migrate_log_directory(str(tmp_path), backup_count=3)

    assert (tmp_path / "qbit_manage.txt").read_text(encoding="utf-8") == "main\n"
    assert (tmp_path / "retired-config.txt").read_text(encoding="utf-8") == "retired\n"
    assert (tmp_path / "retired-config.1.txt").read_text(encoding="utf-8") == "retired archive\n"
    assert all(path.suffix == ".txt" for path in tmp_path.iterdir())


def test_migrate_rotated_logs_rolls_back_partial_staging_failure(tmp_path, monkeypatch):
    log_path = tmp_path / "qbit_manage.txt"
    first_archive = tmp_path / "qbit_manage.log.1"
    second_archive = tmp_path / "qbit_manage.log.2"
    first_archive.write_text("first\n", encoding="utf-8")
    second_archive.write_text("second\n", encoding="utf-8")
    real_replace = logs_module.os.replace

    def fail_on_second_archive(source, destination):
        if str(source) == str(second_archive):
            raise OSError("simulated staging failure")
        real_replace(source, destination)

    monkeypatch.setattr(logs_module.os, "replace", fail_on_second_archive)

    with pytest.raises(OSError, match="simulated staging failure"):
        migrate_rotated_logs(str(log_path), backup_count=3)

    assert first_archive.read_text(encoding="utf-8") == "first\n"
    assert second_archive.read_text(encoding="utf-8") == "second\n"
    assert not list(tmp_path.glob("*.migrating-*"))


def test_main_handler_normalizes_name_and_migrates_before_open(tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir()
    (logs_path / "qbit_manage.log").write_text("active\n", encoding="utf-8")
    (logs_path / "qbit_manage.log.1").write_text("archive\n", encoding="utf-8")
    logger = MyLogger("migration-integration", "qbit_manage.log", "INFO", str(tmp_path), 100, "=", True, 10, 5)

    logger.add_main_handler()
    try:
        assert logger.main_log == str(logs_path / "qbit_manage.txt")
        assert (logs_path / "qbit_manage.txt").read_text(encoding="utf-8") == "active\n"
        assert (logs_path / "qbit_manage.1.txt").read_text(encoding="utf-8") == "archive\n"
        assert not (logs_path / "qbit_manage.log").exists()
        assert not (logs_path / "qbit_manage.log.1").exists()
    finally:
        logger.remove_main_handler()
        logger.main_handler.close()
