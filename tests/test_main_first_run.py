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
