import os
from fnmatch import fnmatch
from itertools import repeat
from multiprocessing import cpu_count
from multiprocessing import Pool

from modules import util

logger = util.logger


class RemoveOrphaned:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0

        self.remote_dir = qbit_manager.config.remote_dir
        self.root_dir = qbit_manager.config.root_dir
        self.orphaned_dir = qbit_manager.config.orphaned_dir

        global _config
        _config = self.config
        self.pool = Pool(processes=max(cpu_count() - 1, 1), initializer=init_pool, initargs=(self.config,))
        self.rem_orphaned()
        self.cleanup_pool()

    def rem_orphaned(self):
        """Remove orphaned files from remote directory"""
        self.stats = 0
        logger.separator("Checking for Orphaned Files", space=False, border=False)
        torrent_files = []
        root_files = []
        orphaned_files = []
        excluded_orphan_files = []

        root_files = util.get_root_files(self.remote_dir, self.root_dir, self.orphaned_dir)

        # Get an updated list of torrents
        logger.print_line("Locating orphan files", self.config.loglevel)
        torrent_list = self.qbt.get_torrents({"sort": "added_on"})
        torrent_files_and_save_path = []
        for torrent in torrent_list:
            torrent_files = []
            for torrent_files_dict in torrent.files:
                torrent_files.append(torrent_files_dict.name)
            torrent_files_and_save_path.append((torrent_files, torrent.save_path))
        torrent_files.extend(
            [
                fullpath
                for fullpathlist in self.pool.starmap(get_full_path_of_torrent_files, torrent_files_and_save_path)
                for fullpath in fullpathlist
                if fullpath not in torrent_files
            ]
        )

        orphaned_files = set(root_files) - set(torrent_files)

        if self.config.orphaned["exclude_patterns"]:
            logger.print_line("Processing orphan exclude patterns")
            exclude_patterns = [
                exclude_pattern.replace(self.remote_dir, self.root_dir)
                for exclude_pattern in self.config.orphaned["exclude_patterns"]
            ]
            excluded_orphan_files = [
                file for file in orphaned_files for exclude_pattern in exclude_patterns if fnmatch(file, exclude_pattern)
            ]

        orphaned_files = set(orphaned_files) - set(excluded_orphan_files)

        if orphaned_files:
            orphaned_files = sorted(orphaned_files)
            os.makedirs(self.orphaned_dir, exist_ok=True)
            body = []
            num_orphaned = len(orphaned_files)
            logger.print_line(f"{num_orphaned} Orphaned files found", self.config.loglevel)
            body += logger.print_line("\n".join(orphaned_files), self.config.loglevel)
            body += logger.print_line(
                f"{'Not moving' if self.config.dry_run else 'Moving'} {num_orphaned} Orphaned files "
                f"to {self.orphaned_dir.replace(self.remote_dir,self.root_dir)}",
                self.config.loglevel,
            )

            attr = {
                "function": "rem_orphaned",
                "title": f"Removing {num_orphaned} Orphaned Files",
                "body": "\n".join(body),
                "orphaned_files": list(orphaned_files),
                "orphaned_directory": self.orphaned_dir.replace(self.remote_dir, self.root_dir),
                "total_orphaned_files": num_orphaned,
            }
            self.config.send_notifications(attr)
            # Delete empty directories after moving orphan files
            if not self.config.dry_run:
                orphaned_parent_path = set(self.pool.map(move_orphan, orphaned_files))
                logger.print_line("Removing newly empty directories", self.config.loglevel)
                self.pool.starmap(util.remove_empty_directories, zip(orphaned_parent_path, repeat("**/*")))

        else:
            logger.print_line("No Orphaned Files found.", self.config.loglevel)

    def cleanup_pool(self):
        self.pool.close()
        self.pool.join()


def init_pool(conf):
    global _config
    _config = conf


def get_full_path_of_torrent_files(torrent_files, save_path):
    fullpath_torrent_files = []
    for file in torrent_files:
        fullpath = os.path.join(save_path, file)
        # Replace fullpath with \\ if qbm is running in docker (linux) but qbt is on windows
        fullpath = fullpath.replace(r"/", "\\") if ":\\" in fullpath else fullpath
        fullpath_torrent_files.append(fullpath)
    return fullpath_torrent_files


def move_orphan(file):
    src = file.replace(_config.root_dir, _config.remote_dir)  # Could be optimized to only run when root != remote
    dest = os.path.join(_config.orphaned_dir, file.replace(_config.root_dir, ""))
    util.move_files(src, dest, True)
    return os.path.dirname(file).replace(_config.root_dir, _config.remote_dir)  # Another candidate for micro optimizing
