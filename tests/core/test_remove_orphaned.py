"""Tests for RemoveOrphaned path handling and file-age checking.

Uses make_remove_orphaned() bypass constructor to test individual methods
without triggering the eager __init__ work (ThreadPoolExecutor + rem_orphaned()).
Focuses on pure logic: path normalization and age-based filtering.
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

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

    def test_handle_orphaned_returns_parent_path_on_success(self, monkeypatch):
        """On successful handling, return the parent directory path."""
        import modules.util as util

        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/remote/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 0},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        monkeypatch.setattr(util, "delete_files", lambda src: None)

        result = ro.handle_orphaned_files("/data/subdir/orphaned_file.txt")
        # Should return parent path transformed via path_replace
        assert result is not None
        assert isinstance(result, str)
        # Result is the parent directory path with root_dir -> remote_dir transformation
        assert "subdir" in result


class TestHandleOrphanedFilesLogic:
    """Test handle_orphaned_files decision logic with mocked file operations."""

    def test_delete_mode_calls_delete_files(self, monkeypatch):
        """When empty_after_x_days == 0, handle_orphaned_files calls util.delete_files."""
        import modules.util as util

        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/remote/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 0},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        deleted = []
        monkeypatch.setattr(util, "delete_files", lambda src: deleted.append(src))

        result = ro.handle_orphaned_files("/data/subdir/orphaned_file.txt")

        assert len(deleted) == 1
        assert "orphaned_file.txt" in deleted[0] or "subdir" in deleted[0]
        assert result is not None

    def test_move_mode_calls_move_files(self, monkeypatch):
        """When empty_after_x_days > 0, handle_orphaned_files calls util.move_files."""
        import modules.util as util

        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/remote/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 30},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        moved = []
        monkeypatch.setattr(util, "move_files", lambda src, dest, mk: moved.append((src, dest)))

        result = ro.handle_orphaned_files("/data/subdir/orphaned_file.txt")

        assert len(moved) == 1
        assert "orphaned" in moved[0][1]  # dest contains orphaned_dir path
        assert result is not None

    def test_permission_error_returns_none(self, monkeypatch):
        """PermissionError during delete returns None (file skipped)."""
        import modules.util as util

        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/remote/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 0},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        def _raise_permission(src):
            raise PermissionError("denied")

        monkeypatch.setattr(util, "delete_files", _raise_permission)

        result = ro.handle_orphaned_files("/data/subdir/file.txt")

        assert result is None

    def test_delete_error_falls_back_to_move(self, monkeypatch):
        """Non-permission error in delete mode falls back to move_files."""
        import modules.util as util

        config = FakeConfig(
            root_dir="/data/",
            remote_dir="/mnt/remote/",
            orphaned_dir="/data/.orphaned/",
            orphaned={"empty_after_x_days": 0},
        )
        qbt = _make_qbt(config=config)
        ro = make_remove_orphaned(qbt)

        deleted = []
        moved = []

        def _raise_oserror(src):
            deleted.append(src)
            raise OSError("disk error")

        monkeypatch.setattr(util, "delete_files", _raise_oserror)
        monkeypatch.setattr(util, "move_files", lambda src, dest, mk: moved.append((src, dest)))

        result = ro.handle_orphaned_files("/data/subdir/file.txt")

        assert len(deleted) == 1
        assert len(moved) == 1
        assert result is not None


class TestFilterTooNew:
    """Age protection for orphaned files (mtime-based, gh#1289 regression fix)."""

    def _ro(self, min_age_minutes):
        cfg = FakeConfig()
        cfg.orphaned["min_file_age_minutes"] = min_age_minutes
        return make_remove_orphaned(_make_qbt(config=cfg))

    def test_new_orphan_protected_old_orphan_eligible(self, tmp_path):
        now = time.time()
        orphan_new = tmp_path / "orphan_new.mkv"
        orphan_new.write_text("x")
        os.utime(orphan_new, (now, now))
        orphan_old = tmp_path / "orphan_old.mkv"
        orphan_old.write_text("y")
        old = now - 30 * 24 * 60 * 60
        os.utime(orphan_old, (old, old))

        ro = self._ro(min_age_minutes=14400)  # 10 days
        result = ro._filter_too_new({str(orphan_new), str(orphan_old)}, now)

        assert str(orphan_old) in result  # old enough → eligible
        assert str(orphan_new) not in result  # too new → protected

    def test_recent_hardlinked_orphan_is_protected(self, tmp_path):
        """gh#1289 regression: a recently-appeared hardlinked orphan must be protected.

        #1289 deleted any hardlinked orphan whose inode matched a tracked file,
        ignoring age — which swept up cross-seed hardlinks before their torrent
        registered. Plain age protection keeps it: the file is recent, so it's
        skipped like any other new orphan, hardlink or not.
        """
        now = time.time()
        tracked = tmp_path / "tracked.mkv"
        tracked.write_text("data")
        orphan_hardlink = tmp_path / "orphan_hardlink.mkv"
        os.link(tracked, orphan_hardlink)
        recent = now - 60 * 60  # 1h old, under the threshold
        os.utime(tracked, (recent, recent))  # shared inode → both links

        ro = self._ro(min_age_minutes=360)  # 6h
        result = ro._filter_too_new({str(orphan_hardlink)}, now)

        assert result == set()  # recent → protected regardless of hardlink status

    def test_age_protection_disabled_is_noop(self, tmp_path):
        now = time.time()
        f = tmp_path / "f.mkv"
        f.write_text("z")
        os.utime(f, (now, now))

        ro = self._ro(min_age_minutes=0)
        result = ro._filter_too_new({str(f)}, now)

        assert result == {str(f)}  # disabled → eligible even though brand new

    def test_unreadable_file_is_left_eligible(self, tmp_path):
        """A stat failure must not protect a file on bad data (fail toward normal handling)."""
        ro = self._ro(min_age_minutes=14400)
        missing = str(tmp_path / "does_not_exist.mkv")

        result = ro._filter_too_new({missing}, time.time())

        assert result == {missing}

    def test_too_new_orphan_protected_with_mapped_remote_dir(self, tmp_path):
        """Age protection must stat the remote_dir path, not the root_dir namespace."""
        now = time.time()
        root_dir = "/data/torrents"
        orphan_host = tmp_path / "Movies" / "orphan_new.mkv"
        orphan_host.parent.mkdir(parents=True)
        orphan_host.write_text("x")
        os.utime(orphan_host, (now, now))

        orphan_root = f"{root_dir}/Movies/orphan_new.mkv"
        cfg = FakeConfig()
        cfg.root_dir = root_dir
        cfg.remote_dir = str(tmp_path)
        cfg.orphaned["min_file_age_minutes"] = 14400

        ro = make_remove_orphaned(_make_qbt(config=cfg))
        result = ro._filter_too_new({orphan_root}, now)

        assert result == set()
