from modules import util
from modules.webhooks import GROUP_NOTIFICATION_LIMIT

logger = util.logger


class Tags:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0
        self.share_limits_suffix_tag = qbit_manager.config.share_limits_suffix_tag  # suffix tag for share limits
        self.torrents_updated = []  # List of torrents updated
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr
        self.tags()
        self.notify()

    def tags(self):
        """Update tags for torrents"""
        ignore_tags = self.config.settings["ignoreTags_OnUpdate"]
        logger.separator("Updating Tags", space=False, border=False)
        for torrent in self.qbt.torrent_list:
            check_tags = [tag for tag in util.get_list(torrent.tags) if self.share_limits_suffix_tag not in tag]

            if torrent.tags == "" or (len([trk for trk in check_tags if trk not in ignore_tags]) == 0):
                tracker = self.qbt.get_tags(torrent.trackers)
                if tracker["tag"]:
                    t_name = torrent.name
                    self.stats += len(tracker["tag"])
                    body = []
                    body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                    body += logger.print_line(
                        logger.insert_space(f'New Tag{"s" if len(tracker["tag"]) > 1 else ""}: {", ".join(tracker["tag"])}', 8),
                        self.config.loglevel,
                    )
                    body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                    if not self.config.dry_run:
                        torrent.add_tags(tracker["tag"])
                    category = self.qbt.get_category(torrent.save_path) if torrent.category == "" else torrent.category
                    attr = {
                        "function": "tag_update",
                        "title": "Updating Tags",
                        "body": "\n".join(body),
                        "torrents": [t_name],
                        "torrent_category": category,
                        "torrent_tag": ", ".join(tracker["tag"]),
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

    def notify(self):
        """Send notifications"""

        def group_notifications_by_tag(self):
            group_attr = {}
            """Group notifications by tag"""
            for attr in self.notify_attr:
                tag = attr["torrent_tag"]
                if tag not in group_attr:
                    group_attr[tag] = {
                        "torrent_tag": tag,
                        "torrents": [attr["torrents"][0]],
                        "torrent_tracker": attr["torrent_tracker"],
                        "notifiarr_indexer": attr["notifiarr_indexer"],
                    }
                else:
                    group_attr[tag]["torrents"].append(attr["torrents"][0])
            return group_attr

        if len(self.torrents_updated) > GROUP_NOTIFICATION_LIMIT:
            logger.trace(
                f"Number of tags > {GROUP_NOTIFICATION_LIMIT}, grouping notifications by tag.",
            )
            group_attr = group_notifications_by_tag(self)
            for tag in group_attr:
                attr = {
                    "function": "tag_update",
                    "title": f"Updating Tags for {tag}",
                    "body": f"Updated {len(group_attr[tag]['torrents'])} "
                    f"{'torrents' if len(group_attr[tag]['torrents']) > 1 else 'torrent'} with tag '{tag}'",
                    "torrents": group_attr[tag]["torrents"],
                    "torrent_category": None,
                    "torrent_tag": tag,
                    "torrent_tracker": group_attr[tag]["torrent_tracker"],
                    "notifiarr_indexer": group_attr[tag]["notifiarr_indexer"],
                }
                self.config.send_notifications(attr)
        else:
            for attr in self.notify_attr:
                self.config.send_notifications(attr)
