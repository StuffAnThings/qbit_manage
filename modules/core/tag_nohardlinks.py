import time

from modules import util

logger = util.logger


class TagNoHardLinks:
    def __init__(self, qbit_manager, hashes: list[str] = None):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_tagged = 0  # counter for the number of torrents that has no hardlinks
        self.hashes = hashes
        # counter for number of torrents that previously had no hardlinks but now have hardlinks
        self.stats_untagged = 0

        self.root_dir = qbit_manager.config.root_dir
        self.remote_dir = qbit_manager.config.remote_dir
        self.nohardlinks = qbit_manager.config.nohardlinks
        self.nohardlinks_tag = qbit_manager.config.nohardlinks_tag

        self.torrents_updated_tagged = []  # List of torrents updated
        self.notify_attr_tagged = []  # List of single torrent attributes to send to notifiarr

        self.torrents_updated_untagged = []  # List of torrents updated
        # List of single torrent attributes to send to notifiarr
        self.notify_attr_untagged = []

        self.status_filter = "completed" if self.config.settings["tag_nohardlinks_filter_completed"] else "all"

        self.tag_nohardlinks()

        self.config.webhooks_factory.notify(self.torrents_updated_tagged, self.notify_attr_tagged, group_by="tag")
        self.config.webhooks_factory.notify(self.torrents_updated_untagged, self.notify_attr_untagged, group_by="tag")

    def add_tag_no_hl(self, torrent, tracker, category):
        """Add tag nohardlinks_tag to torrents with no hardlinks"""
        body = []
        body.append(logger.insert_space(f"Torrent Name: {torrent.name}", 3))
        body.append(logger.insert_space(f"Added Tag: {self.nohardlinks_tag}", 6))
        title = "Tagging Torrents with No Hardlinks"
        body.append(logger.insert_space(f"Tracker: {tracker['url']}", 8))
        if not self.config.dry_run:
            torrent.add_tags(self.nohardlinks_tag)
        self.stats_tagged += 1
        for rcd in body:
            logger.print_line(rcd, self.config.loglevel)
        attr = {
            "function": "tag_nohardlinks",
            "title": title,
            "body": "\n".join(body),
            "torrents": [torrent.name],
            "torrent_category": torrent.category,
            "torrent_tag": self.nohardlinks_tag,
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.torrents_updated_tagged.append(torrent.name)
        self.notify_attr_tagged.append(attr)

    def check_previous_nohardlinks_tagged_torrents(self, has_nohardlinks, torrent, tracker, category):
        """
        Checks for any previous torrents that were tagged with the nohardlinks tag and have since had hardlinks added.
        If any are found, the nohardlinks tag is removed
        """
        if not (has_nohardlinks) and (util.is_tag_in_torrent(self.nohardlinks_tag, torrent.tags)):
            self.stats_untagged += 1
            body = []
            body += logger.print_line(
                f"Previous Tagged {self.nohardlinks_tag} Torrent Name: {torrent.name} has hardlinks found now.",
                self.config.loglevel,
            )
            body += logger.print_line(logger.insert_space(f"Removed Tag: {self.nohardlinks_tag}", 6), self.config.loglevel)
            body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
            if not self.config.dry_run:
                torrent.remove_tags(tags=self.nohardlinks_tag)
            attr = {
                "function": "untag_nohardlinks",
                "title": "Untagging Previous Torrents that now have hardlinks",
                "body": "\n".join(body),
                "torrents": [torrent.name],
                "torrent_category": torrent.category,
                "torrent_tag": self.nohardlinks_tag,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            self.torrents_updated_untagged.append(torrent.name)
            self.notify_attr_untagged.append(attr)

    def _process_torrent_for_nohardlinks(self, torrent, check_hardlinks, ignore_root_dir, exclude_tags, category):
        """Helper method to process a single torrent for nohardlinks tagging."""
        tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
        has_nohardlinks = check_hardlinks.nohardlink(
            util.path_replace(torrent["content_path"], self.root_dir, self.remote_dir),
            self.config.notify,
            ignore_root_dir,
        )
        if any(util.is_tag_in_torrent(tag, torrent.tags) for tag in exclude_tags):
            # Skip to the next torrent if we find any torrents that are in the exclude tag
            return
        else:
            # Checks for any hardlinks and not already tagged
            # Cleans up previously tagged nohardlinks_tag torrents that no longer have hardlinks
            if has_nohardlinks:
                # Will only tag new torrents that don't have nohardlinks_tag tag
                if not util.is_tag_in_torrent(self.nohardlinks_tag, torrent.tags):
                    self.add_tag_no_hl(
                        torrent=torrent,
                        tracker=tracker,
                        category=category,
                    )
        self.check_previous_nohardlinks_tagged_torrents(has_nohardlinks, torrent, tracker, category)

    def tag_nohardlinks(self):
        """Tag torrents with no hardlinks"""
        start_time = time.time()
        logger.separator("Tagging Torrents with No Hardlinks", space=False, border=False)
        nohardlinks = self.nohardlinks
        check_hardlinks = util.CheckHardLinks(self.config)

        if self.hashes:
            torrent_list = self.qbt.get_torrents({"torrent_hashes": self.hashes, "status_filter": self.status_filter})
            for torrent in torrent_list:
                self._process_torrent_for_nohardlinks(
                    torrent,
                    check_hardlinks,
                    nohardlinks.get(torrent.category, {}).get("ignore_root_dir", True),
                    nohardlinks.get(torrent.category, {}).get("exclude_tags", []),
                    torrent.category,
                )
        else:
            for category in nohardlinks:
                torrent_list = self.qbt.get_torrents({"category": category, "status_filter": self.status_filter})
                if len(torrent_list) == 0:
                    ex = (
                        "No torrents found in the category ("
                        + category
                        + ") defined under nohardlinks attribute in the config. "
                        + "Please check if this matches with any category in qbittorrent and has 1 or more torrents."
                    )
                    logger.warning(ex)
                    continue
                for torrent in torrent_list:
                    self._process_torrent_for_nohardlinks(
                        torrent,
                        check_hardlinks,
                        nohardlinks.get(category, {}).get("ignore_root_dir", True),
                        nohardlinks.get(category, {}).get("exclude_tags", []),
                        category,
                    )
        if self.stats_tagged >= 1:
            logger.print_line(
                f"{'Did not Tag' if self.config.dry_run else 'Added Tag'} for {self.stats_tagged} "
                f".torrent{'s.' if self.stats_tagged > 1 else '.'}",
                self.config.loglevel,
            )
        else:
            logger.print_line("No torrents to tag with no hardlinks.", self.config.loglevel)
        if self.stats_untagged >= 1:
            logger.print_line(
                f"{'Did not delete' if self.config.dry_run else 'Deleted'} "
                f"{self.nohardlinks_tag} tags for {self.stats_untagged} "
                f".torrent{'s.' if self.stats_untagged > 1 else '.'}",
                self.config.loglevel,
            )

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Tag nohardlinks command completed in {duration:.2f} seconds")
