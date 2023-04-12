import os

from modules import util

logger = util.logger


class TagNoHardLinks:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_tagged = 0  # counter for the number of torrents that has no hardlinks
        self.stats_untagged = 0  # counter for number of torrents that previously had no hardlinks but now have hardlinks
        self.stats_deleted = 0  # counter for the number of torrents that has no hardlinks and \
        # meets the criteria for ratio limit/seed limit for deletion
        self.stats_deleted_contents = 0  # counter for the number of torrents that has no hardlinks and \
        # meets the criteria for ratio limit/seed limit for deletion including contents

        self.tdel_dict = {}  # dictionary to track the torrent names and content path that meet the deletion criteria
        self.root_dir = qbit_manager.config.root_dir
        self.remote_dir = qbit_manager.config.remote_dir
        self.nohardlinks = qbit_manager.config.nohardlinks
        self.nohardlinks_tag = qbit_manager.config.nohardlinks_tag

        self.tag_nohardlinks()

    def add_tag_no_hl(self, torrent, tracker, category, max_ratio, max_seeding_time, add_tag=True):
        """Add tag nohardlinks_tag to torrents with no hardlinks"""
        body = []
        body.append(logger.insert_space(f"Torrent Name: {torrent.name}", 3))
        if add_tag:
            body.append(logger.insert_space(f"Added Tag: {self.nohardlinks_tag}", 6))
            title = "Tagging Torrents with No Hardlinks"
        else:
            title = "Changing Share Ratio of Torrents with No Hardlinks"
        body.append(logger.insert_space(f'Tracker: {tracker["url"]}', 8))
        body_tags_and_limits = self.qbt.set_tags_and_limits(
            torrent,
            max_ratio,
            max_seeding_time,
            self.nohardlinks[category]["limit_upload_speed"],
            tags=self.nohardlinks_tag,
            do_print=False,
        )
        if body_tags_and_limits or add_tag:
            self.stats_tagged += 1
            # Resume torrent if it was paused now that the share limit has changed
            if torrent.state_enum.is_complete and self.nohardlinks[category]["resume_torrent_after_untagging_noHL"]:
                if not self.config.dry_run:
                    torrent.resume()
            body.extend(body_tags_and_limits)
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
                "torrent_max_ratio": max_ratio,
                "torrent_max_seeding_time": max_seeding_time,
                "torrent_limit_upload_speed": self.nohardlinks[category]["limit_upload_speed"],
            }
            self.config.send_notifications(attr)

    def cleanup_tagged_torrents_with_no_hardlinks(self, category):
        """Delete any tagged torrents that meet noHL criteria"""
        # loop through torrent list again for cleanup purposes
        if self.nohardlinks[category]["cleanup"]:
            torrent_list = self.qbt.get_torrents({"category": category, "status_filter": "completed"})
            for torrent in torrent_list:
                t_name = torrent.name
                t_hash = torrent.hash
                if t_hash in self.tdel_dict and self.nohardlinks_tag in torrent.tags:
                    t_count = self.qbt.torrentinfo[t_name]["count"]
                    t_msg = self.qbt.torrentinfo[t_name]["msg"]
                    t_status = self.qbt.torrentinfo[t_name]["status"]
                    # Double check that the content path is the same before we delete anything
                    if torrent["content_path"].replace(self.root_dir, self.remote_dir) == self.tdel_dict[t_hash]["content_path"]:
                        tracker = self.qbt.get_tags(torrent.trackers)
                        body = []
                        body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                        body += logger.print_line(self.tdel_dict[t_hash]["body"], self.config.loglevel)
                        body += logger.print_line(
                            logger.insert_space("Cleanup: True [No hardlinks found and meets Share Limits.]", 8),
                            self.config.loglevel,
                        )
                        attr = {
                            "function": "cleanup_tag_nohardlinks",
                            "title": "Removing NoHL Torrents and meets Share Limits",
                            "torrent_name": t_name,
                            "torrent_category": torrent.category,
                            "cleanup": "True",
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                        }
                        if os.path.exists(torrent["content_path"].replace(self.root_dir, self.remote_dir)):
                            # Checks if any of the original torrents are working
                            if t_count > 1 and ("" in t_msg or 2 in t_status):
                                self.stats_deleted += 1
                                attr["torrents_deleted_and_contents"] = False
                                if not self.config.dry_run:
                                    self.qbt.tor_delete_recycle(torrent, attr)
                                body += logger.print_line(
                                    logger.insert_space("Deleted .torrent but NOT content files.", 8),
                                    self.config.loglevel,
                                )
                            else:
                                self.stats_deleted_contents += 1
                                attr["torrents_deleted_and_contents"] = True
                                if not self.config.dry_run:
                                    self.qbt.tor_delete_recycle(torrent, attr)
                                body += logger.print_line(
                                    logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel
                                )
                        else:
                            self.stats_deleted += 1
                            attr["torrents_deleted_and_contents"] = False
                            if not self.config.dry_run:
                                self.qbt.tor_delete_recycle(torrent, attr)
                            body += logger.print_line(
                                logger.insert_space("Deleted .torrent but NOT content files.", 8), self.config.loglevel
                            )
                        attr["body"] = "\n".join(body)
                        self.config.send_notifications(attr)
                        self.qbt.torrentinfo[t_name]["count"] -= 1

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
            body += logger.print_line(
                f"{'Not Reverting' if self.config.dry_run else 'Reverting'} to tracker or Global share limits.",
                self.config.loglevel,
            )
            restore_max_ratio = tracker["max_ratio"]
            restore_max_seeding_time = tracker["max_seeding_time"]
            restore_limit_upload_speed = tracker["limit_upload_speed"]
            if restore_max_ratio is None:
                restore_max_ratio = -2
            if restore_max_seeding_time is None:
                restore_max_seeding_time = -2
            if restore_limit_upload_speed is None:
                restore_limit_upload_speed = -1
            if not self.config.dry_run:
                torrent.remove_tags(tags=self.nohardlinks_tag)
                body.extend(
                    self.qbt.set_tags_and_limits(
                        torrent, restore_max_ratio, restore_max_seeding_time, restore_limit_upload_speed, restore=True
                    )
                )
                if torrent.state_enum.is_complete and self.nohardlinks[category]["resume_torrent_after_untagging_noHL"]:
                    torrent.resume()
            attr = {
                "function": "untag_nohardlinks",
                "title": "Untagging Previous Torrents that now have hardlinks",
                "body": "\n".join(body),
                "torrent_name": torrent.name,
                "torrent_category": torrent.category,
                "torrent_tag": self.nohardlinks_tag,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
                "torrent_max_ratio": restore_max_ratio,
                "torrent_max_seeding_time": restore_max_seeding_time,
                "torrent_limit_upload_speed": restore_limit_upload_speed,
            }
            self.config.send_notifications(attr)

    def tag_nohardlinks(self):
        """Tag torrents with no hardlinks"""
        logger.separator("Tagging Torrents with No Hardlinks", space=False, border=False)
        nohardlinks = self.nohardlinks
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
                has_nohardlinks = util.nohardlink(
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
                        # Determine min_seeding_time.
                        # If only tracker setting is set, use tracker's min_seeding_time
                        # If only nohardlinks category setting is set, use nohardlinks category's min_seeding_time
                        # If both tracker and nohardlinks category setting is set, use the larger of the two
                        # If neither set, use 0 (no limit)
                        min_seeding_time = 0
                        logger.trace(f'tracker["min_seeding_time"] is {tracker["min_seeding_time"]}')
                        logger.trace(f'nohardlinks[category]["min_seeding_time"] is {nohardlinks[category]["min_seeding_time"]}')
                        if tracker["min_seeding_time"] is not None and nohardlinks[category]["min_seeding_time"] is not None:
                            if tracker["min_seeding_time"] >= nohardlinks[category]["min_seeding_time"]:
                                min_seeding_time = tracker["min_seeding_time"]
                                logger.trace(f'Using tracker["min_seeding_time"] {min_seeding_time}')
                            else:
                                min_seeding_time = nohardlinks[category]["min_seeding_time"]
                                logger.trace(f'Using nohardlinks[category]["min_seeding_time"] {min_seeding_time}')
                        elif nohardlinks[category]["min_seeding_time"]:
                            min_seeding_time = nohardlinks[category]["min_seeding_time"]
                            logger.trace(f'Using nohardlinks[category]["min_seeding_time"] {min_seeding_time}')
                        elif tracker["min_seeding_time"]:
                            min_seeding_time = tracker["min_seeding_time"]
                            logger.trace(f'Using tracker["min_seeding_time"] {min_seeding_time}')
                        else:
                            logger.trace(f"Using default min_seeding_time {min_seeding_time}")
                        # Determine max_ratio.
                        # If only tracker setting is set, use tracker's max_ratio
                        # If only nohardlinks category setting is set, use nohardlinks category's max_ratio
                        # If both tracker and nohardlinks category setting is set, use the larger of the two
                        # If neither set, use -1 (no limit)
                        max_ratio = -1
                        logger.trace(f'tracker["max_ratio"] is {tracker["max_ratio"]}')
                        logger.trace(f'nohardlinks[category]["max_ratio"] is {nohardlinks[category]["max_ratio"]}')
                        if tracker["max_ratio"] is not None and nohardlinks[category]["max_ratio"] is not None:
                            if tracker["max_ratio"] >= nohardlinks[category]["max_ratio"]:
                                max_ratio = tracker["max_ratio"]
                                logger.trace(f'Using (tracker["max_ratio"]) {max_ratio}')
                            else:
                                max_ratio = nohardlinks[category]["max_ratio"]
                                logger.trace(f'Using (nohardlinks[category]["max_ratio"]) {max_ratio}')
                        elif nohardlinks[category]["max_ratio"]:
                            max_ratio = nohardlinks[category]["max_ratio"]
                            logger.trace(f'Using (nohardlinks[category]["max_ratio"]) {max_ratio}')
                        elif tracker["max_ratio"]:
                            max_ratio = tracker["max_ratio"]
                            logger.trace(f'Using (tracker["max_ratio"]) {max_ratio}')
                        else:
                            logger.trace(f"Using default (max_ratio) {max_ratio}")
                        # Determine max_seeding_time.
                        # If only tracker setting is set, use tracker's max_seeding_time
                        # If only nohardlinks category setting is set, use nohardlinks category's max_seeding_time
                        # If both tracker and nohardlinks category setting is set, use the larger of the two
                        # If neither set, use -1 (no limit)
                        max_seeding_time = -1
                        logger.trace(f'tracker["max_seeding_time"] is {tracker["max_seeding_time"]}')
                        logger.trace(f'nohardlinks[category]["max_seeding_time"] is {nohardlinks[category]["max_seeding_time"]}')
                        if tracker["max_seeding_time"] is not None and nohardlinks[category]["max_seeding_time"] is not None:
                            if tracker["max_seeding_time"] >= nohardlinks[category]["max_seeding_time"]:
                                max_seeding_time = tracker["max_seeding_time"]
                                logger.trace(f'Using (tracker["max_seeding_time"]) {max_seeding_time}')
                            else:
                                max_seeding_time = nohardlinks[category]["max_seeding_time"]
                                logger.trace(f'Using (nohardlinks[category]["max_seeding_time"]) {max_seeding_time}')
                        elif nohardlinks[category]["max_seeding_time"]:
                            max_seeding_time = nohardlinks[category]["max_seeding_time"]
                            logger.trace(f'Using (nohardlinks[category]["max_seeding_time"]) {max_seeding_time}')
                        elif tracker["max_seeding_time"]:
                            max_seeding_time = tracker["max_seeding_time"]
                            logger.trace(f'Using (tracker["max_seeding_time"]) {max_seeding_time}')
                        else:
                            logger.trace(f"Using default (max_seeding_time) {max_seeding_time}")
                        # Will only tag new torrents that don't have nohardlinks_tag tag
                        if self.nohardlinks_tag not in torrent.tags:
                            self.add_tag_no_hl(
                                torrent=torrent,
                                tracker=tracker,
                                category=category,
                                max_ratio=max_ratio,
                                max_seeding_time=max_seeding_time,
                                add_tag=True,
                            )

                        # Deletes torrent with data if cleanup is set to true and meets the ratio/seeding requirements
                        if nohardlinks[category]["cleanup"] and len(nohardlinks[category]) > 0:
                            tor_reach_seed_limit = self.qbt.has_reached_seed_limit(
                                torrent,
                                max_ratio,
                                max_seeding_time,
                                min_seeding_time,
                                nohardlinks[category]["resume_torrent_after_untagging_noHL"],
                                tracker["url"],
                            )
                            if tor_reach_seed_limit:
                                if torrent.hash not in self.tdel_dict:
                                    self.tdel_dict[torrent.hash] = {}
                                self.tdel_dict[torrent.hash]["content_path"] = torrent["content_path"].replace(
                                    self.root_dir, self.remote_dir
                                )
                                self.tdel_dict[torrent.hash]["body"] = tor_reach_seed_limit
                            else:
                                # Updates torrent to see if "MinSeedTimeNotReached" tag has been added
                                torrent = self.qbt.get_torrents({"torrent_hashes": [torrent.hash]}).data[0]
                                # Checks to see if previously nohardlinks_tag share limits have changed.
                                self.add_tag_no_hl(
                                    torrent=torrent,
                                    tracker=tracker,
                                    category=category,
                                    max_ratio=max_ratio,
                                    max_seeding_time=max_seeding_time,
                                    add_tag=False,
                                )
                self.check_previous_nohardlinks_tagged_torrents(has_nohardlinks, torrent, tracker, category)
            self.cleanup_tagged_torrents_with_no_hardlinks(category)
        if self.stats_tagged >= 1:
            logger.print_line(
                f"{'Did not Tag/set' if self.config.dry_run else 'Tag/set'} share limits for {self.stats_tagged} "
                f".torrent{'s.' if self.stats_tagged > 1 else '.'}",
                self.config.loglevel,
            )
        else:
            logger.print_line("No torrents to tag with no hardlinks.", self.config.loglevel)
        if self.stats_untagged >= 1:
            logger.print_line(
                f"{'Did not delete' if self.config.dry_run else 'Deleted'} "
                f"{self.nohardlinks_tag} tags / share limits for {self.stats_untagged} "
                f".torrent{'s.' if self.stats_untagged > 1 else '.'}",
                self.config.loglevel,
            )
        if self.stats_deleted >= 1:
            logger.print_line(
                f"{'Did not delete' if self.config.dry_run else 'Deleted'} {self.stats_deleted} "
                f".torrent{'s' if self.stats_deleted > 1 else ''} but not content files.",
                self.config.loglevel,
            )
        if self.stats_deleted_contents >= 1:
            logger.print_line(
                f"{'Did not delete' if self.config.dry_run else 'Deleted'} {self.stats_deleted_contents} "
                f".torrent{'s' if self.stats_deleted_contents > 1 else ''} AND content files.",
                self.config.loglevel,
            )
