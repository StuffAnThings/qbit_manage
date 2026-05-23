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
        # production code reads `.private` (Qbt.is_torrent_private). qbittorrent-api
        # fixtures also use `private`, not `isPrivate`. (Copilot review #1198:140.)
        "private": False,
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

    def get(self, key, default=None):
        """Dict-like .get() method for optional keys."""
        return getattr(self, key, default)

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

    def set_share_limits(self, ratio_limit, seeding_time_limit, inactive_seeding_time_limit=-2, share_limit_action=None):
        self._record(
            "set_share_limits",
            ratio_limit=ratio_limit,
            seeding_time_limit=seeding_time_limit,
            inactive_seeding_time_limit=inactive_seeding_time_limit,
        )
        # Production code + tests reason about per-torrent ratio_limit /
        # seeding_time_limit (the qbittorrent-api field names), not the
        # legacy max_ratio / max_seeding_time aliases. (Copilot review
        # #1198:201.) Update the canonical fields so subsequent reads
        # see the correct value.
        self.ratio_limit = ratio_limit
        self.seeding_time_limit = seeding_time_limit
        self.inactive_seeding_time_limit = inactive_seeding_time_limit
        # Keep legacy aliases populated for any test still reading them.
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


class _FakeWebhooksFactory:
    """Minimal stand-in for webhooks_factory used by Category and TagNoHardLinks."""

    def __init__(self):
        self.notify_calls = []

    def notify(self, torrents_updated, notify_attr, group_by=None):
        self.notify_calls.append((list(torrents_updated), list(notify_attr), group_by))


@dataclass
class FakeConfig:
    """Stand-in for modules.config.Config — only the attributes ShareLimits reads."""

    share_limits: OrderedDict[str, dict] = field(default_factory=OrderedDict)
    share_limits_tag: str = "~share_limit"
    share_limits_min_seeding_time_tag: str = "MinSeedTimeNotReached"
    share_limits_min_num_seeds_tag: str = "MinSeedsNotMet"
    share_limits_last_active_tag: str = "LastActiveLimitNotReached"
    tracker_error_tag: str = "TrackerError"
    stalled_tag: str = "Stalled"
    private_tag: str = "Private"
    settings: dict = field(
        default_factory=lambda: {
            "share_limits_filter_completed": True,
            "cat_filter_completed": True,
            "cat_update_all": False,
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
            "tag_nohardlinks_filter_completed": True,
            "rem_unregistered_filter_completed": True,
            "rem_unregistered_grace_minutes": 0,
            "rem_unregistered_max_torrents": 0,
            "rem_unregistered_ignore_list": [],
        }
    )
    root_dir: str = "/data/torrents/"
    remote_dir: str = "/data/torrents/"
    orphaned_dir: str = "/data/torrents/.orphaned/"
    dry_run: bool = False
    loglevel: str = "INFO"
    commands: dict = field(
        default_factory=lambda: {
            "share_limits": True,
            "skip_qb_version_check": False,
            "rem_unregistered": True,
            "tag_tracker_error": True,
        }
    )
    share_limits_custom_tags: list = field(default_factory=list)
    notifications_sent: list = field(default_factory=list)
    notify_calls: list = field(default_factory=list)
    # Category-specific
    cat_change: dict = field(default_factory=dict)
    # TagNoHardLinks-specific
    nohardlinks: dict = field(default_factory=dict)
    nohardlinks_tag: str = "noHL"
    # RemoveOrphaned-specific
    orphaned: dict = field(
        default_factory=lambda: {
            "empty_after_x_days": 0,
            "max_orphaned_files_to_delete": 100,
            "exclude_patterns": [],
            "min_file_age_minutes": 0,
        }
    )
    # webhooks_factory stand-in
    webhooks_factory: Any = field(default_factory=_FakeWebhooksFactory)

    def send_notifications(self, attr):
        self.notifications_sent.append(copy.deepcopy(attr))

    def notify(self, err, function, *args, **kwargs):
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
        # Mirror Qbt.torrentfiles — populated by add_torrent_files in production,
        # exposed here so cross-seed-aware tests can pre-seed it directly.
        self.torrentfiles = {}

    def get_torrents(self, params):
        result = list(self._torrents)
        status = params.get("status_filter")
        if status == "completed":
            result = [t for t in result if t.state in _COMPLETE_STATES]
        elif status == "paused":
            # Match qBittorrent states that start with "paused"
            result = [t for t in result if t.state.startswith("paused")]
        hashes = params.get("torrent_hashes")
        if hashes:
            wanted = hashes.split("|") if isinstance(hashes, str) else list(hashes)
            result = [t for t in result if t.hash in wanted]
        category = params.get("category")
        if category is not None:
            result = [t for t in result if t.category == category]
        return result

    def get_tracker_urls(self, trackers):
        return tuple(t.url for t in trackers if t.url.startswith(("http", "udp", "ws")))

    def get_tags(self, urls):
        # Mirror the real Qbt.get_tags shape — a dict with tag/cat/notifiarr/url keys.
        url = urls[0] if urls else ""
        return {"tag": [], "cat": "", "notifiarr": None, "url": url}

    def is_torrent_private(self, torrent):
        """Return whether a torrent is private (based on .private attribute)."""
        return getattr(torrent, "private", False)

    def is_cross_seed(self, torrent):
        return False

    def has_cross_seed(self, torrent):
        return self.cross_seed_map.get(torrent.hash, False)

    def tor_delete_recycle(self, torrent, attr):
        self.tor_delete_recycle_calls.append((torrent, copy.deepcopy(attr)))

    def get_category(self, path):
        """Return 'Uncategorized' for all save paths (overridable via subclassing or monkeypatching)."""
        return "Uncategorized"

    @property
    def torrent_list(self):
        """Return all torrents (shorthand for get_torrents with no filter)."""
        return list(self._torrents)

    @property
    def torrentissue(self):
        """Return torrents with issues (those in torrentinfo with issues)."""
        return self._torrents

    @property
    def torrentvalid(self):
        """Return valid torrents (those without issues)."""
        return self._torrents


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
    instance.hashes = None
    instance.share_limits_custom_tags = qbt_manager.config.share_limits_custom_tags
    instance.group_tag = None
    return instance


def make_category(qbt_manager):
    """Construct a Category instance with __init__'s eager work skipped.

    Production ``Category.__init__`` immediately runs ``category()`` and
    ``change_categories()`` — awkward for unit tests. This bypass wires up the
    same attributes so tests can call individual methods directly.
    """
    from modules.core.category import Category

    instance = object.__new__(Category)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.hashes = None
    instance.stats = 0
    instance.torrents_updated = []
    instance.notify_attr = []
    instance.uncategorized_mapping = "Uncategorized"
    instance.status_filter = "completed" if qbt_manager.config.settings["cat_filter_completed"] else "all"
    instance.cat_update_all = qbt_manager.config.settings["cat_update_all"]
    return instance


def make_tags(qbt_manager):
    """Construct a Tags instance with __init__'s eager work skipped.

    Production ``Tags.__init__`` immediately runs ``tags()`` and calls
    ``webhooks_factory.notify``. This bypass wires up the same attributes
    so tests can call individual methods directly.
    """
    from modules.core.tags import Tags

    instance = object.__new__(Tags)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.stats = 0
    instance.share_limits_tag = qbt_manager.config.share_limits_tag
    instance.stalled_tag = getattr(qbt_manager.config, "stalled_tag", "Stalled")
    instance.private_tag = getattr(qbt_manager.config, "private_tag", "Private")
    instance.tag_stalled_torrents = qbt_manager.config.settings.get("tag_stalled_torrents", False)
    instance.torrents_updated = []
    instance.notify_attr = []
    instance.hashes = None
    return instance


def make_recheck(qbt_manager):
    """Construct a ReCheck instance with __init__'s eager work skipped.

    Production ``ReCheck.__init__`` immediately runs ``recheck()`` and calls
    ``webhooks_factory.notify``. This bypass wires up the same attributes
    so tests can call individual methods directly.
    """
    from modules.core.recheck import ReCheck

    instance = object.__new__(ReCheck)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.hashes = None
    instance.stats_resumed = 0
    instance.stats_rechecked = 0
    instance.torrents_updated_recheck = []
    instance.notify_attr_recheck = []
    instance.torrents_updated_resume = []
    instance.notify_attr_resume = []
    return instance


def make_tag_nohardlinks(qbt_manager):
    """Construct a TagNoHardLinks instance with __init__'s eager work skipped.

    Production ``TagNoHardLinks.__init__`` immediately runs ``tag_nohardlinks()``
    and calls ``webhooks_factory.notify``. This bypass wires up the same
    attributes so tests can call individual methods directly.
    """
    from modules.core.tag_nohardlinks import TagNoHardLinks

    instance = object.__new__(TagNoHardLinks)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.hashes = None
    instance.stats_tagged = 0
    instance.stats_untagged = 0
    instance.root_dir = qbt_manager.config.root_dir
    instance.remote_dir = qbt_manager.config.remote_dir
    instance.nohardlinks = qbt_manager.config.nohardlinks
    instance.nohardlinks_tag = qbt_manager.config.nohardlinks_tag
    instance.torrents_updated_tagged = []
    instance.notify_attr_tagged = []
    instance.torrents_updated_untagged = []
    instance.notify_attr_untagged = []
    instance.status_filter = "completed" if qbt_manager.config.settings["tag_nohardlinks_filter_completed"] else "all"
    return instance


def make_remove_unregistered(qbt_manager, hashes=None):
    """Construct a RemoveUnregistered instance with __init__'s eager work skipped.

    Production ``RemoveUnregistered.__init__`` immediately runs ``rem_unregistered()``
    which calls ``remove_previous_errors()`` and ``process_torrent_issues()``.
    This bypass wires up the same attributes so tests can call individual methods
    directly without triggering the eager work.
    """
    from modules.core.remove_unregistered import RemoveUnregistered

    instance = object.__new__(RemoveUnregistered)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.stats_deleted = 0
    instance.stats_deleted_contents = 0
    instance.stats_tagged = 0
    instance.stats_untagged = 0
    instance.tor_error_summary = ""
    instance.tag_error = qbt_manager.config.tracker_error_tag
    instance.cfg_rem_unregistered = qbt_manager.config.commands.get("rem_unregistered", True)
    instance.cfg_tag_error = qbt_manager.config.commands.get("tag_tracker_error", True)
    instance.rem_unregistered_ignore_list = qbt_manager.config.settings.get("rem_unregistered_ignore_list", [])
    instance.filter_completed = qbt_manager.config.settings.get("rem_unregistered_filter_completed", True)
    instance.rem_unregistered_grace_minutes = qbt_manager.config.settings.get("rem_unregistered_grace_minutes", 0)
    instance.rem_unregistered_max_torrents = qbt_manager.config.settings.get("rem_unregistered_max_torrents", 0)
    instance.hashes = hashes
    instance.tracker_del_count = {}
    instance.torrents_updated_issue = []
    instance.notify_attr_issue = []
    instance.torrents_updated_unreg = []
    instance.notify_attr_unreg = []
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
        "min_torrent_size": None,
        "max_torrent_size": None,
        "cleanup": False,
        "max_ratio": -1.0,
        "max_seeding_time": -1,
        "max_last_active": -1,
        "min_seeding_time": 0,
        "limit_upload_speed": 0,
        "upload_speed_on_limit_reached": 0,
        "enable_group_upload_speed": False,
        "min_num_seeds": 0,
        "min_last_active": 0,
        "resume_torrent_after_change": True,
        "add_group_to_tag": True,
        "custom_tag": None,
        "reset_upload_speed_on_unmet_minimums": True,
        "torrents": [],
    }
    base.update(overrides)
    return base


def make_remove_orphaned(qbt_manager):
    """Construct a RemoveOrphaned instance with __init__'s eager work skipped.

    Production ``RemoveOrphaned.__init__`` immediately runs ``rem_orphaned()``
    with ThreadPoolExecutor — awkward for unit tests. This bypass wires up the
    same attributes so tests can call individual methods directly.
    """
    from modules.core.remove_orphaned import RemoveOrphaned

    instance = object.__new__(RemoveOrphaned)
    instance.qbt = qbt_manager
    instance.config = qbt_manager.config
    instance.client = qbt_manager.client
    instance.stats = 0
    instance.remote_dir = qbt_manager.config.remote_dir
    instance.root_dir = qbt_manager.config.root_dir
    instance.orphaned_dir = qbt_manager.config.orphaned_dir
    instance.executor = None  # Skip ThreadPoolExecutor for tests
    return instance
