import os
from datetime import timedelta

from modules import util

logger = util.logger


class ShareLimits:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_tagged = 0  # counter for the number of share limits changed
        self.stats_deleted = 0  # counter for the number of torrents that \
        # meets the criteria for ratio limit/seed limit for deletion
        self.stats_deleted_contents = 0  # counter for the number of torrents that  \
        # meets the criteria for ratio limit/seed limit for deletion including contents \

        self.tdel_dict = {}  # dictionary to track the torrent names and content path that meet the deletion criteria
        self.root_dir = qbit_manager.config.root_dir  # root directory of torrents
        self.remote_dir = qbit_manager.config.remote_dir  # remote directory of torrents
        self.share_limits_config = qbit_manager.config.share_limits  # configuration of share limits
        self.torrents_updated = []  # list of torrents that have been updated
        self.torrent_hash_checked = []  # list of torrent hashes that have been checked for share limits
        self.share_limits_suffix_tag = qbit_manager.config.share_limits_suffix_tag  # suffix tag for share limits
        self.group_tag = None  # tag for the share limit group

        self.update_share_limits()

    def update_share_limits(self):
        """Updates share limits for torrents based on grouping"""
        logger.separator("Updating Share Limits based on priority", space=False, border=False)
        torrent_list = self.qbt.get_torrents({"status_filter": "completed"})
        self.assign_torrents_to_group(torrent_list)
        for group_name, group_config in self.share_limits_config.items():
            torrents = group_config["torrents"]
            self.torrents_updated = []
            self.tdel_dict = {}
            if torrents:
                self.update_share_limits_for_group(group_name, group_config, torrents)
                attr = {
                    "function": "share_limits",
                    "title": f"Updating Share Limits for {group_name}. Priority {group_config['priority']}",
                    "body": f"Updated {len(self.torrents_updated)} torrents.",
                    "grouping": group_name,
                    "torrent_list": self.torrents_updated,
                    "torrent_tag": self.group_tag,
                    "torrent_max_ratio": group_config["max_ratio"],
                    "torrent_max_seeding_time": group_config["max_seeding_time"],
                    "torrent_min_seeding_time": group_config["min_seeding_time"],
                    "torrent_limit_upload_speed": group_config["limit_upload_speed"],
                }
                if len(self.torrents_updated) > 0:
                    self.config.send_notifications(attr)
                if group_config["cleanup"] and len(self.tdel_dict) > 0:
                    self.cleanup_torrents_for_group(group_name, group_config["priority"])

    def cleanup_torrents_for_group(self, group_name, priority):
        """Deletes torrents that have reached the ratio/seed limit"""
        logger.separator(
            f"Cleaning up torrents that have reached ratio/seed limit for {group_name}. Priority {priority}",
            space=False,
            border=False,
        )
        group_notifications = len(self.tdel_dict) > 10
        t_deleted = set()
        t_deleted_and_contents = set()
        for torrent_hash, torrent_dict in self.tdel_dict.items():
            torrent = torrent_dict["torrent"]
            t_name = torrent.name
            t_count = self.qbt.torrentinfo[t_name]["count"]
            t_msg = self.qbt.torrentinfo[t_name]["msg"]
            t_status = self.qbt.torrentinfo[t_name]["status"]
            # Double check that the content path is the same before we delete anything
            if torrent["content_path"].replace(self.root_dir, self.remote_dir) == torrent_dict["content_path"]:
                tracker = self.qbt.get_tags(torrent.trackers)
                body = []
                body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                body += logger.print_line(torrent_dict["body"], self.config.loglevel)
                body += logger.print_line(
                    logger.insert_space("Cleanup: True [Meets Share Limits]", 8),
                    self.config.loglevel,
                )
                attr = {
                    "function": "cleanup_share_limits",
                    "title": "Share limit removal",
                    "grouping": group_name,
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
                        t_deleted.add(t_name)
                        if not self.config.dry_run:
                            self.qbt.tor_delete_recycle(torrent, attr)
                        body += logger.print_line(
                            logger.insert_space("Deleted .torrent but NOT content files.", 8),
                            self.config.loglevel,
                        )
                    else:
                        self.stats_deleted_contents += 1
                        attr["torrents_deleted_and_contents"] = True
                        t_deleted_and_contents.add(t_name)
                        if not self.config.dry_run:
                            self.qbt.tor_delete_recycle(torrent, attr)
                        body += logger.print_line(
                            logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel
                        )
                else:
                    self.stats_deleted += 1
                    attr["torrents_deleted_and_contents"] = False
                    t_deleted.add(t_name)
                    if not self.config.dry_run:
                        self.qbt.tor_delete_recycle(torrent, attr)
                    body += logger.print_line(
                        logger.insert_space("Deleted .torrent but NOT content files.", 8), self.config.loglevel
                    )
                attr["body"] = "\n".join(body)
                if not group_notifications:
                    self.config.send_notifications(attr)
                self.qbt.torrentinfo[t_name]["count"] -= 1
        if group_notifications:
            if t_deleted:
                attr = {
                    "function": "cleanup_share_limits",
                    "title": "Share limit removal - Deleted .torrent but NOT content files.",
                    "body": f"Deleted {self.stats_deleted} .torrents but NOT content files.",
                    "grouping": group_name,
                    "torrent_list": list(t_deleted),
                    "cleanup": True,
                    "torrents_deleted_and_contents": False,
                }
                self.config.send_notifications(attr)
            if t_deleted_and_contents:
                attr = {
                    "function": "cleanup_share_limits",
                    "title": "Share limit removal - Deleted .torrent AND content files.",
                    "body": f"Deleted {self.stats_deleted_contents} .torrents AND content files.",
                    "grouping": group_name,
                    "torrent_list": list(t_deleted_and_contents),
                    "cleanup": True,
                    "torrents_deleted_and_contents": True,
                }
                self.config.send_notifications(attr)

    def update_share_limits_for_group(self, group_name, group_config, torrents):
        """Updates share limits for torrents in a group"""
        logger.separator(
            f"Updating Share Limits for [Group {group_name}] [Priority {group_config['priority']}]", space=False, border=False
        )
        for torrent in torrents:
            t_name = torrent.name
            t_hash = torrent.hash
            tracker = self.qbt.get_tags(torrent.trackers)
            check_max_ratio = group_config["max_ratio"] != torrent.max_ratio
            check_max_seeding_time = group_config["max_seeding_time"] != torrent.max_seeding_time
            # Treat upload limit as -1 if it is set to 0 (unlimited)
            torrent_upload_limit = -1 if round(torrent.up_limit / 1024) == 0 else round(torrent.up_limit / 1024)
            if group_config["limit_upload_speed"] == 0:
                group_config["limit_upload_speed"] = -1
            check_limit_upload_speed = group_config["limit_upload_speed"] != torrent_upload_limit
            if (
                check_max_ratio or check_max_seeding_time or check_limit_upload_speed
            ) and t_hash not in self.torrent_hash_checked:
                if "MinSeedTimeNotReached" not in torrent.tags:
                    self.group_tag = f"{group_name}{self.share_limits_suffix_tag}" if group_config["add_group_to_tag"] else None
                    logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                    logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                    logger.trace(f"Torrent Category: {torrent.category}")
                    logger.trace(f"Torrent Tags: {torrent.tags}")
                    logger.trace(f"Grouping: {group_name}")
                    logger.trace(f"Config Max Ratio vs Torrent Max Ratio:{group_config['max_ratio']} vs {torrent.max_ratio}")
                    logger.trace(
                        "Config Max Seeding Time vs Torrent Max Seeding Time: "
                        f"{group_config['max_seeding_time']} vs {torrent.max_seeding_time}"
                    )
                    logger.trace(
                        "Config Limit Upload Speed vs Torrent Limit Upload Speed: "
                        f"{group_config['limit_upload_speed']} vs {torrent_upload_limit}"
                    )
                    if self.group_tag:
                        logger.print_line(logger.insert_space(f"Added Tag: {self.group_tag}", 8), self.config.loglevel)
                    self.tag_and_update_share_limits_for_torrent(torrent, group_config)
                    self.stats_tagged += 1
                    self.torrents_updated.append(t_name)
            else:
                self.share_limits_config[group_name]["torrents"].remove(torrent)

            # Cleanup torrents if the torrent meets the criteria for deletion and cleanup is enabled
            if group_config["cleanup"]:
                tor_reached_seed_limit = self.has_reached_seed_limit(
                    torrent=torrent,
                    max_ratio=group_config["max_ratio"],
                    max_seeding_time=group_config["max_seeding_time"],
                    min_seeding_time=group_config["min_seeding_time"],
                    resume_torrent=group_config["resume_torrent_after_change"],
                    tracker=tracker["url"],
                )
                if tor_reached_seed_limit:
                    if t_hash not in self.tdel_dict:
                        self.tdel_dict[t_hash] = {}
                    self.tdel_dict[t_hash]["torrent"] = torrent
                    self.tdel_dict[t_hash]["content_path"] = torrent["content_path"].replace(self.root_dir, self.remote_dir)
                    self.tdel_dict[t_hash]["body"] = tor_reached_seed_limit
            self.torrent_hash_checked.append(t_hash)

    def tag_and_update_share_limits_for_torrent(self, torrent, group_config):
        """Removes previous share limits tag, updates tag and share limits for a torrent, and resumes the torrent"""
        # Remove previous share_limits tag
        tags = util.get_list(torrent.tags)
        for tag in tags:
            if self.share_limits_suffix_tag in tag:
                torrent.remove_tags(tag)

        # Will tag the torrent with the group name if add_group_to_tag is True and set the share limits
        self.set_tags_and_limits(
            torrent=torrent,
            max_ratio=group_config["max_ratio"],
            max_seeding_time=group_config["max_seeding_time"],
            limit_upload_speed=group_config["limit_upload_speed"],
            tags=self.group_tag,
        )
        # Resume torrent if it was paused now that the share limit has changed
        if torrent.state_enum.is_complete and group_config["resume_torrent_after_change"]:
            if not self.config.dry_run:
                torrent.resume()

    def assign_torrents_to_group(self, torrent_list):
        """Assign torrents to a share limit group based on its tags and category"""
        logger.info("Assigning torrents to share limit groups...")
        for torrent in torrent_list:
            tags = util.get_list(torrent.tags)
            category = torrent.category or ""
            grouping = self.get_share_limit_group(tags, category)
            if grouping:
                self.share_limits_config[grouping]["torrents"].append(torrent)

    def get_share_limit_group(self, tags, category):
        """Get the share limit group based on the tags and category of the torrent"""
        for group_name, group_config in self.share_limits_config.items():
            check_tags = self.check_tags(
                tags=tags,
                include_all_tags=group_config["include_all_tags"],
                include_any_tags=group_config["include_any_tags"],
                exclude_all_tags=group_config["exclude_all_tags"],
                exclude_any_tags=group_config["exclude_any_tags"],
            )
            check_category = self.check_category(category, group_config["categories"])

            if check_tags and check_category:
                return group_name
        return None

    def check_tags(self, tags, include_all_tags=set(), include_any_tags=set(), exclude_all_tags=set(), exclude_any_tags=set()):
        """Check if the torrent has the required tags"""
        tags_set = set(tags)
        if include_all_tags:
            if not set(include_all_tags).issubset(tags_set):
                return False
        if include_any_tags:
            if not set(include_any_tags).intersection(tags_set):
                return False
        if exclude_all_tags:
            if set(exclude_all_tags).issubset(tags_set):
                return False
        if exclude_any_tags:
            if set(exclude_any_tags).intersection(tags_set):
                return False
        return True

    def check_category(self, category, categories):
        """Check if the torrent has the required category"""
        if categories:
            if category not in categories:
                return False
        return True

    def set_tags_and_limits(
        self, torrent, max_ratio, max_seeding_time, limit_upload_speed=None, tags=None, restore=False, do_print=True
    ):
        """Set tags and limits for a torrent"""
        body = []
        if limit_upload_speed:
            if limit_upload_speed != -1:
                msg = logger.insert_space(f"Limit UL Speed: {limit_upload_speed} kB/s", 1)
                if do_print:
                    body += logger.print_line(msg, self.config.loglevel)
                else:
                    body.append(msg)
        if max_ratio or max_seeding_time:
            if (max_ratio == -2 and max_seeding_time == -2) and not restore:
                msg = logger.insert_space("Share Limit: Use Global Share Limit", 4)
                if do_print:
                    body += logger.print_line(msg, self.config.loglevel)
                else:
                    body.append(msg)
            elif (max_ratio == -1 and max_seeding_time == -1) and not restore:
                msg = logger.insert_space("Share Limit: Set No Share Limit", 4)
                if do_print:
                    body += logger.print_line(msg, self.config.loglevel)
                else:
                    body.append(msg)
            else:
                if max_ratio != torrent.max_ratio and (not max_seeding_time or max_seeding_time < 0):
                    msg = logger.insert_space(f"Share Limit: Max Ratio = {max_ratio}", 4)
                    if do_print:
                        body += logger.print_line(msg, self.config.loglevel)
                    else:
                        body.append(msg)
                elif max_seeding_time != torrent.max_seeding_time and (not max_ratio or max_ratio < 0):
                    msg = logger.insert_space(f"Share Limit: Max Seed Time = {max_seeding_time} min", 4)
                    if do_print:
                        body += logger.print_line(msg, self.config.loglevel)
                    else:
                        body.append(msg)
                elif max_ratio != torrent.max_ratio or max_seeding_time != torrent.max_seeding_time:
                    msg = logger.insert_space(f"Share Limit: Max Ratio = {max_ratio}, Max Seed Time = {max_seeding_time} min", 4)
                    if do_print:
                        body += logger.print_line(msg, self.config.loglevel)
                    else:
                        body.append(msg)
        # Update Torrents
        if not self.config.dry_run:
            if tags and tags not in torrent.tags:
                torrent.add_tags(tags)
            if limit_upload_speed:
                if limit_upload_speed == -1:
                    torrent.set_upload_limit(-1)
                else:
                    torrent.set_upload_limit(limit_upload_speed * 1024)
            if not max_ratio:
                max_ratio = torrent.max_ratio
            if not max_seeding_time:
                max_seeding_time = torrent.max_seeding_time
            if "MinSeedTimeNotReached" in torrent.tags:
                return []
            torrent.set_share_limits(max_ratio, max_seeding_time)
        return body

    def has_reached_seed_limit(self, torrent, max_ratio, max_seeding_time, min_seeding_time, resume_torrent, tracker):
        """Check if torrent has reached seed limit"""
        body = ""

        def _has_reached_min_seeding_time_limit():
            print_log = []
            if torrent.seeding_time >= min_seeding_time * 60:
                if "MinSeedTimeNotReached" in torrent.tags:
                    torrent.remove_tags(tags="MinSeedTimeNotReached")
                return True
            else:
                if "MinSeedTimeNotReached" not in torrent.tags:
                    print_log += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
                    print_log += logger.print_line(logger.insert_space(f"Tracker: {tracker}", 8), self.config.loglevel)
                    print_log += logger.print_line(
                        logger.insert_space(
                            f"Min seed time not met: {timedelta(seconds=torrent.seeding_time)} <= "
                            f"{timedelta(minutes=min_seeding_time)}. Removing Share Limits so qBittorrent can continue seeding.",
                            8,
                        ),
                        self.config.loglevel,
                    )
                    print_log += logger.print_line(
                        logger.insert_space("Adding Tag: MinSeedTimeNotReached", 8), self.config.loglevel
                    )
                    if not self.config.dry_run:
                        torrent.add_tags("MinSeedTimeNotReached")
                        torrent.set_share_limits(-1, -1)
                        if resume_torrent:
                            torrent.resume()
            return False

        def _has_reached_seeding_time_limit():
            nonlocal body
            seeding_time_limit = None
            if not max_seeding_time:
                return False
            if max_seeding_time >= 0:
                seeding_time_limit = max_seeding_time
            elif max_seeding_time == -2 and self.global_max_seeding_time_enabled:
                seeding_time_limit = self.global_max_seeding_time
            else:
                return False
            if seeding_time_limit:
                if (torrent.seeding_time >= seeding_time_limit * 60) and _has_reached_min_seeding_time_limit():
                    body += logger.insert_space(
                        f"Seeding Time vs Max Seed Time: {timedelta(seconds=torrent.seeding_time)} >= "
                        f"{timedelta(minutes=seeding_time_limit)}",
                        8,
                    )
                    return True
            return False

        if max_ratio:
            if max_ratio >= 0:
                if torrent.ratio >= max_ratio and _has_reached_min_seeding_time_limit():
                    body += logger.insert_space(f"Ratio vs Max Ratio: {torrent.ratio:.2f} >= {max_ratio:.2f}", 8)
                    return body
            elif max_ratio == -2 and self.global_max_ratio_enabled and _has_reached_min_seeding_time_limit():
                if torrent.ratio >= self.global_max_ratio:
                    body += logger.insert_space(
                        f"Ratio vs Global Max Ratio: {torrent.ratio:.2f} >= {self.global_max_ratio:.2f}", 8
                    )
                    return body
        if _has_reached_seeding_time_limit():
            return body
        return False
