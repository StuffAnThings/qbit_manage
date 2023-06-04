from datetime import timedelta

from modules import util

logger = util.logger


class ReCheck:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_resumed = 0
        self.stats_rechecked = 0

        self.recheck()

    def recheck(self):
        """Function used to recheck paused torrents sorted by size and resume torrents that are completed"""
        if self.config.commands["recheck"]:
            logger.separator("Rechecking Paused Torrents", space=False, border=False)
            # sort by size and paused
            torrent_list = self.qbt.get_torrents({"status_filter": "paused", "sort": "size"})
            if torrent_list:
                for torrent in torrent_list:
                    tracker = self.qbt.get_tags(torrent.trackers)
                    # Resume torrent if completed
                    if torrent.progress == 1:
                        if torrent.max_ratio < 0 and torrent.max_seeding_time < 0:
                            self.stats_resumed += 1
                            body = logger.print_line(
                                f"{'Not Resuming' if self.config.dry_run else 'Resuming'} [{tracker['tag']}] - {torrent.name}",
                                self.config.loglevel,
                            )
                            attr = {
                                "function": "recheck",
                                "title": "Resuming Torrent",
                                "body": body,
                                "torrents": [torrent.name],
                                "torrent_category": torrent.category,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                            }
                            self.config.send_notifications(attr)
                            if not self.config.dry_run:
                                torrent.resume()
                        else:
                            # Check to see if torrent meets AutoTorrentManagement criteria
                            logger.debug("DEBUG: Torrent to see if torrent meets AutoTorrentManagement Criteria")
                            logger.debug(logger.insert_space(f"- Torrent Name: {torrent.name}", 2))
                            logger.debug(
                                logger.insert_space(f"-- Ratio vs Max Ratio: {torrent.ratio:.2f} < {torrent.max_ratio:.2f}", 4)
                            )
                            logger.debug(
                                logger.insert_space(
                                    f"-- Seeding Time vs Max Seed Time: {timedelta(seconds=torrent.seeding_time)} < "
                                    f"{timedelta(minutes=torrent.max_seeding_time)}",
                                    4,
                                )
                            )
                            if (
                                (torrent.max_ratio >= 0 and torrent.ratio < torrent.max_ratio and torrent.max_seeding_time < 0)
                                or (
                                    torrent.max_seeding_time >= 0
                                    and (torrent.seeding_time < (torrent.max_seeding_time * 60))
                                    and torrent.max_ratio < 0
                                )
                                or (
                                    torrent.max_ratio >= 0
                                    and torrent.max_seeding_time >= 0
                                    and torrent.ratio < torrent.max_ratio
                                    and (torrent.seeding_time < (torrent.max_seeding_time * 60))
                                )
                            ):
                                self.stats_resumed += 1
                                body = logger.print_line(
                                    f"{'Not Resuming' if self.config.dry_run else 'Resuming'} [{tracker['tag']}] - "
                                    f"{torrent.name}",
                                    self.config.loglevel,
                                )
                                attr = {
                                    "function": "recheck",
                                    "title": "Resuming Torrent",
                                    "body": body,
                                    "torrents": [torrent.name],
                                    "torrent_category": torrent.category,
                                    "torrent_tracker": tracker["url"],
                                    "notifiarr_indexer": tracker["notifiarr"],
                                }
                                self.config.send_notifications(attr)
                                if not self.config.dry_run:
                                    torrent.resume()
                    # Recheck
                    elif (
                        torrent.progress == 0
                        and self.qbt.torrentinfo[torrent.name]["is_complete"]
                        and not torrent.state_enum.is_checking
                    ):
                        self.stats_rechecked += 1
                        body = logger.print_line(
                            f"{'Not Rechecking' if self.config.dry_run else 'Rechecking'} [{tracker['tag']}] - {torrent.name}",
                            self.config.loglevel,
                        )
                        attr = {
                            "function": "recheck",
                            "title": "Rechecking Torrent",
                            "body": body,
                            "torrents": [torrent.name],
                            "torrent_category": torrent.category,
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                        }
                        self.config.send_notifications(attr)
                        if not self.config.dry_run:
                            torrent.recheck()
