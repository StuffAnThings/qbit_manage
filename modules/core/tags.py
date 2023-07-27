from modules import util

logger = util.logger


class Tags:
    def __init__(self, qbit_manager, torrents_to_tag=None, silent=False):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0
        self.share_limits_tag = qbit_manager.config.share_limits_tag  # suffix tag for share limits
        self.torrents_updated = []  # List of torrents updated
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr

        level = logger._logger.level
        if silent:
            logger._logger.setLevel("WARN")
        self.tags(self.qbt.torrent_list if torrents_to_tag is None else torrents_to_tag)
        if silent:
            logger._logger.setLevel(level)
        else:  # TODO: This should probably be a setting
            self.config.webhooks_factory.notify(self.torrents_updated, self.notify_attr, group_by="tag")

    def tags(self, torrent_list):
        """Update tags for torrents"""
        ignore_tags = self.config.settings["ignoreTags_OnUpdate"]
        logger.separator("Updating Tags", space=False, border=False)
        for torrent in torrent_list:
            check_tags = [tag for tag in util.get_list(torrent.tags) if self.share_limits_tag not in tag]
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
