import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
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

        # Try to use ThreadPoolExecutor, but fall back to synchronous if thread creation fails
        try:
            # Use reasonable thread count: min of 4 or CPU count, but at least 2
            max_workers = min(4, max(2, os.cpu_count() or 2))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                self.executor = executor
                self.rem_orphaned()
        except RuntimeError as e:
            if "can't start new thread" in str(e):
                logger.warning("Thread creation failed, falling back to synchronous processing")
                # Fall back to synchronous processing
                self.executor = None
                self.rem_orphaned()
            else:
                raise

    def rem_orphaned(self):
        """Remove orphaned files from remote directory"""
        start_time = time.time()
        self.stats = 0
        logger.separator("Checking for Orphaned Files", space=False, border=False)

        # Get torrents and files in parallel
        logger.print_line("Locating orphan files", self.config.loglevel)

        # Fetch torrents and root files (parallel if executor available, synchronous otherwise)
        if self.executor:
            torrent_list_future = self.executor.submit(self.qbt.get_torrents, {"sort": "added_on"})
            root_files_future = self.executor.submit(util.get_root_files, self.root_dir, self.remote_dir, self.orphaned_dir)
            torrent_list = torrent_list_future.result()
            root_files = set(root_files_future.result())
        else:
            torrent_list = self.qbt.get_torrents({"sort": "added_on"})
            root_files = set(util.get_root_files(self.root_dir, self.remote_dir, self.orphaned_dir))

        # Process torrent files (parallel if executor available, synchronous otherwise)
        torrent_files = set()
        if self.executor:
            for fullpath_list in self.executor.map(self.get_full_path_of_torrent_files, torrent_list):
                torrent_files.update(fullpath_list)
        else:
            for torrent in torrent_list:
                torrent_files.update(self.get_full_path_of_torrent_files(torrent))

        # Find orphaned files efficiently
        orphaned_files = root_files - torrent_files

        # Process exclude patterns efficiently
        if self.config.orphaned["exclude_patterns"]:
            logger.print_line("Processing orphan exclude patterns")
            exclude_patterns = [
                util.path_replace(exclude_pattern, self.remote_dir, self.root_dir)
                for exclude_pattern in self.config.orphaned["exclude_patterns"]
            ]

            # Use set comprehension for efficient filtering
            excluded_files = {file for file in orphaned_files if any(fnmatch(file, pattern) for pattern in exclude_patterns)}
            orphaned_files -= excluded_files

        # === AGE PROTECTION: Don't touch files that are "too new" (likely being created/uploaded) ===
        orphaned_files = self._filter_too_new(orphaned_files, torrent_files, time.time())

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
        self.stats = num_orphaned
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
                f"to {util.path_replace(self.orphaned_dir, self.remote_dir, self.root_dir)}",
                self.config.loglevel,
            )

        attr = {
            "function": "rem_orphaned",
            "title": f"Removing {num_orphaned} Orphaned Files",
            "body": "\n".join(body),
            "orphaned_files": list(orphaned_files),
            "orphaned_directory": util.path_replace(self.orphaned_dir, self.remote_dir, self.root_dir),
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
                if self.executor:
                    batch_results = self.executor.map(self.handle_orphaned_files, batch)
                else:
                    batch_results = [self.handle_orphaned_files(file) for file in batch]
                # Filter out None values (skipped files due to permission errors)
                valid_paths = [path for path in batch_results if path is not None]
                orphaned_parent_paths.update(valid_paths)

            # Remove empty directories
            if orphaned_parent_paths:
                logger.print_line("Removing newly empty directories", self.config.loglevel)
                exclude_patterns = [
                    util.path_replace(exclude_pattern, self.remote_dir, self.root_dir)
                    for exclude_pattern in self.config.orphaned.get("exclude_patterns", [])
                ]

                # Process directories (parallel if executor available, synchronous otherwise)
                if self.executor:
                    for _ in self.executor.map(
                        lambda directory: util.remove_empty_directories(
                            directory, self.qbt.get_category_save_paths(), exclude_patterns
                        ),
                        orphaned_parent_paths,
                    ):
                        pass
                else:
                    for directory in orphaned_parent_paths:
                        util.remove_empty_directories(directory, self.qbt.get_category_save_paths(), exclude_patterns)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Remove orphaned command completed in {duration:.2f} seconds")

    def _host_path(self, path):
        """Map a root_dir-namespace path to the host-accessible remote_dir path."""
        return util.path_replace(path, self.root_dir, self.remote_dir)

    def _filter_too_new(self, orphaned_files, torrent_files, now):
        """Drop orphaned files younger than ``min_file_age_minutes`` from the deletion set.

        Inode-aware exception (gh#1095): a hardlinked orphan whose inode is also
        referenced by a tracked torrent file inherits the tracked sibling's mtime
        (the shared inode is kept fresh while that torrent seeds), so it can never
        age past the threshold. Such an orphan is a stale hardlink of a tracked
        file and is safe to clean regardless of mtime — the data survives via the
        tracked path. Age protection still applies to every other orphan.
        """
        min_file_age_minutes = self.config.orphaned.get("min_file_age_minutes", 0)
        if min_file_age_minutes <= 0:
            return orphaned_files

        def stat_file(file):
            try:
                st = os.stat(self._host_path(file))
                return file, (now - st.st_mtime) / 60, st.st_nlink, (st.st_dev, st.st_ino)
            except PermissionError as e:
                logger.warning(f"Permission denied checking file age for {file}: {e}")
            except Exception as e:
                logger.error(f"Error checking file age for {file}: {e}")
            # Stat failed — leave file eligible for cleanup rather than protecting it on bad data.
            return file, None, None, None

        stats = []
        if self.executor:
            futures = {self.executor.submit(stat_file, file): file for file in orphaned_files}
            for future in futures:
                try:
                    stats.append(future.result(timeout=30.0))  # 30 second timeout per file
                except FuturesTimeoutError:
                    logger.warning(f"Timeout checking file age (permission issue?): {futures[future]}")
                except Exception as e:
                    logger.error(f"Unexpected error during age check for {futures[future]}: {e}")
        else:
            stats = [stat_file(file) for file in orphaned_files]

        # Only pay for the tracked-inode index if a "too new" orphan is hardlinked.
        tracked_inodes = None
        protected_files = set()
        for file, age_minutes, nlink, inode in stats:
            if age_minutes is None or age_minutes >= min_file_age_minutes:
                continue  # unreadable or old enough — leave eligible for handling
            if nlink and nlink > 1:
                if tracked_inodes is None:
                    tracked_inodes = self._tracked_inodes(torrent_files)
                if inode in tracked_inodes:
                    logger.print_line(
                        f"Cleaning hardlinked orphan (shares an inode with a tracked file; the "
                        f"{age_minutes:.1f} min mtime age is the tracked sibling's, not the orphan's): "
                        f"{os.path.basename(file)}",
                        self.config.loglevel,
                    )
                    continue
            protected_files.add(file)
            logger.print_line(
                f"Skipping orphaned file (too new): {os.path.basename(file)} "
                f"(age {age_minutes:.1f} mins < {min_file_age_minutes} mins)",
                self.config.loglevel,
            )

        if protected_files:
            logger.print_line(
                f"Protected {len(protected_files)} orphaned files from deletion due to age filter "
                f"(min_file_age_minutes={min_file_age_minutes})",
                self.config.loglevel,
            )
        return orphaned_files - protected_files

    def _tracked_inodes(self, torrent_files):
        """Return the set of ``(st_dev, st_ino)`` for tracked torrent files present on disk."""

        def stat_inode(path):
            try:
                st = os.stat(self._host_path(path))
                return (st.st_dev, st.st_ino)
            except OSError:
                return None

        results = self.executor.map(stat_inode, torrent_files) if self.executor else map(stat_inode, torrent_files)
        return {inode for inode in results if inode is not None}

    def handle_orphaned_files(self, file):
        """Handle orphaned file with improved error handling and batching"""
        src = util.path_replace(file, self.root_dir, self.remote_dir)
        dest = os.path.join(self.orphaned_dir, util.path_replace(file, self.root_dir, ""))
        orphaned_parent_path = util.path_replace(os.path.dirname(file), self.root_dir, self.remote_dir)

        try:
            if self.config.orphaned["empty_after_x_days"] == 0:
                util.delete_files(src)
            else:
                util.move_files(src, dest, True)
        except PermissionError as e:
            logger.warning(f"Permission denied processing orphaned file {file}: {e}. Skipping file.")
            # Return None to indicate this file should not be counted in parent path processing
            return None
        except Exception as e:
            logger.error(f"Error processing orphaned file {file}: {e}")
            if self.config.orphaned["empty_after_x_days"] == 0:
                # Fallback to move if delete fails
                try:
                    util.move_files(src, dest, True)
                except PermissionError as move_e:
                    logger.warning(f"Permission denied moving orphaned file {file}: {move_e}. Skipping file.")
                    return None
                except Exception as move_e:
                    logger.error(f"Error moving orphaned file {file}: {move_e}")

        return orphaned_parent_path

    def get_full_path_of_torrent_files(self, torrent):
        """Get full paths for torrent files with improved path handling"""
        # Use download_path for incomplete torrents so that files actively
        # downloading to a separate directory are not incorrectly flagged as
        # orphans.
        if not torrent.state_enum.is_complete and torrent.get("download_path", ""):
            base_path = torrent["download_path"]
        else:
            base_path = torrent.save_path

        # Use list comprehension for better performance with cross-platform
        # path normalization
        fullpath_torrent_files = [os.path.normpath(os.path.join(base_path, file.name)) for file in torrent.files]

        return fullpath_torrent_files
