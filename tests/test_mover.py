"""Tests for the standalone scripts/mover.py resume batching."""

import importlib.util
import logging
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

MOVER_PATH = Path(__file__).resolve().parent.parent / "scripts" / "mover.py"


@pytest.fixture(scope="module")
def mover():
    spec = importlib.util.spec_from_file_location("mover_script", MOVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    logging.getLogger().handlers.clear()
    return module


def _torrents(count):
    return [MagicMock(name=f"t{i}", added_on=i) for i in range(count)]


class TestResumeBatching:
    def test_defaults_resume_all_without_sleeping(self, mover):
        torrents = _torrents(5)
        with patch.object(mover.time, "sleep") as sleep:
            mover.stop_start_torrents(torrents, pause=False)
        assert all(t.resume.call_count == 1 for t in torrents)
        sleep.assert_not_called()

    def test_batches_sleep_between_batches_only(self, mover):
        torrents = _torrents(5)
        with patch.object(mover.time, "sleep") as sleep:
            mover.stop_start_torrents(torrents, pause=False, batch_size=2, batch_delay=7)
        assert all(t.resume.call_count == 1 for t in torrents)
        assert [c.args[0] for c in sleep.call_args_list] == [7, 7]

    def test_exact_multiple_has_no_trailing_sleep(self, mover):
        torrents = _torrents(4)
        with patch.object(mover.time, "sleep") as sleep:
            mover.stop_start_torrents(torrents, pause=False, batch_size=2, batch_delay=3)
        assert sleep.call_count == 1

    def test_pause_ignores_batching(self, mover):
        torrents = _torrents(4)
        with patch.object(mover.time, "sleep") as sleep:
            mover.stop_start_torrents(torrents, pause=True, batch_size=1, batch_delay=5)
        assert all(t.pause.call_count == 1 for t in torrents)
        sleep.assert_not_called()

    def test_cli_args_default_to_current_behavior(self, mover):
        args = mover.parser.parse_args(["--host", "localhost:8080"])
        assert args.resume_batch_size == 0
        assert args.resume_batch_delay == 0

    def test_cli_args_parse(self, mover):
        args = mover.parser.parse_args(["--host", "localhost:8080", "--resume-batch-size", "10", "--resume-batch-delay", "30"])
        assert (args.resume_batch_size, args.resume_batch_delay) == (10, 30)
