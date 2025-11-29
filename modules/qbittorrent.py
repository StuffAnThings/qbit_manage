"""Qbittorrent Module"""

import os
import sys
from fnmatch import fnmatch
from functools import cache

from qbittorrentapi import APIConnectionError
from qbittorrentapi import Client
from qbittorrentapi import LoginFailed
from qbittorrentapi import TrackerStatus
from qbittorrentapi import Version
from ruamel.yaml import CommentedSeq

from modules import util
from modules.qbit_error_handler import handle_qbit_api_errors
from modules.util import Failed
from modules.util import TorrentMessages
from modules.util import list_in_text

logger = util.logger


class Qbt:
    """
    Qbittorrent Class
    """

    SUPPORTED_VERSION = Version.latest_supported_app_version()
    MIN_SUPPORTED_VERSION = "v4.3.0"
    TORRENT_DICT_COMMANDS = ["recheck", "rem_unregistered", "tag_tracker_error", "tag_nohardlinks", "share_limits"]

    def __init__(self, config, params):
        self.config = config
        self.host = params["host"]
        self.username = params["username"]
        self.password = params["password"]
        logger.secret(self.username)
        logger.secret(self.password)
        logger.debug(f"Host: {self.host}")
        ex = ""
        try:
            self.client = Client(
                host=self.host,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False,
                REQUESTS_ARGS={"timeout": (45, 60)},
            )
            self.client.auth_log_in()
            self.current_version = self.client.app.version
            logger.info(f"qBittorrent: {self.current_version}")
            logger.info(f"qBittorrent Web API: {self.client.app.web_api_version}")
            logger.info(f"qbit_manage supported versions: {self.MIN_SUPPORTED_VERSION} - {self.SUPPORTED_VERSION}")
            if self.current_version < self.MIN_SUPPORTED_VERSION:
                ex = (
                    f"Qbittorrent Error: qbit_manage is only compatible with {self.MIN_SUPPORTED_VERSION} or higher. "
                    f"You are currently on {self.current_version}."
                    + "\n"
                    + f"Please upgrade your qBittorrent version to {self.MIN_SUPPORTED_VERSION} or higher to use qbit_manage."
                )
            elif not Version.is_app_version_supported(self.current_version):
                ex = (
                    f"Qbittorrent Error: qbit_manage is only compatible with {self.SUPPORTED_VERSION} or lower. "
                    f"You are currently on {self.current_version}."
                    + "\n"
                    + f"Please downgrade your qBittorrent version to {self.SUPPORTED_VERSION} to use qbit_manage."
                )
            if ex:
                if self.config.commands["skip_qb_version_check"]:
                    ex += "\n[BYPASS]: Continuing because qBittorrent version check is bypassed... Please do not ask for support!"
                    logger.print_line(ex, "WARN")
                else:
                    self.config.notify(ex, "Qbittorrent")
                    logger.print_line(ex, "CRITICAL")
                    sys.exit(1)
            logger.info("Qbt Connection Successful")
        except LoginFailed:
            ex = "Qbittorrent Error: Failed to login. Invalid username/password."
            self.config.notify(ex, "Qbittorrent")
            raise Failed(ex)
        except APIConnectionError as exc:
            self.config.notify(exc, "Qbittorrent")
            raise Failed(exc) from ConnectionError(exc)
        except Exception as exc:
            self.config.notify(exc, "Qbittorrent")
            raise Failed(exc)
        self.torrent_list = self.get_torrents({"sort": "added_on"})
        self.torrentfiles = {}  # a map of torrent files to track cross-seeds

        if (
            self.config.commands["share_limits"]
            and self.config.settings["disable_qbt_default_share_limits"]
            and self.client.app.preferences.max_ratio_act != 0
        ):
            logger.info("Disabling qBittorrent default share limits to allow qbm to manage share limits.")
            # max_ratio_act: 0 = Pause Torrent, 1 = Remove Torrent, 2 = superseeding, 3 = Remove Torrent and Files
            self.client.app_set_preferences(
                {
                    "max_ratio_act": 0,
                    "max_seeding_time_enabled": False,
                    "max_ratio_enabled": False,
                    "max_inactive_seeding_time_enabled": False,
                }
            )

        self.global_max_ratio_enabled = self.client.app.preferences.max_ratio_enabled
        self.global_max_ratio = self.client.app.preferences.max_ratio
        self.global_max_seeding_time_enabled = self.client.app.preferences.max_seeding_time_enabled
        self.global_max_seeding_time = self.client.app.preferences.max_seeding_time

        if any(config.commands.get(command, False) for command in self.TORRENT_DICT_COMMANDS):
            # Get an updated torrent dictionary information of the torrents
            self.get_torrent_info()
        else:
            self.torrentinfo = None
            self.torrentissue = None
            self.torrentvalid = None
        self.get_tags = cache(self.get_tags)
        self.get_category = cache(self.get_category)
        self.get_category_save_paths = cache(self.get_category_save_paths)

    def get_torrent_info(self):
        """
        Will create a 2D Dictionary with the torrent name as the key
        self.torrentinfo = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'msg':'[]'...},
                    'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}, 'msg':'[]'...}
        List of dictionary key definitions
        Category = Returns category of the torrent (str)
        save_path = Returns the save path of the torrent (str)
        msg = Returns a list of torrent messages by name (list of str)
        status = Returns the list of status numbers of the torrent by name
        (0: Tracker is disabled (used for DHT, PeX, and LSD),
        1: Tracker has not been contacted yet,
        2: Tracker has been contacted and is working,
        3: Tracker is updating,
        4: Tracker has been contacted, but it is not working (or doesn't send proper replies)
        is_complete = Returns the state of torrent
                    (Returns True if at least one of the torrent with the State is categorized as Complete.)
        """
        self.torrentinfo = {}
        self.torrentissue = []  # list of unregistered torrent objects
        self.torrentvalid = []  # list of working torrents
        t_obj_list = []  # list of all torrent objects
        settings = self.config.settings
        logger.separator("Checking Settings", space=False, border=False)
        if settings["force_auto_tmm"]:
            logger.print_line(
                "force_auto_tmm set to True. Will force Auto Torrent Management "
                "for all torrents without matching force_auto_tmm_ignore_tags.",
                self.config.loglevel,
            )
        logger.separator("Gathering Torrent Information", space=True, border=True)
        for torrent in self.torrent_list:
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
                # check whether the torrent has a matching tag to ignore force_auto_tmm.
                and not any(tag in torrent.tags for tag in self.config.settings.get("force_auto_tmm_ignore_tags", []))
            ):
                torrent.set_auto_management(True)
            try:
                torrent_name = torrent.name
                torrent_hash = torrent.hash
                torrent_is_complete = torrent.state_enum.is_complete
                save_path = torrent.save_path
                category = torrent.category
                torrent_trackers = torrent.trackers
                self.add_torrent_files(torrent_hash, torrent.files, save_path)
            except Exception as ex:
                self.config.notify(ex, "Get Torrent Info", False)
                logger.warning(ex)
            if torrent_name in self.torrentinfo:
                t_obj_list.append(torrent)
                msg_list = self.torrentinfo[torrent_name]["msg"]
                status_list = self.torrentinfo[torrent_name]["status"]
                is_complete = True if self.torrentinfo[torrent_name]["is_complete"] is True else torrent_is_complete
            else:
                t_obj_list = [torrent]
                msg_list = []
                status_list = []
                is_complete = torrent_is_complete
            for trk in torrent_trackers:
                if trk.url.split(":")[0] in ["http", "https", "udp", "ws", "wss"]:
                    status = trk.status
                    msg = trk.msg.upper()
                    if TrackerStatus(trk.status) == TrackerStatus.WORKING:
                        working_tracker = True
                        break
                    # Add any potential unregistered torrents to a list
                    if TrackerStatus(trk.status) == TrackerStatus.NOT_WORKING and not list_in_text(
                        msg, TorrentMessages.EXCEPTIONS_MSGS
                    ):
                        issue["potential"] = True
                        issue["msg"] = msg
                        issue["status"] = status
            if working_tracker:
                status = 2
                msg = ""
                self.torrentvalid.append(torrent)
            elif issue["potential"]:
                status = issue["status"]
                msg = issue["msg"]
                self.torrentissue.append(torrent)
            if msg is not None:
                msg_list.append(msg)
            if status is not None:
                status_list.append(status)
            torrentattr = {
                "torrents": t_obj_list,
                "Category": category,
                "save_path": save_path,
                "msg": msg_list,
                "status": status_list,
                "is_complete": is_complete,
            }
            self.torrentinfo[torrent_name] = torrentattr

    def add_torrent_files(self, torrent_hash, torrent_files, save_path):
        """Process torrent files by adding the hash to the appropriate torrent_files list.
        Example structure:
        torrent_files = {
            "folder1/file1.txt": {"original": torrent_hash1, "cross_seed": ["torrent_hash2", "torrent_hash3"]},
            "folder1/file2.txt": {"original": torrent_hash1, "cross_seed": ["torrent_hash2"]},
            "folder2/file1.txt": {"original": torrent_hash2, "cross_seed": []},
        }
        """
        for file in torrent_files:
            full_path = os.path.join(save_path, file.name)
            if full_path not in self.torrentfiles:
                self.torrentfiles[full_path] = {"original": torrent_hash, "cross_seed": []}
            else:
                self.torrentfiles[full_path]["cross_seed"].append(torrent_hash)

    def is_cross_seed(self, torrent):
        """Check if the torrent is a cross seed if it has one or more files that are cross seeded."""
        t_hash = torrent.hash
        t_name = torrent.name
        if torrent.downloaded != 0:
            logger.trace(f"Torrent: {t_name} [Hash: {t_hash}] is not a cross seeded torrent. Download is > 0.")
            return False
        cross_seed = True
        for file in torrent.files:
            full_path = os.path.join(torrent.save_path, file.name)
            if self.torrentfiles[full_path]["original"] == t_hash or t_hash not in self.torrentfiles[full_path]["cross_seed"]:
                logger.trace(f"File: [{full_path}] is found in Torrent: {t_name} [Hash: {t_hash}] as the original torrent")
                cross_seed = False
                break
            elif self.torrentfiles[full_path]["original"] is None:
                cross_seed = False
                break
        logger.trace(f"Torrent: {t_name} [Hash: {t_hash}] {'is' if cross_seed else 'is not'} a cross seed torrent.")
        return cross_seed

    def has_cross_seed(self, torrent):
        """Check if the torrent has a cross seed"""
        cross_seed = False
        t_hash = torrent.hash
        t_name = torrent.name
        for file in torrent.files:
            full_path = os.path.join(torrent.save_path, file.name)
            if len(self.torrentfiles[full_path]["cross_seed"]) > 0:
                logger.trace(f"{full_path} has cross seeds: {self.torrentfiles[full_path]['cross_seed']}")
                cross_seed = True
                break
        logger.trace(f"Torrent: {t_name} [Hash: {t_hash}] {'has' if cross_seed else 'has no'} cross seeds.")
        return cross_seed

    def remove_torrent_files(self, torrent):
        """Update the torrent_files list after a torrent is deleted"""
        torrent_hash = torrent.hash
        for file in torrent.files:
            full_path = os.path.join(torrent.save_path, file.name)
            if self.torrentfiles[full_path]["original"] == torrent_hash:
                if len(self.torrentfiles[full_path]["cross_seed"]) > 0:
                    self.torrentfiles[full_path]["original"] = self.torrentfiles[full_path]["cross_seed"].pop(0)
                    logger.trace(f"Updated {full_path} original to {self.torrentfiles[full_path]['original']}")
                else:
                    self.torrentfiles[full_path]["original"] = None
            else:
                if torrent_hash in self.torrentfiles[full_path]["cross_seed"]:
                    self.torrentfiles[full_path]["cross_seed"].remove(torrent_hash)
                    logger.trace(f"Removed {torrent_hash} from {full_path} cross seeds")
                    logger.trace(f"{full_path} original: {self.torrentfiles[full_path]['original']}")
                    logger.trace(f"{full_path} cross seeds: {self.torrentfiles[full_path]['cross_seed']}")

    def get_torrents(self, params):
        """Get torrents from qBittorrent"""
        return self.client.torrents.info(**params)

    def get_tracker_urls(self, trackers):
        """Get tracker urls from torrent"""
        return tuple(x.url for x in trackers if x.url.startswith(("http", "udp", "ws")))

    def is_torrent_private(self, torrent):
        """Checks if torrent is private"""
        if hasattr(torrent, "private") and torrent.private:
            return True
        if hasattr(torrent, "private") and not torrent.private:
            return False

        if isinstance(torrent, str):
            torrent_hash = torrent
        else:
            torrent_hash = torrent.hash
        torrent_trackers = self.client.torrents_trackers(torrent_hash)
        for tracker in torrent_trackers:
            if "private" in tracker["msg"].lower() or "private" in tracker["url"].lower():
                return True
        return False

    def get_tags(self, urls):
        """Get tags from config file based on keyword"""
        urls = list(urls)
        tracker = {}
        tracker["tag"] = None
        tracker["cat"] = None
        tracker["notifiarr"] = None
        tracker["url"] = None
        tracker_other_tag = self.config.util.check_for_attribute(
            self.config.data, "tag", parent="tracker", subparent="other", default_is_none=True, var_type="list", save=False
        )
        try:
            tracker["url"] = util.trunc_val(urls[0], "/")
        except IndexError as e:
            tracker["url"] = None
            if not urls:
                urls = []
                if not tracker_other_tag:
                    tracker_other_tag = ["other"]
                tracker["url"] = "No http URL found"
            else:
                logger.debug(f"Tracker Url:{urls}")
                logger.debug(e)
        if "tracker" in self.config.data and self.config.data["tracker"] is not None:
            tag_values = self.config.data["tracker"]
            for tag_url, tag_details in tag_values.items():
                for url in urls:
                    if tag_url in url:
                        if tracker["url"] is None:
                            default_tag = tracker_other_tag
                        else:
                            try:
                                tracker["url"] = util.trunc_val(url, "/")
                                default_tag = tracker["url"].split("/")[2].split(":")[0]
                            except IndexError as e:
                                logger.debug(f"Tracker Url:{url}")
                                logger.debug(e)
                        tracker["tag"] = self.config.util.check_for_attribute(
                            self.config.data, "tag", parent="tracker", subparent=tag_url, default=tag_url, var_type="list"
                        )
                        tracker["cat"] = self.config.util.check_for_attribute(
                            self.config.data,
                            "cat",
                            parent="tracker",
                            subparent=tag_url,
                            default_is_none=True,
                            var_type="str",
                            save=False,
                            do_print=False,
                        )
                        if tracker["tag"] == [tag_url]:
                            self.config.data["tracker"][tag_url]["tag"] = [tag_url]
                        if isinstance(tracker["tag"], str):
                            tracker["tag"] = [tracker["tag"]]
                        tracker["notifiarr"] = self.config.util.check_for_attribute(
                            self.config.data,
                            "notifiarr",
                            parent="tracker",
                            subparent=tag_url,
                            default_is_none=True,
                            do_print=False,
                            save=False,
                        )
                        return tracker
            if tracker_other_tag:
                tracker["tag"] = tracker_other_tag
                tracker["notifiarr"] = self.config.util.check_for_attribute(
                    self.config.data,
                    "notifiarr",
                    parent="tracker",
                    subparent="other",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                return tracker
        if tracker["url"]:
            logger.trace(f"tracker url: {tracker['url']}")
            if tracker_other_tag:
                default_tag = tracker_other_tag
            else:
                default_tag = tracker["url"].split("/")[2].split(":")[0]
            tracker["tag"] = self.config.util.check_for_attribute(
                self.config.data, "tag", parent="tracker", subparent=default_tag, default=default_tag, var_type="list"
            )
            if isinstance(tracker["tag"], str):
                tracker["tag"] = [tracker["tag"]]
            try:
                self.config.data["tracker"][default_tag]["tag"] = [default_tag]
            except Exception:
                self.config.data["tracker"][default_tag] = {"tag": [default_tag]}
            e = f"No tags matched for {tracker['url']}. Please check your config.yml file. Setting tag to {default_tag}"
            self.config.notify(e, "Tag", False)
            logger.warning(e)
        return tracker

    def get_category(self, path):
        """Get category from config file based on path provided"""
        category = []
        path = os.path.join(path, "")
        if "cat" in self.config.data and self.config.data["cat"] is not None:
            cat_path = self.config.data["cat"]
            for cat, save_path in cat_path.items():
                try:
                    if cat == "Uncategorized" and isinstance(save_path, CommentedSeq):
                        if any(os.path.join(p, "") == path or fnmatch(path, p) for p in save_path):
                            category.append(cat)
                    elif os.path.join(save_path, "") == path or fnmatch(path, save_path):
                        category.append(cat)
                except TypeError:
                    e = f"Invalid configuration for category {cat}. Check your config.yml file."
                    self.config.notify(e, "Category", True)
                    logger.print_line(e, "CRITICAL")
                    sys.exit(1)

        if not category:
            default_cat = path.split(os.sep)[-2]
            category = [default_cat]
            self.config.util.check_for_attribute(self.config.data, default_cat, parent="cat", default=path)
            self.config.data["cat"][str(default_cat)] = path
            e = f"No categories matched for the save path {path}. Check your config.yml file. - Setting category to {default_cat}"
            self.config.notify(e, "Category", False)
            logger.warning(e)
        return category

    def get_category_save_paths(self):
        """Get all categories from qbitorrenta and return a list of save_paths"""
        save_paths = set()
        categories = self.client.torrent_categories.categories
        for cat in categories:
            save_path = util.path_replace(categories[cat].savePath, self.config.root_dir, self.config.remote_dir)
            if save_path:
                save_paths.add(save_path)
        # Also add root_dir to the list
        save_paths.add(self.config.remote_dir)
        return list(save_paths)

    def tor_delete_recycle(self, torrent, info):
        """Move torrent to recycle bin"""
        try:
            self.remove_torrent_files(torrent)
        except ValueError:
            logger.debug(f"Torrent {torrent.name} has already been removed from torrent files.")

        tor_files = []

        @handle_qbit_api_errors(context="tor_delete_recycle_get_files", retry_attempts=1)
        def get_torrent_files():
            info_hash = torrent.hash
            save_path = util.path_replace(torrent.save_path, self.config.root_dir, self.config.remote_dir)
            # Define torrent files/folders
            for file in torrent.files:
                tor_files.append(os.path.join(save_path, file.name))
            return info_hash, save_path

        result = get_torrent_files()
        if result is None:  # Error occurred and was handled
            return
        info_hash, save_path = result

        if self.config.recyclebin["enabled"]:
            if self.config.recyclebin["split_by_category"]:
                recycle_path = os.path.join(save_path, os.path.basename(self.config.recycle_dir.rstrip(os.sep)))
            else:
                recycle_path = self.config.recycle_dir
            # Create recycle bin if not exists
            # Export torrent/fastresume from BT_backup
            torrent_path = os.path.join(recycle_path, "torrents")
            # Exported torrent file (qbittorrent v4.5.0+)
            torrent_export_path = os.path.join(recycle_path, "torrents_export")
            torrents_json_path = os.path.join(recycle_path, "torrents_json")
            torrent_name = info["torrents"][0]
            torrent_exportable = self.current_version >= "v4.5.0"
            os.makedirs(recycle_path, exist_ok=True)
            if self.config.recyclebin["save_torrents"]:
                if os.path.isdir(torrent_path) is False:
                    os.makedirs(torrent_path)
                if os.path.isdir(torrents_json_path) is False:
                    os.makedirs(torrents_json_path)
                if torrent_exportable and os.path.isdir(torrent_export_path) is False:
                    os.makedirs(torrent_export_path)
                torrent_json_file = os.path.join(torrents_json_path, f"{torrent_name}.json")
                torrent_json = util.load_json(torrent_json_file)
                if not torrent_json:
                    logger.info(f"Saving Torrent JSON file to {torrent_json_file}")
                    torrent_json["torrent_name"] = torrent_name
                    torrent_json["category"] = info["torrent_category"]
                else:
                    logger.info(f"Adding {info['torrent_tracker']} to existing {os.path.basename(torrent_json_file)}")
                dot_torrent_files = []
                # Exporting torrent via Qbit API (v4.5.0+)
                if torrent_exportable:
                    # Get the last 8 hash characters of the torrent
                    hash_suffix = f"{info_hash[-8:]}"
                    torrent_export_file = os.path.join(torrent_export_path, f"{torrent_name} [{hash_suffix}].torrent")
                    truncated_torrent_export_file = util.truncate_filename(torrent_export_file, offset=11)
                    try:
                        with open(f"{truncated_torrent_export_file}", "wb") as file:
                            file.write(torrent.export())
                    except Exception as ex:
                        logger.stacktrace()
                        self.config.notify(ex, "Deleting Torrent", False)
                        logger.warning(f"RecycleBin Warning: {ex}")
                    dot_torrent_files.append(os.path.basename(truncated_torrent_export_file))
                # Exporting torrent via torrent directory (backwards compatibility)
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
                            backup_str += f" and {val.replace(info_hash, '')}"
                    backup_str += f" to {torrent_export_path if torrent_exportable else torrent_path}"
                    logger.info(backup_str)
                torrent_json["tracker_torrent_files"] = tracker_torrent_files
                if "files" not in torrent_json:
                    files_cleaned = [util.path_replace(f, self.config.remote_dir, "") for f in tor_files]
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
                    f"Moved {len(tor_files)} files to "
                    f"{util.path_replace(recycle_path, self.config.remote_dir, self.config.root_dir)}"
                )

                # Move files from torrent contents to Recycle bin
                for file in tor_files:
                    src = file
                    dest = os.path.join(recycle_path, util.path_replace(file, self.config.remote_dir, ""))
                    # Move files and change date modified
                    try:
                        to_delete = util.move_files(src, dest, True)
                    except FileNotFoundError:
                        ex = logger.print_line(f"RecycleBin Warning - FileNotFound: No such file or directory: {src} ", "WARNING")
                        self.config.notify(ex, "Deleting Torrent", False)
                    # Add src file to orphan exclusion since sometimes deleting files are slow in certain environments
                    exclude_file = util.path_replace(src, self.config.remote_dir, self.config.root_dir)
                    if exclude_file not in self.config.orphaned["exclude_patterns"]:
                        self.config.orphaned["exclude_patterns"].append(exclude_file)
                # Delete torrent and files
                torrent.delete(delete_files=to_delete)
                # Remove any empty directories
                util.remove_empty_directories(save_path, self.get_category_save_paths())
            else:
                torrent.delete(delete_files=False)
        else:
            if info["torrents_deleted_and_contents"] is True:
                for file in tor_files:
                    # Add src file to orphan exclusion since sometimes deleting files are slow in certain environments
                    exclude_file = util.path_replace(file, self.config.remote_dir, self.config.root_dir)
                    if exclude_file not in self.config.orphaned["exclude_patterns"]:
                        self.config.orphaned["exclude_patterns"].append(exclude_file)
                torrent.delete(delete_files=True)
            else:
                torrent.delete(delete_files=False)
        try:
            if torrent in self.torrent_list:
                self.torrent_list.remove(torrent)
        except ValueError:
            logger.debug(f"Torrent {torrent.name} has already been deleted from torrent list.")
