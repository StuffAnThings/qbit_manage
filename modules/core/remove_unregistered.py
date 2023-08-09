from qbittorrentapi import NotFound404Error
from qbittorrentapi import TrackerStatus

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

        for torrent in self.qbt.torrentvalid:
            check_tags = util.get_list(torrent.tags)
            t_name = torrent.name
            # Remove any error torrents Tags that are no longer unreachable.
            if self.tag_error in check_tags:
                tracker = self.qbt.get_tags(torrent.trackers)
                self.stats_untagged += 1
                body = []
                body += logger.print_line(
                    f"Previous Tagged {self.tag_error} torrent currently has a working tracker.", self.config.loglevel
                )
                body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f"Removed Tag: {self.tag_error}", 4), self.config.loglevel)
                body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
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

    def check_for_unregistered_torrents_using_bhd_api(self, tracker, msg_up, torrent_hash):
        """
        Checks if a torrent is unregistered using the BHD API if the tracker is BHD.
        """
        if (
            "tracker.beyond-hd.me" in tracker["url"]
            and self.config.beyond_hd is not None
            and not list_in_text(msg_up, TorrentMessages.IGNORE_MSGS)
        ):
            json = {"info_hash": torrent_hash}
            response = self.config.beyond_hd.search(json)
            if response["total_results"] == 0:
                return True
        return False

    def process_torrent_issues(self):
        """Process torrent issues."""
        self.torrents_updated_issue = []  # List of torrents updated
        self.notify_attr_issue = []  # List of single torrent attributes to send to notifiarr
        self.torrents_updated_unreg = []  # List of torrents updated
        self.notify_attr_unreg = []  # List of single torrent attributes to send to notifiarr

        for torrent in self.qbt.torrentissue:
            self.t_name = torrent.name
            self.t_cat = self.qbt.torrentinfo[self.t_name]["Category"]
            self.t_msg = self.qbt.torrentinfo[self.t_name]["msg"]
            self.t_status = self.qbt.torrentinfo[self.t_name]["status"]
            check_tags = util.get_list(torrent.tags)
            try:
                unregistered_everywhere = self.cfg_rem_unregistered
                no_trackers_working = self.cfg_tag_error and self.tag_error not in check_tags
                msgs = []
                for trk in torrent.trackers:
                    if trk.url.startswith("http") or trk.url.startswith("udp://"):
                        tracker = self.qbt.get_tags([trk])
                        msg_up = trk.msg.upper()
                        msgs.append(trk.msg)
                        if TrackerStatus(trk.status) == TrackerStatus.NOT_WORKING:
                            # Check for unregistered torrents
                            if unregistered_everywhere:
                                if (
                                    not list_in_text(msg_up, TorrentMessages.UNREGISTERED_MSGS)
                                    or list_in_text(msg_up, TorrentMessages.IGNORE_MSGS)
                                ) and not self.check_for_unregistered_torrents_using_bhd_api(tracker, msg_up, torrent.hash):
                                    unregistered_everywhere = False
                        else:
                            no_trackers_working = False
                        if not unregistered_everywhere and not no_trackers_working:  # No reason to continue
                            break

                # Remove torrents when no tracker has this torrent
                if unregistered_everywhere:
                    self.del_unregistered(" | ".join(msgs), self.qbt.get_tags(torrent.trackers), torrent)
                # Tag torrents when all trackers have issues
                elif no_trackers_working:
                    self.tag_tracker_error(" | ".join(msgs), self.qbt.get_tags(torrent.trackers), torrent)

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

        self.config.webhooks_factory.notify(self.torrents_updated_issue, self.notify_attr_issue, group_by="tag")
        self.config.webhooks_factory.notify(self.torrents_updated_unreg, self.notify_attr_unreg, group_by="tag")

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
        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
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
        self.torrents_updated_unreg.append(self.t_name)
        self.notify_attr_unreg.append(attr)
        self.qbt.torrentinfo[self.t_name]["count"] -= 1
