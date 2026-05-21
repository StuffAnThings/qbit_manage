"""Fake objects that mimic the slice of qbittorrent-api / qbit_manage surface
that the production code under test actually touches.

Built from real qBittorrent Web API response shapes (see ``tests/fixtures/qbit_api/``
and ``scripts/capture_qbit_fixtures.py``). Every mutating method records the call
into a ``.calls`` list and updates internal state, so subsequent reads reflect the
change just like the real qBittorrent API would.

The surface is intentionally the UNION of what every ``modules/core/*`` feature
touches, not just share_limits — that way the per-module follow-up test PRs can
reuse these without extending the fakes.
"""

from __future__ import annotations

import copy
import json
from collections import OrderedDict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "qbit_api"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture from tests/fixtures/qbit_api/<name>.json."""
    path = FIXTURES_DIR / f"{name}.json"
    with path.open() as fh:
        return json.load(fh)


# qBittorrent torrent state strings that count as "complete" (mirrors
# qbittorrentapi.TorrentStates.is_complete).
_COMPLETE_STATES = {
    "uploading",
    "stalledUP",
    "queuedUP",
    "pausedUP",
    "forcedUP",
    "checkingUP",
}


class _Tags:
    """Mimics client.torrent_tags namespace."""

    def __init__(self, initial=None):
        self._tags = list(initial or [])
        self.calls = []

    @property
    def tags(self):
        return list(self._tags)

    def delete_tags(self, tag):
        self.calls.append(("delete_tags", tag))
        if isinstance(tag, str):
            self._tags = [t for t in self._tags if t != tag]
        else:
            self._tags = [t for t in self._tags if t not in tag]


class FakeClient:
    """Stand-in for qbittorrentapi.Client. Only the surface qbit_manage uses."""

    def __init__(self, *, tags=None, preferences=None):
        self.torrent_tags = _Tags(tags or [])
        prefs = preferences or {}
        self.app = SimpleNamespace(
            version="v4.6.0",
            web_api_version="2.9.3",
            preferences=SimpleNamespace(
                max_ratio_enabled=prefs.get("max_ratio_enabled", False),
                max_ratio=prefs.get("max_ratio", -1),
                max_seeding_time_enabled=prefs.get("max_seeding_time_enabled", False),
                max_seeding_time=prefs.get("max_seeding_time", -1),
            ),
        )


@dataclass
class _Tracker:
    url: str
    status: int = 2  # 2 = working
    msg: str = ""
    num_seeds: int = 0
    num_peers: int = 0
    num_leeches: int = 0
    num_downloaded: int = 0
    tier: int = 0


class FakeTorrent:
    """Stand-in for qbittorrentapi.TorrentDictionary.

    Construct via ``FakeTorrent.from_fixture(row, **overrides)`` to inherit a
    real qBittorrent payload, or directly with keyword args for ad-hoc cases.
    """

    # Default values for every attribute share_limits.py (and the other core
    # modules) read from a TorrentDictionary. Keeping these centralized means
    # tests can override only the fields they care about.
    _DEFAULTS = {
        "name": "Torrent.NAME.1",
        "hash": "0000000000000000000000000000000000000001",
        "category": "",
        "tags": "",
        "max_ratio": -1.0,
        "max_seeding_time": -1,
        "min_seeding_time": 0,
        "seeding_time": 0,
        "ratio": 0.0,
        "num_complete": 0,
        "num_incomplete": 0,
        "num_seeds": 0,
        "last_activity": 0,
        "up_limit": -1,
        "dl_limit": -1,
        "state": "uploading",
        "content_path": "/data/torrents/Torrent.NAME.1",
        "save_path": "/data/torrents/",
        "size": 1024 * 1024,
        "progress": 1.0,
        "amount_left": 0,
        "completed": 1024 * 1024,
        "completion_on": 1_700_000_000,
        "added_on": 1_700_000_000,
        "uploaded": 0,
        "downloaded": 1024 * 1024,
        "auto_tmm": False,
        "force_start": False,
        "super_seeding": False,
        "seq_dl": False,
        "magnet_uri": "",
        "isPrivate": False,
        "tracker": "http://tracker1.example/announce",
        "ratio_limit": -2.0,
        "seeding_time_limit": -2,
        "availability": -1.0,
        "f_l_piece_prio": False,
    }

    def __init__(self, **kwargs):
        data = {**self._DEFAULTS, **kwargs}
        trackers = data.pop("trackers", None)
        files = data.pop("files", None)
        for key, value in data.items():
            setattr(self, key, value)
        self.trackers = [
            _Tracker(**t) if isinstance(t, dict) else t for t in (trackers or [_Tracker(url="http://tracker1.example/announce")])
        ]
        self.files = files or []
        self.calls = []
        self.state_enum = SimpleNamespace(is_complete=self.state in _COMPLETE_STATES)

    @classmethod
    def from_fixture(cls, row: dict, **overrides) -> FakeTorrent:
        merged = {**row, **overrides}
        # The torrents_info endpoint doesn't return per-torrent trackers — they
        # come from torrents/trackers. Tests that care about trackers pass them
        # via overrides.
        return cls(**merged)

    # qBittorrent's TorrentDictionary supports dict-style access too —
    # share_limits.py uses ``torrent["content_path"]``.
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    # ---- mutating methods (recorded in self.calls) ----------------------------

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))

    def add_tags(self, tags):
        self._record("add_tags", tags=tags)
        existing = [t.strip() for t in (self.tags or "").split(",") if t.strip()]
        new = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(",") if t.strip()]
        for t in new:
            if t not in existing:
                existing.append(t)
        self.tags = ", ".join(existing)

    def remove_tags(self, tags=None):
        self._record("remove_tags", tags=tags)
        existing = [t.strip() for t in (self.tags or "").split(",") if t.strip()]
        remove = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(",") if t.strip()]
        self.tags = ", ".join(t for t in existing if t not in remove)

    def set_share_limits(self, ratio_limit, seeding_time_limit, inactive_seeding_time_limit=-2):
        self._record(
            "set_share_limits",
            ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit,
            inactive_seeding_time_limit=inactive_seeding_time_limit,
        )
        self.max_ratio = ratio_limit
        self.max_seeding_time = seeding_time_limit

    def set_upload_limit(self, limit):
        self._record("set_upload_limit", limit=limit)
        # qBittorrent stores 0 to mean "unlimited", -1 from the API is normalized
        # to 0 in share_limits' read path.
        self.up_limit = 0 if limit == -1 else limit

    def resume(self):
        self._record("resume")

    def pause(self):
        self._record("pause")

    def recheck(self):
        self._record("recheck")

    def delete(self, delete_files=False):
        self._record("delete", delete_files=delete_files)

    def set_category(self, category):
        self._record("set_category", category=category)
        self.category = category

    def set_auto_management(self, enable):
        self._record("set_auto_management", enable=enable)
        self.auto_tmm = enable

    def add_trackers(self, urls):
        self._record("add_trackers", urls=urls)

    def remove_trackers(self, urls):
        self._record("remove_trackers", urls=urls)


@dataclass
class FakeConfig:
    """Stand-in for modules.config.Config — only the attributes ShareLimits reads."""

    share_limits: OrderedDict[str, dict] = field(default_factory=OrderedDict)
    share_limits_tag: str = "~share_limit"
    share_limits_min_seeding_time_tag: str = "MinSeedTimeNotReached"
    share_limits_min_num_seeds_tag: str = "MinSeedsNotMet"
    share_limits_last_active_tag: str = "LastActiveLimitNotReached"
    settings: dict = field(default_factory=lambda: {"share_limits_filter_completed": True})
    root_dir: str = "/data/torrents/"
    remote_dir: str = "/data/torrents/"
    dry_run: bool = False
    loglevel: str = "INFO"
    commands: dict = field(default_factory=lambda: {"share_limits": True, "skip_qb_version_check": False})
    notifications_sent: list = field(default_factory=list)
    notify_calls: list = field(default_factory=list)

    def send_notifications(self, attr):
        self.notifications_sent.append(copy.deepcopy(attr))

    def notify(self, err, function):
        self.notify_calls.append((err, function))


class FakeQbtManager:
    """Stand-in for modules.qbittorrent.Qbt — only the surface ShareLimits reads.

    Pass in the list of torrents you want ``get_torrents`` to return. Filtering
    by ``status_filter`` and ``torrent_hashes`` is implemented to match the real
    qBittorrent Web API behavior.
    """

    def __init__(
        self,
        *,
        torrents=None,
        config=None,
        client=None,
        torrentinfo=None,
        global_max_ratio=2.0,
        global_max_ratio_enabled=False,
        global_max_seeding_time=43200,  # 30 days in minutes
        global_max_seeding_time_enabled=False,
    ):
        self.config = config or FakeConfig()
        self.client = client or FakeClient()
        self._torrents = list(torrents or [])
        self.torrentinfo = torrentinfo or {}
        self.global_max_ratio = global_max_ratio
        self.global_max_ratio_enabled = global_max_ratio_enabled
        self.global_max_seeding_time = global_max_seeding_time
        self.global_max_seeding_time_enabled = global_max_seeding_time_enabled
        # Records of calls — used by tests to assert behavior
        self.tor_delete_recycle_calls = []
        self.cross_seed_map = {}

    def get_torrents(self, params):
        result = list(self._torrents)
        status = params.get("status_filter")
        if status == "completed":
            result = [t for t in result if t.state in _COMPLETE_STATES]
        hashes = params.get("torrent_hashes")
        if hashes:
            wanted = hashes.split("|") if isinstance(hashes, str) else list(hashes)
            result = [t for t in result if t.hash in wanted]
        return result

    def get_tracker_urls(self, trackers):
        return tuple(t.url for t in trackers if t.url.startswith(("http", "udp", "ws")))

    def get_tags(self, urls):
        # Mirror the real Qbt.get_tags shape — a dict with tag/cat/notifiarr/url keys.
        url = urls[0] if urls else ""
        return {"tag": [], "cat": "", "notifiarr": None, "url": url}

    def is_cross_seed(self, torrent):
        return False

    def has_cross_seed(self, torrent):
        return self.cross_seed_map.get(torrent.hash, False)

    def tor_delete_recycle(self, torrent, attr):
        self.tor_delete_recycle_calls.append((torrent, copy.deepcopy(attr)))


# ---- ShareLimits constructor bypass ---------------------------------------


def make_share_limits(qbt_manager):
    """Construct a ShareLimits instance with __init__'s eager work skipped.

    Production ``ShareLimits.__init__`` immediately runs ``update_share_limits()``
    and ``delete_share_limits_suffix_tag()`` — convenient for production, awkward
    for unit-testing individual methods. Tests use this helper to get an instance
    whose attributes are wired up but whose entrypoints haven't fired yet, then
    drive whichever method is under test.
    """
    from modules.core.share_limits import ShareLimits

    instance = object.__new__(ShareLimits)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.stats_tagged = 0
    instance.stats_deleted = 0
    instance.stats_deleted_contents = 0
    instance.status_filter = "completed" if qbt_manager.config.settings["share_limits_filter_completed"] else "all"
    instance.tdel_dict = {}
    instance.root_dir = qbt_manager.config.root_dir
    instance.remote_dir = qbt_manager.config.remote_dir
    instance.share_limits_config = qbt_manager.config.share_limits
    instance.torrents_updated = []
    instance.torrent_hash_checked = []
    instance.share_limits_tag = qbt_manager.config.share_limits_tag
    instance.min_seeding_time_tag = qbt_manager.config.share_limits_min_seeding_time_tag
    instance.min_num_seeds_tag = qbt_manager.config.share_limits_min_num_seeds_tag
    instance.last_active_tag = qbt_manager.config.share_limits_last_active_tag
    instance.group_tag = None
    return instance


def make_group_config(**overrides):
    """Build a share_limits group config dict with sensible defaults.

    Mirrors the defaults that ``modules.config.Config`` produces when parsing
    a share_limits YAML group with all keys defaulted.
    """
    base = {
        "priority": 1.0,
        "include_all_tags": None,
        "include_any_tags": None,
        "exclude_all_tags": None,
        "exclude_any_tags": None,
        "categories": None,
        "cleanup": False,
        "max_ratio": -1.0,
        "max_seeding_time": -1,
        "min_seeding_time": 0,
        "limit_upload_speed": 0,
        "enable_group_upload_speed": False,
        "min_num_seeds": 0,
        "last_active": 0,
        "resume_torrent_after_change": True,
        "add_group_to_tag": True,
        "torrents": [],
    }
    base.update(overrides)
    return base
