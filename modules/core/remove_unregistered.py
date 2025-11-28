import time

from qbittorrentapi import TrackerStatus

from modules import util
from modules.qbit_error_handler import handle_qbit_api_errors
from modules.util import TorrentMessages
from modules.util import list_in_text

logger = util.logger


class RemoveUnregistered:
    def __init__(self, qbit_manager, hashes: list[str] = None):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_deleted = 0
        self.stats_deleted_contents = 0
        self.stats_tagged = 0
        self.stats_untagged = 0
        self.tor_error_summary = ""
        self.tag_error = self.config.tracker_error_tag
        self.cfg_rem_unregistered = self.config.commands["rem_unregistered"]
        self.cfg_tag_error = self.config.commands["tag_tracker_error"]
        self.rem_unregistered_ignore_list = self.config.settings["rem_unregistered_ignore_list"]
        self.filter_completed = self.config.settings["rem_unregistered_filter_completed"]
        self.rem_unregistered_grace_minutes = self.config.settings["rem_unregistered_grace_minutes"]
        self.rem_unregistered_max_torrents = self.config.settings["rem_unregistered_max_torrents"]
        self.hashes = hashes
        self.tracker_del_count = {}

        tag_error_msg = "Tagging Torrents with Tracker Errors" if self.cfg_tag_error else ""
        rem_unregistered_msg = "Removing Unregistered Torrents" if self.cfg_rem_unregistered else ""

        if tag_error_msg and rem_unregistered_msg:
            message = f"{tag_error_msg} and {rem_unregistered_msg}"
        elif tag_error_msg:
            message = tag_error_msg
        elif rem_unregistered_msg:
            message = rem_unregistered_msg

        if message:
            logger.separator(message, space=False, border=False)

        self.rem_unregistered()

    def remove_previous_errors(self):
        """Removes any previous torrents that were tagged as an error but are now working."""
        torrents_updated = []
        notify_attr = []

        torrent_valid_list = self.qbt.torrentvalid
        if self.hashes:
            torrent_valid_list = [t for t in torrent_valid_list if t.hash in self.hashes]
        for torrent in torrent_valid_list:
            check_tags = util.get_list(torrent.tags)
            t_name = torrent.name
            # Remove any error torrents Tags that are no longer unreachable.
            if self.tag_error in check_tags:
                tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
                self.stats_untagged += 1
                body = []
                body += logger.print_line(
                    f"Previous Tagged {self.tag_error} torrent currently has a working tracker.", self.config.loglevel
                )
                body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f"Removed Tag: {self.tag_error}", 4), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
                if not self.config.dry_run:
                    torrent.remove_tags(tags=self.tag_error)
                attr = {
                    "function": "untag_tracker_error",
                    "title": "Untagging Tracker Error Torrent",
                    "body": "\n".join(body),
                    "torrents": [t_name],
                    "torrent_category": torrent.category,
                    "torrent_tag": self.tag_error,
                    "torrent_tracker": tracker["url"],
                    "notifiarr_indexer": tracker["notifiarr"],
                }
                torrents_updated.append(t_name)
                notify_attr.append(attr)

        self.config.webhooks_factory.notify(torrents_updated, notify_attr, group_by="tag")

    def check_for_unregistered_torrents_in_bhd(self, tracker, msg_up, torrent_hash):
        """
        Checks if a torrent is unregistered in BHD using their deletion reasons.
        Legacy method uses the BHD API to check if a torrent is unregistered.
        """
        # Some status's from BHD have a option message such as
        # "Trumped: Internal: https://beyond-hd.xxxxx", so removing the colon is needed to match the status
        status_filtered = msg_up.split(":")[0]
        if "tracker.beyond-hd.me" in tracker["url"]:
            # Checks if the tracker is BHD and the message is in the deletion reasons for BHD
            if list_in_text(status_filtered, TorrentMessages.UNREGISTERED_MSGS_BHD):
                return True
        return False

    def is_within_grace(self, torrent):
        """
        Determine whether the torrent should be protected by the grace window.

        Returns:
            (bool, float): Tuple of (is_within_grace, age_minutes)
        """
        try:
            grace = int(self.rem_unregistered_grace_minutes or 0)
        except Exception:
            grace = 0
        if grace <= 0:
            return False, 0.0
        added_on = getattr(torrent, "added_on", None)
        if not added_on:
            return False, 0.0
        try:
            age_seconds = max(0.0, time.time() - float(added_on))
        except Exception:
            return False, 0.0
        age_minutes = age_seconds / 60.0
        return age_minutes < grace, age_minutes

    def process_torrent_issues(self):
        """Process torrent issues."""
        self.torrents_updated_issue = []  # List of torrents updated
        self.notify_attr_issue = []  # List of single torrent attributes to send to notifiarr
        self.torrents_updated_unreg = []  # List of torrents updated
        self.notify_attr_unreg = []  # List of single torrent attributes to send to notifiarr

        torrent_issue_list = self.qbt.torrentissue
        if self.hashes:
            torrent_issue_list = [t for t in torrent_issue_list if t.hash in self.hashes]
        for torrent in torrent_issue_list:
            self.t_name = torrent.name
            self.t_cat = self.qbt.torrentinfo[self.t_name]["Category"]
            self.t_msg = self.qbt.torrentinfo[self.t_name]["msg"]
            self.t_status = self.qbt.torrentinfo[self.t_name]["status"]
            check_tags = util.get_list(torrent.tags)

            @handle_qbit_api_errors(context="process_torrent_issues", retry_attempts=1)
            def process_single_torrent():
                if self.filter_completed and not torrent.state_enum.is_complete:
                    return
                tracker_working = False
                for trk in torrent.trackers:
                    if (
                        trk.url.split(":")[0] in ["http", "https", "udp", "ws", "wss"]
                        and TrackerStatus(trk.status) == TrackerStatus.WORKING
                    ):
                        tracker_working = True
                if tracker_working:
                    return
                tracker = self.qbt.get_tags(self.qbt.get_tracker_urls([trk]))
                msg_up = trk.msg.upper()
                msg = trk.msg
                if TrackerStatus(trk.status) == TrackerStatus.NOT_WORKING:
                    # Check for unregistered torrents
                    if self.cfg_rem_unregistered:
                        if list_in_text(msg_up, TorrentMessages.UNREGISTERED_MSGS) and not list_in_text(
                            msg_up, TorrentMessages.IGNORE_MSGS
                        ):
                            if list_in_text(msg_up, self.rem_unregistered_ignore_list):
                                logger.print_line(
                                    f"Ignoring unregistered torrent {self.t_name} due to matching phrase found in ignore list.",
                                    self.config.loglevel,
                                )
                            else:
                                skip, age = self.is_within_grace(torrent)
                                if skip:
                                    logger.print_line(
                                        logger.insert_space(
                                            f"Skipping removal (within grace "
                                            f"{self.rem_unregistered_grace_minutes} min, age {age:.1f} min): "
                                            f"{self.t_name}",
                                            3,
                                        ),
                                        self.config.loglevel,
                                    )
                                else:
                                    self.check_max_limit_and_delete(msg, tracker, torrent)
                        else:
                            if self.check_for_unregistered_torrents_in_bhd(tracker, msg_up, torrent.hash):
                                skip, age = self.is_within_grace(torrent)
                                if skip:
                                    logger.print_line(
                                        logger.insert_space(
                                            f"Skipping removal (within grace "
                                            f"{self.rem_unregistered_grace_minutes} min, age {age:.1f} min): "
                                            f"{self.t_name}",
                                            3,
                                        ),
                                        self.config.loglevel,
                                    )
                                else:
                                    self.check_max_limit_and_delete(msg, tracker, torrent)
                    # Tag any error torrents
                    if self.cfg_tag_error and self.tag_error not in check_tags:
                        self.tag_tracker_error(msg, tracker, torrent)

            try:
                process_single_torrent()
            except Exception as ex:
                logger.stacktrace()
                self.config.notify(ex, "Remove Unregistered Torrents", False)
                logger.error(f"Remove Unregistered Torrents Error: {ex}")

    def check_max_limit_and_delete(self, msg, tracker, torrent):
        """Checks if the max limit of torrents to remove has been reached for the tracker."""
        tracker_url = tracker["url"]
        if self.rem_unregistered_max_torrents > 0:
            if tracker_url not in self.tracker_del_count:
                self.tracker_del_count[tracker_url] = 0
            if self.tracker_del_count[tracker_url] >= self.rem_unregistered_max_torrents:
                logger.print_line(
                    logger.insert_space(
                        f"Skipping removal (max limit of {self.rem_unregistered_max_torrents} reached for tracker {tracker_url}):"
                        f" {self.t_name}",
                        3,
                    ),
                    self.config.loglevel,
                )
                return
            self.tracker_del_count[tracker_url] += 1
        self.del_unregistered(msg, tracker, torrent)

    def rem_unregistered(self):
        """Remove torrents with unregistered trackers."""
        start_time = time.time()
        self.remove_previous_errors()
        self.process_torrent_issues()

        self.config.webhooks_factory.notify(self.torrents_updated_issue, self.notify_attr_issue, group_by="status")
        self.config.webhooks_factory.notify(self.torrents_updated_unreg, self.notify_attr_unreg, group_by="status")

        if self.cfg_rem_unregistered:
            if self.stats_deleted >= 1 or self.stats_deleted_contents >= 1:
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
            else:
                logger.print_line("No unregistered torrents found.", self.config.loglevel)
        if self.stats_untagged >= 1:
            logger.print_line(
                f"{'Did not delete' if self.config.dry_run else 'Deleted'} {self.tag_error} tags for {self.stats_untagged} "
                f".torrent{'s.' if self.stats_untagged > 1 else '.'}",
                self.config.loglevel,
            )
        if self.stats_tagged >= 1:
            logger.separator(
                f"{self.stats_tagged} Torrents with tracker errors found",
                space=False,
                border=False,
                loglevel=self.config.loglevel,
            )
            logger.print_line(self.tor_error_summary.rstrip(), self.config.loglevel)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Remove unregistered command completed in {duration:.2f} seconds")

    def tag_tracker_error(self, msg, tracker, torrent):
        """Tags any trackers with errors"""
        tor_error = ""
        tor_error += logger.insert_space(f"Torrent Name: {self.t_name}", 3) + "\n"
        tor_error += logger.insert_space(f"Status: {msg}", 9) + "\n"
        tor_error += logger.insert_space(f"Tracker: {tracker['url']}", 8) + "\n"
        tor_error += logger.insert_space(f"Added Tag: {self.tag_error}", 6) + "\n"
        self.tor_error_summary += tor_error
        self.stats_tagged += 1
        attr = {
            "function": "tag_tracker_error",
            "title": "Tag Tracker Error Torrents",
            "body": tor_error,
            "torrents": [self.t_name],
            "torrent_category": self.t_cat,
            "torrent_tag": self.tag_error,
            "torrent_status": msg,
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.torrents_updated_issue.append(self.t_name)
        self.notify_attr_issue.append(attr)
        if not self.config.dry_run:
            torrent.add_tags(tags=self.tag_error)

    def del_unregistered(self, msg, tracker, torrent):
        """Deletes unregistered torrents"""
        body = []
        body += logger.print_line(logger.insert_space(f"Torrent Name: {self.t_name}", 3), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f"Status: {msg}", 9), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
        attr = {
            "function": "rem_unregistered",
            "title": "Removing Unregistered Torrents",
            "torrents": [self.t_name],
            "torrent_category": self.t_cat,
            "torrent_status": msg,
            "torrent_tag": ", ".join(tracker["tag"]),
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        if self.qbt.has_cross_seed(torrent):
            # Checks if any of the original torrents are working
            if "" in self.t_msg or 2 in self.t_status:
                attr["torrents_deleted_and_contents"] = False
                if not self.config.dry_run:
                    self.qbt.tor_delete_recycle(torrent, attr)
                body += logger.print_line(logger.insert_space("Deleted .torrent but NOT content files.", 8), self.config.loglevel)
                self.stats_deleted += 1
            else:
                attr["torrents_deleted_and_contents"] = True
                if not self.config.dry_run:
                    self.qbt.tor_delete_recycle(torrent, attr)
                body += logger.print_line(logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel)
                self.stats_deleted_contents += 1
        else:
            attr["torrents_deleted_and_contents"] = True
            if not self.config.dry_run:
                self.qbt.tor_delete_recycle(torrent, attr)
            body += logger.print_line(logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel)
            self.stats_deleted_contents += 1
        attr["body"] = "\n".join(body)
        self.torrents_updated_unreg.append(self.t_name)
        self.notify_attr_unreg.append(attr)
