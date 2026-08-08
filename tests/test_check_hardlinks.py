"""Regression tests for category-aware hardlink detection."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.util import CheckHardLinks


def _directory(path: Path | str) -> str:
    return os.path.join(str(path), "")


def _config(root: Path | str, categories: dict, remote: Path | str | None = None):
    root_dir = _directory(root)
    return SimpleNamespace(
        root_dir=root_dir,
        remote_dir=_directory(remote) if remote is not None else root_dir,
        orphaned_dir="",
        recycle_dir="",
        data={"cat": categories},
    )


def _file(path: Path, size: int = 1024) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def _link(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, destination)
    return destination


def _notify(*_args):
    return None


def test_category_local_file_link_is_ignored(tmp_path):
    category_path = tmp_path / "cross-seed"
    source = _file(category_path / "source.mkv")
    _link(source, category_path / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(category_path)}))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", True) is True


def test_link_outside_category_still_counts(tmp_path):
    category_path = tmp_path / "cross-seed"
    source = _file(category_path / "source.mkv")
    _link(source, category_path / "copy.mkv")
    _link(source, tmp_path / "library" / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(category_path)}))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", True) is False


def test_false_category_default_counts_local_link(tmp_path):
    category_path = tmp_path / "cross-seed"
    source = _file(category_path / "source.mkv")
    _link(source, category_path / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(category_path)}))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", False) is False


def test_ignore_root_dir_takes_precedence(tmp_path):
    category_path = tmp_path / "cross-seed"
    source = _file(category_path / "source.mkv")
    _link(source, tmp_path / "other-category" / "copy.mkv")
    checker = CheckHardLinks(
        _config(
            tmp_path,
            {
                "CrossSeed": str(category_path),
                "Other": str(tmp_path / "other-category"),
            },
        )
    )

    assert checker.nohardlink(source, _notify, True, "CrossSeed", True) is True


def test_folder_ignores_category_local_links(tmp_path):
    category_path = tmp_path / "cross-seed"
    torrent = category_path / "torrent"
    source = _file(torrent / "video.mkv", size=2048)
    _link(source, category_path / "duplicate" / "video.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(category_path)}))

    assert checker.nohardlink(torrent, _notify, False, "CrossSeed", True) is True


def test_folder_detects_link_outside_category(tmp_path):
    category_path = tmp_path / "cross-seed"
    torrent = category_path / "torrent"
    source = _file(torrent / "video.mkv", size=2048)
    _link(source, category_path / "duplicate" / "video.mkv")
    _link(source, tmp_path / "library" / "video.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(category_path)}))

    assert checker.nohardlink(torrent, _notify, False, "CrossSeed", True) is False


def test_multiple_paths_for_category_are_combined(tmp_path):
    first = tmp_path / "cross-seed-a"
    second = tmp_path / "cross-seed-b"
    source = _file(first / "video.mkv")
    _link(source, second / "video.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": [str(first), str(second)]}))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", True) is True


def test_most_specific_nested_category_owns_file(tmp_path):
    parent = tmp_path / "tv"
    child = parent / "4k"
    source = _file(child / "source.mkv")
    _link(source, child / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"TV": str(parent), "TV4K": str(child)}))

    assert checker.nohardlink(source, _notify, False, "TV4K", True) is True
    assert checker.nohardlink(source, _notify, False, "TV", True) is False


def test_glob_category_paths_are_indexed(tmp_path):
    category_pattern = str(tmp_path / "cross-seed" / "*")
    source = _file(tmp_path / "cross-seed" / "one" / "source.mkv")
    _link(source, tmp_path / "cross-seed" / "two" / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": category_pattern}))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", True) is True


def test_glob_category_path_can_match_ancestor_directory(tmp_path):
    category_pattern = str(tmp_path / "cross-seed" / "*" / "complete")
    source = _file(tmp_path / "cross-seed" / "one" / "complete" / "torrent" / "source.mkv")
    _link(source, tmp_path / "cross-seed" / "two" / "complete" / "torrent" / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": category_pattern}))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", True) is True


def test_deeper_glob_scope_wins_over_concrete_parent(tmp_path):
    category_root = tmp_path / "cross-seed"
    concrete_parent = category_root / "one"
    glob_path = str(category_root / "*" / "complete")
    source = _file(concrete_parent / "complete" / "torrent" / "source.mkv")
    _link(source, concrete_parent / "complete" / "duplicate" / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"Parent": str(concrete_parent), "Complete": glob_path}))

    assert checker.nohardlink(source, _notify, False, "Complete", True) is True
    assert checker.nohardlink(source, _notify, False, "Parent", True) is False


def test_remote_mapping_uses_accessible_category_path(tmp_path):
    logical_root = Path(os.sep) / "logical" / "qbit-root"
    remote_root = tmp_path / "remote"
    source = _file(remote_root / "cross-seed" / "source.mkv")
    _link(source, remote_root / "cross-seed" / "copy.mkv")
    checker = CheckHardLinks(_config(logical_root, {"CrossSeed": str(logical_root / "cross-seed")}, remote=remote_root))

    assert checker.nohardlink(source, _notify, False, "CrossSeed", True) is True


def test_inode_index_uses_device_and_inode_identity(tmp_path):
    source = _file(tmp_path / "source.mkv")
    _link(source, tmp_path / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"Root": str(tmp_path)}))
    source_stat = source.stat()

    assert checker.inode_count[(source_stat.st_dev, source_stat.st_ino)] == 2


def test_missing_category_fails_safe(tmp_path):
    category_path = tmp_path / "cross-seed"
    source = _file(category_path / "source.mkv")
    _link(source, category_path / "copy.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(category_path)}))

    assert checker.nohardlink(source, _notify, False, "Missing", True) is False


def test_missing_category_does_not_create_false_positive(tmp_path):
    source = _file(tmp_path / "cross-seed" / "source.mkv")
    checker = CheckHardLinks(_config(tmp_path, {"CrossSeed": str(tmp_path / "cross-seed")}))

    assert checker.nohardlink(source, _notify, False, "Missing", True) is True


def test_missing_file_preserves_empty_folder_result(tmp_path):
    checker = CheckHardLinks(_config(tmp_path, {"Root": str(tmp_path)}))

    assert checker.nohardlink(tmp_path / "missing.mkv", _notify, False, "Root", True) is True


def test_inode_indexes_are_built_in_one_pass(tmp_path, monkeypatch):
    _file(tmp_path / "source.mkv")
    calls = 0
    original = CheckHardLinks.get_inode_count

    def count_calls(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(CheckHardLinks, "get_inode_count", count_calls)

    CheckHardLinks(_config(tmp_path, {"Root": str(tmp_path)}))

    assert calls == 1


@pytest.mark.parametrize(
    ("file_path", "category_path"),
    [
        (r"C:\\Torrents\\Movies\\film.mkv", r"C:\\Torrents\\Movies"),
        (r"\\\\server\\share\\Movies\\film.mkv", r"\\\\server\\share\\Movies"),
    ],
)
def test_category_path_matching_preserves_windows_and_unc_boundaries(file_path, category_path):
    assert CheckHardLinks._path_matches_category(file_path, category_path) is True
    assert CheckHardLinks._path_matches_category(file_path, category_path + "-other") is False
