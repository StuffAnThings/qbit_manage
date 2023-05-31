"""Config class for qBittorrent-Manage"""
import os
import re
import stat
import time
from collections import OrderedDict

import requests
from retrying import retry

from modules import util
from modules.apprise import Apprise
from modules.bhd import BeyondHD
from modules.notifiarr import Notifiarr
from modules.qbittorrent import Qbt
from modules.util import check
from modules.util import Failed
from modules.util import YAML
from modules.webhooks import Webhooks

logger = util.logger

COMMANDS = [
    "cross_seed",
    "recheck",
    "cat_update",
    "tag_update",
    "rem_unregistered",
    "tag_tracker_error",
    "rem_orphaned",
    "tag_nohardlinks",
    "share_limits",
    "skip_cleanup",
    "skip_qb_version_check",
    "dry_run",
]


class Config:
    """Config class for qBittorrent-Manage"""

    def __init__(self, default_dir, args):
        logger.info("Locating config...")
        self.args = args
        config_file = args["config_file"]
        if config_file and os.path.exists(config_file):
            self.config_path = os.path.abspath(config_file)
        elif config_file and os.path.exists(os.path.join(default_dir, config_file)):
            self.config_path = os.path.abspath(os.path.join(default_dir, config_file))
        elif config_file and not os.path.exists(config_file):
            raise Failed(f"Config Error: config not found at {os.path.abspath(config_file)}")
        elif os.path.exists(os.path.join(default_dir, "config.yml")):
            self.config_path = os.path.abspath(os.path.join(default_dir, "config.yml"))
        else:
            raise Failed(f"Config Error: config not found at {os.path.abspath(default_dir)}")
        logger.info(f"Using {self.config_path} as config")

        self.util = check(self)
        self.default_dir = default_dir
        self.start_time = args["time_obj"]

        loaded_yaml = YAML(self.config_path)
        self.data = loaded_yaml.data

        # Replace env variables with config commands
        if "commands" in self.data:
            if self.data["commands"] is not None:
                logger.info(f"Commands found in {config_file}, ignoring env variables and using config commands instead.")
                self.commands = {}
                for command in COMMANDS:
                    self.commands[command] = self.util.check_for_attribute(
                        self.data,
                        command,
                        parent="commands",
                        var_type="bool",
                        default=False,
                        save=True,
                    )
                logger.debug(f"    --cross-seed (QBT_CROSS_SEED): {self.commands['cross_seed']}")
                logger.debug(f"    --recheck (QBT_RECHECK): {self.commands['recheck']}")
                logger.debug(f"    --cat-update (QBT_CAT_UPDATE): {self.commands['cat_update']}")
                logger.debug(f"    --tag-update (QBT_TAG_UPDATE): {self.commands['tag_update']}")
                logger.debug(f"    --rem-unregistered (QBT_REM_UNREGISTERED): {self.commands['rem_unregistered']}")
                logger.debug(f"    --tag-tracker-error (QBT_TAG_TRACKER_ERROR): {self.commands['tag_tracker_error']}")
                logger.debug(f"    --rem-orphaned (QBT_REM_ORPHANED): {self.commands['rem_orphaned']}")
                logger.debug(f"    --tag-nohardlinks (QBT_TAG_NOHARDLINKS): {self.commands['tag_nohardlinks']}")
                logger.debug(f"    --share-limits (QBT_SHARE_LIMITS): {self.commands['share_limits']}")
                logger.debug(f"    --skip-cleanup (QBT_SKIP_CLEANUP): {self.commands['skip_cleanup']}")
                logger.debug(f"    --skip-qb-version-check (QBT_SKIP_QB_VERSION_CHECK): {self.commands['skip_qb_version_check']}")
                logger.debug(f"    --dry-run (QBT_DRY_RUN): {self.commands['dry_run']}")
        else:
            self.commands = args

        if "qbt" in self.data:
            self.data["qbt"] = self.data.pop("qbt")
        self.data["settings"] = self.data.pop("settings") if "settings" in self.data else {}
        if "directory" in self.data:
            self.data["directory"] = self.data.pop("directory")
        self.data["cat"] = self.data.pop("cat") if "cat" in self.data else {}
        if "cat_change" in self.data:
            self.data["cat_change"] = self.data.pop("cat_change")
        if "tracker" in self.data:
            self.data["tracker"] = self.data.pop("tracker")
        else:
            self.data["tracker"] = {}
        if "nohardlinks" in self.data:
            self.data["nohardlinks"] = self.data.pop("nohardlinks")
        if "recyclebin" in self.data:
            self.data["recyclebin"] = self.data.pop("recyclebin")
        if "orphaned" in self.data:
            self.data["orphaned"] = self.data.pop("orphaned")
        if "apprise" in self.data:
            self.data["apprise"] = self.data.pop("apprise")
        if "notifiarr" in self.data:
            self.data["notifiarr"] = self.data.pop("notifiarr")
        if "webhooks" in self.data:
            temp = self.data.pop("webhooks")
            if temp is not None:
                if "function" not in temp or ("function" in temp and temp["function"] is None):
                    temp["function"] = {}

                def hooks(attr):
                    if attr in temp:
                        items = temp.pop(attr)
                        if items:
                            temp["function"][attr] = items
                    if attr not in temp["function"]:
                        temp["function"][attr] = {}
                        temp["function"][attr] = None

                hooks("cross_seed")
                hooks("recheck")
                hooks("cat_update")
                hooks("tag_update")
                hooks("rem_unregistered")
                hooks("rem_orphaned")
                hooks("tag_nohardlinks")
                hooks("cleanup_dirs")
                self.data["webhooks"] = temp
        if "bhd" in self.data:
            self.data["bhd"] = self.data.pop("bhd")
        if "share_limits" in self.data:
            self.data["share_limits"] = self.data.pop("share_limits")

        self.dry_run = self.commands["dry_run"]
        self.loglevel = "DRYRUN" if self.dry_run else "INFO"
        self.session = requests.Session()

        self.settings = {
            "force_auto_tmm": self.util.check_for_attribute(
                self.data, "force_auto_tmm", parent="settings", var_type="bool", default=False
            ),
            "tracker_error_tag": self.util.check_for_attribute(
                self.data, "tracker_error_tag", parent="settings", default="issue"
            ),
            "nohardlinks_tag": self.util.check_for_attribute(self.data, "nohardlinks_tag", parent="settings", default="noHL"),
            "share_limits_suffix_tag": self.util.check_for_attribute(
                self.data, "share_limits_suffix_tag", parent="settings", default="share_limit"
            ),
        }

        self.tracker_error_tag = self.settings["tracker_error_tag"]
        self.nohardlinks_tag = self.settings["nohardlinks_tag"]
        self.share_limits_suffix_tag = "." + self.settings["share_limits_suffix_tag"]

        default_ignore_tags = [self.nohardlinks_tag, self.tracker_error_tag, "cross-seed"]
        self.settings["ignoreTags_OnUpdate"] = self.util.check_for_attribute(
            self.data, "ignoreTags_OnUpdate", parent="settings", default=default_ignore_tags, var_type="list"
        )

        default_function = {
            "cross_seed": None,
            "recheck": None,
            "cat_update": None,
            "tag_update": None,
            "rem_unregistered": None,
            "tag_tracker_error": None,
            "rem_orphaned": None,
            "tag_nohardlinks": None,
            "share_limits": None,
            "cleanup_dirs": None,
        }

        self.webhooks_factory = {
            "error": self.util.check_for_attribute(self.data, "error", parent="webhooks", var_type="list", default_is_none=True),
            "run_start": self.util.check_for_attribute(
                self.data, "run_start", parent="webhooks", var_type="list", default_is_none=True
            ),
            "run_end": self.util.check_for_attribute(
                self.data, "run_end", parent="webhooks", var_type="list", default_is_none=True
            ),
            "function": self.util.check_for_attribute(
                self.data, "function", parent="webhooks", var_type="list", default=default_function
            ),
        }
        for func in default_function:
            self.util.check_for_attribute(self.data, func, parent="webhooks", subparent="function", default_is_none=True)

        self.cat_change = self.data["cat_change"] if "cat_change" in self.data else {}

        self.apprise_factory = None
        if "apprise" in self.data:
            if self.data["apprise"] is not None:
                logger.info("Connecting to Apprise...")
                try:
                    self.apprise_factory = Apprise(
                        self,
                        {
                            "api_url": self.util.check_for_attribute(
                                self.data, "api_url", parent="apprise", var_type="url", throw=True
                            ),
                            "notify_url": self.util.check_for_attribute(
                                self.data, "notify_url", parent="apprise", var_type="list", throw=True
                            ),
                        },
                    )
                except Failed as err:
                    logger.error(err)
                logger.info(f"Apprise Connection {'Failed' if self.apprise_factory is None else 'Successful'}")

        self.notifiarr_factory = None
        if "notifiarr" in self.data:
            if self.data["notifiarr"] is not None:
                logger.info("Connecting to Notifiarr...")
                try:
                    self.notifiarr_factory = Notifiarr(
                        self,
                        {
                            "apikey": self.util.check_for_attribute(self.data, "apikey", parent="notifiarr", throw=True),
                            "instance": self.util.check_for_attribute(
                                self.data, "instance", parent="notifiarr", default=False, do_print=False, save=False
                            ),
                        },
                    )
                except Failed as err:
                    logger.error(err)
                logger.info(f"Notifiarr Connection {'Failed' if self.notifiarr_factory is None else 'Successful'}")

        self.webhooks_factory = Webhooks(
            self, self.webhooks_factory, notifiarr=self.notifiarr_factory, apprise=self.apprise_factory
        )
        try:
            self.webhooks_factory.start_time_hooks(self.start_time)
        except Failed as err:
            logger.stacktrace()
            logger.error(f"Webhooks Error: {err}")

        self.beyond_hd = None
        if "bhd" in self.data:
            if self.data["bhd"] is not None:
                logger.info("Connecting to BHD API...")
                try:
                    self.beyond_hd = BeyondHD(
                        self, {"apikey": self.util.check_for_attribute(self.data, "apikey", parent="bhd", throw=True)}
                    )
                except Failed as err:
                    logger.error(err)
                    self.notify(err, "BHD")
                logger.info(f"BHD Connection {'Failed' if self.beyond_hd is None else 'Successful'}")

        # nohardlinks
        self.nohardlinks = None
        if "nohardlinks" in self.data and self.commands["tag_nohardlinks"]:
            self.nohardlinks = {}
            for cat in self.data["nohardlinks"]:
                if isinstance(cat, dict):
                    cat_str = list(cat.keys())[0]
                    self.nohardlinks[cat_str] = {}
                    exclude_tags = cat[cat_str].get("exclude_tags", None)
                    if isinstance(exclude_tags, str):
                        exclude_tags = [exclude_tags]
                    self.nohardlinks[cat_str]["exclude_tags"] = exclude_tags
                elif isinstance(cat, str):
                    self.nohardlinks[cat] = {}
                    self.nohardlinks[cat]["exclude_tags"] = None
        else:
            if self.commands["tag_nohardlinks"]:
                err = "Config Error: nohardlinks attribute max_ratio not found"
                self.notify(err, "Config")
                raise Failed(err)

        # share limits
        self.share_limits = None
        if "share_limits" in self.data and self.commands["share_limits"]:

            def _sort_share_limits(share_limits):
                sorted_limits = sorted(
                    share_limits.items(), key=lambda x: x[1].get("priority", float("inf")) if x[1] is not None else float("inf")
                )
                priorities = set()
                for key, value in sorted_limits:
                    if value is None:
                        value = {}
                    if "priority" in value:
                        priority = value["priority"]
                        if priority in priorities:
                            err = (
                                f"Config Error: Duplicate priority '{priority}' found in share_limits "
                                f"for the grouping '{key}'. Priority must be a unique value and greater than or equal to 1"
                            )
                            self.notify(err, "Config")
                            raise Failed(err)
                    else:
                        priority = max(priorities) + 1
                        logger.warning(
                            f"Priority not defined for the grouping '{key}' in share_limits. " f"Setting priority to {priority}"
                        )
                        value["priority"] = self.util.check_for_attribute(
                            self.data,
                            "priority",
                            parent="share_limits",
                            subparent=key,
                            var_type="float",
                            default=priority,
                            save=True,
                        )
                    priorities.add(priority)
                return OrderedDict(sorted_limits)

            self.share_limits = OrderedDict()
            sorted_share_limits = _sort_share_limits(self.data["share_limits"])
            for group in sorted_share_limits:
                self.share_limits[group] = {}
                self.share_limits[group]["priority"] = sorted_share_limits[group]["priority"]
                self.share_limits[group]["tags"] = self.util.check_for_attribute(
                    self.data,
                    "tags",
                    parent="share_limits",
                    subparent=group,
                    var_type="list",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["exclude_tags"] = self.util.check_for_attribute(
                    self.data,
                    "exclude_tags",
                    parent="share_limits",
                    subparent=group,
                    var_type="list",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["categories"] = self.util.check_for_attribute(
                    self.data,
                    "categories",
                    parent="share_limits",
                    subparent=group,
                    var_type="list",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["cleanup"] = self.util.check_for_attribute(
                    self.data, "cleanup", parent="share_limits", subparent=group, var_type="bool", default=False, do_print=False
                )
                self.share_limits[group]["max_ratio"] = self.util.check_for_attribute(
                    self.data,
                    "max_ratio",
                    parent="share_limits",
                    subparent=group,
                    var_type="float",
                    min_int=-2,
                    default=-1,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["max_seeding_time"] = self.util.check_for_attribute(
                    self.data,
                    "max_seeding_time",
                    parent="share_limits",
                    subparent=group,
                    var_type="int",
                    min_int=-2,
                    default=-1,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["min_seeding_time"] = self.util.check_for_attribute(
                    self.data,
                    "min_seeding_time",
                    parent="share_limits",
                    subparent=group,
                    var_type="int",
                    min_int=0,
                    default=0,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["limit_upload_speed"] = self.util.check_for_attribute(
                    self.data,
                    "limit_upload_speed",
                    parent="share_limits",
                    subparent=group,
                    var_type="int",
                    min_int=-1,
                    default=0,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["resume_torrent_after_change"] = self.util.check_for_attribute(
                    self.data,
                    "resume_torrent_after_change",
                    parent="share_limits",
                    subparent=group,
                    var_type="bool",
                    default=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["add_group_to_tag"] = self.util.check_for_attribute(
                    self.data,
                    "add_group_to_tag",
                    parent="share_limits",
                    subparent=group,
                    var_type="bool",
                    default=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["torrents"] = []
        else:
            if self.commands["share_limits"]:
                err = "Config Error: share_limits. No valid grouping found."
                self.notify(err, "Config")
                raise Failed(err)

        # Add RecycleBin
        self.recyclebin = {}
        self.recyclebin["enabled"] = self.util.check_for_attribute(
            self.data, "enabled", parent="recyclebin", var_type="bool", default=True
        )
        self.recyclebin["empty_after_x_days"] = self.util.check_for_attribute(
            self.data, "empty_after_x_days", parent="recyclebin", var_type="int", default_is_none=True
        )
        self.recyclebin["save_torrents"] = self.util.check_for_attribute(
            self.data, "save_torrents", parent="recyclebin", var_type="bool", default=False
        )
        self.recyclebin["split_by_category"] = self.util.check_for_attribute(
            self.data, "split_by_category", parent="recyclebin", var_type="bool", default=False
        )

        # Assign directories
        if "directory" in self.data:
            self.root_dir = os.path.join(
                self.util.check_for_attribute(self.data, "root_dir", parent="directory", default_is_none=True), ""
            )
            self.remote_dir = os.path.join(
                self.util.check_for_attribute(self.data, "remote_dir", parent="directory", default=self.root_dir), ""
            )
            if self.commands["cross_seed"] or self.commands["tag_nohardlinks"] or self.commands["rem_orphaned"]:
                self.remote_dir = self.util.check_for_attribute(
                    self.data, "remote_dir", parent="directory", var_type="path", default=self.root_dir
                )
            else:
                if self.recyclebin["enabled"]:
                    self.remote_dir = self.util.check_for_attribute(
                        self.data, "remote_dir", parent="directory", var_type="path", default=self.root_dir
                    )
            if self.commands["cross_seed"]:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory", var_type="path")
            else:
                self.cross_seed_dir = self.util.check_for_attribute(
                    self.data, "cross_seed", parent="directory", default_is_none=True
                )
            if self.commands["rem_orphaned"]:
                if "orphaned_dir" in self.data["directory"] and self.data["directory"]["orphaned_dir"] is not None:
                    default_orphaned = os.path.join(
                        self.remote_dir, os.path.basename(self.data["directory"]["orphaned_dir"].rstrip(os.sep))
                    )
                else:
                    default_orphaned = os.path.join(self.remote_dir, "orphaned_data")
                self.orphaned_dir = self.util.check_for_attribute(
                    self.data, "orphaned_dir", parent="directory", var_type="path", default=default_orphaned, make_dirs=True
                )
            else:
                self.orphaned_dir = None
            if self.recyclebin["enabled"]:
                if "recycle_bin" in self.data["directory"] and self.data["directory"]["recycle_bin"] is not None:
                    default_recycle = os.path.join(
                        self.remote_dir, os.path.basename(self.data["directory"]["recycle_bin"].rstrip(os.sep))
                    )
                else:
                    default_recycle = os.path.join(self.remote_dir, ".RecycleBin")
                if self.recyclebin["split_by_category"]:
                    self.recycle_dir = self.util.check_for_attribute(
                        self.data, "recycle_bin", parent="directory", default=default_recycle
                    )
                else:
                    self.recycle_dir = self.util.check_for_attribute(
                        self.data, "recycle_bin", parent="directory", var_type="path", default=default_recycle, make_dirs=True
                    )
            else:
                self.recycle_dir = None
            if self.recyclebin["enabled"] and self.recyclebin["save_torrents"]:
                self.torrents_dir = self.util.check_for_attribute(self.data, "torrents_dir", parent="directory", var_type="path")
                if not any(File.endswith(".torrent") for File in os.listdir(self.torrents_dir)):
                    err = f"Config Error: The location {self.torrents_dir} does not contain any .torrents"
                    self.notify(err, "Config")
                    raise Failed(err)
            else:
                self.torrents_dir = self.util.check_for_attribute(
                    self.data, "torrents_dir", parent="directory", default_is_none=True
                )
        else:
            e = "Config Error: directory attribute not found"
            self.notify(e, "Config")
            raise Failed(e)

        # Add Orphaned
        self.orphaned = {}
        self.orphaned["empty_after_x_days"] = self.util.check_for_attribute(
            self.data, "empty_after_x_days", parent="orphaned", var_type="int", default_is_none=True
        )
        self.orphaned["exclude_patterns"] = self.util.check_for_attribute(
            self.data, "exclude_patterns", parent="orphaned", var_type="list", default_is_none=True, do_print=False
        )
        if self.commands["rem_orphaned"]:
            exclude_orphaned = f"**{os.sep}{os.path.basename(self.orphaned_dir.rstrip(os.sep))}{os.sep}*"
            self.orphaned["exclude_patterns"].append(exclude_orphaned) if exclude_orphaned not in self.orphaned[
                "exclude_patterns"
            ] else self.orphaned["exclude_patterns"]
        if self.recyclebin["enabled"]:
            exclude_recycle = f"**{os.sep}{os.path.basename(self.recycle_dir.rstrip(os.sep))}{os.sep}*"
            self.orphaned["exclude_patterns"].append(exclude_recycle) if exclude_recycle not in self.orphaned[
                "exclude_patterns"
            ] else self.orphaned["exclude_patterns"]

        # Connect to Qbittorrent
        self.qbt = None
        if "qbt" in self.data:
            logger.info("Connecting to Qbittorrent...")
            self.qbt = Qbt(
                self,
                {
                    "host": self.util.check_for_attribute(self.data, "host", parent="qbt", throw=True),
                    "username": self.util.check_for_attribute(self.data, "user", parent="qbt", default_is_none=True),
                    "password": self.util.check_for_attribute(self.data, "pass", parent="qbt", default_is_none=True),
                },
            )
        else:
            e = "Config Error: qbt attribute not found"
            self.notify(e, "Config")
            raise Failed(e)

    # Empty old files from recycle bin or orphaned
    def cleanup_dirs(self, location):
        num_del = 0
        files = []
        size_bytes = 0
        skip = self.commands["skip_cleanup"]
        if location == "Recycle Bin":
            enabled = self.recyclebin["enabled"]
            empty_after_x_days = self.recyclebin["empty_after_x_days"]
            function = "cleanup_dirs"
            location_path = self.recycle_dir

        elif location == "Orphaned Data":
            enabled = self.commands["rem_orphaned"]
            empty_after_x_days = self.orphaned["empty_after_x_days"]
            function = "cleanup_dirs"
            location_path = self.orphaned_dir

        if not skip:
            if enabled and empty_after_x_days is not None:
                if location == "Recycle Bin" and self.recyclebin["split_by_category"]:
                    if "cat" in self.data and self.data["cat"] is not None:
                        save_path = list(self.data["cat"].values())
                        cleaned_save_path = [
                            os.path.join(
                                s.replace(self.root_dir, self.remote_dir), os.path.basename(location_path.rstrip(os.sep))
                            )
                            for s in save_path
                        ]
                        location_path_list = [location_path]
                        for folder in cleaned_save_path:
                            if os.path.exists(folder):
                                location_path_list.append(folder)
                    else:
                        e = f"No categories defined. Checking {location} directory {location_path}."
                        self.notify(e, f"Empty {location}", False)
                        logger.warning(e)
                        location_path_list = [location_path]
                else:
                    location_path_list = [location_path]
                location_files = [
                    os.path.join(path, name)
                    for r_path in location_path_list
                    for path, subdirs, files in os.walk(r_path)
                    for name in files
                ]
                location_files = sorted(location_files)
                logger.trace(f"location_files: {location_files}")
                if location_files:
                    body = []
                    logger.separator(f"Emptying {location} (Files > {empty_after_x_days} days)", space=True, border=True)
                    prevfolder = ""
                    for file in location_files:
                        folder = re.search(f".*{os.path.basename(location_path.rstrip(os.sep))}", file).group(0)
                        if folder != prevfolder:
                            body += logger.separator(f"Searching: {folder}", space=False, border=False)
                        try:
                            fileStats = os.stat(file)
                            filename = os.path.basename(file)
                            last_modified = fileStats[stat.ST_MTIME]  # in seconds (last modified time)
                        except FileNotFoundError:
                            ex = logger.print_line(
                                f"{location} Warning - FileNotFound: No such file or directory: {file} ", "WARNING"
                            )
                            self.config.notify(ex, "Cleanup Dirs", False)
                            continue
                        now = time.time()  # in seconds
                        days = (now - last_modified) / (60 * 60 * 24)
                        if empty_after_x_days <= days:
                            num_del += 1
                            body += logger.print_line(
                                f"{'Did not delete' if self.dry_run else 'Deleted'} "
                                f"{filename} from {folder} (Last modified {round(days)} days ago).",
                                self.loglevel,
                            )
                            files += [str(filename)]
                            size_bytes += os.path.getsize(file)
                            if not self.dry_run:
                                os.remove(file)
                        prevfolder = re.search(f".*{os.path.basename(location_path.rstrip(os.sep))}", file).group(0)
                    if num_del > 0:
                        if not self.dry_run:
                            for path in location_path_list:
                                util.remove_empty_directories(path, "**/*")
                        body += logger.print_line(
                            f"{'Did not delete' if self.dry_run else 'Deleted'} {num_del} files "
                            f"({util.human_readable_size(size_bytes)}) from the {location}.",
                            self.loglevel,
                        )
                        attr = {
                            "function": function,
                            "location": location,
                            "title": f"Emptying {location} (Files > {empty_after_x_days} days)",
                            "body": "\n".join(body),
                            "files": files,
                            "empty_after_x_days": empty_after_x_days,
                            "size_in_bytes": size_bytes,
                        }
                        self.send_notifications(attr)
                else:
                    logger.debug(f'No files found in "{(",".join(location_path_list))}"')
        return num_del

    def send_notifications(self, attr):
        try:
            function = attr["function"]
            config_webhooks = self.webhooks_factory.function_webhooks
            config_function = None
            for key in config_webhooks:
                if key in function:
                    config_function = key
                    break
            if config_function:
                self.webhooks_factory.function_hooks([config_webhooks[config_function]], attr)
        except Failed as e:
            logger.stacktrace()
            logger.error(f"webhooks_factory Error: {e}")

    def notify(self, text, function=None, critical=True):
        for error in util.get_list(text, split=False):
            try:
                self.webhooks_factory.error_hooks(error, function_error=function, critical=critical)
            except Failed as e:
                logger.stacktrace()
                logger.error(f"webhooks_factory Error: {e}")

    def get_json(self, url, json=None, headers=None, params=None):
        return self.get(url, json=json, headers=headers, params=params).json()

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def get(self, url, json=None, headers=None, params=None):
        return self.session.get(url, json=json, headers=headers, params=params)

    def post_json(self, url, data=None, json=None, headers=None):
        return self.post(url, data=data, json=json, headers=headers).json()

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def post(self, url, data=None, json=None, headers=None):
        return self.session.post(url, data=data, json=json, headers=headers)
