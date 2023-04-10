from modules import util

logger = util.logger


class Tags:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0

        self.tags()

    def tags(self):
        """Update tags for torrents"""
        self.stats = 0
        ignore_tags = self.config.settings["ignoreTags_OnUpdate"]
        logger.separator("Updating Tags", space=False, border=False)
        for torrent in self.qbt.torrent_list:
            check_tags = util.get_list(torrent.tags)
            if torrent.tags == "" or (len([trk for trk in check_tags if trk not in ignore_tags]) == 0):
                tracker = self.qbt.get_tags(torrent.trackers)
                if tracker["tag"]:
                    self.stats += len(tracker["tag"])
                    body = []
                    body += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
                    body += logger.print_line(
                        logger.insert_space(f'New Tag{"s" if len(tracker["tag"]) > 1 else ""}: {", ".join(tracker["tag"])}', 8),
                        self.config.loglevel,
                    )
                    body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                    body.extend(
                        self.qbt.set_tags_and_limits(
                            torrent,
                            tracker["max_ratio"],
                            tracker["max_seeding_time"],
                            tracker["limit_upload_speed"],
                            tracker["tag"],
                        )
                    )
                    category = self.qbt.get_category(torrent.save_path) if torrent.category == "" else torrent.category
                    attr = {
                        "function": "tag_update",
                        "title": "Updating Tags",
                        "body": "\n".join(body),
                        "torrent_name": torrent.name,
                        "torrent_category": category,
                        "torrent_tag": ", ".join(tracker["tag"]),
                        "torrent_tracker": tracker["url"],
                        "notifiarr_indexer": tracker["notifiarr"],
                        "torrent_max_ratio": tracker["max_ratio"],
                        "torrent_max_seeding_time": tracker["max_seeding_time"],
                        "torrent_limit_upload_speed": tracker["limit_upload_speed"],
                    }
                    self.config.send_notifications(attr)
        if self.stats >= 1:
            logger.print_line(
                f"{'Did not update' if self.config.dry_run else 'Updated'} {self.stats} new tags.", self.config.loglevel
            )
        else:
            logger.print_line("No new torrents to tag.", self.config.loglevel)
