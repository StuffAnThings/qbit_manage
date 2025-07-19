import os
import time
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

        max_workers = max(os.cpu_count() * 2, 4)  # Increased workers for I/O bound operations
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            self.executor = executor
            self.rem_orphaned()

    def rem_orphaned(self):
        """Remove orphaned files from remote directory"""
        start_time = time.time()
        self.stats = 0
        logger.separator("Checking for Orphaned Files", space=False, border=False)

        # Get torrents and files in parallel
        logger.print_line("Locating orphan files", self.config.loglevel)

        # Parallel fetch torrents and root files
        torrent_list_future = self.executor.submit(self.qbt.get_torrents, {"sort": "added_on"})
        root_files_future = self.executor.submit(util.get_root_files, self.root_dir, self.remote_dir, self.orphaned_dir)

        # Process torrent files in parallel
        torrent_list = torrent_list_future.result()

        # Use generator expression to reduce memory usage
        torrent_files = set()
        for fullpath_list in self.executor.map(self.get_full_path_of_torrent_files, torrent_list):
            torrent_files.update(fullpath_list)

        # Get root files
        root_files = set(root_files_future.result())

        # Find orphaned files efficiently
        orphaned_files = root_files - torrent_files

        # Process exclude patterns efficiently
        if self.config.orphaned["exclude_patterns"]:
            logger.print_line("Processing orphan exclude patterns")
            exclude_patterns = [
                exclude_pattern.replace(self.remote_dir, self.root_dir)
                for exclude_pattern in self.config.orphaned["exclude_patterns"]
            ]

            # Use set comprehension for efficient filtering
            excluded_files = {file for file in orphaned_files if any(fnmatch(file, pattern) for pattern in exclude_patterns)}
            orphaned_files -= excluded_files

        # Early return if no orphaned files
        if not orphaned_files:
            logger.print_line("No Orphaned Files found.", self.config.loglevel)
            return

        # Check threshold
        max_orphaned_files_to_delete = self.config.orphaned.get("max_orphaned_files_to_delete")
        if len(orphaned_files) > max_orphaned_files_to_delete and max_orphaned_files_to_delete != -1:
            e = (
                f"Too many orphaned files detected ({len(orphaned_files)}). "
                f"Max Threshold for deletion is set to {max_orphaned_files_to_delete}. "
                "Aborting deletion to avoid accidental data loss."
            )
            self.config.notify(e, "Remove Orphaned", False)
            logger.info(f"Orphaned files detected: {orphaned_files}")
            logger.warning(e)
            return

        # Process orphaned files
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

        # Batch process orphaned files
        if not self.config.dry_run:
            orphaned_parent_paths = set()

            # Process files in batches to reduce I/O overhead
            batch_size = 100
            for i in range(0, len(orphaned_files), batch_size):
                batch = orphaned_files[i : i + batch_size]
                batch_results = self.executor.map(self.handle_orphaned_files, batch)
                orphaned_parent_paths.update(batch_results)

            # Remove empty directories
            if orphaned_parent_paths:
                logger.print_line("Removing newly empty directories", self.config.loglevel)
                exclude_patterns = [
                    exclude_pattern.replace(self.remote_dir, self.root_dir)
                    for exclude_pattern in self.config.orphaned.get("exclude_patterns", [])
                ]

                # Process directories in parallel
                self.executor.map(
                    lambda directory: util.remove_empty_directories(
                        directory, self.qbt.get_category_save_paths(), exclude_patterns
                    ),
                    orphaned_parent_paths,
                )

        else:
            logger.print_line("No Orphaned Files found.", self.config.loglevel)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Remove orphaned command completed in {duration:.2f} seconds")

    def handle_orphaned_files(self, file):
        """Handle orphaned file with improved error handling and batching"""
        src = file.replace(self.root_dir, self.remote_dir)
        dest = os.path.join(self.orphaned_dir, file.replace(self.root_dir, ""))
        orphaned_parent_path = os.path.dirname(file).replace(self.root_dir, self.remote_dir)

        try:
            if self.config.orphaned["empty_after_x_days"] == 0:
                util.delete_files(src)
            else:
                util.move_files(src, dest, True)
        except Exception as e:
            logger.error(f"Error processing orphaned file {file}: {e}")
            if self.config.orphaned["empty_after_x_days"] == 0:
                # Fallback to move if delete fails
                util.move_files(src, dest, True)

        return orphaned_parent_path

    def get_full_path_of_torrent_files(self, torrent):
        """Get full paths for torrent files with improved path handling"""
        save_path = torrent.save_path

        # Use list comprehension for better performance
        fullpath_torrent_files = [
            os.path.join(save_path, file.name).replace(r"/", "\\")
            if ":\\" in os.path.join(save_path, file.name)
            else os.path.join(save_path, file.name)
            for file in torrent.files
        ]

        return fullpath_torrent_files
