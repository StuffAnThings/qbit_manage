"""Unit tests for modules/qbittorrent.py — Qbt class.

Coverage:
- get_tracker_urls() — URL extraction, protocol filtering, sentinels ([DHT], [PeX], [LSD])
- is_torrent_private() — boolean checks using private attr and tracker messages
- get_tags() — config-based tracker URL mapping
- get_torrent_info() — torrentinfo cache population, state mapping
- Cross-seed detection (is_cross_seed, has_cross_seed, torrentfiles tracking)
"""

from __future__ import annotations

import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from modules.qbittorrent import Qbt
from modules.qbittorrent import recycle_backup_name
from tests.factories import FakeTorrent
from tests.factories import _Tracker


def make_qbt_config():
    return SimpleNamespace(
        commands={
            "skip_qb_version_check": False,
            "share_limits": False,
            "recheck": False,
            "rem_unregistered": False,
            "tag_tracker_error": False,
            "tag_nohardlinks": False,
        },
        settings={"disable_qbt_default_share_limits": False},
        notify=MagicMock(),
    )


def make_qbt_client():
    client = MagicMock()
    client.app.version = "v5.5.0"
    client.app.web_api_version = "2.11.0"
    client.app.preferences.max_ratio_act = 0
    client.app.preferences.max_ratio_enabled = False
    client.app.preferences.max_ratio = 0
    client.app.preferences.max_seeding_time_enabled = False
    client.app.preferences.max_seeding_time = 0
    return client


class TestAuthentication:
    """Test Qbt authentication configuration."""

    @patch("modules.qbittorrent.Version.is_app_version_supported", return_value=True)
    @patch("modules.qbittorrent.Qbt.get_torrents", return_value=[])
    @patch("modules.qbittorrent.Client")
    @patch("modules.qbittorrent.logger.secret", create=True)
    def test_passes_api_key_to_client(self, _mock_secret, mock_client, _mock_get_torrents, _mock_version_supported):
        client = make_qbt_client()
        mock_client.return_value = client

        Qbt(
            make_qbt_config(),
            {"host": "localhost:8080", "username": None, "password": None, "api_key": "qbt_test_key"},
        )

        mock_client.assert_called_once_with(
            host="localhost:8080",
            username=None,
            password=None,
            api_key="qbt_test_key",
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={"timeout": (45, 60)},
        )
        client.auth_log_in.assert_called_once()

    @patch("modules.qbittorrent.Version.is_app_version_supported", return_value=True)
    @patch("modules.qbittorrent.Qbt.get_torrents", return_value=[])
    @patch("modules.qbittorrent.logger.warning")
    @patch("modules.qbittorrent.Client")
    @patch("modules.qbittorrent.logger.secret", create=True)
    def test_warns_when_api_key_and_password_credentials_are_set(
        self, _mock_secret, mock_client, mock_warning, _mock_get_torrents, _mock_version_supported
    ):
        mock_client.return_value = make_qbt_client()

        Qbt(
            make_qbt_config(),
            {"host": "localhost:8080", "username": "admin", "password": "password", "api_key": "qbt_test_key"},
        )

        mock_warning.assert_called_once_with("qBittorrent API key is set; it takes precedence over username and password.")


# ---- get_tracker_urls tests --------------------------------------------------


class TestGetTrackerUrls:
    """Test Qbt.get_tracker_urls() tracker URL extraction."""

    def test_extracts_http_https_udp_ws_urls(self):
        """Filter out DHT/PeX/LSD sentinels; keep http, https, udp, ws."""
        trackers = [
            _Tracker(url="http://tracker1.example/announce"),
            _Tracker(url="https://tracker2.example/announce"),
            _Tracker(url="udp://tracker3.example:6969/announce"),
            _Tracker(url="ws://tracker4.example/announce"),
            _Tracker(url="** [DHT] **"),
            _Tracker(url="** [PeX] **"),
            _Tracker(url="** [LSD] **"),
        ]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert len(urls) == 4
        assert "http://tracker1.example/announce" in urls
        assert "** [DHT] **" not in urls
        assert "** [PeX] **" not in urls

    def test_returns_tuple(self):
        """get_tracker_urls returns a tuple."""
        trackers = [_Tracker(url="http://tracker1.example/announce")]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert isinstance(urls, tuple)

    def test_empty_trackers_returns_empty_tuple(self):
        """Empty tracker list returns empty tuple."""
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, [])
        assert urls == ()

    def test_filters_non_protocol_urls(self):
        """Filter out URLs without http/https/udp/ws prefix."""
        trackers = [
            _Tracker(url="http://valid.example/announce"),
            _Tracker(url="/announce"),
            _Tracker(url="file:///announce"),
        ]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert len(urls) == 1
        assert "http://valid.example/announce" in urls


# ---- is_torrent_private tests ------------------------------------------------


class TestIsTorrentPrivate:
    """Test Qbt.is_torrent_private() boolean detection."""

    def test_private_attr_true_returns_true(self):
        """If torrent.private == True, return True immediately."""
        torrent = FakeTorrent(private=True)
        qbt = MagicMock(spec=Qbt)
        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True

    def test_private_attr_false_returns_false(self):
        """If torrent.private == False, return False immediately."""
        torrent = FakeTorrent(private=False)
        qbt = MagicMock(spec=Qbt)
        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is False

    def test_no_private_attr_checks_trackers(self):
        """If torrent has no private attr, check tracker messages/URLs."""
        torrent = FakeTorrent(name="test", hash="abc123")
        # Remove the private attribute to simulate old API response
        delattr(torrent, "private")

        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(
            return_value=[
                {"url": "http://tracker1.example/announce", "msg": ""},
                {"url": "http://private.tracker.example/announce", "msg": "private"},
            ]
        )

        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True

    def test_tracker_url_contains_private(self):
        """Detect private=True if tracker URL contains 'private'."""
        torrent = FakeTorrent(name="test", hash="abc123")
        delattr(torrent, "private")

        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(return_value=[{"url": "http://private.example/announce", "msg": ""}])

        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True

    def test_accepts_hash_string_as_torrent_param(self):
        """is_torrent_private accepts torrent hash string (not just object)."""
        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(return_value=[{"url": "http://tracker1.example/announce", "msg": ""}])

        result = Qbt.is_torrent_private(qbt, "abc123xyz")
        assert result is False
        qbt.client.torrents_trackers.assert_called_once_with("abc123xyz")


# ---- get_tags tests ----------------------------------------------------------


class TestGetTags:
    """Test Qbt.get_tags() tracker URL → tag mapping."""

    @patch("modules.qbittorrent.logger")
    def test_returns_dict_shape(self, mock_logger):
        """get_tags returns dict with tag/cat/notifiarr/url keys."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value=None)

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        assert isinstance(result, dict)
        assert "tag" in result
        assert "cat" in result
        assert "notifiarr" in result
        assert "url" in result

    @patch("modules.qbittorrent.logger")
    def test_no_urls_returns_default_other_tag(self, mock_logger):
        """Empty URL list defaults to 'other' tag."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value=["other"])

        result = Qbt.get_tags(qbt, [])
        assert result["url"] == "No http URL found"
        assert result["tag"] == ["other"]

    def test_matches_tracker_config_url(self):
        """If tracker URL matches config key, return that tag/cat."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {"tracker1.example": {"tag": ["t1tag"], "cat": "T1Cat"}}}
        qbt.config.util = MagicMock()
        # Discriminate by the 2nd positional arg (the attribute key name).
        qbt.config.util.check_for_attribute = MagicMock(
            side_effect=lambda *args, **kwargs: ["t1tag"] if args[1] == "tag" else "T1Cat"
        )

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        # URL matched config key → specific tag/cat returned
        assert result["tag"] == ["t1tag"]
        assert result["cat"] == "T1Cat"

    def test_converts_string_tag_to_list(self):
        """If tag is a string, convert to list."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {"tracker1.example": {"tag": "singletag"}}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value="singletag")

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        # String tag input must be converted to a one-element list
        assert result["tag"] == ["singletag"]


# ---- get_torrent_info tests --------------------------------------------------


class TestGetTorrentInfo:
    """Test Qbt.get_torrent_info() torrentinfo cache population."""

    @patch("modules.qbittorrent.logger")
    def test_populates_torrentinfo_dict(self, mock_logger):
        """get_torrent_info populates self.torrentinfo with torrent name keys."""
        torrent = FakeTorrent(
            name="TestTorrent",
            hash="hash123",
            category="TV",
            save_path="/data/torrents/TV",
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = [torrent]
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        # Call the actual method
        Qbt.get_torrent_info(qbt)

        assert qbt.torrentinfo is not None
        assert isinstance(qbt.torrentinfo, dict)

    @patch("modules.qbittorrent.logger")
    def test_populates_torrentvalid_list(self, mock_logger):
        """Torrents with working trackers go to torrentvalid list."""
        torrent = FakeTorrent(
            name="ValidTorrent",
            hash="hash456",
            trackers=[_Tracker(url="http://tracker1.example/announce", status=2)],
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = [torrent]
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        Qbt.get_torrent_info(qbt)

        # Check that torrentvalid list was populated
        assert hasattr(qbt, "torrentvalid")

    @patch("modules.qbittorrent.logger")
    def test_none_tracker_msg_does_not_crash(self, mock_logger):
        """A tracker with msg=None must not crash torrentinfo population (#1358)."""
        torrent = FakeTorrent(
            name="NoneMsgTorrent",
            hash="hashnone",
            trackers=[_Tracker(url="http://tracker1.example/announce", status=4, msg=None)],
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = [torrent]
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        Qbt.get_torrent_info(qbt)

        assert isinstance(qbt.torrentinfo, dict)

    @patch("modules.qbittorrent.logger")
    def test_populates_torrentissue_list(self, mock_logger):
        """Torrents with broken trackers go to torrentissue list."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = []
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        Qbt.get_torrent_info(qbt)

        # Check that torrentissue list was created
        assert hasattr(qbt, "torrentissue")
        assert isinstance(qbt.torrentissue, list)


# ---- Cross-seed detection tests ----------------------------------------------


class TestCrossSeedDetection:
    """Test is_cross_seed, has_cross_seed, add_torrent_files tracking."""

    @patch("modules.qbittorrent.logger")
    def test_is_cross_seed_returns_false_when_downloaded_nonzero(self, mock_logger):
        """is_cross_seed returns False if torrent.downloaded != 0."""
        torrent = FakeTorrent(downloaded=1024)
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {}

        result = Qbt.is_cross_seed(qbt, torrent)
        assert result is False

    def test_add_torrent_files_tracks_original_and_crossseeds(self):
        """add_torrent_files populates cross_seed map correctly."""
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {}

        class FakeFile:
            def __init__(self, name):
                self.name = name

        files = [FakeFile("file1.txt")]
        Qbt.add_torrent_files(qbt, "hash1", files, "/data/torrents/")

        assert "/data/torrents/file1.txt" in qbt.torrentfiles
        assert qbt.torrentfiles["/data/torrents/file1.txt"]["original"] == "hash1"
        assert qbt.torrentfiles["/data/torrents/file1.txt"]["cross_seed"] == []

    def test_add_torrent_files_appends_crossseed_hash(self):
        """Duplicate files append hash to cross_seed list."""
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {}

        class FakeFile:
            def __init__(self, name):
                self.name = name

        files1 = [FakeFile("file1.txt")]
        files2 = [FakeFile("file1.txt")]

        Qbt.add_torrent_files(qbt, "hash1", files1, "/data/torrents/")
        Qbt.add_torrent_files(qbt, "hash2", files2, "/data/torrents/")

        assert qbt.torrentfiles["/data/torrents/file1.txt"]["original"] == "hash1"
        assert "hash2" in qbt.torrentfiles["/data/torrents/file1.txt"]["cross_seed"]

    @patch("modules.qbittorrent.logger")
    def test_has_cross_seed_returns_true_if_files_have_crossseeds(self, mock_logger):
        """has_cross_seed returns True if any file has cross_seed entries."""

        class FakeFile:
            def __init__(self, name):
                self.name = name

        torrent = FakeTorrent(name="Test", hash="hash1", save_path="/data/", files=[FakeFile("file1.txt")])
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {"/data/file1.txt": {"original": "hash1", "cross_seed": ["hash2"]}}

        result = Qbt.has_cross_seed(qbt, torrent)
        assert result is True

    @patch("modules.qbittorrent.logger")
    def test_remove_torrent_files_updates_original_on_delete(self, mock_logger):
        """remove_torrent_files promotes cross_seed[0] to original on delete."""
        torrent = FakeTorrent(hash="hash1")

        class FakeFile:
            def __init__(self, name):
                self.name = name

        torrent.files = [FakeFile("file1.txt")]
        torrent.save_path = "/data/"

        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {"/data/file1.txt": {"original": "hash1", "cross_seed": ["hash2", "hash3"]}}

        Qbt.remove_torrent_files(qbt, torrent)

        assert qbt.torrentfiles["/data/file1.txt"]["original"] == "hash2"
        assert qbt.torrentfiles["/data/file1.txt"]["cross_seed"] == ["hash3"]


# ---- tor_delete_recycle tests ------------------------------------------------


class TestTorDeleteRecycle:
    """Test Qbt.tor_delete_recycle() torrent backups in the recycle bin."""

    @patch("modules.qbittorrent.logger")
    def test_backs_up_torrent_whose_name_contains_path_separator(self, _mock_logger, tmp_path):
        """A "/" in the torrent name must not be treated as a directory in the backup filenames."""
        torrent_name = "Some Series [ENG / EPUB]"
        recycle_dir = tmp_path / ".RecycleBin"
        torrents_dir = tmp_path / "BT_backup"
        torrents_dir.mkdir()
        torrent = FakeTorrent(
            name=torrent_name,
            hash="00000000000000000000000000000000abcdef12",
            save_path=str(tmp_path / "downloads"),
            export=lambda: b"d4:infod4:name4:testee",
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = SimpleNamespace(
            recyclebin={"enabled": True, "split_by_category": False, "save_torrents": True},
            recycle_dir=str(recycle_dir),
            root_dir=str(tmp_path),
            remote_dir=str(tmp_path),
            torrents_dir=str(torrents_dir),
            orphaned={"exclude_patterns": []},
            notify=MagicMock(),
        )
        qbt.current_version = "v5.0.0"
        qbt.torrent_list = [torrent]
        info = {
            "torrents": [torrent_name],
            "torrent_category": "books",
            "torrent_tracker": "https://tracker.example",
            "torrents_deleted_and_contents": False,
        }

        Qbt.tor_delete_recycle(qbt, torrent, info)

        json_file = recycle_dir / "torrents_json" / "Some Series [ENG _ EPUB] [d8695fac].json"
        export_file = recycle_dir / "torrents_export" / "Some Series [ENG _ EPUB] [d8695fac] [abcdef12].torrent"
        assert json.loads(json_file.read_text())["torrent_name"] == torrent_name
        assert export_file.read_bytes() == b"d4:infod4:name4:testee"
        qbt.config.notify.assert_not_called()
        assert ("delete", {"delete_files": False}) in torrent.calls

    @patch("modules.qbittorrent.logger")
    def test_long_name_with_separator_aggregates_into_one_reloadable_backup(self, _mock_logger, tmp_path):
        """A long name keeps its .json extension and a second removal of the same name merges into it."""
        torrent_name = "A" * 240 + "/EPUB"
        recycle_dir = tmp_path / ".RecycleBin"
        torrents_dir = tmp_path / "BT_backup"
        torrents_dir.mkdir()
        qbt = MagicMock(spec=Qbt)
        qbt.config = SimpleNamespace(
            recyclebin={"enabled": True, "split_by_category": False, "save_torrents": True},
            recycle_dir=str(recycle_dir),
            root_dir=str(tmp_path),
            remote_dir=str(tmp_path),
            torrents_dir=str(torrents_dir),
            orphaned={"exclude_patterns": []},
            notify=MagicMock(),
        )
        qbt.current_version = "v5.0.0"
        qbt.torrent_list = []

        for info_hash, tracker in (("1" * 40, "https://tracker1.example"), ("2" * 40, "https://tracker2.example")):
            torrent = FakeTorrent(
                name=torrent_name, hash=info_hash, save_path=str(tmp_path / "downloads"), export=lambda: b"d4:infod4:name4:testee"
            )
            info = {
                "torrents": [torrent_name],
                "torrent_category": "books",
                "torrent_tracker": tracker,
                "torrents_deleted_and_contents": False,
            }
            Qbt.tor_delete_recycle(qbt, torrent, info)

        json_files = list((recycle_dir / "torrents_json").iterdir())
        assert len(json_files) == 1
        assert json_files[0].suffix == ".json"
        torrent_json = json.loads(json_files[0].read_text())
        assert torrent_json["torrent_name"] == torrent_name
        assert set(torrent_json["tracker_torrent_files"]) == {"https://tracker1.example", "https://tracker2.example"}
        qbt.config.notify.assert_not_called()


class TestRecycleBackupName:
    """Test recycle_backup_name() filenames for recycle bin backups."""

    def test_name_without_separator_is_unchanged(self):
        """Existing backups keep their filenames."""
        assert recycle_backup_name("Some Series [ENG - EPUB]") == "Some Series [ENG - EPUB]"

    def test_name_with_separator_does_not_collide_with_replaced_name(self):
        """A name with "/" and the same name with "_" get different backup files."""
        assert recycle_backup_name("Book/EPUB") != recycle_backup_name("Book_EPUB")

    def test_identical_names_share_a_backup_file(self):
        """Cross-seeds with the same name keep aggregating into one backup file."""
        assert recycle_backup_name("Book/EPUB") == recycle_backup_name("Book/EPUB")

    def test_long_name_with_separator_keeps_hash_within_limit(self):
        """The hash survives on a long name, so long names differing only at the end stay distinct."""
        name_a = recycle_backup_name("A" * 240 + "/EPUB")
        name_b = recycle_backup_name("A" * 240 + "/MOBI")
        assert len(name_a) <= 250
        assert name_a.endswith(f" [{hashlib.sha1(('A' * 240 + '/EPUB').encode()).hexdigest()[:8]}]")
        assert name_a != name_b

    def test_overlong_name_without_separator_is_bounded(self):
        """A name too long for a filename is shortened with a hash rather than truncated by save_json."""
        name = recycle_backup_name("A" * 300)
        assert len(name) == 250
        assert name.endswith(f" [{hashlib.sha1(('A' * 300).encode()).hexdigest()[:8]}]")

    def test_only_platform_separators_are_replaced(self, monkeypatch):
        """On POSIX a backslash is a valid filename character and is kept."""
        monkeypatch.setattr(os, "sep", "/")
        monkeypatch.setattr(os, "altsep", None)
        assert recycle_backup_name("Book\\EPUB") == "Book\\EPUB"


class TestGetCategoryInvalidConfig:
    @patch("modules.qbittorrent.logger")
    def test_invalid_category_config_raises_failed_not_system_exit(self, _mock_logger):
        import pytest

        from modules.util import Failed

        fake = SimpleNamespace(config=SimpleNamespace(data={"cat": {"movies": None}}, notify=MagicMock()))

        with pytest.raises(Failed):
            Qbt.get_category(fake, "/data/movies")
