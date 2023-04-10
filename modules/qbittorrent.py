"""Qbittorrent Module"""
import os
import sys
from collections import Counter
from datetime import timedelta
from fnmatch import fnmatch

from qbittorrentapi import APIConnectionError
from qbittorrentapi import Client
from qbittorrentapi import Conflict409Error
from qbittorrentapi import LoginFailed
from qbittorrentapi import NotFound404Error
from qbittorrentapi import Version

from modules import util
from modules.util import Failed
from modules.util import list_in_text

logger = util.logger


class Qbt:
    """
    Qbittorrent Class
    """

    SUPPORTED_VERSION = Version.latest_supported_app_version()
    MIN_SUPPORTED_VERSION = "v4.3.0"

    def __init__(self, config, params):
        self.config = config
        self.host = params["host"]
        self.username = params["username"]
        self.password = params["password"]
        logger.secret(self.username)
        logger.secret(self.password)
        logger.debug(f"Host: {self.host}, Username: {self.username}, Password: {self.password}")
        ex = ""
        try:
            self.client = Client(host=self.host, username=self.username, password=self.password, VERIFY_WEBUI_CERTIFICATE=False)
            self.client.auth_log_in()
            self.current_version = self.client.app.version
            logger.debug(f"qBittorrent: {self.current_version}")
            logger.debug(f"qBittorrent Web API: {self.client.app.web_api_version}")
            logger.debug(f"qbit_manage supported versions: {self.MIN_SUPPORTED_VERSION} - {self.SUPPORTED_VERSION}")
            if self.current_version < self.MIN_SUPPORTED_VERSION:
                ex = (
                    f"Qbittorrent Error: qbit_manage is only compatible with {self.MIN_SUPPORTED_VERSION} or higher. "
                    f"You are currently on {self.current_version}."
                    + "\n"
                    + f"Please upgrade to your Qbittorrent version to {self.MIN_SUPPORTED_VERSION} or higher to use qbit_manage."
                )
            elif not Version.is_app_version_supported(self.current_version):
                ex = (
                    f"Qbittorrent Error: qbit_manage is only compatible with {self.SUPPORTED_VERSION} or lower. "
                    f"You are currently on {self.current_version}."
                    + "\n"
                    + f"Please downgrade to your Qbittorrent version to {self.SUPPORTED_VERSION} to use qbit_manage."
                )
            if ex:
                self.config.notify(ex, "Qbittorrent")
                logger.print_line(ex, "CRITICAL")
                sys.exit(0)
            else:
                logger.info("Qbt Connection Successful")
        except LoginFailed as exc:
            ex = "Qbittorrent Error: Failed to login. Invalid username/password."
            self.config.notify(ex, "Qbittorrent")
            raise Failed(ex) from exc
        except APIConnectionError as exc:
            ex = "Qbittorrent Error: Unable to connect to the client."
            self.config.notify(ex, "Qbittorrent")
            raise Failed(ex) from exc
        except Exception as exc:
            ex = "Qbittorrent Error: Unable to connect to the client."
            self.config.notify(ex, "Qbittorrent")
            raise Failed(ex) from exc
        logger.separator("Getting Torrent List", space=False, border=False)
        self.torrent_list = self.get_torrents({"sort": "added_on"})

        self.global_max_ratio_enabled = self.client.app.preferences.max_ratio_enabled
        self.global_max_ratio = self.client.app.preferences.max_ratio
        self.global_max_seeding_time_enabled = self.client.app.preferences.max_seeding_time_enabled
        self.global_max_seeding_time = self.client.app.preferences.max_seeding_time

        def get_torrent_info(torrent_list):
            """
            Will create a 2D Dictionary with the torrent name as the key
            torrentdict = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'count':1, 'msg':'[]'...},
                        'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}, 'count':2, 'msg':'[]'...}
            List of dictionary key definitions
            Category = Returns category of the torrent (str)
            save_path = Returns the save path of the torrent (str)
            count = Returns a count of the total number of torrents with the same name (int)
            msg = Returns a list of torrent messages by name (list of str)
            status = Returns the list of status numbers of the torrent by name
            (0: Tracker is disabled (used for DHT, PeX, and LSD),
            1: Tracker has not been contacted yet,
            2: Tracker has been contacted and is working,
            3: Tracker is updating,
            4: Tracker has been contacted, but it is not working (or doesn't send proper replies)
            is_complete = Returns the state of torrent
                        (Returns True if at least one of the torrent with the State is categorized as Complete.)
            first_hash = Returns the hash number of the original torrent (Assuming the torrent list is sorted by date added (Asc))
                Takes in a number n, returns the square of n
            """
            torrentdict = {}
            t_obj_unreg = []  # list of unregistered torrent objects
            t_obj_valid = []  # list of working torrents
            t_obj_list = []  # list of all torrent objects
            settings = self.config.settings
            logger.separator("Checking Settings", space=False, border=False)
            if settings["force_auto_tmm"]:
                logger.print_line(
                    "force_auto_tmm set to True. Will force Auto Torrent Management for all torrents.", self.config.loglevel
                )
            logger.separator("Gathering Torrent Information", space=True, border=True)
            for torrent in torrent_list:
                is_complete = False
                msg = None
                status = None
                working_tracker = None
                issue = {"potential": False}
                if (
                    torrent.auto_tmm is False
                    and settings["force_auto_tmm"]
                    and torrent.category != ""
                    and not self.config.dry_run
                ):
                    torrent.set_auto_management(True)
                try:
                    torrent_name = torrent.name
                    torrent_hash = torrent.hash
                    torrent_is_complete = torrent.state_enum.is_complete
                    save_path = torrent.save_path
                    category = torrent.category
                    torrent_trackers = torrent.trackers
                except Exception as ex:
                    self.config.notify(ex, "Get Torrent Info", False)
                    logger.warning(ex)
                if torrent_name in torrentdict:
                    t_obj_list.append(torrent)
                    t_count = torrentdict[torrent_name]["count"] + 1
                    msg_list = torrentdict[torrent_name]["msg"]
                    status_list = torrentdict[torrent_name]["status"]
                    is_complete = True if torrentdict[torrent_name]["is_complete"] is True else torrent_is_complete
                    first_hash = torrentdict[torrent_name]["first_hash"]
                else:
                    t_obj_list = [torrent]
                    t_count = 1
                    msg_list = []
                    status_list = []
                    is_complete = torrent_is_complete
                    first_hash = torrent_hash
                for trk in torrent_trackers:
                    if trk.url.startswith("http"):
                        status = trk.status
                        msg = trk.msg.upper()
                        exception = [
                            "DOWN",
                            "DOWN.",
                            "IT MAY BE DOWN,",
                            "UNREACHABLE",
                            "(UNREACHABLE)",
                            "BAD GATEWAY",
                            "TRACKER UNAVAILABLE",
                        ]
                        if trk.status == 2:
                            working_tracker = True
                            break
                        # Add any potential unregistered torrents to a list
                        if trk.status == 4 and not list_in_text(msg, exception):
                            issue["potential"] = True
                            issue["msg"] = msg
                            issue["status"] = status
                if working_tracker:
                    status = 2
                    msg = ""
                    t_obj_valid.append(torrent)
                elif issue["potential"]:
                    status = issue["status"]
                    msg = issue["msg"]
                    t_obj_unreg.append(torrent)
                if msg is not None:
                    msg_list.append(msg)
                if status is not None:
                    status_list.append(status)
                torrentattr = {
                    "torrents": t_obj_list,
                    "Category": category,
                    "save_path": save_path,
                    "count": t_count,
                    "msg": msg_list,
                    "status": status_list,
                    "is_complete": is_complete,
                    "first_hash": first_hash,
                }
                torrentdict[torrent_name] = torrentattr
            return torrentdict, t_obj_unreg, t_obj_valid

        self.torrentinfo = None
        self.torrentissue = None
        self.torrentvalid = None
        if (
            config.commands["recheck"]
            or config.commands["cross_seed"]
            or config.commands["rem_unregistered"]
            or config.commands["tag_tracker_error"]
            or config.commands["tag_nohardlinks"]
        ):
            # Get an updated torrent dictionary information of the torrents
            self.torrentinfo, self.torrentissue, self.torrentvalid = get_torrent_info(self.torrent_list)

    def get_torrents(self, params):
        """Get torrents from qBittorrent"""
        return self.client.torrents.info(**params)

    def category(self):
        """Update category for torrents"""
        num_cat = 0

        def update_cat(new_cat, cat_change):
            nonlocal torrent, num_cat
            tracker = self.config.get_tags(torrent.trackers)
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
            body += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
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
                "torrent_name": torrent.name,
                "torrent_category": new_cat,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            self.config.send_notifications(attr)
            num_cat += 1

        if self.config.commands["cat_update"]:
            logger.separator("Updating Categories", space=False, border=False)
            torrent_list = self.get_torrents({"category": "", "status_filter": "completed"})
            for torrent in torrent_list:
                new_cat = self.config.get_category(torrent.save_path)
                update_cat(new_cat, False)

            # Change categories
            if self.config.cat_change:
                for old_cat in self.config.cat_change:
                    torrent_list = self.get_torrents({"category": old_cat, "status_filter": "completed"})
                    for torrent in torrent_list:
                        new_cat = self.config.cat_change[old_cat]
                        update_cat(new_cat, True)

            if num_cat >= 1:
                logger.print_line(
                    f"{'Did not update' if self.config.dry_run else 'Updated'} {num_cat} new categories.", self.config.loglevel
                )
            else:
                logger.print_line("No new torrents to categorize.", self.config.loglevel)
        return num_cat

    def tags(self):
        """Update tags for torrents"""
        num_tags = 0
        ignore_tags = self.config.settings["ignoreTags_OnUpdate"]
        if self.config.commands["tag_update"]:
            logger.separator("Updating Tags", space=False, border=False)
            for torrent in self.torrent_list:
                check_tags = util.get_list(torrent.tags)
                if torrent.tags == "" or (len([trk for trk in check_tags if trk not in ignore_tags]) == 0):
                    tracker = self.config.get_tags(torrent.trackers)
                    if tracker["tag"]:
                        num_tags += len(tracker["tag"])
                        body = []
                        body += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
                        body += logger.print_line(
                            logger.insert_space(
                                f'New Tag{"s" if len(tracker["tag"]) > 1 else ""}: {", ".join(tracker["tag"])}', 8
                            ),
                            self.config.loglevel,
                        )
                        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                        body.extend(
                            self.set_tags_and_limits(
                                torrent,
                                tracker["max_ratio"],
                                tracker["max_seeding_time"],
                                tracker["limit_upload_speed"],
                                tracker["tag"],
                            )
                        )
                        category = self.config.get_category(torrent.save_path) if torrent.category == "" else torrent.category
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
            if num_tags >= 1:
                logger.print_line(
                    f"{'Did not update' if self.config.dry_run else 'Updated'} {num_tags} new tags.", self.config.loglevel
                )
            else:
                logger.print_line("No new torrents to tag.", self.config.loglevel)
        return num_tags

    def set_tags_and_limits(
        self, torrent, max_ratio, max_seeding_time, limit_upload_speed=None, tags=None, restore=False, do_print=True
    ):
        """Set tags and limits for a torrent"""
        body = []
        if limit_upload_speed:
            if limit_upload_speed != -1:
                msg = logger.insert_space(f"Limit UL Speed: {limit_upload_speed} kB/s", 1)
                if do_print:
                    body += logger.print_line(msg, self.config.loglevel)
                else:
                    body.append(msg)
        if max_ratio or max_seeding_time:
            if (max_ratio == -2 and max_seeding_time == -2) and not restore:
                msg = logger.insert_space("Share Limit: Use Global Share Limit", 4)
                if do_print:
                    body += logger.print_line(msg, self.config.loglevel)
                else:
                    body.append(msg)
            elif (max_ratio == -1 and max_seeding_time == -1) and not restore:
                msg = logger.insert_space("Share Limit: Set No Share Limit", 4)
                if do_print:
                    body += logger.print_line(msg, self.config.loglevel)
                else:
                    body.append(msg)
            else:
                if max_ratio != torrent.max_ratio and (not max_seeding_time or max_seeding_time < 0):
                    msg = logger.insert_space(f"Share Limit: Max Ratio = {max_ratio}", 4)
                    if do_print:
                        body += logger.print_line(msg, self.config.loglevel)
                    else:
                        body.append(msg)
                elif max_seeding_time != torrent.max_seeding_time and (not max_ratio or max_ratio < 0):
                    msg = logger.insert_space(f"Share Limit: Max Seed Time = {max_seeding_time} min", 4)
                    if do_print:
                        body += logger.print_line(msg, self.config.loglevel)
                    else:
                        body.append(msg)
                elif max_ratio != torrent.max_ratio or max_seeding_time != torrent.max_seeding_time:
                    msg = logger.insert_space(f"Share Limit: Max Ratio = {max_ratio}, Max Seed Time = {max_seeding_time} min", 4)
                    if do_print:
                        body += logger.print_line(msg, self.config.loglevel)
                    else:
                        body.append(msg)
        # Update Torrents
        if not self.config.dry_run:
            if tags:
                torrent.add_tags(tags)
            if limit_upload_speed:
                if limit_upload_speed == -1:
                    torrent.set_upload_limit(-1)
                else:
                    torrent.set_upload_limit(limit_upload_speed * 1024)
            if not max_ratio:
                max_ratio = torrent.max_ratio
            if not max_seeding_time:
                max_seeding_time = torrent.max_seeding_time
            if "MinSeedTimeNotReached" in torrent.tags:
                return []
            torrent.set_share_limits(max_ratio, max_seeding_time)
        return body

    def has_reached_seed_limit(self, torrent, max_ratio, max_seeding_time, min_seeding_time, resume_torrent, tracker):
        """Check if torrent has reached seed limit"""
        body = ""

        def _has_reached_min_seeding_time_limit():
            print_log = []
            if torrent.seeding_time >= min_seeding_time * 60:
                if "MinSeedTimeNotReached" in torrent.tags:
                    torrent.remove_tags(tags="MinSeedTimeNotReached")
                return True
            else:
                print_log += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
                print_log += logger.print_line(logger.insert_space(f"Tracker: {tracker}", 8), self.config.loglevel)
                print_log += logger.print_line(
                    logger.insert_space(
                        f"Min seed time not met: {timedelta(seconds=torrent.seeding_time)} <= "
                        f"{timedelta(minutes=min_seeding_time)}. Removing Share Limits so qBittorrent can continue seeding.",
                        8,
                    ),
                    self.config.loglevel,
                )
                print_log += logger.print_line(logger.insert_space("Adding Tag: MinSeedTimeNotReached", 8), self.config.loglevel)
                if not self.config.dry_run:
                    torrent.add_tags("MinSeedTimeNotReached")
                    torrent.set_share_limits(-1, -1)
                    if resume_torrent:
                        torrent.resume()
            return False

        def _has_reached_seeding_time_limit():
            nonlocal body
            seeding_time_limit = None
            if not max_seeding_time:
                return False
            if max_seeding_time >= 0:
                seeding_time_limit = max_seeding_time
            elif max_seeding_time == -2 and self.global_max_seeding_time_enabled:
                seeding_time_limit = self.global_max_seeding_time
            else:
                return False
            if seeding_time_limit:
                if (torrent.seeding_time >= seeding_time_limit * 60) and _has_reached_min_seeding_time_limit():
                    body += logger.insert_space(
                        f"Seeding Time vs Max Seed Time: {timedelta(seconds=torrent.seeding_time)} >= "
                        f"{timedelta(minutes=seeding_time_limit)}",
                        8,
                    )
                    return True
            return False

        if max_ratio:
            if max_ratio >= 0:
                if torrent.ratio >= max_ratio and _has_reached_min_seeding_time_limit():
                    body += logger.insert_space(f"Ratio vs Max Ratio: {torrent.ratio:.2f} >= {max_ratio:.2f}", 8)
                    return body
            elif max_ratio == -2 and self.global_max_ratio_enabled and _has_reached_min_seeding_time_limit():
                if torrent.ratio >= self.global_max_ratio:
                    body += logger.insert_space(
                        f"Ratio vs Global Max Ratio: {torrent.ratio:.2f} >= {self.global_max_ratio:.2f}", 8
                    )
                    return body
        if _has_reached_seeding_time_limit():
            return body
        return False

    def tag_nohardlinks(self):
        """Tag torrents with no hardlinks"""
        num_tags = 0  # counter for the number of torrents that has no hardlinks
        del_tor = 0  # counter for the number of torrents that has no hardlinks and \
        # meets the criteria for ratio limit/seed limit for deletion
        del_tor_cont = 0  # counter for the number of torrents that has no hardlinks and \
        # meets the criteria for ratio limit/seed limit for deletion including contents
        num_untag = 0  # counter for number of torrents that previously had no hardlinks but now have hardlinks

        def add_tag_no_hl(add_tag=True):
            """Add tag nohardlinks_tag to torrents with no hardlinks"""
            nonlocal num_tags, torrent, tracker, nohardlinks, category, max_ratio, max_seeding_time
            body = []
            body.append(logger.insert_space(f"Torrent Name: {torrent.name}", 3))
            if add_tag:
                body.append(logger.insert_space(f"Added Tag: {self.config.nohardlinks_tag}", 6))
                title = "Tagging Torrents with No Hardlinks"
            else:
                title = "Changing Share Ratio of Torrents with No Hardlinks"
            body.append(logger.insert_space(f'Tracker: {tracker["url"]}', 8))
            body_tags_and_limits = self.set_tags_and_limits(
                torrent,
                max_ratio,
                max_seeding_time,
                nohardlinks[category]["limit_upload_speed"],
                tags=self.config.nohardlinks_tag,
                do_print=False,
            )
            if body_tags_and_limits or add_tag:
                num_tags += 1
                # Resume torrent if it was paused now that the share limit has changed
                if torrent.state_enum.is_complete and nohardlinks[category]["resume_torrent_after_untagging_noHL"]:
                    if not self.config.dry_run:
                        torrent.resume()
                body.extend(body_tags_and_limits)
                for rcd in body:
                    logger.print_line(rcd, self.config.loglevel)
                attr = {
                    "function": "tag_nohardlinks",
                    "title": title,
                    "body": "\n".join(body),
                    "torrent_name": torrent.name,
                    "torrent_category": torrent.category,
                    "torrent_tag": self.config.nohardlinks_tag,
                    "torrent_tracker": tracker["url"],
                    "notifiarr_indexer": tracker["notifiarr"],
                    "torrent_max_ratio": max_ratio,
                    "torrent_max_seeding_time": max_seeding_time,
                    "torrent_limit_upload_speed": nohardlinks[category]["limit_upload_speed"],
                }
                self.config.send_notifications(attr)

        if self.config.commands["tag_nohardlinks"]:
            logger.separator("Tagging Torrents with No Hardlinks", space=False, border=False)
            nohardlinks = self.config.nohardlinks
            tdel_dict = {}  # dictionary to track the torrent names and content path that meet the deletion criteria
            root_dir = self.config.root_dir
            remote_dir = self.config.remote_dir
            for category in nohardlinks:
                torrent_list = self.get_torrents({"category": category, "status_filter": "completed"})
                if len(torrent_list) == 0:
                    ex = (
                        "No torrents found in the category ("
                        + category
                        + ") defined under nohardlinks attribute in the config. "
                        + "Please check if this matches with any category in qbittorrent and has 1 or more torrents."
                    )
                    logger.warning(ex)
                    continue
                for torrent in torrent_list:
                    tracker = self.config.get_tags(torrent.trackers)
                    has_nohardlinks = util.nohardlink(torrent["content_path"].replace(root_dir, remote_dir), self.config.notify)
                    if any(tag in torrent.tags for tag in nohardlinks[category]["exclude_tags"]):
                        # Skip to the next torrent if we find any torrents that are in the exclude tag
                        continue
                    else:
                        # Checks for any hardlinks and not already tagged
                        # Cleans up previously tagged nohardlinks_tag torrents that no longer have hardlinks
                        if has_nohardlinks:
                            tracker = self.config.get_tags(torrent.trackers)
                            # Determine min_seeding_time.
                            # If only tracker setting is set, use tracker's min_seeding_time
                            # If only nohardlinks category setting is set, use nohardlinks category's min_seeding_time
                            # If both tracker and nohardlinks category setting is set, use the larger of the two
                            # If neither set, use 0 (no limit)
                            min_seeding_time = 0
                            logger.trace(f'tracker["min_seeding_time"] is {tracker["min_seeding_time"]}')
                            logger.trace(
                                f'nohardlinks[category]["min_seeding_time"] is {nohardlinks[category]["min_seeding_time"]}')
                            if tracker["min_seeding_time"] is not None and nohardlinks[category]["min_seeding_time"] is not None:
                                if tracker["min_seeding_time"] >= nohardlinks[category]["min_seeding_time"]:
                                    min_seeding_time = tracker["min_seeding_time"]
                                    logger.debug(f'Using tracker["min_seeding_time"] {min_seeding_time}')
                                else:
                                    min_seeding_time = nohardlinks[category]["min_seeding_time"]
                                    logger.debug(
                                        f'Using nohardlinks[category]["min_seeding_time"] {min_seeding_time}')
                            elif nohardlinks[category]["min_seeding_time"]:
                                min_seeding_time = nohardlinks[category]["min_seeding_time"]
                                logger.debug(
                                    f'Using nohardlinks[category]["min_seeding_time"] {min_seeding_time}')
                            elif tracker["min_seeding_time"]:
                                min_seeding_time = tracker["min_seeding_time"]
                                logger.debug(f'Using tracker["min_seeding_time"] {min_seeding_time}')
                            else:
                                logger.debug(f'Using default min_seeding_time {min_seeding_time}')
                            # Determine max_ratio.
                            # If only tracker setting is set, use tracker's max_ratio
                            # If only nohardlinks category setting is set, use nohardlinks category's max_ratio
                            # If both tracker and nohardlinks category setting is set, use the larger of the two
                            # If neither set, use -1 (no limit)
                            max_ratio = -1
                            logger.trace(f'tracker["max_ratio"] is {tracker["max_ratio"]}')
                            logger.trace(f'nohardlinks[category]["max_ratio"] is {nohardlinks[category]["max_ratio"]}')
                            if tracker["max_ratio"] is not None and nohardlinks[category]["max_ratio"] is not None:
                                if tracker["max_ratio"] >= nohardlinks[category]["max_ratio"]:
                                    max_ratio = tracker["max_ratio"]
                                    logger.debug(f'Using (tracker["max_ratio"]) {max_ratio}')
                                else:
                                    max_ratio = nohardlinks[category]["max_ratio"]
                                    logger.debug(f'Using (nohardlinks[category]["max_ratio"]) {max_ratio}')
                            elif nohardlinks[category]["max_ratio"]:
                                max_ratio = nohardlinks[category]["max_ratio"]
                                logger.debug(f'Using (nohardlinks[category]["max_ratio"]) {max_ratio}')
                            elif tracker["max_ratio"]:
                                max_ratio = tracker["max_ratio"]
                                logger.debug(f'Using (tracker["max_ratio"]) {max_ratio}')
                            else:
                                logger.debug(f'Using default (max_ratio) {max_ratio}')
                            # Determine max_seeding_time.
                            # If only tracker setting is set, use tracker's max_seeding_time
                            # If only nohardlinks category setting is set, use nohardlinks category's max_seeding_time
                            # If both tracker and nohardlinks category setting is set, use the larger of the two
                            # If neither set, use -1 (no limit)
                            max_seeding_time = -1
                            logger.trace(f'tracker["max_seeding_time"] is {tracker["max_seeding_time"]}')
                            logger.trace(
                                f'nohardlinks[category]["max_seeding_time"] is {nohardlinks[category]["max_seeding_time"]}')
                            if tracker["max_seeding_time"] is not None and nohardlinks[category]["max_seeding_time"] is not None:
                                if tracker["max_seeding_time"] >= nohardlinks[category]["max_seeding_time"]:
                                    max_seeding_time = tracker["max_seeding_time"]
                                    logger.debug(f'Using (tracker["max_seeding_time"]) {max_seeding_time}')
                                else:
                                    max_seeding_time = nohardlinks[category]["max_seeding_time"]
                                    logger.debug(f'Using (nohardlinks[category]["max_seeding_time"]) {max_seeding_time}')
                            elif nohardlinks[category]["max_seeding_time"]:
                                max_seeding_time = nohardlinks[category]["max_seeding_time"]
                                logger.debug(f'Using (nohardlinks[category]["max_seeding_time"]) {max_seeding_time}')
                            elif tracker["max_seeding_time"]:
                                max_seeding_time = tracker["max_seeding_time"]
                                logger.debug(f'Using (tracker["max_seeding_time"]) {max_seeding_time}')
                            else:
                                logger.debug(f'Using default (max_seeding_time) {max_seeding_time}')
                            # Will only tag new torrents that don't have nohardlinks_tag tag
                            if self.config.nohardlinks_tag not in torrent.tags:
                                add_tag_no_hl(add_tag=True)

                            # Deletes torrent with data if cleanup is set to true and meets the ratio/seeding requirements
                            if nohardlinks[category]["cleanup"] and len(nohardlinks[category]) > 0:
                                tor_reach_seed_limit = self.has_reached_seed_limit(
                                    torrent,
                                    max_ratio,
                                    max_seeding_time,
                                    min_seeding_time,
                                    nohardlinks[category]["resume_torrent_after_untagging_noHL"],
                                    tracker["url"],
                                )
                                if tor_reach_seed_limit:
                                    if torrent.hash not in tdel_dict:
                                        tdel_dict[torrent.hash] = {}
                                    tdel_dict[torrent.hash]["content_path"] = torrent["content_path"].replace(
                                        root_dir, remote_dir
                                    )
                                    tdel_dict[torrent.hash]["body"] = tor_reach_seed_limit
                                else:
                                    # Updates torrent to see if "MinSeedTimeNotReached" tag has been added
                                    torrent = self.get_torrents({"torrent_hashes": [torrent.hash]}).data[0]
                                    # Checks to see if previously nohardlinks_tag share limits have changed.
                                    add_tag_no_hl(add_tag=False)
                    # Checks to see if previous nohardlinks_tag tagged torrents now have hardlinks.
                    if not (has_nohardlinks) and (self.config.nohardlinks_tag in torrent.tags):
                        num_untag += 1
                        body = []
                        body += logger.print_line(
                            f"Previous Tagged {self.config.nohardlinks_tag} "
                            f"Torrent Name: {torrent.name} has hardlinks found now.",
                            self.config.loglevel,
                        )
                        body += logger.print_line(
                            logger.insert_space(f"Removed Tag: {self.config.nohardlinks_tag}", 6), self.config.loglevel
                        )
                        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                        body += logger.print_line(
                            f"{'Not Reverting' if self.config.dry_run else 'Reverting'} to tracker or Global share limits.",
                            self.config.loglevel,
                        )
                        restore_max_ratio = tracker["max_ratio"]
                        restore_max_seeding_time = tracker["max_seeding_time"]
                        restore_limit_upload_speed = tracker["limit_upload_speed"]
                        if restore_max_ratio is None:
                            restore_max_ratio = -2
                        if restore_max_seeding_time is None:
                            restore_max_seeding_time = -2
                        if restore_limit_upload_speed is None:
                            restore_limit_upload_speed = -1
                        if not self.config.dry_run:
                            torrent.remove_tags(tags=self.config.nohardlinks_tag)
                            body.extend(
                                self.set_tags_and_limits(
                                    torrent, restore_max_ratio, restore_max_seeding_time, restore_limit_upload_speed, restore=True
                                )
                            )
                            if torrent.state_enum.is_complete and nohardlinks[category]["resume_torrent_after_untagging_noHL"]:
                                torrent.resume()
                        attr = {
                            "function": "untag_nohardlinks",
                            "title": "Untagging Previous Torrents that now have hardlinks",
                            "body": "\n".join(body),
                            "torrent_name": torrent.name,
                            "torrent_category": torrent.category,
                            "torrent_tag": self.config.nohardlinks_tag,
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                            "torrent_max_ratio": restore_max_ratio,
                            "torrent_max_seeding_time": restore_max_seeding_time,
                            "torrent_limit_upload_speed": restore_limit_upload_speed,
                        }
                        self.config.send_notifications(attr)
                # loop through torrent list again for cleanup purposes
                if nohardlinks[category]["cleanup"]:
                    torrent_list = self.get_torrents({"category": category, "status_filter": "completed"})
                    for torrent in torrent_list:
                        t_name = torrent.name
                        t_hash = torrent.hash
                        if t_hash in tdel_dict and self.config.nohardlinks_tag in torrent.tags:
                            t_count = self.torrentinfo[t_name]["count"]
                            t_msg = self.torrentinfo[t_name]["msg"]
                            t_status = self.torrentinfo[t_name]["status"]
                            # Double check that the content path is the same before we delete anything
                            if torrent["content_path"].replace(root_dir, remote_dir) == tdel_dict[t_hash]["content_path"]:
                                tracker = self.config.get_tags(torrent.trackers)
                                body = []
                                body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
                                body += logger.print_line(
                                    logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel
                                )
                                body += logger.print_line(tdel_dict[t_hash]["body"], self.config.loglevel)
                                body += logger.print_line(
                                    logger.insert_space("Cleanup: True [No hardlinks found and meets Share Limits.]", 8),
                                    self.config.loglevel,
                                )
                                attr = {
                                    "function": "cleanup_tag_nohardlinks",
                                    "title": "Removing NoHL Torrents and meets Share Limits",
                                    "torrent_name": t_name,
                                    "torrent_category": torrent.category,
                                    "cleanup": "True",
                                    "torrent_tracker": tracker["url"],
                                    "notifiarr_indexer": tracker["notifiarr"],
                                }
                                if os.path.exists(torrent["content_path"].replace(root_dir, remote_dir)):
                                    # Checks if any of the original torrents are working
                                    if t_count > 1 and ("" in t_msg or 2 in t_status):
                                        del_tor += 1
                                        attr["torrents_deleted_and_contents"] = False
                                        if not self.config.dry_run:
                                            self.tor_delete_recycle(torrent, attr)
                                        body += logger.print_line(
                                            logger.insert_space("Deleted .torrent but NOT content files.", 8),
                                            self.config.loglevel,
                                        )
                                    else:
                                        del_tor_cont += 1
                                        attr["torrents_deleted_and_contents"] = True
                                        if not self.config.dry_run:
                                            self.tor_delete_recycle(torrent, attr)
                                        body += logger.print_line(
                                            logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel
                                        )
                                else:
                                    del_tor += 1
                                    attr["torrents_deleted_and_contents"] = False
                                    if not self.config.dry_run:
                                        self.tor_delete_recycle(torrent, attr)
                                    body += logger.print_line(
                                        logger.insert_space("Deleted .torrent but NOT content files.", 8), self.config.loglevel
                                    )
                                attr["body"] = "\n".join(body)
                                self.config.send_notifications(attr)
                                self.torrentinfo[t_name]["count"] -= 1
            if num_tags >= 1:
                logger.print_line(
                    f"{'Did not Tag/set' if self.config.dry_run else 'Tag/set'} share limits for {num_tags} "
                    f".torrent{'s.' if num_tags > 1 else '.'}",
                    self.config.loglevel,
                )
            else:
                logger.print_line("No torrents to tag with no hardlinks.", self.config.loglevel)
            if num_untag >= 1:
                logger.print_line(
                    f"{'Did not delete' if self.config.dry_run else 'Deleted'} "
                    f"{self.config.nohardlinks_tag} tags / share limits for {num_untag} "
                    f".torrent{'s.' if num_untag > 1 else '.'}",
                    self.config.loglevel,
                )
            if del_tor >= 1:
                logger.print_line(
                    f"{'Did not delete' if self.config.dry_run else 'Deleted'} {del_tor} "
                    f".torrent{'s' if del_tor > 1 else ''} but not content files.",
                    self.config.loglevel,
                )
            if del_tor_cont >= 1:
                logger.print_line(
                    f"{'Did not delete' if self.config.dry_run else 'Deleted'} {del_tor_cont} "
                    f".torrent{'s' if del_tor_cont > 1 else ''} AND content files.",
                    self.config.loglevel,
                )
        return num_tags, num_untag, del_tor, del_tor_cont

    def rem_unregistered(self):
        """Remove torrents with unregistered trackers."""
        del_tor = 0
        del_tor_cont = 0
        num_tor_error = 0
        num_untag = 0
        tor_error_summary = ""
        tag_error = self.config.tracker_error_tag
        cfg_rem_unregistered = self.config.commands["rem_unregistered"]
        cfg_tag_error = self.config.commands["tag_tracker_error"]

        def tag_tracker_error():
            nonlocal t_name, msg_up, msg, tracker, t_cat, torrent, tag_error, tor_error_summary, num_tor_error
            tor_error = ""
            tor_error += logger.insert_space(f"Torrent Name: {t_name}", 3) + "\n"
            tor_error += logger.insert_space(f"Status: {msg}", 9) + "\n"
            tor_error += logger.insert_space(f'Tracker: {tracker["url"]}', 8) + "\n"
            tor_error += logger.insert_space(f"Added Tag: {tag_error}", 6) + "\n"
            tor_error_summary += tor_error
            num_tor_error += 1
            attr = {
                "function": "tag_tracker_error",
                "title": "Tag Tracker Error Torrents",
                "body": tor_error,
                "torrent_name": t_name,
                "torrent_category": t_cat,
                "torrent_tag": tag_error,
                "torrent_status": msg,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            self.config.send_notifications(attr)
            if not self.config.dry_run:
                torrent.add_tags(tags=tag_error)

        def del_unregistered():
            nonlocal del_tor, del_tor_cont, t_name, msg_up, msg, tracker, t_cat, t_msg, t_status, torrent
            body = []
            body += logger.print_line(logger.insert_space(f"Torrent Name: {t_name}", 3), self.config.loglevel)
            body += logger.print_line(logger.insert_space(f"Status: {msg}", 9), self.config.loglevel)
            body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
            attr = {
                "function": "rem_unregistered",
                "title": "Removing Unregistered Torrents",
                "torrent_name": t_name,
                "torrent_category": t_cat,
                "torrent_status": msg,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            if t_count > 1:
                # Checks if any of the original torrents are working
                if "" in t_msg or 2 in t_status:
                    attr["torrents_deleted_and_contents"] = False
                    if not self.config.dry_run:
                        self.tor_delete_recycle(torrent, attr)
                    body += logger.print_line(
                        logger.insert_space("Deleted .torrent but NOT content files.", 8), self.config.loglevel
                    )
                    del_tor += 1
                else:
                    attr["torrents_deleted_and_contents"] = True
                    if not self.config.dry_run:
                        self.tor_delete_recycle(torrent, attr)
                    body += logger.print_line(logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel)
                    del_tor_cont += 1
            else:
                attr["torrents_deleted_and_contents"] = True
                if not self.config.dry_run:
                    self.tor_delete_recycle(torrent, attr)
                body += logger.print_line(logger.insert_space("Deleted .torrent AND content files.", 8), self.config.loglevel)
                del_tor_cont += 1
            attr["body"] = "\n".join(body)
            self.config.send_notifications(attr)
            self.torrentinfo[t_name]["count"] -= 1

        if cfg_rem_unregistered or cfg_tag_error:
            if cfg_tag_error:
                logger.separator("Tagging Torrents with Tracker Errors", space=False, border=False)
            elif cfg_rem_unregistered:
                logger.separator("Removing Unregistered Torrents", space=False, border=False)
            unreg_msgs = [
                "UNREGISTERED",
                "TORRENT NOT FOUND",
                "TORRENT IS NOT FOUND",
                "NOT REGISTERED",
                "NOT EXIST",
                "UNKNOWN TORRENT",
                "TRUMP",
                "RETITLED",
                "TRUNCATED",
                "TORRENT IS NOT AUTHORIZED FOR USE ON THIS TRACKER",
            ]
            ignore_msgs = [
                "YOU HAVE REACHED THE CLIENT LIMIT FOR THIS TORRENT",
                "MISSING PASSKEY",
                "MISSING INFO_HASH",
                "PASSKEY IS INVALID",
                "INVALID PASSKEY",
                "EXPECTED VALUE (LIST, DICT, INT OR STRING) IN BENCODED STRING",
                "COULD NOT PARSE BENCODED DATA",
                "STREAM TRUNCATED",
            ]
            for torrent in self.torrentvalid:
                check_tags = util.get_list(torrent.tags)
                # Remove any error torrents Tags that are no longer unreachable.
                if tag_error in check_tags:
                    tracker = self.config.get_tags(torrent.trackers)
                    num_untag += 1
                    body = []
                    body += logger.print_line(
                        f"Previous Tagged {tag_error} torrent currently has a working tracker.", self.config.loglevel
                    )
                    body += logger.print_line(logger.insert_space(f"Torrent Name: {torrent.name}", 3), self.config.loglevel)
                    body += logger.print_line(logger.insert_space(f"Removed Tag: {tag_error}", 4), self.config.loglevel)
                    body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), self.config.loglevel)
                    if not self.config.dry_run:
                        torrent.remove_tags(tags=tag_error)
                    attr = {
                        "function": "untag_tracker_error",
                        "title": "Untagging Tracker Error Torrent",
                        "body": "\n".join(body),
                        "torrent_name": torrent.name,
                        "torrent_category": torrent.category,
                        "torrent_tag": tag_error,
                        "torrent_tracker": tracker["url"],
                        "notifiarr_indexer": tracker["notifiarr"],
                    }
                    self.config.send_notifications(attr)
            for torrent in self.torrentissue:
                t_name = torrent.name
                t_cat = self.torrentinfo[t_name]["Category"]
                t_count = self.torrentinfo[t_name]["count"]
                t_msg = self.torrentinfo[t_name]["msg"]
                t_status = self.torrentinfo[t_name]["status"]
                check_tags = util.get_list(torrent.tags)
                try:
                    for trk in torrent.trackers:
                        if trk.url.startswith("http"):
                            tracker = self.config.get_tags([trk])
                            msg_up = trk.msg.upper()
                            msg = trk.msg
                            # Tag any error torrents
                            if cfg_tag_error:
                                if trk.status == 4 and tag_error not in check_tags:
                                    tag_tracker_error()
                            if cfg_rem_unregistered:
                                # Tag any error torrents that are not unregistered
                                if not list_in_text(msg_up, unreg_msgs) and trk.status == 4 and tag_error not in check_tags:
                                    # Check for unregistered torrents using BHD API if the tracker is BHD
                                    if (
                                        "tracker.beyond-hd.me" in tracker["url"]
                                        and self.config.beyond_hd is not None
                                        and not list_in_text(msg_up, ignore_msgs)
                                    ):
                                        json = {"info_hash": torrent.hash}
                                        response = self.config.beyond_hd.search(json)
                                        if response["total_results"] == 0:
                                            del_unregistered()
                                            break
                                    tag_tracker_error()
                                if list_in_text(msg_up, unreg_msgs) and not list_in_text(msg_up, ignore_msgs) and trk.status == 4:
                                    del_unregistered()
                                    break
                except NotFound404Error:
                    continue
                except Exception as ex:
                    logger.stacktrace()
                    self.config.notify(ex, "Remove Unregistered Torrents", False)
                    logger.error(f"Remove Unregistered Torrents Error: {ex}")
            if cfg_rem_unregistered:
                if del_tor >= 1 or del_tor_cont >= 1:
                    if del_tor >= 1:
                        logger.print_line(
                            f"{'Did not delete' if self.config.dry_run else 'Deleted'} {del_tor} "
                            f".torrent{'s' if del_tor > 1 else ''} but not content files.",
                            self.config.loglevel,
                        )
                    if del_tor_cont >= 1:
                        logger.print_line(
                            f"{'Did not delete' if self.config.dry_run else 'Deleted'} {del_tor_cont} "
                            f".torrent{'s' if del_tor_cont > 1 else ''} AND content files.",
                            self.config.loglevel,
                        )
                else:
                    logger.print_line("No unregistered torrents found.", self.config.loglevel)
            if num_untag >= 1:
                logger.print_line(
                    f"{'Did not delete' if self.config.dry_run else 'Deleted'} {tag_error} tags for {num_untag} "
                    f".torrent{'s.' if num_untag > 1 else '.'}",
                    self.config.loglevel,
                )
            if num_tor_error >= 1:
                logger.separator(
                    f"{num_tor_error} Torrents with tracker errors found",
                    space=False,
                    border=False,
                    loglevel=self.config.loglevel,
                )
                logger.print_line(tor_error_summary.rstrip(), self.config.loglevel)
        return del_tor, del_tor_cont, num_tor_error, num_untag

    def cross_seed(self):
        """Move torrents from cross seed directory to correct save directory."""
        added = 0  # Keep track of total torrents tagged
        tagged = 0  # Track # of torrents tagged that are not cross-seeded
        if self.config.commands["cross_seed"]:
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
                # Substring Key match in dictionary (used because t_name might not match exactly with torrentdict key)
                # Returned the dictionary of filtered item
                torrentdict_file = dict(filter(lambda item: tr_name in item[0], self.torrentinfo.items()))
                if torrentdict_file:
                    # Get the exact torrent match name from torrentdict
                    t_name = next(iter(torrentdict_file))
                    dest = os.path.join(self.torrentinfo[t_name]["save_path"], "")
                    src = os.path.join(dir_cs, file)
                    dir_cs_out = os.path.join(dir_cs, "qbit_manage_added", file)
                    category = self.config.get_category(dest)
                    # Only add cross-seed torrent if original torrent is complete
                    if self.torrentinfo[t_name]["is_complete"]:
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
                        added += 1
                        if not self.config.dry_run:
                            self.client.torrents.add(
                                torrent_files=src, save_path=dest, category=category, tags="cross-seed", is_paused=True
                            )
                            util.move_files(src, dir_cs_out)
                    else:
                        logger.print_line(
                            f"Found {t_name} in {dir_cs} but original torrent is not complete.", self.config.loglevel
                        )
                        logger.print_line("Not adding to qBittorrent", self.config.loglevel)
                else:
                    error = f"{t_name} not found in torrents. Cross-seed Torrent not added to qBittorrent."
                    if self.config.dry_run:
                        logger.print_line(error, self.config.loglevel)
                    else:
                        logger.print_line(error, "WARNING")
                    self.config.notify(error, "cross-seed", False)
            # Tag missing cross-seed torrents tags
            for torrent in self.torrent_list:
                t_name = torrent.name
                t_cat = torrent.category
                if (
                    "cross-seed" not in torrent.tags
                    and self.torrentinfo[t_name]["count"] > 1
                    and self.torrentinfo[t_name]["first_hash"] != torrent.hash
                ):
                    tracker = self.config.get_tags(torrent.trackers)
                    tagged += 1
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
            if added > 0:
                logger.print_line(
                    f"Total {added} cross-seed .torrents {'not added' if self.config.dry_run else 'added'}.", self.config.loglevel
                )
            if tagged > 0:
                logger.print_line(
                    f"Total {tagged} cross-seed .torrents {'not tagged' if self.config.dry_run else 'tagged'}.",
                    self.config.loglevel,
                )
        return added, tagged

    def recheck(self):
        """Function used to recheck paused torrents sorted by size and resume torrents that are completed"""
        resumed = 0
        rechecked = 0
        if self.config.commands["recheck"]:
            logger.separator("Rechecking Paused Torrents", space=False, border=False)
            # sort by size and paused
            torrent_list = self.get_torrents({"status_filter": "paused", "sort": "size"})
            if torrent_list:
                for torrent in torrent_list:
                    tracker = self.config.get_tags(torrent.trackers)
                    # Resume torrent if completed
                    if torrent.progress == 1:
                        if torrent.max_ratio < 0 and torrent.max_seeding_time < 0:
                            resumed += 1
                            body = logger.print_line(
                                f"{'Not Resuming' if self.config.dry_run else 'Resuming'} [{tracker['tag']}] - {torrent.name}",
                                self.config.loglevel,
                            )
                            attr = {
                                "function": "recheck",
                                "title": "Resuming Torrent",
                                "body": body,
                                "torrent_name": torrent.name,
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
                                resumed += 1
                                body = logger.print_line(
                                    f"{'Not Resuming' if self.config.dry_run else 'Resuming'} [{tracker['tag']}] - "
                                    f"{torrent.name}",
                                    self.config.loglevel,
                                )
                                attr = {
                                    "function": "recheck",
                                    "title": "Resuming Torrent",
                                    "body": body,
                                    "torrent_name": torrent.name,
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
                        and self.torrentinfo[torrent.name]["is_complete"]
                        and not torrent.state_enum.is_checking
                    ):
                        rechecked += 1
                        body = logger.print_line(
                            f"{'Not Rechecking' if self.config.dry_run else 'Rechecking'} [{tracker['tag']}] - {torrent.name}",
                            self.config.loglevel,
                        )
                        attr = {
                            "function": "recheck",
                            "title": "Rechecking Torrent",
                            "body": body,
                            "torrent_name": torrent.name,
                            "torrent_category": torrent.category,
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                        }
                        self.config.send_notifications(attr)
                        if not self.config.dry_run:
                            torrent.recheck()
        return resumed, rechecked

    def rem_orphaned(self):
        """Remove orphaned files from remote directory"""
        orphaned = 0
        if self.config.commands["rem_orphaned"]:
            logger.separator("Checking for Orphaned Files", space=False, border=False)
            torrent_files = []
            root_files = []
            orphaned_files = []
            excluded_orphan_files = []
            orphaned_parent_path = set()
            remote_path = self.config.remote_dir
            root_path = self.config.root_dir
            orphaned_path = self.config.orphaned_dir
            if remote_path != root_path:
                root_files = [
                    os.path.join(path.replace(remote_path, root_path), name)
                    for path, subdirs, files in os.walk(remote_path)
                    for name in files
                    if orphaned_path.replace(remote_path, root_path) not in path
                ]
            else:
                root_files = [
                    os.path.join(path, name)
                    for path, subdirs, files in os.walk(root_path)
                    for name in files
                    if orphaned_path.replace(root_path, remote_path) not in path
                ]

            # Get an updated list of torrents
            torrent_list = self.get_torrents({"sort": "added_on"})
            for torrent in torrent_list:
                for file in torrent.files:
                    fullpath = os.path.join(torrent.save_path, file.name)
                    # Replace fullpath with \\ if qbm is running in docker (linux) but qbt is on windows
                    fullpath = fullpath.replace(r"/", "\\") if ":\\" in fullpath else fullpath
                    torrent_files.append(fullpath)

            orphaned_files = set(root_files) - set(torrent_files)
            orphaned_files = sorted(orphaned_files)

            if self.config.orphaned["exclude_patterns"]:
                exclude_patterns = self.config.orphaned["exclude_patterns"]
                excluded_orphan_files = [
                    file
                    for file in orphaned_files
                    for exclude_pattern in exclude_patterns
                    if fnmatch(file, exclude_pattern.replace(remote_path, root_path))
                ]

            orphaned_files = set(orphaned_files) - set(excluded_orphan_files)

            if orphaned_files:
                os.makedirs(orphaned_path, exist_ok=True)
                body = []
                num_orphaned = len(orphaned_files)
                logger.print_line(f"{num_orphaned} Orphaned files found", self.config.loglevel)
                body += logger.print_line("\n".join(orphaned_files), self.config.loglevel)
                body += logger.print_line(
                    f"{'Did not move' if self.config.dry_run else 'Moved'} {num_orphaned} Orphaned files "
                    f"to {orphaned_path.replace(remote_path,root_path)}",
                    self.config.loglevel,
                )

                attr = {
                    "function": "rem_orphaned",
                    "title": f"Removing {num_orphaned} Orphaned Files",
                    "body": "\n".join(body),
                    "orphaned_files": list(orphaned_files),
                    "orphaned_directory": orphaned_path.replace(remote_path, root_path),
                    "total_orphaned_files": num_orphaned,
                }
                self.config.send_notifications(attr)
                # Delete empty directories after moving orphan files
                logger.info("Cleaning up any empty directories...")
                if not self.config.dry_run:
                    for file in orphaned_files:
                        src = file.replace(root_path, remote_path)
                        dest = os.path.join(orphaned_path, file.replace(root_path, ""))
                        util.move_files(src, dest, True)
                        orphaned_parent_path.add(os.path.dirname(file).replace(root_path, remote_path))
                        for parent_path in orphaned_parent_path:
                            util.remove_empty_directories(parent_path, "**/*")
            else:
                logger.print_line("No Orphaned Files found.", self.config.loglevel)
        return orphaned

    def tor_delete_recycle(self, torrent, info):
        """Move torrent to recycle bin"""
        if self.config.recyclebin["enabled"]:
            tor_files = []
            try:
                info_hash = torrent.hash
                save_path = torrent.save_path.replace(self.config.root_dir, self.config.remote_dir)
                # Define torrent files/folders
                for file in torrent.files:
                    tor_files.append(os.path.join(save_path, file.name))
            except NotFound404Error:
                return

            if self.config.recyclebin["split_by_category"]:
                recycle_path = os.path.join(save_path, os.path.basename(self.config.recycle_dir.rstrip(os.sep)))
            else:
                recycle_path = self.config.recycle_dir
            # Create recycle bin if not exists
            torrent_path = os.path.join(recycle_path, "torrents")
            torrents_json_path = os.path.join(recycle_path, "torrents_json")

            os.makedirs(recycle_path, exist_ok=True)
            if self.config.recyclebin["save_torrents"]:
                if os.path.isdir(torrent_path) is False:
                    os.makedirs(torrent_path)
                if os.path.isdir(torrents_json_path) is False:
                    os.makedirs(torrents_json_path)
                torrent_json_file = os.path.join(torrents_json_path, f"{info['torrent_name']}.json")
                torrent_json = util.load_json(torrent_json_file)
                if not torrent_json:
                    logger.info(f"Saving Torrent JSON file to {torrent_json_file}")
                    torrent_json["torrent_name"] = info["torrent_name"]
                    torrent_json["category"] = info["torrent_category"]
                else:
                    logger.info(f"Adding {info['torrent_tracker']} to existing {os.path.basename(torrent_json_file)}")
                dot_torrent_files = []
                for file in os.listdir(self.config.torrents_dir):
                    if file.startswith(info_hash):
                        dot_torrent_files.append(file)
                        try:
                            util.copy_files(os.path.join(self.config.torrents_dir, file), os.path.join(torrent_path, file))
                        except Exception as ex:
                            logger.stacktrace()
                            self.config.notify(ex, "Deleting Torrent", False)
                            logger.warning(f"RecycleBin Warning: {ex}")
                if "tracker_torrent_files" in torrent_json:
                    tracker_torrent_files = torrent_json["tracker_torrent_files"]
                else:
                    tracker_torrent_files = {}
                tracker_torrent_files[info["torrent_tracker"]] = dot_torrent_files
                if dot_torrent_files:
                    backup_str = "Backing up "
                    for idx, val in enumerate(dot_torrent_files):
                        if idx == 0:
                            backup_str += val
                        else:
                            backup_str += f" and {val.replace(info_hash,'')}"
                    backup_str += f" to {torrent_path}"
                    logger.info(backup_str)
                torrent_json["tracker_torrent_files"] = tracker_torrent_files
                if "files" not in torrent_json:
                    files_cleaned = [f.replace(self.config.remote_dir, "") for f in tor_files]
                    torrent_json["files"] = files_cleaned
                if "deleted_contents" not in torrent_json:
                    torrent_json["deleted_contents"] = info["torrents_deleted_and_contents"]
                else:
                    if torrent_json["deleted_contents"] is False and info["torrents_deleted_and_contents"] is True:
                        torrent_json["deleted_contents"] = info["torrents_deleted_and_contents"]
                logger.debug("")
                logger.debug(f"JSON: {torrent_json}")
                util.save_json(torrent_json, torrent_json_file)
            if info["torrents_deleted_and_contents"] is True:
                logger.separator(f"Moving {len(tor_files)} files to RecycleBin", space=False, border=False, loglevel="DEBUG")
                if len(tor_files) == 1:
                    logger.print_line(tor_files[0], "DEBUG")
                else:
                    logger.print_line("\n".join(tor_files), "DEBUG")
                logger.debug(
                    f"Moved {len(tor_files)} files to {recycle_path.replace(self.config.remote_dir,self.config.root_dir)}"
                )

                # Move files from torrent contents to Recycle bin
                for file in tor_files:
                    src = file
                    dest = os.path.join(recycle_path, file.replace(self.config.remote_dir, ""))
                    # Move files and change date modified
                    try:
                        to_delete = util.move_files(src, dest, True)
                    except FileNotFoundError:
                        ex = logger.print_line(f"RecycleBin Warning - FileNotFound: No such file or directory: {src} ", "WARNING")
                        self.config.notify(ex, "Deleting Torrent", False)
                # Delete torrent and files
                torrent.delete(delete_files=to_delete)
                # Remove any empty directories
                util.remove_empty_directories(save_path, "**/*")
            else:
                torrent.delete(delete_files=False)
        else:
            if info["torrents_deleted_and_contents"] is True:
                torrent.delete(delete_files=True)
            else:
                torrent.delete(delete_files=False)
        try:
            if torrent in self.torrent_list:
                self.torrent_list.remove(torrent)
        except ValueError:
            logger.debug(f"Torrent {torrent.name} has already been deleted from torrent list.")
