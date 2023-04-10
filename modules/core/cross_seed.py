import os
from collections import Counter

from modules import util

logger = util.logger


class CrossSeed:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats_added = 0
        self.stats_tagged = 0

        self.cross_seed()

    def cross_seed(self):
        """Move torrents from cross seed directory to correct save directory."""
        logger.separator("Checking for Cross-Seed Torrents", space=False, border=False)
        # List of categories for all torrents moved
        categories = []

        # Only get torrent files
        cs_files = [f for f in os.listdir(self.config.cross_seed_dir) if f.endswith("torrent")]
        dir_cs = self.config.cross_seed_dir
        dir_cs_out = os.path.join(dir_cs, "qbit_manage_added")
        os.makedirs(dir_cs_out, exist_ok=True)
        for file in cs_files:
            tr_name = file.split("]", 2)[2].split(".torrent")[0]
            t_tracker = file.split("]", 2)[1][1:]
            # Substring Key match in dictionary (used because t_name might not match exactly with self.qbt.torrentinfo key)
            # Returned the dictionary of filtered item
            torrentdict_file = dict(filter(lambda item: tr_name in item[0], self.qbt.torrentinfo.items()))
            if torrentdict_file:
                # Get the exact torrent match name from self.qbt.torrentinfo
                t_name = next(iter(torrentdict_file))
                dest = os.path.join(self.qbt.torrentinfo[t_name]["save_path"], "")
                src = os.path.join(dir_cs, file)
                dir_cs_out = os.path.join(dir_cs, "qbit_manage_added", file)
                category = self.get_category(dest)
                # Only add cross-seed torrent if original torrent is complete
                if self.qbt.torrentinfo[t_name]["is_complete"]:
                    categories.append(category)
                    body = []
                    body += logger.print_line(
                        f"{'Not Adding' if self.config.dry_run else 'Adding'} to qBittorrent:", self.config.loglevel
                    )
                    body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                    body += logger.print_line(logger.insert_space(f"Category: {category}", 7), self.config.loglevel)
                    body += logger.print_line(logger.insert_space(f"Save_Path: {dest}", 6), self.config.loglevel)
                    body += logger.print_line(logger.insert_space(f"Tracker: {t_tracker}", 8), self.config.loglevel)
                    attr = {
                        "function": "cross_seed",
                        "title": "Adding New Cross-Seed Torrent",
                        "body": "\n".join(body),
                        "torrent_name": t_name,
                        "torrent_category": category,
                        "torrent_save_path": dest,
                        "torrent_tag": "cross-seed",
                        "torrent_tracker": t_tracker,
                    }
                    self.config.send_notifications(attr)
                    self.stats_added += 1
                    if not self.config.dry_run:
                        self.client.torrents.add(
                            torrent_files=src, save_path=dest, category=category, tags="cross-seed", is_paused=True
                        )
                        util.move_files(src, dir_cs_out)
                else:
                    logger.print_line(f"Found {t_name} in {dir_cs} but original torrent is not complete.", self.config.loglevel)
                    logger.print_line("Not adding to qBittorrent", self.config.loglevel)
            else:
                error = f"{t_name} not found in torrents. Cross-seed Torrent not added to qBittorrent."
                if self.config.dry_run:
                    logger.print_line(error, self.config.loglevel)
                else:
                    logger.print_line(error, "WARNING")
                self.config.notify(error, "cross-seed", False)
        # Tag missing cross-seed torrents tags
        for torrent in self.qbt.torrent_list:
            t_name = torrent.name
            t_cat = torrent.category
            if (
                "cross-seed" not in torrent.tags
                and self.qbt.torrentinfo[t_name]["count"] > 1
                and self.qbt.torrentinfo[t_name]["first_hash"] != torrent.hash
            ):
                tracker = self.qbt.get_tags(torrent.trackers)
                self.stats_tagged += 1
                body = logger.print_line(
                    f"{'Not Adding' if self.config.dry_run else 'Adding'} 'cross-seed' tag to {t_name}", self.config.loglevel
                )
                attr = {
                    "function": "tag_cross_seed",
                    "title": "Tagging Cross-Seed Torrent",
                    "body": body,
                    "torrent_name": t_name,
                    "torrent_category": t_cat,
                    "torrent_tag": "cross-seed",
                    "torrent_tracker": tracker,
                }
                self.config.send_notifications(attr)
                if not self.config.dry_run:
                    torrent.add_tags(tags="cross-seed")

        numcategory = Counter(categories)
        for cat in numcategory:
            if numcategory[cat] > 0:
                logger.print_line(
                    f"{numcategory[cat]} {cat} cross-seed .torrents {'not added' if self.config.dry_run else 'added'}.",
                    self.config.loglevel,
                )
        if self.stats_added > 0:
            logger.print_line(
                f"Total {self.stats_added} cross-seed .torrents {'not added' if self.config.dry_run else 'added'}.",
                self.config.loglevel,
            )
        if self.stats_tagged > 0:
            logger.print_line(
                f"Total {self.stats_tagged} cross-seed .torrents {'not added' if self.config.dry_run else 'added'}.",
                self.config.loglevel,
            )
