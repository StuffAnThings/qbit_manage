"""Tests for the shareLimitsMode parameter required by qBittorrent Web API 2.15.3+.

qBittorrent 5.3.0 (Web API 2.16.2) rejects torrents/setShareLimits with
"Missing required parameters: shareLimitsMode" when the param is absent.
qbit_manage must send it on 2.15.3+ and leave older servers untouched.
"""

from __future__ import annotations

import pytest

from modules.core.share_limits import _parse_api_version
from tests.factories import FakeClient


def _calls_of(torrent, name):
    return [c for c in torrent.calls if c[0] == name]


def _sl(share_limits_factory, version):
    return share_limits_factory(qbt_overrides={"client": FakeClient(web_api_version=version)})


def _reset_via_min_seeds(sl, torrent):
    sl.has_reached_seed_limit(
        torrent=torrent,
        max_ratio=-1,
        max_seeding_time=-1,
        max_last_active=-1,
        min_seeding_time=0,
        min_num_seeds=5,
        min_last_active=0,
        resume_torrent=True,
        tracker="http://tracker1.example/announce",
        reset_upload_speed_on_unmet_minimums=True,
    )


@pytest.mark.parametrize("version", ["2.15.3", "2.16.0", "2.16.2", "2.20.0", "3.0.0"])
def test_set_limits_sends_mode_on_new_api(share_limits_factory, torrent_factory, version):
    sl = _sl(share_limits_factory, version)
    t = torrent_factory()
    sl.set_limits(t, max_ratio=2.0, max_seeding_time=60)
    assert _calls_of(t, "set_share_limits")[0][1]["share_limits_mode"] == "Default"


@pytest.mark.parametrize("version", ["2.9.3", "2.11.4", "2.15.0", "2.15.2"])
def test_set_limits_omits_mode_on_old_api(share_limits_factory, torrent_factory, version):
    sl = _sl(share_limits_factory, version)
    t = torrent_factory()
    sl.set_limits(t, max_ratio=2.0, max_seeding_time=60)
    assert _calls_of(t, "set_share_limits")[0][1]["share_limits_mode"] is None


def test_reset_path_sends_mode_on_new_api(share_limits_factory, torrent_factory):
    sl = _sl(share_limits_factory, "2.16.2")
    t = torrent_factory(num_complete=2, tags="")
    _reset_via_min_seeds(sl, t)
    assert _calls_of(t, "set_share_limits")[0][1]["share_limits_mode"] == "Default"


def test_reset_path_omits_mode_on_old_api(share_limits_factory, torrent_factory):
    sl = _sl(share_limits_factory, "2.9.3")
    t = torrent_factory(num_complete=2, tags="")
    _reset_via_min_seeds(sl, t)
    assert _calls_of(t, "set_share_limits")[0][1]["share_limits_mode"] is None


@pytest.mark.parametrize("version", ["2.15.2-rc1"])
def test_parse_api_version_uses_leading_digits(version):
    assert _parse_api_version(version) == (2, 15, 2)


@pytest.mark.parametrize("failure", ["raises", "absent"])
def test_set_limits_caches_mode_fallback(share_limits_factory, torrent_factory, failure):
    sl = _sl(share_limits_factory, "2.16.2")
    if failure == "raises":

        class BrokenApp:
            @property
            def web_api_version(self):
                raise RuntimeError("version unavailable")

        sl.client.app = BrokenApp()
    else:
        sl.client.app = object()

    assert sl._mode_kwargs() == {}
    cached = sl._share_limits_mode_kwargs
    assert sl._mode_kwargs() is cached
