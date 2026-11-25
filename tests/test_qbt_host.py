"""QBT_HOST must reach the web server bind address."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture
def load_qbm(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["qbit_manage.py"])
    monkeypatch.setenv("QBT_CONFIG_DIR", str(tmp_path))

    def load(**env):
        for key in ("QBT_HOST", "QBM_DOCKER"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(
            "modules.util.in_docker", lambda: "QBM_DOCKER" in env
        )  # a containerized runner must not change the result
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delitem(sys.modules, "qbit_manage", raising=False)
        import qbit_manage

        return qbit_manage

    yield load
    sys.modules.pop("qbit_manage", None)


@pytest.mark.parametrize("value", ["127.0.0.2", "127.0.0.1", "192.168.1.5", "localhost"])
def test_qbt_host_env_is_used(load_qbm, value):
    assert load_qbm(QBT_HOST=value).host == value


def test_qbt_host_env_wins_in_docker(load_qbm):
    assert load_qbm(QBT_HOST="127.0.0.2", QBM_DOCKER="true").host == "127.0.0.2"


def test_default_host_is_loopback(load_qbm):
    assert load_qbm().host == "127.0.0.1"
