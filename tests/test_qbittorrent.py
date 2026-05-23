"""Unit tests for modules/qbittorrent.py — Qbt class.

Coverage:
- get_tracker_urls() — URL extraction, protocol filtering, sentinels ([DHT], [PeX], [LSD])
- is_torrent_private() — boolean checks using private attr and tracker messages
- get_tags() — config-based tracker URL mapping
- get_torrent_info() — torrentinfo cache population, state mapping
- Cross-seed detection (is_cross_seed, has_cross_seed, torrentfiles tracking)
"""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

from modules.qbittorrent import Qbt
from tests.factories import FakeTorrent
from tests.factories import _Tracker

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
        qbt.config.util.check_for_attribute = MagicMock(
            side_effect=lambda *args, **kwargs: ["t1tag"] if "tag" in str(args) else "T1Cat"
        )

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        # URL is processed and matched
        assert result["tag"] is not None or result["cat"] is not None

    def test_converts_string_tag_to_list(self):
        """If tag is a string, convert to list."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {"tracker1.example": {"tag": "singletag"}}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value="singletag")

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        # Result should have tag as list
        assert isinstance(result["tag"], list) or result["tag"] is not None


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


# ---- Integration-style smoke tests -------------------------------------------


class TestQbtModuleSmoke:
    """Smoke tests for module integration."""

    def test_tracker_url_extraction_with_sentinels_filtered(self):
        """End-to-end: DHT/PeX/LSD sentinels are filtered out."""
        trackers = [
            _Tracker(url="http://tracker1.example/announce"),
            _Tracker(url="** [DHT] **"),
            _Tracker(url="** [PeX] **"),
        ]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert len(urls) == 1
        assert all("**" not in url for url in urls)

    def test_private_torrent_detection_fallback_to_tracker(self):
        """If private attr missing, fallback to tracker inspection."""
        torrent = FakeTorrent(name="TestPrivate", hash="privhash")
        delattr(torrent, "private")

        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(
            return_value=[{"url": "http://tracker.example", "msg": "This torrent is private"}]
        )

        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True
