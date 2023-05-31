from modules import util

logger = util.logger


class TagNoHardLinks:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_tagged = 0  # counter for the number of torrents that has no hardlinks
        self.stats_untagged = 0  # counter for number of torrents that previously had no hardlinks but now have hardlinks

        self.root_dir = qbit_manager.config.root_dir
        self.remote_dir = qbit_manager.config.remote_dir
        self.nohardlinks = qbit_manager.config.nohardlinks
        self.nohardlinks_tag = qbit_manager.config.nohardlinks_tag

        self.tag_nohardlinks()

    def add_tag_no_hl(self, torrent, tracker, category):
        """Add tag nohardlinks_tag to torrents with no hardlinks"""
        body = []
        body.append(logger.insert_space(f"Torrent Name: {torrent.name}", 3))
        body.append(logger.insert_space(f"Added Tag: {self.nohardlinks_tag}", 6))
        title = "Tagging Torrents with No Hardlinks"
        body.append(logger.insert_space(f'Tracker: {tracker["url"]}', 8))
        if not self.config.dry_run:
            torrent.add_tags(self.nohardlinks_tag)
        self.stats_tagged += 1
        for rcd in body:
            logger.print_line(rcd, self.config.loglevel)
        attr = {
            "function": "tag_nohardlinks",
            "title": title,
            "body": "\n".join(body),
            "torrent_name": torrent.name,
            "torrent_category": torrent.category,
            "torrent_tag": self.nohardlinks_tag,
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.config.send_notifications(attr)

    def check_previous_nohardlinks_tagged_torrents(self, has_nohardlinks, torrent, tracker, category):
        """
        Checks for any previous torrents that were tagged with the nohardlinks tag and have since had hardlinks added.
        If any are found, the nohardlinks tag is removed from the torrent and the tracker or global share limits are restored.
        If the torrent is complete and the option to resume after untagging is enabled, the torrent is resumed.
        """
        if not (has_nohardlinks) and (self.nohardlinks_tag in torrent.tags):
            self.stats_untagged += 1
            body = []
            body += logger.print_line(
                f"Previous Tagged {self.nohardlinks_tag} " f"Torrent Name: {torrent.name} has hardlinks found now.",
                self.config.loglevel,
            )
            body += logger.print_line(logger.insert_space(f"Removed Tag: {self.nohardlinks_tag}", 6), self.config.loglevel)
            body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
            if not self.config.dry_run:
                torrent.remove_tags(tags=self.nohardlinks_tag)
            attr = {
                "function": "untag_nohardlinks",
                "title": "Untagging Previous Torrents that now have hardlinks",
                "body": "\n".join(body),
                "torrent_name": torrent.name,
                "torrent_category": torrent.category,
                "torrent_tag": self.nohardlinks_tag,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            self.config.send_notifications(attr)

    def tag_nohardlinks(self):
        """Tag torrents with no hardlinks"""
        logger.separator("Tagging Torrents with No Hardlinks", space=False, border=False)
        nohardlinks = self.nohardlinks
        check_hardlinks = util.CheckHardLinks(self.root_dir, self.remote_dir)
        for category in nohardlinks:
            torrent_list = self.qbt.get_torrents({"category": category, "status_filter": "completed"})
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
                tracker = self.qbt.get_tags(torrent.trackers)
                has_nohardlinks = check_hardlinks.nohardlink(
                    torrent["content_path"].replace(self.root_dir, self.remote_dir), self.config.notify
                )
                if any(tag in torrent.tags for tag in nohardlinks[category]["exclude_tags"]):
                    # Skip to the next torrent if we find any torrents that are in the exclude tag
                    continue
                else:
                    # Checks for any hardlinks and not already tagged
                    # Cleans up previously tagged nohardlinks_tag torrents that no longer have hardlinks
                    if has_nohardlinks:
                        tracker = self.qbt.get_tags(torrent.trackers)
                        # Will only tag new torrents that don't have nohardlinks_tag tag
                        if self.nohardlinks_tag not in torrent.tags:
                            self.add_tag_no_hl(
                                torrent=torrent,
                                tracker=tracker,
                                category=category,
                            )
                self.check_previous_nohardlinks_tagged_torrents(has_nohardlinks, torrent, tracker, category)
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
