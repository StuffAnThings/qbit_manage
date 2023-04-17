import os
from multiprocessing import Pool, cpu_count
from itertools import repeat
from fnmatch import fnmatch

from modules import util

logger = util.logger
_config = None

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

        self.rem_orphaned()

    def rem_orphaned(self):
        """Remove orphaned files from remote directory"""
        self.stats = 0
        logger.separator("Checking for Orphaned Files", space=False, border=False)
        torrent_files = []
        root_files = []
        orphaned_files = []
        excluded_orphan_files = []

        if self.remote_dir != self.root_dir:
            local_orphaned_dir = self.orphaned_dir.replace(self.remote_dir, self.root_dir)
            root_files = [
                os.path.join(path.replace(self.remote_dir, self.root_dir), name)
                for path, subdirs, files in os.walk(self.remote_dir)
                for name in files
                if local_orphaned_dir not in path
            ]
        else:
            root_files = [
                os.path.join(path, name)
                for path, subdirs, files in os.walk(self.root_dir)
                for name in files
                if self.orphaned_dir not in path
            ]


        # Get an updated list of torrents
        logger.print_line("Removing torrent files from orphans", self.config.loglevel)
        torrent_list = self.qbt.get_torrents({"sort": "added_on"})
        logger.print_line("Fetched torrents", self.config.loglevel)
        for torrent in torrent_list:
            for file in torrent.files:
                fullpath = os.path.join(torrent.save_path, file.name)
                # Replace fullpath with \\ if qbm is running in docker (linux) but qbt is on windows
                fullpath = fullpath.replace(r"/", "\\") if ":\\" in fullpath else fullpath
                torrent_files.append(fullpath)

        orphaned_files = set(root_files) - set(torrent_files)

        if self.config.orphaned["exclude_patterns"]:
            logger.print_line("Processing orphan exclude patterns")
            exclude_patterns = [
                exclude_pattern.replace(self.remote_dir, self.root_dir)
                for exclude_pattern in self.config.orphaned["exclude_patterns"]
            ]
            excluded_orphan_files = [
                file
                for file in orphaned_files
                for exclude_pattern in exclude_patterns
                if fnmatch(file, exclude_pattern)
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
                f"{'Did not move' if self.config.dry_run else 'Moved'} {num_orphaned} Orphaned files "
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
            logger.info("Cleaning up any empty directories...")
            if not self.config.dry_run:
                with Pool(processes = cpu_count()) as pool:
                    orphaned_parent_path = set(pool.map(move_orphan, orphaned_files))

                    logger.print_line("Removing orphan dirs", self.config.loglevel)
                    pool.starmap(util.remove_empty_directories, zip(orphaned_parent_path, repeat("**/*")))
        else:
            logger.print_line("No Orphaned Files found.", self.config.loglevel)

def move_orphan(file):
    src = file.replace(_config.root_dir, _config.remote_dir) # Could be optimized to only run when root != remote
    dest = os.path.join(_config.orphaned_dir, file.replace(_config.root_dir, ""))
    util.move_files(src, dest, True)
    return os.path.dirname(file).replace(_config.root_dir, _config.remote_dir) # Another candidate for micro optimizing
