"""A failing scheduled run must not kill the scheduler thread, and health must expose scheduler state."""

from __future__ import annotations

import asyncio
import sys
import threading
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from modules.scheduler import Scheduler
from modules.util import Failed
from modules.web_api import WebAPI


def _scheduler_with_callback(callback):
    sched = object.__new__(Scheduler)
    sched.lock = threading.Lock()
    sched.stop_event = threading.Event()
    sched.next_run = datetime.now() - timedelta(seconds=1)
    sched._callback = callback
    sched._calculate_next_run = lambda: datetime.now() - timedelta(seconds=1)
    return sched


def test_scheduler_loop_survives_system_exit_from_callback():
    calls = []

    def callback():
        calls.append(1)
        if len(calls) == 1:
            raise SystemExit(1)
        sched.stop_event.set()

    sched = _scheduler_with_callback(callback)
    thread = threading.Thread(target=sched._scheduler_loop, daemon=True)
    thread.start()
    thread.join(timeout=5)

    assert len(calls) == 2


def test_scheduler_is_alive_reflects_thread_state():
    sched = object.__new__(Scheduler)
    sched._scheduler_thread = None
    assert sched.is_alive() is False

    done = threading.Thread(target=lambda: None)
    done.start()
    done.join()
    sched._scheduler_thread = done
    assert sched.is_alive() is False

    stop = threading.Event()
    live = threading.Thread(target=stop.wait, daemon=True)
    live.start()
    sched._scheduler_thread = live
    assert sched.is_alive() is True
    stop.set()


@pytest.fixture
def qbm(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["qbit_manage.py"])
    monkeypatch.setenv("QBT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delitem(sys.modules, "qbit_manage", raising=False)
    import qbit_manage

    monkeypatch.setattr(qbit_manage, "run", False)
    monkeypatch.setattr(qbit_manage, "is_running", MagicMock(value=False), raising=False)
    monkeypatch.setattr(qbit_manage, "is_running_lock", MagicMock(), raising=False)
    monkeypatch.setattr(qbit_manage, "next_scheduled_run_info_shared", {}, raising=False)
    monkeypatch.setattr(qbit_manage, "web_api_queue", MagicMock(), raising=False)
    return qbit_manage


def test_non_failed_exception_in_run_releases_flag_and_records_result(qbm, monkeypatch):
    monkeypatch.setattr(qbm, "Config", MagicMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        qbm.start()

    assert qbm.is_running.value is False
    assert qbm.next_scheduled_run_info_shared["last_run_result"] == "failed"
    assert "last_run" in qbm.next_scheduled_run_info_shared


def test_failed_run_records_failed_result(qbm, monkeypatch):
    monkeypatch.setattr(qbm, "Config", MagicMock(side_effect=Failed("bad config")))

    qbm.start()

    assert qbm.is_running.value is False
    assert qbm.next_scheduled_run_info_shared["last_run_result"] == "failed"


def _health_api(tmp_path, shared):
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "config.yml").write_text("x: 1")
    api = object.__new__(WebAPI)
    for name, value in {
        "config_path": tmp_path,
        "logs_path": tmp_path / "logs",
        "web_api_queue": MagicMock(qsize=lambda: 0),
        "is_running_lock": MagicMock(),
        "next_scheduled_run_info": shared,
    }.items():
        object.__setattr__(api, name, value)
    return api


def test_health_reports_last_run(tmp_path):
    shared = {
        "scheduler_alive": True,
        "scheduler_heartbeat": datetime.now().isoformat(),
        "last_run": "2026-10-12T10:00:00",
        "last_run_result": "success",
    }
    health = asyncio.run(_health_api(tmp_path, shared).health_check())

    assert health["status"] != "unhealthy"
    assert health["application"]["last_run"] == "2026-10-12T10:00:00"
    assert health["application"]["last_run_result"] == "success"
    assert health["application"]["scheduler_alive"] is True


def test_health_unhealthy_when_scheduler_thread_dead(tmp_path):
    shared = {"scheduler_alive": False, "scheduler_heartbeat": datetime.now().isoformat()}
    health = asyncio.run(_health_api(tmp_path, shared).health_check())

    assert health["status"] == "unhealthy"
    assert "Scheduler is not running" in health["issues"]


def test_health_unhealthy_when_heartbeat_stale(tmp_path):
    stale = (datetime.now() - timedelta(minutes=10)).isoformat()
    shared = {"scheduler_alive": True, "scheduler_heartbeat": stale}
    health = asyncio.run(_health_api(tmp_path, shared).health_check())

    assert health["status"] == "unhealthy"
    assert "Scheduler heartbeat is stale" in health["issues"]
