from modules import util

logger = util.logger


class RemoveCrossSeedTags:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_removed = 0

        self.torrents_updated = []  # List of torrents with tags removed
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr

        self.rem_cross_seed_tags()

    def rem_cross_seed_tags(self):
        """Move torrents from cross seed directory to correct save directory."""
        logger.separator("Removing cross-seed tag from Torrents", space=False, border=False)

        logger.print_line("Checking for torrents with cross-seed tag")
        torrents_list = self.qbt.get_torrents({"sort": "added_on", "reverse": True})

        for torrent in torrents_list:
            torrent_tags = torrent.tags.split(", ")
            if 'cross-seed' in torrent_tags:
                torrent.remove_tags(tags='cross-seed')
                self.torrents_updated.append(torrent.name)
                self.stats_removed +=1 

        if self.stats_removed >= 1:
            logger.print_line(
                f"{'Did not remove' if self.config.dry_run else 'Removed'} {self.stats_removed} torrents with cross-seed tag.", self.config.loglevel
            )
        else:
            logger.print_line("No new torrents to update.", self.config.loglevel)



