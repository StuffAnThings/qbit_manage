from qbittorrentapi import NotFound404Error

from modules import util
from modules.util import list_in_text
from modules.util import TorrentMessages

logger = util.logger


class RemoveUnregistered:
    def __init__(self, qbit_manager):
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

        if self.cfg_tag_error:
            logger.separator("Tagging Torrents with Tracker Errors", space=False, border=False)
        elif self.cfg_rem_unregistered:
            logger.separator("Removing Unregistered Torrents", space=False, border=False)

        self.rem_unregistered()

    def remove_previous_errors(self):
        """Removes any previous torrents that were tagged as an error but are now working."""
        for torrent in self.qbt.torrentvalid:
            check_tags = util.get_list(torrent.tags)
            # Remove any error torrents Tags that are no longer unreachable.
            if self.tag_error in check_tags:
                tracker = self.get_tags(torrent.trackers)
                self.stats_untagged += 1
                body = []
                body += logger.print_line(
                    f"Previous Tagged {self.tag_error} torrent currently has a working tracker.", self.config.loglevel
                )
                body += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f"Removed Tag: {self.tag_error}", 4), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                if not self.config.dry_run:
                    torrent.remove_tags(tags=self.tag_error)
                attr = {
                    "function": "untag_tracker_error",
                    "title": "Untagging Tracker Error Torrent",
                    "body": "\n".join(body),
                    "torrent_name": torrent.name,
                    "torrent_category": torrent.category,
                    "torrent_tag": self.tag_error,
                    "torrent_tracker": tracker["url"],
                    "notifiarr_indexer": tracker["notifiarr"],
                }
                self.config.send_notifications(attr)

    def process_torrent_issues(self):
        for torrent in self.qbt.torrentissue:
            self.t_name = torrent.name
            self.t_cat = self.qbt.torrentinfo[self.t_name]["Category"]
            self.t_msg = self.qbt.torrentinfo[self.t_name]["msg"]
            self.t_status = self.qbt.torrentinfo[self.t_name]["status"]
            check_tags = util.get_list(torrent.tags)
            try:
                for trk in torrent.trackers:
                    if trk.url.startswith("http"):
                        tracker = self.qbt.get_tags([trk])
                        msg_up = trk.msg.upper()
                        msg = trk.msg
                        # Tag any error torrents
                        if self.cfg_tag_error:
                            if trk.status == TorrentMessages.TORRENT_STATUS_NOT_WORKING and self.tag_error not in check_tags:
                                self.tag_tracker_error(msg, tracker, torrent)
                        if self.cfg_rem_unregistered:
                            # Tag any error torrents that are not unregistered
                            if (
                                not list_in_text(msg_up, TorrentMessages.UNREGISTERED_MSGS)
                                and trk.status == TorrentMessages.TORRENT_STATUS_NOT_WORKING
                                and self.tag_error not in check_tags
                            ):
                                # Check for unregistered torrents using BHD API if the tracker is BHD
                                if (
                                    "tracker.beyond-hd.me" in tracker["url"]
                                    and self.config.beyond_hd is not None
                                    and not list_in_text(msg_up, TorrentMessages.IGNORE_MSGS)
                                ):
                                    json = {"info_hash": torrent.hash}
                                    response = self.config.beyond_hd.search(json)
                                    if response["total_results"] == 0:
                                        self.del_unregistered(msg, tracker, torrent)
                                        break
                                self.tag_tracker_error(msg, tracker, torrent)
                            if (
                                list_in_text(msg_up, TorrentMessages.UNREGISTERED_MSGS)
                                and not list_in_text(msg_up, TorrentMessages.IGNORE_MSGS)
                                and trk.status == TorrentMessages.TORRENT_STATUS_NOT_WORKING
                            ):
                                self.del_unregistered(msg, tracker, torrent)
                                break
            except NotFound404Error:
                continue
            except Exception as ex:
                logger.stacktrace()
                self.config.notify(ex, "Remove Unregistered Torrents", False)
                logger.error(f"Remove Unregistered Torrents Error: {ex}")

    def rem_unregistered(self):
        """Remove torrents with unregistered trackers."""
        self.remove_previous_errors()
        self.process_torrent_issues()
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

    def tag_tracker_error(self, msg, tracker, torrent):
        """Tags any trackers with errors"""
        tor_error = ""
        tor_error += logger.insert_space(f"Torrent Name: {self.t_name}", 3) + "\n"
        tor_error += logger.insert_space(f"Status: {msg}", 9) + "\n"
        tor_error += logger.insert_space(f'Tracker: {tracker["url"]}', 8) + "\n"
        tor_error += logger.insert_space(f"Added Tag: {self.tag_error}", 6) + "\n"
        self.tor_error_summary += tor_error
        self.stats_tagged += 1
        attr = {
            "function": "tag_tracker_error",
            "title": "Tag Tracker Error Torrents",
            "body": tor_error,
            "torrent_name": self.t_name,
            "torrent_category": self.t_cat,
            "torrent_tag": self.tag_error,
            "torrent_status": msg,
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.config.send_notifications(attr)
        if not self.config.dry_run:
            torrent.add_tags(tags=self.tag_error)

    def del_unregistered(self, msg, tracker, torrent):
        """Deletes unregistered torrents"""
        body = []
        body += logger.print_line(logger.insert_space(f"Torrent Name: {self.t_name}", 3), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f"Status: {msg}", 9), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
        attr = {
            "function": "rem_unregistered",
            "title": "Removing Unregistered Torrents",
            "torrent_name": self.t_name,
            "torrent_category": self.t_cat,
            "torrent_status": msg,
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        if self.qbt.torrentinfo[self.t_name]["count"] > 1:
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
        self.config.send_notifications(attr)
        self.qbt.torrentinfo[self.t_name]["count"] -= 1
