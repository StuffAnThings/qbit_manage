import os
import time

from modules import util

logger = util.logger


class Tags:
    def __init__(self, qbit_manager, hashes: list[str] = None):
        self.qbt = qbit_manager
        self.hashes = hashes
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0
        # suffix tag for share limits
        self.share_limits_tag = qbit_manager.config.share_limits_tag
        self.torrents_updated = []  # List of torrents updated
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr
        self.stalled_tag = qbit_manager.config.stalled_tag
        self.private_tag = qbit_manager.config.private_tag
        self.tag_stalled_torrents = self.config.settings["tag_stalled_torrents"]
        self.file_extension = qbit_manager.config.file_extension

        self.tags()
        self.config.webhooks_factory.notify(self.torrents_updated, self.notify_attr, group_by="tag")

    def tags(self):
        """Update tags for torrents"""
        start_time = time.time()
        logger.separator("Updating Tags", space=False, border=False)
        torrent_list = self.qbt.torrent_list
        if self.hashes:
            torrent_list = self.qbt.get_torrents({"torrent_hashes": self.hashes})
        for torrent in torrent_list:
            tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))

            # Remove stalled_tag if torrent is no longer stalled
            if (
                self.tag_stalled_torrents
                and util.is_tag_in_torrent(self.stalled_tag, torrent.tags)
                and torrent.state != "stalledDL"
            ):
                t_name = torrent.name
                body = []
                body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f"Removing Tag: {self.stalled_tag}", 3), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
                if not self.config.dry_run:
                    torrent.remove_tags(self.stalled_tag)

            # Get file extension tags for this torrent
            file_extension = self.get_file_extension(torrent)

            if (
                torrent.tags == ""
                or not util.is_tag_in_torrent(tracker["tag"], torrent.tags)
                or (
                    self.tag_stalled_torrents
                    and torrent.state == "stalledDL"
                    and not util.is_tag_in_torrent(self.stalled_tag, torrent.tags)
                )
                or (
                    self.private_tag
                    and not util.is_tag_in_torrent(self.private_tag, torrent.tags)
                    and self.qbt.is_torrent_private(torrent)
                )
                or (
                    file_extension
                    and not all(util.is_tag_in_torrent(tag, torrent.tags) for tag in file_extension)
                )
            ):
                tags_to_add = tracker["tag"].copy()
                if self.tag_stalled_torrents and torrent.state == "stalledDL":
                    tags_to_add.append(self.stalled_tag)
                if self.private_tag and self.qbt.is_torrent_private(torrent):
                    tags_to_add.append(self.private_tag)
                for tag in file_extension:
                    if tag not in tags_to_add:
                        tags_to_add.append(tag)
                if tags_to_add:
                    t_name = torrent.name
                    self.stats += len(tags_to_add)
                    body = []
                    body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                    body += logger.print_line(
                        logger.insert_space(f"New Tag{'s' if len(tags_to_add) > 1 else ''}: {', '.join(tags_to_add)}", 8),
                        self.config.loglevel,
                    )
                    body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
                    if not self.config.dry_run:
                        torrent.add_tags(tags_to_add)
                    category = self.qbt.get_category(torrent.save_path)[0] if torrent.category == "" else torrent.category
                    attr = {
                        "function": "tag_update",
                        "title": "Updating Tags",
                        "body": "\n".join(body),
                        "torrents": [t_name],
                        "torrent_category": category,
                        "torrent_tag": ", ".join(tags_to_add),
                        "torrent_tracker": tracker["url"],
                        "notifiarr_indexer": tracker["notifiarr"],
                    }
                    self.notify_attr.append(attr)
                    self.torrents_updated.append(t_name)
        if self.stats >= 1:
            logger.print_line(
                f"{'Did not update' if self.config.dry_run else 'Updated'} {self.stats} new tags.", self.config.loglevel
            )
        else:
            logger.print_line("No new torrents to tag.", self.config.loglevel)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Tags command completed in {duration:.2f} seconds")

    def get_file_extension(self, torrent):
        """
        Check torrent files for configured file extensions and return matching tags.

        Args:
            torrent: The torrent object to check

        Returns:
            list: List of tags to apply based on file extensions found
        """
        if not self.file_extension:
            return []

        tags_to_add = []
        extensions_found = set()

        # Iterate through all files in the torrent
        for file in torrent.files:
            # Get the file extension (without the dot, lowercase)
            _, ext = os.path.splitext(file.name)
            ext = ext.lower().lstrip(".")

            # Check if this extension is configured for tagging
            if ext in self.file_extension and ext not in extensions_found:
                extensions_found.add(ext)
                # Add the configured tags for this extension
                for tag in self.file_extension[ext]:
                    if tag not in tags_to_add:
                        tags_to_add.append(tag)
                logger.trace(f"Found extension '.{ext}' in torrent '{torrent.name}', adding tags: {self.file_extension[ext]}")

        return tags_to_add
