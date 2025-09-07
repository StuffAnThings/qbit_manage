import time

from modules import util
from modules.qbit_error_handler import handle_qbit_api_errors

logger = util.logger


class Category:
    def __init__(self, qbit_manager, hashes: list[str] = None):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.hashes = hashes
        self.client = qbit_manager.client
        self.stats = 0
        self.torrents_updated = []  # List of torrents updated
        self.notify_attr = []  # List of single torrent attributes to send to notifiarr
        self.uncategorized_mapping = "Uncategorized"
        self.status_filter = "completed" if self.config.settings["cat_filter_completed"] else "all"
        self.cat_update_all = self.config.settings["cat_update_all"]
        self.category()
        self.change_categories()
        self.config.webhooks_factory.notify(self.torrents_updated, self.notify_attr, group_by="category")

    def category(self):
        """Update category for torrents that don't have any category defined and returns total number categories updated"""
        start_time = time.time()
        logger.separator("Updating Categories", space=False, border=False)
        torrent_list_filter = {"status_filter": self.status_filter}
        if self.hashes:
            torrent_list_filter["torrent_hashes"] = self.hashes
        if not self.cat_update_all and not self.hashes:
            torrent_list_filter["category"] = ""
        torrent_list = self.qbt.get_torrents(torrent_list_filter)
        for torrent in torrent_list:
            torrent_category = torrent.category
            new_cat = []
            new_cat.extend(self.get_tracker_cat(torrent) or self.qbt.get_category(torrent.save_path))
            if not torrent.auto_tmm and torrent_category:
                logger.print_line(
                    f"{torrent.name} has Automatic Torrent Management disabled and already has the category"
                    f" {torrent_category}. Skipping..",
                    "DEBUG",
                )
                continue
            if new_cat[0] == self.uncategorized_mapping:
                logger.print_line(f"{torrent.name} remains uncategorized.", "DEBUG")
                continue
            if torrent_category not in new_cat:
                self.update_cat(torrent, new_cat[0], False)

        if self.stats >= 1:
            logger.print_line(
                f"{'Did not update' if self.config.dry_run else 'Updated'} {self.stats} new categories.", self.config.loglevel
            )
        else:
            logger.print_line("No new torrents to categorize.", self.config.loglevel)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Category command completed in {duration:.2f} seconds")

    def change_categories(self):
        """Handle category changes separately after main categorization"""
        if not self.config.cat_change:
            return

        logger.separator("Changing Categories", space=False, border=False)
        start_time = time.time()

        for torrent_category, updated_cat in self.config.cat_change.items():
            # Get torrents with the specific category to be changed
            torrent_list_filter = {"status_filter": self.status_filter, "category": torrent_category}
            if self.hashes:
                torrent_list_filter["torrent_hashes"] = self.hashes

            torrent_list = self.qbt.get_torrents(torrent_list_filter)

            for torrent in torrent_list:
                self.update_cat(torrent, updated_cat, True)

        end_time = time.time()
        duration = end_time - start_time
        logger.debug(f"Category change command completed in {duration:.2f} seconds")

    def get_tracker_cat(self, torrent):
        tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
        return [tracker["cat"]] if tracker["cat"] else None

    def update_cat(self, torrent, new_cat, cat_change):
        """Update category based on the torrent information"""
        tracker = self.qbt.get_tags(self.qbt.get_tracker_urls(torrent.trackers))
        t_name = torrent.name
        old_cat = torrent.category
        if not self.config.dry_run:

            @handle_qbit_api_errors(context="set_category", retry_attempts=2)
            def set_category_with_creation():
                try:
                    torrent.set_category(category=new_cat)
                    if (
                        torrent.auto_tmm is False
                        and self.config.settings["force_auto_tmm"]
                        and not any(tag in torrent.tags for tag in self.config.settings.get("force_auto_tmm_ignore_tags", []))
                    ):
                        torrent.set_auto_management(True)
                except Exception as e:
                    # Check if it's a category creation issue
                    if "not found" in str(e).lower() or "409" in str(e):
                        ex = logger.print_line(
                            f'Existing category "{new_cat}" not found for save path '
                            f"{torrent.save_path}, category will be created.",
                            self.config.loglevel,
                        )
                        self.config.notify(ex, "Update Category", False)
                        self.client.torrent_categories.create_category(name=new_cat, save_path=torrent.save_path)
                        torrent.set_category(category=new_cat)
                    else:
                        raise

            set_category_with_creation()
        body = []
        body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
        if cat_change:
            body += logger.print_line(logger.insert_space(f"Old Category: {old_cat}", 3), self.config.loglevel)
            title = "Moving Categories"
        else:
            title = "Updating Categories"
        body += logger.print_line(logger.insert_space(f"New Category: {new_cat}", 3), self.config.loglevel)
        body += logger.print_line(logger.insert_space(f"Tracker: {tracker['url']}", 8), self.config.loglevel)
        attr = {
            "function": "cat_update",
            "title": title,
            "body": "\n".join(body),
            "torrents": [t_name],
            "torrent_category": new_cat,
            "torrent_tag": ", ".join(tracker["tag"]),
            "torrent_tracker": tracker["url"],
            "notifiarr_indexer": tracker["notifiarr"],
        }
        self.notify_attr.append(attr)
        self.torrents_updated.append(t_name)
        self.stats += 1
