from qbittorrentapi import Conflict409Error

from modules import util
from modules.webhooks import GROUP_NOTIFICATION_LIMIT

logger = util.logger


class Category:
    def __init__(self, qbit_manager):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0
        self.torrents_updated = []  # List of torrents updated
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr

        self.category()
        self.notify()

    def category(self):
        """Update category for torrents that don't have any category defined and returns total number categories updated"""
        logger.separator("Updating Categories", space=False, border=False)
        torrent_list = self.qbt.get_torrents({"category": "", "status_filter": "completed"})
        for torrent in torrent_list:
            new_cat = self.qbt.get_category(torrent.save_path)
            self.update_cat(torrent, new_cat, False)

        # Change categories
        if self.config.cat_change:
            for old_cat in self.config.cat_change:
                torrent_list = self.qbt.get_torrents({"category": old_cat, "status_filter": "completed"})
                for torrent in torrent_list:
                    new_cat = self.config.cat_change[old_cat]
                    self.update_cat(torrent, new_cat, True)

        if self.stats >= 1:
            logger.print_line(
                f"{'Did not update' if self.config.dry_run else 'Updated'} {self.stats} new categories.", self.config.loglevel
            )
        else:
            logger.print_line("No new torrents to categorize.", self.config.loglevel)

    def update_cat(self, torrent, new_cat, cat_change):
        """Update category based on the torrent information"""
        tracker = self.qbt.get_tags(torrent.trackers)
        t_name = torrent.name
        old_cat = torrent.category
        if not self.config.dry_run:
            try:
                torrent.set_category(category=new_cat)
                if torrent.auto_tmm is False and self.config.settings["force_auto_tmm"]:
                    torrent.set_auto_management(True)
            except Conflict409Error:
                ex = logger.print_line(
                    f'Existing category "{new_cat}" not found for save path {torrent.save_path}, category will be created.',
                    self.config.loglevel,
                )
                self.config.notify(ex, "Update Category", False)
                self.client.torrent_categories.create_category(name=new_cat, save_path=torrent.save_path)
                torrent.set_category(category=new_cat)
        body = []
        body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
        if cat_change:
            body += logger.print_line(logger.insert_space(f"Old Category: {old_cat}", 3), self.config.loglevel)
            title = "Moving Categories"
        else:
            title = "Updating Categories"
        body += logger.print_line(logger.insert_space(f"New Category: {new_cat}", 3), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
        attr = {
            "function": "cat_update",
            "title": title,
            "body": "\n".join(body),
            "torrents": [t_name],
            "torrent_category": new_cat,
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.notify_attr.append(attr)
        self.torrents_updated.append(t_name)
        self.stats += 1

    def notify(self):
        """Send notifications"""

        def group_notifications_by_category(self):
            group_attr = {}
            """Group notifications by category"""
            for attr in self.notify_attr:
                category = attr["torrent_category"]
                if category not in group_attr:
                    group_attr[category] = {
                        "torrent_category": category,
                        "torrents": [attr["torrents"][0]],
                    }
                else:
                    group_attr[category]["torrents"].append(attr["torrents"][0])
            return group_attr

        if len(self.torrents_updated) > GROUP_NOTIFICATION_LIMIT:
            logger.trace(
                f"Number of torrents updated > {GROUP_NOTIFICATION_LIMIT}, grouping notifications by category.",
            )
            group_attr = group_notifications_by_category(self)
            for category in group_attr:
                attr = {
                    "function": "cat_update",
                    "title": f"Updating Category for {category}",
                    "body": f"Updated {len(group_attr[category]['torrents'])} "
                    f"{'torrents' if len(group_attr[category]['torrents']) > 1 else 'torrent'} with category '{category}'",
                    "torrents": group_attr[category]["torrents"],
                    "torrent_category": category,
                    "torrent_tracker": None,
                    "notifiarr_indexer": None,
                }
                self.config.send_notifications(attr)
        else:
            for attr in self.notify_attr:
                self.config.send_notifications(attr)
