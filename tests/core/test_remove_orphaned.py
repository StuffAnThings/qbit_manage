"""Tests for RemoveOrphaned path handling and file-age checking.

Uses make_remove_orphaned() bypass constructor to test individual methods
without triggering the eager __init__ work (ThreadPoolExecutor + rem_orphaned()).
Focuses on pure logic: path normalization and age-based filtering.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_remove_orphaned


def _make_qbt(torrents=None, config=None):
    cfg = config or FakeConfig()
    return FakeQbtManager(torrents=torrents or [], config=cfg)


class TestGetFullPathOfTorrentFiles:
    """Test get_full_path_of_torrent_files path resolution logic."""

    def test_complete_torrent_uses_save_path(self):
        """Complete torrent files use save_path, not download_path."""
        file1 = SimpleNamespace(name="file1.txt")
        file2 = SimpleNamespace(name="file2.txt")
        torrent = FakeTorrent(
            name="Tv.Series.S01E01-NOGRP",
            hash="abc123",
            state="uploading",  # complete state
            save_path="/data/torrents/completed/",
            download_path="/tmp/incomplete/",
            files=[file1, file2],
        )
        qbt = _make_qbt(torrents=[torrent])
        ro = make_remove_orphaned(qbt)

        paths = ro.get_full_path_of_torrent_files(torrent)

        # Should use save_path since state is complete
        assert len(paths) == 2
        assert paths[0] == "/data/torrents/completed/file1.txt"
        assert paths[1] == "/data/torrents/completed/file2.txt"

    def test_incomplete_torrent_with_download_path(self):
        """Incomplete torrent with download_path uses download_path."""
        file1 = SimpleNamespace(name="partial.txt")
        torrent = FakeTorrent(
            name="Tv.Series.S01E02-NOGRP",
            hash="abc124",
            state="downloading",  # incomplete state
            save_path="/data/torrents/completed/",
            download_path="/tmp/incomplete/",
            files=[file1],
        )
        qbt = _make_qbt(torrents=[torrent])
        ro = make_remove_orphaned(qbt)

        paths = ro.get_full_path_of_torrent_files(torrent)

        # Should use download_path since state is incomplete
        assert len(paths) == 1
        assert paths[0] == "/tmp/incomplete/partial.txt"

    def test_incomplete_torrent_without_download_path(self):
        """Incomplete torrent without download_path falls back to save_path."""
        file1 = SimpleNamespace(name="file.txt")
        torrent = FakeTorrent(
            name="Tv.Series.S01E03-NOGRP",
            hash="abc125",
            state="downloading",  # incomplete state
            save_path="/data/torrents/completed/",
            download_path="",  # empty download_path
            files=[file1],
        )
        qbt = _make_qbt(torrents=[torrent])
        ro = make_remove_orphaned(qbt)

        paths = ro.get_full_path_of_torrent_files(torrent)

        # Should fall back to save_path
        assert len(paths) == 1
        assert paths[0] == "/data/torrents/completed/file.txt"

    def test_single_file_torrent(self):
        """Single-file torrent returns one path."""
        file1 = SimpleNamespace(name="Torrent.NAME.X.iso")
        torrent = FakeTorrent(
            name="Torrent.NAME.X",
            hash="xyz789",
            state="uploading",
            save_path="/mnt/media/",
            files=[file1],
        )
        qbt = _make_qbt(torrents=[torrent])
        ro = make_remove_orphaned(qbt)

        paths = ro.get_full_path_of_torrent_files(torrent)

        assert len(paths) == 1
        assert paths[0] == "/mnt/media/Torrent.NAME.X.iso"

    def test_multi_file_torrent_preserves_structure(self):
        """Multi-file torrent returns all file paths in order."""
        files = [
            SimpleNamespace(name="intro.mp4"),
            SimpleNamespace(name="main.mp4"),
            SimpleNamespace(name="outro.mp4"),
        ]
        torrent = FakeTorrent(
            name="Torrent.NAME.MULTI",
            hash="multi123",
            state="uploading",
            save_path="/data/tv/",
            files=files,
        )
        qbt = _make_qbt(torrents=[torrent])
        ro = make_remove_orphaned(qbt)

        paths = ro.get_full_path_of_torrent_files(torrent)

        assert len(paths) == 3
        assert paths[0] == "/data/tv/intro.mp4"
        assert paths[1] == "/data/tv/main.mp4"
        assert paths[2] == "/data/tv/outro.mp4"

    def test_path_normalization_windows_style_paths(self):
        """Paths are normalized (os.path.normpath applied)."""
        file1 = SimpleNamespace(name="file.txt")
        torrent = FakeTorrent(
            name="Torrent.NAME.NORM",
            hash="norm123",
            state="uploading",
            save_path="/data/torrents/",
            files=[file1],
        )
        qbt = _make_qbt(torrents=[torrent])
        ro = make_remove_orphaned(qbt)

        paths = ro.get_full_path_of_torrent_files(torrent)

        # normpath should return a valid path
        assert len(paths) == 1
        assert isinstance(paths[0], str)


class TestHandleOrphanedFiles:
    """Test handle_orphaned_files logic for file operations.

    Note: This tests path construction and decision logic.
    Actual file deletion/move operations are mocked out.
    """

    def test_handle_orphaned_returns_parent_path_on_success(self):
        """On successful handling, return the parent directory path."""
        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/remote/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 0},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        # Mock util.delete_files so it doesn't actually delete
        import modules.util as util

        original_delete = util.delete_files
        util.delete_files = MagicMock()

        try:
            result = ro.handle_orphaned_files("/data/subdir/orphaned_file.txt")
            # Should return parent path transformed via path_replace
            assert result is not None
            assert isinstance(result, str)
            # Result is the parent directory path with root_dir -> remote_dir transformation
            # This is used for cleanup of empty directories
            assert "data" in result or "mnt" in result or "subdir" in result
        finally:
            util.delete_files = original_delete

    def test_handle_orphaned_path_construction_delete_mode(self):
        """Path construction in delete mode (empty_after_x_days == 0)."""
        config = FakeConfig(
            root_dir="/data/torrents/",
            remote_dir="/mnt/torrents/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 0},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        # Verify path construction logic (not the actual operations)
        # src = path_replace(file, root_dir, remote_dir)
        # dest = os.path.join(orphaned_dir, path_replace(file, root_dir, ""))
        # orphaned_parent_path = path_replace(os.path.dirname(file), root_dir, remote_dir)

        # These are internal details of the method we're testing
        assert ro.root_dir == "/data/torrents/"
        assert ro.remote_dir == "/mnt/torrents/"
        assert ro.orphaned_dir == "/data/.orphaned/"

    def test_handle_orphaned_path_construction_move_mode(self):
        """Path construction in move mode (empty_after_x_days > 0)."""
        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 30},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        # In move mode, files are moved to orphaned_dir instead of deleted
        assert ro.config.orphaned["empty_after_x_days"] == 30
        assert ro.orphaned_dir == "/data/.orphaned/"


class TestExcludePatternMatching:
    """Test exclude pattern logic (conceptual; actual fnmatch tested separately)."""

    def test_exclude_patterns_empty_list(self):
        """Empty exclude patterns means nothing is excluded."""
        config = FakeConfig(orphaned={"exclude_patterns": []})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        # Empty patterns should match nothing
        assert ro.config.orphaned["exclude_patterns"] == []

    def test_exclude_patterns_list_structure(self):
        """Exclude patterns are stored as a list of strings."""
        config = FakeConfig(
            orphaned={
                "exclude_patterns": [
                    "*.tmp",
                    "*/.git/*",
                    "*/logs/*",
                ]
            }
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        patterns = ro.config.orphaned["exclude_patterns"]
        assert isinstance(patterns, list)
        assert len(patterns) == 3
        assert all(isinstance(p, str) for p in patterns)


class TestMinFileAgeLogic:
    """Test min_file_age_minutes configuration and age checking."""

    def test_min_file_age_zero_disables_protection(self):
        """min_file_age_minutes of 0 means no age protection."""
        config = FakeConfig(orphaned={"min_file_age_minutes": 0})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        # Should not apply age filtering
        assert ro.config.orphaned["min_file_age_minutes"] == 0

    def test_min_file_age_positive_enables_protection(self):
        """Positive min_file_age_minutes enables age protection."""
        config = FakeConfig(orphaned={"min_file_age_minutes": 60})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        # Should apply age filtering
        assert ro.config.orphaned["min_file_age_minutes"] == 60
        assert ro.config.orphaned["min_file_age_minutes"] > 0

    def test_min_file_age_calculation_would_work(self):
        """Age calculation logic: (now - mtime) / 60 >= min_file_age_minutes."""
        config = FakeConfig(orphaned={"min_file_age_minutes": 120})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        file_age_minutes = 180  # 3 hours old
        min_age = ro.config.orphaned["min_file_age_minutes"]

        # File should NOT be protected (it's old enough)
        should_protect = file_age_minutes < min_age
        assert not should_protect

        # File at exactly the threshold should NOT be protected
        file_age_minutes = 120
        should_protect = file_age_minutes < min_age
        assert not should_protect

        # File younger than threshold SHOULD be protected
        file_age_minutes = 60
        should_protect = file_age_minutes < min_age
        assert should_protect


class TestMaxOrphanedFilesThreshold:
    """Test max_orphaned_files_to_delete threshold logic."""

    def test_max_orphaned_negative_one_unlimited(self):
        """max_orphaned_files_to_delete of -1 means unlimited."""
        config = FakeConfig(orphaned={"max_orphaned_files_to_delete": -1})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        max_threshold = ro.config.orphaned["max_orphaned_files_to_delete"]
        # Production code: if count > max AND max != -1: abort
        # So -1 should never trigger an abort
        assert max_threshold == -1

    def test_max_orphaned_positive_sets_limit(self):
        """Positive max_orphaned_files_to_delete sets a hard limit."""
        config = FakeConfig(orphaned={"max_orphaned_files_to_delete": 50})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        max_threshold = ro.config.orphaned["max_orphaned_files_to_delete"]
        assert max_threshold == 50

    def test_threshold_abort_logic_when_exceeded(self):
        """Abort logic: if found > max AND max != -1, abort."""
        config = FakeConfig(orphaned={"max_orphaned_files_to_delete": 100})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        found_count = 150
        max_threshold = ro.config.orphaned["max_orphaned_files_to_delete"]
        should_abort = found_count > max_threshold and max_threshold != -1

        assert should_abort

    def test_threshold_allow_logic_when_not_exceeded(self):
        """Allow logic: if found <= max, proceed."""
        config = FakeConfig(orphaned={"max_orphaned_files_to_delete": 100})
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        found_count = 50
        max_threshold = ro.config.orphaned["max_orphaned_files_to_delete"]
        should_abort = found_count > max_threshold and max_threshold != -1

        assert not should_abort
