"""An unhandled exception in the first run must stop the process, not leave the web server alive."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


class _FakeManager:
    def Value(self, *_a):
        return MagicMock()

    def Lock(self):
        return MagicMock()

    def Queue(self):
        return MagicMock()

    def dict(self):
        return {}


@pytest.fixture
def qbm(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["qbit_manage.py"])
    monkeypatch.setenv("QBT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delitem(sys.modules, "qbit_manage", raising=False)
    import qbit_manage

    return qbit_manager_setup(qbit_manage, monkeypatch)


def qbit_manager_setup(mod, monkeypatch):
    web_process = MagicMock()
    sched = MagicMock()
    sched.get_current_schedule.return_value = None
    monkeypatch.setattr(mod.multiprocessing, "set_start_method", lambda *a, **k: None)
    monkeypatch.setattr(mod.multiprocessing, "Process", lambda *a, **k: web_process)
    monkeypatch.setattr(mod, "Manager", _FakeManager)
    monkeypatch.setattr(mod, "Scheduler", lambda *a, **k: sched)
    monkeypatch.setattr(mod, "GracefulKiller", MagicMock())
    monkeypatch.setattr(mod, "print_logo", lambda *a, **k: None)
    monkeypatch.setattr(mod, "is_docker", True)
    monkeypatch.setattr(mod, "web_server", True)
    monkeypatch.setattr(mod, "run", False)
    monkeypatch.setattr(mod, "sch", 1)
    monkeypatch.setattr(mod, "startupDelay", 0)
    mod.web_process_mock = web_process
    mod.sched_mock = sched
    return mod


def test_first_run_exception_terminates_web_server_and_exits_nonzero(qbm, monkeypatch):
    def boom(*_a, **_k):
        raise AttributeError("unexpected qBittorrent answer")

    monkeypatch.setattr(qbm, "start_loop", boom)

    with pytest.raises(SystemExit) as exc:
        qbm.main()

    assert exc.value.code == 1
    qbm.web_process_mock.terminate.assert_called_once()
    qbm.web_process_mock.join.assert_called_once()
    qbm.sched_mock.stop.assert_called_once()


def _prime_start(qbm, monkeypatch, exc, run):
    cfg = MagicMock()
    cfg.qbt = MagicMock()
    monkeypatch.setattr(qbm, "Config", lambda *a, **k: cfg)
    monkeypatch.setattr(qbm, "execute_qbit_commands", MagicMock(side_effect=exc))
    monkeypatch.setattr(qbm, "run", run)
    monkeypatch.setattr(qbm, "is_running", MagicMock(), raising=False)
    monkeypatch.setattr(qbm, "is_running_lock", MagicMock(), raising=False)
    monkeypatch.setattr(qbm, "next_scheduled_run_info_shared", {}, raising=False)
    monkeypatch.setattr(qbm, "stats", {}, raising=False)
    monkeypatch.setattr(qbm, "finished_run", lambda *a, **k: None, raising=False)


@pytest.mark.parametrize("exc_name", ["InvalidCategoryConfig", "UnsupportedVersion"])
def test_start_one_shot_reraises_config_fatal_errors(qbm, monkeypatch, exc_name):
    exc_cls = getattr(qbm, exc_name)
    _prime_start(qbm, monkeypatch, exc_cls("bad config"), run=True)

    with pytest.raises(exc_cls):
        qbm.start()

    assert qbm.next_scheduled_run_info_shared["last_run_result"] == "failed"


def test_start_scheduled_mode_swallows_config_fatal_errors(qbm, monkeypatch):
    _prime_start(qbm, monkeypatch, qbm.InvalidCategoryConfig("bad config"), run=False)

    assert qbm.start() is None


def test_one_shot_config_fatal_error_terminates_web_server_and_exits_nonzero(qbm, monkeypatch):
    monkeypatch.setattr(qbm, "run", True)
    monkeypatch.setattr(qbm, "start_loop", MagicMock(side_effect=qbm.InvalidCategoryConfig("bad config")))

    with pytest.raises(SystemExit) as exc:
        qbm.main()

    assert exc.value.code == 1
    qbm.web_process_mock.terminate.assert_called_once()
    qbm.web_process_mock.join.assert_called_once()
