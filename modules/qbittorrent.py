"""Qbittorrent Module"""
import os
import sys

from qbittorrentapi import Client
from qbittorrentapi import LoginFailed
from qbittorrentapi import NotFound404Error
from qbittorrentapi import TrackerStatus
from qbittorrentapi import Version

from modules import util
from modules.util import Failed
from modules.util import list_in_text
from modules.util import TorrentMessages

logger = util.logger


class Qbt:
    """
    Qbittorrent Class
    """

    SUPPORTED_VERSION = Version.latest_supported_app_version()
    MIN_SUPPORTED_VERSION = "v4.3.0"
    TORRENT_DICT_COMMANDS = ["recheck", "cross_seed", "rem_unregistered", "tag_tracker_error", "tag_nohardlinks", "share_limits"]

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
            self.client = Client(
                host=self.host,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False,
                REQUESTS_ARGS={"timeout": (45, 60)},
            )
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
        except LoginFailed as exc:
            ex = "Qbittorrent Error: Failed to login. Invalid username/password."
            self.config.notify(ex, "Qbittorrent")
            raise Failed(exc) from exc
        except Exception as exc:
            self.config.notify(exc, "Qbittorrent")
            raise Failed(exc) from exc
        logger.separator("Getting Torrent List", space=False, border=False)
        self.torrent_list = self.get_torrents({"sort": "added_on"})

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

    def get_torrent_info(self):
        """
        Will create a 2D Dictionary with the torrent name as the key
        self.torrentinfo = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'count':1, 'msg':'[]'...},
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
        self.torrentinfo = {}
        self.torrentissue = []  # list of unregistered torrent objects
        self.torrentvalid = []  # list of working torrents
        t_obj_list = []  # list of all torrent objects
        settings = self.config.settings
        logger.separator("Checking Settings", space=False, border=False)
        if settings["force_auto_tmm"]:
            logger.print_line(
                "force_auto_tmm set to True. Will force Auto Torrent Management for all torrents.", self.config.loglevel
            )
        logger.separator("Gathering Torrent Information", space=True, border=True)
        for torrent in self.torrent_list:
            is_complete = False
            msg = None
            status = None
            working_tracker = None
            issue = {"potential": False}
            if torrent.auto_tmm is False and settings["force_auto_tmm"] and torrent.category != "" and not self.config.dry_run:
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
            if torrent_name in self.torrentinfo:
                t_obj_list.append(torrent)
                t_count = self.torrentinfo[torrent_name]["count"] + 1
                msg_list = self.torrentinfo[torrent_name]["msg"]
                status_list = self.torrentinfo[torrent_name]["status"]
                is_complete = True if self.torrentinfo[torrent_name]["is_complete"] is True else torrent_is_complete
                first_hash = self.torrentinfo[torrent_name]["first_hash"]
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
                "count": t_count,
                "msg": msg_list,
                "status": status_list,
                "is_complete": is_complete,
                "first_hash": first_hash,
            }
            self.torrentinfo[torrent_name] = torrentattr

    def get_torrents(self, params):
        """Get torrents from qBittorrent"""
        return self.client.torrents.info(**params)

    def get_tags(self, trackers):
        """Get tags from config file based on keyword"""
        urls = [x.url for x in trackers if x.url.startswith("http")]
        tracker = {}
        tracker["tag"] = None
        tracker["notifiarr"] = None
        tracker["url"] = None
        tracker_other_tag = self.config.util.check_for_attribute(
            self.config.data, "tag", parent="tracker", subparent="other", default_is_none=True, var_type="list", save=False
        )
        try:
            tracker["url"] = util.trunc_val(urls[0], os.sep)
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
                                tracker["url"] = util.trunc_val(url, os.sep)
                                default_tag = tracker["url"].split(os.sep)[2].split(":")[0]
                            except IndexError as e:
                                logger.debug(f"Tracker Url:{url}")
                                logger.debug(e)
                        tracker["tag"] = self.config.util.check_for_attribute(
                            self.config.data, "tag", parent="tracker", subparent=tag_url, default=tag_url, var_type="list"
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
                default_tag = tracker["url"].split(os.sep)[2].split(":")[0]
            tracker["tag"] = self.config.util.check_for_attribute(
                self.config.data, "tag", parent="tracker", subparent=default_tag, default=default_tag, var_type="list"
            )
            if isinstance(tracker["tag"], str):
                tracker["tag"] = [tracker["tag"]]
            try:
                self.config.data["tracker"][default_tag]["tag"] = [default_tag]
            except Exception:
                self.config.data["tracker"][default_tag] = {"tag": [default_tag]}
            e = f'No tags matched for {tracker["url"]}. Please check your config.yml file. Setting tag to {default_tag}'
            self.config.notify(e, "Tag", False)
            logger.warning(e)
        return tracker

    def get_category(self, path):
        """Get category from config file based on path provided"""
        category = ""
        path = os.path.join(path, "")
        if "cat" in self.config.data and self.config.data["cat"] is not None:
            cat_path = self.config.data["cat"]
            for cat, save_path in cat_path.items():
                if os.path.join(save_path, "") == path:
                    category = cat
                    break

        if not category:
            default_cat = path.split(os.sep)[-2]
            category = str(default_cat)
            self.config.util.check_for_attribute(self.config.data, default_cat, parent="cat", default=path)
            self.config.data["cat"][str(default_cat)] = path
            e = f"No categories matched for the save path {path}. Check your config.yml file. - Setting category to {default_cat}"
            self.config.notify(e, "Category", False)
            logger.warning(e)
        return category

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
            torrent_name = info["torrents"][0]
            os.makedirs(recycle_path, exist_ok=True)
            if self.config.recyclebin["save_torrents"]:
                if os.path.isdir(torrent_path) is False:
                    os.makedirs(torrent_path)
                if os.path.isdir(torrents_json_path) is False:
                    os.makedirs(torrents_json_path)
                torrent_json_file = os.path.join(torrents_json_path, f"{torrent_name}.json")
                torrent_json = util.load_json(torrent_json_file)
                if not torrent_json:
                    logger.info(f"Saving Torrent JSON file to {torrent_json_file}")
                    torrent_json["torrent_name"] = torrent_name
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
