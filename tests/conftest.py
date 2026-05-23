"""Shared pytest fixtures and test-time monkey patches."""

from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _FakeLogger:
    """Stand-in for modules.logs.MyLogger.

    Production code calls logger.print_line / insert_space / separator / trace /
    info / warning / etc. We need a fake that returns the same *shape* of values
    (print_line returns a list, insert_space returns a string) so the share_limits
    code path doesn't crash.
    """

    def __init__(self):
        self.messages = []

    def separator(self, *args, **kwargs):
        return None

    def print_line(self, msg, loglevel="INFO", *args, **kwargs):
        self.messages.append(str(msg))
        return [str(msg)]

    def insert_space(self, msg, space_length=0):
        return f"{' ' * space_length}{msg}"

    def trace(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def info_center(self, *args, **kwargs):
        return None

    def dryrun(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def critical(self, *args, **kwargs):
        return None

    def stacktrace(self, *args, **kwargs):
        return None

    def secret(self, *args, **kwargs):
        return None


@pytest.fixture(autouse=True)
def fake_logger(monkeypatch):
    """Replace the real MyLogger (or the bootstrap logging.getLogger stub) with
    a fake everywhere the production code reads it from.
    """
    fake = _FakeLogger()
    # share_limits.py does ``from modules import util`` and ``logger = util.logger``
    # at module import time, so we need to patch both the source attribute and
    # the cached module-level reference.
    from modules import util

    monkeypatch.setattr(util, "logger", fake, raising=False)
    from modules.core import remove_unregistered as remove_unregistered_mod
    from modules.core import share_limits as share_limits_mod

    monkeypatch.setattr(share_limits_mod, "logger", fake, raising=False)
    monkeypatch.setattr(remove_unregistered_mod, "logger", fake, raising=False)
    return fake


# ---- factory-based fixtures ---------------------------------------------------


@pytest.fixture
def torrent_factory():
    """Return a callable that builds FakeTorrent instances with overrides."""
    from tests.factories import FakeTorrent

    def _make(**overrides):
        return FakeTorrent(**overrides)

    return _make


@pytest.fixture
def fixture_torrent():
    """Return a callable that builds a FakeTorrent from a real qbit fixture row."""
    from tests.factories import FakeTorrent
    from tests.factories import load_fixture

    rows = load_fixture("torrents_info")

    def _make(index=0, **overrides):
        return FakeTorrent.from_fixture(rows[index], **overrides)

    return _make


@pytest.fixture
def config_factory():
    """Return a callable that builds FakeConfig instances."""
    from tests.factories import FakeConfig

    def _make(**overrides):
        return FakeConfig(**overrides)

    return _make


@pytest.fixture
def group_config_factory():
    from tests.factories import make_group_config

    return make_group_config


@pytest.fixture
def qbt_manager_factory():
    """Return a callable that builds FakeQbtManager instances."""
    from tests.factories import FakeQbtManager

    def _make(**overrides):
        return FakeQbtManager(**overrides)

    return _make


@pytest.fixture
def share_limits_factory(qbt_manager_factory, config_factory):
    """Return a callable that builds a ShareLimits instance ready for unit testing.

    Usage:
        sl = share_limits_factory(
            torrents=[t1, t2],
            share_limits_config=OrderedDict({"groupA": make_group_config(...)}),
        )
    """
    from tests.factories import make_share_limits

    def _make(*, torrents=None, share_limits_config=None, config_overrides=None, qbt_overrides=None):
        config = config_factory(
            share_limits=share_limits_config if share_limits_config is not None else OrderedDict(),
            **(config_overrides or {}),
        )
        qbt = qbt_manager_factory(
            torrents=torrents or [],
            config=config,
            **(qbt_overrides or {}),
        )
        return make_share_limits(qbt)

    return _make


@pytest.fixture
def remove_unregistered_factory(qbt_manager_factory, config_factory):
    """Return a callable that builds a RemoveUnregistered instance ready for unit testing."""
    from tests.factories import make_remove_unregistered

    def _make(*, torrents=None, config_overrides=None, qbt_overrides=None, hashes=None):
        config = config_factory(**(config_overrides or {}))
        qbt = qbt_manager_factory(
            torrents=torrents or [],
            config=config,
            **(qbt_overrides or {}),
        )
        return make_remove_unregistered(qbt, hashes=hashes)

    return _make
