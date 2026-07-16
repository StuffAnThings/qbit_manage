"""Tests for modules/logs.py — JSON log format mode."""

import io
import json
import logging
import sys
from logging.handlers import RotatingFileHandler

from modules.logs import JsonFormatter
from modules.logs import MyLogger


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
    return MyLogger(name, "test.log", "INFO", str(tmp_path), 100, "=", True, 10, 5, log_format=log_format)


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
        logger.info("from default handler")
        parsed = json.loads(sio.getvalue().strip())
        assert parsed["message"] == "from default handler"
        assert parsed["level"] == "INFO"
        assert parsed["source"].endswith("test_logs.py:85")

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
