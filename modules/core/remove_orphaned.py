import os
from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatch

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

        max_workers = max(os.cpu_count() - 1, 1)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.rem_orphaned()
        self.executor.shutdown()

    def rem_orphaned(self):
        """Remove orphaned files from remote directory"""
        self.stats = 0
        logger.separator("Checking for Orphaned Files", space=False, border=False)
        torrent_files = []
        orphaned_files = []
        excluded_orphan_files = []

        root_files = self.executor.submit(util.get_root_files, self.root_dir, self.remote_dir, self.orphaned_dir)

        # Get an updated list of torrents
        logger.print_line("Locating orphan files", self.config.loglevel)
        torrent_list = self.qbt.get_torrents({"sort": "added_on"})

        torrent_files.extend(
            [
                fullpath
                for fullpathlist in self.executor.map(self.get_full_path_of_torrent_files, torrent_list)
                for fullpath in fullpathlist
            ]
        )

        orphaned_files = set(root_files.result()) - set(torrent_files)

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
            if self.config.orphaned["empty_after_x_days"] == 0:
                body += logger.print_line(
                    f"{'Not Deleting' if self.config.dry_run else 'Deleting'} {num_orphaned} Orphaned files",
                    self.config.loglevel,
                )
            else:
                body += logger.print_line(
                    f"{'Not moving' if self.config.dry_run else 'Moving'} {num_orphaned} Orphaned files "
                    f"to {self.orphaned_dir.replace(self.remote_dir, self.root_dir)}",
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
                orphaned_parent_path = set(self.executor.map(self.handle_orphaned_files, orphaned_files))
                logger.print_line("Removing newly empty directories", self.config.loglevel)
                self.executor.map(
                    lambda directory: util.remove_empty_directories(directory, self.qbt.get_category_save_paths()),
                    orphaned_parent_path,
                )

        else:
            logger.print_line("No Orphaned Files found.", self.config.loglevel)

    def handle_orphaned_files(self, file):
        src = file.replace(self.root_dir, self.remote_dir)
        dest = os.path.join(self.orphaned_dir, file.replace(self.root_dir, ""))
        orphaned_parent_path = os.path.dirname(file).replace(self.root_dir, self.remote_dir)

        """Delete orphaned files directly if empty_after_x_days is set to 0"""
        if self.config.orphaned["empty_after_x_days"] == 0:
            try:
                util.delete_files(src)
            except Exception:
                logger.error(f"Error deleting orphaned file: {file}")
                util.move_files(src, dest, True)
        else:  # Move orphaned files to orphaned directory
            util.move_files(src, dest, True)
        return orphaned_parent_path

    def get_full_path_of_torrent_files(self, torrent):
        torrent_files = map(lambda dict: dict.name, torrent.files)
        save_path = torrent.save_path

        fullpath_torrent_files = []
        for file in torrent_files:
            fullpath = os.path.join(save_path, file)
            # Replace fullpath with \\ if qbm is running in docker (linux) but qbt is on windows
            fullpath = fullpath.replace(r"/", "\\") if ":\\" in fullpath else fullpath
            fullpath_torrent_files.append(fullpath)
        return fullpath_torrent_files
