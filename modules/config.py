"""Config class for qBittorrent-Manage"""

import os
import re
import stat
import time

import requests
from retrying import retry

from modules import util
from modules.apprise import Apprise
from modules.notifiarr import Notifiarr
from modules.qbittorrent import Qbt
from modules.util import YAML
from modules.util import Failed
from modules.util import check
from modules.webhooks import Webhooks

logger = util.logger

COMMANDS = [
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
        self.args = args
        self.config_file = args["config_file"]
        if self.config_file and os.path.exists(self.config_file):
            self.config_path = os.path.abspath(self.config_file)
        elif self.config_file and os.path.exists(os.path.join(default_dir, self.config_file)):
            self.config_path = os.path.abspath(os.path.join(default_dir, self.config_file))
        elif self.config_file and not os.path.exists(self.config_file):
            raise Failed(f"Config Error: config not found at {os.path.abspath(self.config_file)}")
        elif os.path.exists(os.path.join(default_dir, "config.yml")):
            self.config_path = os.path.abspath(os.path.join(default_dir, "config.yml"))
        else:
            raise Failed(f"Config Error: config not found at {os.path.abspath(default_dir)}")
        logger.info(f"Using {self.config_path} as config")

        self.util = check(self)
        self.default_dir = default_dir
        self.start_time = self.args["time_obj"]

        loaded_yaml = YAML(self.config_path)
        self.data = loaded_yaml.data

        self.load_config()
        self.configure_qbt()

    def load_config(self):
        """
        Loads and processes the configuration settings for the application.
        """
        self.commands = self.process_config_commands()
        self.data = self.process_config_data()
        self.process_config_settings()
        self.process_config_webhooks()
        self.cat_change = self.data["cat_change"] if "cat_change" in self.data else {}
        self.process_config_apprise()
        self.process_config_notifiarr()
        self.process_config_all_webhooks()
        self.validate_required_sections()
        self.process_config_nohardlinks()
        self.process_config_share_limits()
        self.processs_config_recyclebin()
        self.process_config_directories()
        self.process_config_orphaned()

    def configure_qbt(self):
        """
        Configure qBittorrent client settings based on the loaded configuration data.
        This method initializes the qBittorrent client with the necessary settings.
        """
        # Connect to Qbittorrent
        self.qbt = None
        if "qbt" in self.data:
            self.qbt = self.__connect()
        else:
            e = "Config Error: qbt attribute not found"
            self.notify(e, "Config")
            raise Failed(e)

    def process_config_commands(self):
        """
        Process and log command settings from either config file or environment variables.
        """
        # Check if request is from web API
        self.web_api_enabled = self.args.get("_from_web_api", False)

        # Determine source of commands (config file or args)
        if "commands" in self.data and not self.web_api_enabled:
            if self.data["commands"] is not None:
                logger.info(f"Commands found in {self.config_file}, ignoring env variables and using config commands instead.")
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
                # For logging, we'll still use args
                command_source = "CONFIG OVERRIDE RUN COMMANDS"
            else:
                self.commands = self.args
                command_source = "DOCKER ENV RUN COMMANDS"
        else:
            self.commands = self.args
            command_source = "WEB API RUN COMMANDS"

        # Log Docker env commands (same regardless of source)
        logger.separator("DOCKER ENV COMMANDS", loglevel="DEBUG")
        logger.debug(f"    --run (QBT_RUN): {self.args['run']}")
        logger.debug(f"    --schedule (QBT_SCHEDULE): {self.args['sch']}")
        logger.debug(f"    --startup-delay (QBT_STARTUP_DELAY): {self.args['startupDelay']}")
        logger.debug(f"    --config-dir (QBT_CONFIG_DIR): {self.args['config_dir_args']}")
        if self.args["config_dir_args"] is None:
            logger.debug(f"    --config-file (QBT_CONFIG): {self.args['config_files']} (legacy)")
        else:
            logger.debug(f"    Configs found from QBT_CONFIG_DIR: {self.args['config_files']}")
        logger.debug(f"    --log-file (QBT_LOGFILE): {self.args['log_file']}")
        logger.debug(f"    --log-level (QBT_LOG_LEVEL): {self.args['log_level']}")
        logger.debug(f"    --log-size (QBT_LOG_SIZE): {self.args['log_size']}")
        logger.debug(f"    --log-count (QBT_LOG_COUNT): {self.args['log_count']}")
        logger.debug(f"    --divider (QBT_DIVIDER): {self.args['divider']}")
        logger.debug(f"    --width (QBT_WIDTH): {self.args['screen_width']}")
        logger.debug(f"    --debug (QBT_DEBUG): {self.args['debug']}")
        logger.debug(f"    --trace (QBT_TRACE): {self.args['trace']}")
        logger.debug(f"    --web-server (QBT_WEB_SERVER): {self.args['web_server']}")
        logger.debug(f"    --port (QBT_PORT): {self.args['port']}")
        logger.debug(f"    --base-url (QBT_BASE_URL): {self.args['base_url']}")
        logger.debug(f"    --host (QBT_HOST): {self.args['host']}")

        # Log run commands (which may come from config or env)
        logger.separator(command_source, space=False, border=False, loglevel="DEBUG")
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
        logger.separator(loglevel="DEBUG")

        return self.commands

    def process_config_data(self):
        """
        Process configuration data by normalizing structure and handling special cases.
        Transforms configuration data into the expected internal format.
        """
        # Handle section renames and ensure all required sections exist
        section_mappings = {
            "qbt": "qbt",
            "settings": "settings",
            "directory": "directory",
            "cat": "cat",
            "cat_change": "cat_change",
            "nohardlinks": "nohardlinks",
            "recyclebin": "recyclebin",
            "orphaned": "orphaned",
            "apprise": "apprise",
            "notifiarr": "notifiarr",
            "share_limits": "share_limits",
        }

        # Ensure settings section exists
        if "settings" not in self.data:
            self.data["settings"] = {}

        # Ensure cat section exists
        if "cat" not in self.data:
            self.data["cat"] = {}

        # Process each standard section
        for target_key, source_key in section_mappings.items():
            if source_key in self.data:
                if target_key != source_key:  # Only pop if renaming is needed
                    self.data[target_key] = self.data.pop(source_key)

        # Process tracker section with special handling for pipe-separated URLs
        if "tracker" in self.data:
            trackers = self.data.pop("tracker")
            self.data["tracker"] = {}
            # Splits tracker urls at pipes, useful for trackers with multiple announce urls
            for tracker_urls, data in trackers.items():
                for tracker_url in tracker_urls.split("|"):
                    self.data["tracker"][tracker_url.strip()] = data
        else:
            self.data["tracker"] = {}

        # Process webhooks with special handling for function hooks
        if "webhooks" in self.data:
            temp = self.data.pop("webhooks")
            if temp is not None:
                if "function" not in temp or ("function" in temp and temp["function"] is None):
                    temp["function"] = {}

                # Helper function to process each webhook function type
                def process_hook(attr):
                    if attr in temp:
                        items = temp.pop(attr)
                        if items:
                            temp["function"][attr] = items
                    if attr not in temp["function"]:
                        temp["function"][attr] = {}
                        temp["function"][attr] = None

                # Process all webhook function types
                hook_types = [
                    "recheck",
                    "cat_update",
                    "tag_update",
                    "rem_unregistered",
                    "rem_orphaned",
                    "tag_nohardlinks",
                    "cleanup_dirs",
                ]
                for hook_type in hook_types:
                    process_hook(hook_type)

                self.data["webhooks"] = temp

        # Set final values from commands
        self.dry_run = self.commands["dry_run"]
        self.loglevel = "DRYRUN" if self.dry_run else "INFO"
        self.session = requests.Session()

        return self.data

    def validate_required_sections(self):
        """
        Validate that required configuration sections are present.
        Ensures that at least one of 'cat' or 'tracker' sections is defined.
        """
        has_categories = "cat" in self.data and self.data["cat"] is not None and len(self.data["cat"]) > 0
        has_trackers = "tracker" in self.data and self.data["tracker"] is not None and len(self.data["tracker"]) > 0

        # Check categories section
        if "cat" in self.data:
            if self.data["cat"] is None or len(self.data["cat"]) == 0:
                err = (
                    "Config Error: Category section is not completed and is mandatory. "
                    "Please enter all categories and save path combinations."
                )
                self.notify(err, "Config")
                raise Failed(err)
        # Check tracker section
        if "tracker" in self.data:
            if self.data["tracker"] is None or len(self.data["tracker"]) == 0:
                err = "Config Error: 'Tracker section is not completed and is mandatory."
                self.notify(err, "Config")
                raise Failed(err)
        if not has_categories and not has_trackers:
            # Both sections exist but are empty (since process_config_data creates them)
            err = (
                "Config Error: Both 'cat' (categories) and 'tracker' sections are empty. "
                "At least one must be defined and contain valid entries. "
                "Categories organize torrents by save path, trackers tag torrents by tracker URL. "
                "Please add either category definitions or tracker configurations to your config file."
            )
            self.notify(err, "Config")
            raise Failed(err)

    def process_config_settings(self):
        """
        Process settings from the configuration data.
        This method ensures that all required settings are present and correctly formatted.
        """
        share_limits_tag = self.data["settings"].get("share_limits_suffix_tag", "~share_limit")
        # Convert previous share_limits_suffix_tag to new default share_limits_tag
        if share_limits_tag == "share_limit":
            share_limits_tag = "~share_limit"

        self.settings = {
            "force_auto_tmm": self.util.check_for_attribute(
                self.data, "force_auto_tmm", parent="settings", var_type="bool", default=False
            ),
            "tracker_error_tag": self.util.check_for_attribute(
                self.data, "tracker_error_tag", parent="settings", default="issue"
            ),
            "nohardlinks_tag": self.util.check_for_attribute(self.data, "nohardlinks_tag", parent="settings", default="noHL"),
            "stalled_tag": self.util.check_for_attribute(self.data, "stalled_tag", parent="settings", default="stalledDL"),
            "private_tag": self.util.check_for_attribute(self.data, "private_tag", parent="settings", default_is_none=True),
            "share_limits_tag": self.util.check_for_attribute(
                self.data, "share_limits_tag", parent="settings", default=share_limits_tag
            ),
            "share_limits_min_seeding_time_tag": self.util.check_for_attribute(
                self.data, "share_limits_min_seeding_time_tag", parent="settings", default="MinSeedTimeNotReached"
            ),
            "share_limits_min_num_seeds_tag": self.util.check_for_attribute(
                self.data, "share_limits_min_num_seeds_tag", parent="settings", default="MinSeedsNotMet"
            ),
            "share_limits_last_active_tag": self.util.check_for_attribute(
                self.data, "share_limits_last_active_tag", parent="settings", default="LastActiveLimitNotReached"
            ),
            "cat_filter_completed": self.util.check_for_attribute(
                self.data, "cat_filter_completed", parent="settings", var_type="bool", default=True
            ),
            "share_limits_filter_completed": self.util.check_for_attribute(
                self.data, "share_limits_filter_completed", parent="settings", var_type="bool", default=True
            ),
            "tag_nohardlinks_filter_completed": self.util.check_for_attribute(
                self.data, "tag_nohardlinks_filter_completed", parent="settings", var_type="bool", default=True
            ),
            "rem_unregistered_filter_completed": self.util.check_for_attribute(
                self.data, "rem_unregistered_filter_completed", parent="settings", var_type="bool", default=False
            ),
            "cat_update_all": self.util.check_for_attribute(
                self.data, "cat_update_all", parent="settings", var_type="bool", default=True
            ),
            "force_auto_tmm_ignore_tags": self.util.check_for_attribute(
                self.data, "force_auto_tmm_ignore_tags", parent="settings", var_type="list", default=[]
            ),
            "disable_qbt_default_share_limits": self.util.check_for_attribute(
                self.data, "disable_qbt_default_share_limits", parent="settings", var_type="bool", default=True
            ),
            "tag_stalled_torrents": self.util.check_for_attribute(
                self.data, "tag_stalled_torrents", parent="settings", var_type="bool", default=True
            ),
            "rem_unregistered_ignore_list": self.util.check_for_attribute(
                self.data, "rem_unregistered_ignore_list", parent="settings", var_type="upper_list", default=[]
            ),
            "rem_unregistered_grace_minutes": self.util.check_for_attribute(
                self.data, "rem_unregistered_grace_minutes", parent="settings", var_type="int", default=10, min_int=0
            ),
            "rem_unregistered_max_torrents": self.util.check_for_attribute(
                self.data, "rem_unregistered_max_torrents", parent="settings", var_type="int", default=10, min_int=0
            ),
        }

        self.tracker_error_tag = self.settings["tracker_error_tag"]
        self.nohardlinks_tag = self.settings["nohardlinks_tag"]
        self.stalled_tag = self.settings["stalled_tag"]
        self.private_tag = self.settings["private_tag"]
        self.share_limits_tag = self.settings["share_limits_tag"]
        self.share_limits_custom_tags = []
        self.share_limits_min_seeding_time_tag = self.settings["share_limits_min_seeding_time_tag"]
        self.share_limits_min_num_seeds_tag = self.settings["share_limits_min_num_seeds_tag"]
        self.share_limits_last_active_tag = self.settings["share_limits_last_active_tag"]

        self.default_ignore_tags = [
            self.nohardlinks_tag,
            self.tracker_error_tag,
            self.share_limits_min_seeding_time_tag,
            self.share_limits_min_num_seeds_tag,
            self.share_limits_last_active_tag,
            self.share_limits_tag,
            self.private_tag,
        ]
        # "Migrate settings from v4.0.0 to v4.0.1 and beyond. Convert 'share_limits_suffix_tag' to 'share_limits_tag'"
        if "share_limits_suffix_tag" in self.data["settings"]:
            self.util.overwrite_attributes(self.settings, "settings")

    def process_config_webhooks(self):
        """
        Process webhooks from the configuration data.
        This method ensures that all required webhooks are present and correctly formatted.
        """
        default_function = {
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

    def process_config_apprise(self):
        """
        Process the Apprise configuration data.
        This method ensures that all required Apprise settings are present and correctly formatted.
        """
        self.apprise_factory = None
        if "apprise" in self.data:
            if self.data["apprise"] is not None and self.data["apprise"].get("api_url") is not None:
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

    def process_config_notifiarr(self):
        """
        Process the Notifiarr configuration data.
        This method ensures that all required Notifiarr settings are present and correctly formatted.
        """
        self.notifiarr_factory = None
        if "notifiarr" in self.data:
            if self.data["notifiarr"] is not None and self.data["notifiarr"].get("apikey") is not None:
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

    def process_config_all_webhooks(self):
        """
        Process all the webhooks configuration data for any type of webhook.
        This method ensures that all required webhooks settings are present and correctly formatted.
        """
        self.webhooks_factory = Webhooks(
            self,
            self.webhooks_factory,
            notifiarr=self.notifiarr_factory,
            apprise=self.apprise_factory,
            web_api_used=self.web_api_enabled,
        )
        try:
            self.webhooks_factory.start_time_hooks(self.start_time)
        except Failed as err:
            logger.stacktrace()
            logger.error(f"Webhooks Error: {err}")

    def process_config_nohardlinks(self):
        """
        Process the nohardlinks configuration data.
        This method ensures that all required nohardlinks settings are present and correctly formatted.
        """
        # nohardlinks
        self.nohardlinks = None
        if "nohardlinks" in self.data and self.commands["tag_nohardlinks"] and self.data["nohardlinks"] is not None:
            self.nohardlinks = {}
            for cat in self.data["nohardlinks"]:
                if isinstance(self.data["nohardlinks"], list) and isinstance(cat, str):
                    self.nohardlinks[cat] = {"exclude_tags": [], "ignore_root_dir": True}
                    continue
                if isinstance(cat, dict):
                    cat_str = list(cat.keys())[0]
                elif isinstance(cat, str):
                    cat_str = cat
                    cat = self.data["nohardlinks"]
                if cat[cat_str] is None:
                    cat[cat_str] = {}
                self.nohardlinks[cat_str] = {
                    "exclude_tags": cat[cat_str].get("exclude_tags", []),
                    "ignore_root_dir": cat[cat_str].get("ignore_root_dir", True),
                }
                if self.nohardlinks[cat_str]["exclude_tags"] is None:
                    self.nohardlinks[cat_str]["exclude_tags"] = []
                if not isinstance(self.nohardlinks[cat_str]["ignore_root_dir"], bool):
                    err = f"Config Error: nohardlinks category {cat_str} attribute ignore_root_dir must be a boolean type"
                    self.notify(err, "Config")
                    raise Failed(err)
        else:
            if self.commands["tag_nohardlinks"]:
                err = "Config Error: nohardlinks must be a list of categories"
                self.notify(err, "Config")
                raise Failed(err)

    def process_config_share_limits(self):
        """
        Process the share limits configuration data.
        This method ensures that all required share limits settings are present and correctly formatted.
        """
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
                            f"Priority not defined for the grouping '{key}' in share_limits. Setting priority to {priority}"
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
                return dict(sorted_limits)

            self.share_limits = dict()
            sorted_share_limits = _sort_share_limits(self.data["share_limits"])
            logger.trace(f"Unsorted Share Limits: {self.data['share_limits']}")
            logger.trace(f"Sorted Share Limits: {sorted_share_limits}")
            for group in sorted_share_limits:
                self.share_limits[group] = {}
                self.share_limits[group]["priority"] = sorted_share_limits[group]["priority"]
                self.share_limits[group]["include_all_tags"] = self.util.check_for_attribute(
                    self.data,
                    "include_all_tags",
                    parent="share_limits",
                    subparent=group,
                    var_type="list",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["include_any_tags"] = self.util.check_for_attribute(
                    self.data,
                    "include_any_tags",
                    parent="share_limits",
                    subparent=group,
                    var_type="list",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["exclude_all_tags"] = self.util.check_for_attribute(
                    self.data,
                    "exclude_all_tags",
                    parent="share_limits",
                    subparent=group,
                    var_type="list",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["exclude_any_tags"] = self.util.check_for_attribute(
                    self.data,
                    "exclude_any_tags",
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
                self.share_limits[group]["min_torrent_size"] = self.util.check_for_attribute(
                    self.data,
                    "min_torrent_size",
                    parent="share_limits",
                    subparent=group,
                    var_type="size_parse",
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["max_torrent_size"] = self.util.check_for_attribute(
                    self.data,
                    "max_torrent_size",
                    parent="share_limits",
                    subparent=group,
                    var_type="size_parse",
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
                    var_type="time_parse",
                    min_int=-2,
                    default=-1,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["max_last_active"] = self.util.check_for_attribute(
                    self.data,
                    "max_last_active",
                    parent="share_limits",
                    subparent=group,
                    var_type="time_parse",
                    min_int=-1,
                    default=-1,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["min_seeding_time"] = self.util.check_for_attribute(
                    self.data,
                    "min_seeding_time",
                    parent="share_limits",
                    subparent=group,
                    var_type="time_parse",
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
                    default=-1,
                    do_print=False,
                    save=False,
                )
                # New: throttle upload speed once share limits are reached (when cleanup is False)
                self.share_limits[group]["upload_speed_on_limit_reached"] = self.util.check_for_attribute(
                    self.data,
                    "upload_speed_on_limit_reached",
                    parent="share_limits",
                    subparent=group,
                    var_type="int",
                    min_int=-1,
                    default=0,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["enable_group_upload_speed"] = self.util.check_for_attribute(
                    self.data,
                    "enable_group_upload_speed",
                    parent="share_limits",
                    subparent=group,
                    var_type="bool",
                    default=False,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["min_num_seeds"] = self.util.check_for_attribute(
                    self.data,
                    "min_num_seeds",
                    parent="share_limits",
                    subparent=group,
                    var_type="int",
                    min_int=0,
                    default=0,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["min_last_active"] = self.util.check_for_attribute(
                    self.data,
                    "last_active",
                    parent="share_limits",
                    subparent=group,
                    var_type="time_parse",
                    min_int=0,
                    default=0,
                    do_print=False,
                    save=False,
                ) or self.util.check_for_attribute(
                    self.data,
                    "min_last_active",
                    parent="share_limits",
                    subparent=group,
                    var_type="time_parse",
                    min_int=0,
                    default=0,
                    do_print=False,
                    save=False,
                )
                if "last_active" in self.data["share_limits"][group]:
                    self.data["share_limits"][group]["min_last_active"] = self.data["share_limits"][group].pop("last_active")
                    self.util.overwrite_attributes(data=self.data["share_limits"][group], attribute=group, parent="share_limits")
                    self.util.check_for_attribute(
                        self.data,
                        "min_last_active",
                        parent="share_limits",
                        subparent=group,
                        var_type="time_parse",
                        min_int=0,
                        default=self.data["share_limits"][group]["min_last_active"],
                        do_print=False,
                        save=True,
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
                self.share_limits[group]["custom_tag"] = self.util.check_for_attribute(
                    self.data,
                    "custom_tag",
                    parent="share_limits",
                    subparent=group,
                    default_is_none=True,
                    do_print=False,
                    save=False,
                )
                if self.share_limits[group]["custom_tag"]:
                    if (
                        self.share_limits[group]["custom_tag"] not in self.share_limits_custom_tags
                        and self.share_limits[group]["custom_tag"] not in self.default_ignore_tags
                    ):
                        self.share_limits_custom_tags.append(self.share_limits[group]["custom_tag"])
                    else:
                        err = (
                            f"Config Error: Duplicate custom tag '{self.share_limits[group]['custom_tag']}' "
                            f"found in share_limits for the grouping '{group}'. Custom tag must be a unique value."
                        )
                        self.notify(err, "Config")
                        raise Failed(err)
                self.share_limits[group]["reset_upload_speed_on_unmet_minimums"] = self.util.check_for_attribute(
                    self.data,
                    "reset_upload_speed_on_unmet_minimums",
                    parent="share_limits",
                    subparent=group,
                    var_type="bool",
                    default=True,
                    do_print=False,
                    save=False,
                )
                self.share_limits[group]["torrents"] = []
                # Validate min/max torrent size (in bytes)
                min_sz = self.share_limits[group]["min_torrent_size"]
                max_sz = self.share_limits[group]["max_torrent_size"]
                if min_sz is not None and max_sz is not None and min_sz > max_sz:
                    err = (
                        f"Config Error: min_torrent_size ({min_sz} bytes) is greater than "
                        f"max_torrent_size ({max_sz} bytes) for the grouping '{group}'."
                    )
                    self.notify(err, "Config")
                    raise Failed(err)
                if (
                    self.share_limits[group]["min_seeding_time"] > 0
                    and self.share_limits[group]["max_seeding_time"] != -1
                    and self.share_limits[group]["min_seeding_time"] > self.share_limits[group]["max_seeding_time"]
                ):
                    err = (
                        f"Config Error: min_seeding_time ({self.share_limits[group]['min_seeding_time']}) is greater than "
                        f"max_seeding_time ({self.share_limits[group]['max_seeding_time']}) for the grouping '{group}'.\n"
                        f"min_seeding_time must be less than or equal to max_seeding_time or "
                        "max_seeding_time must be unlimited (-1)."
                    )
                    self.notify(err, "Config")
                    raise Failed(err)
                if self.share_limits[group]["min_seeding_time"] > 0 and self.share_limits[group]["max_ratio"] <= 0:
                    err = (
                        f"Config Error: min_seeding_time ({self.share_limits[group]['min_seeding_time']}) is set, "
                        f"but max_ratio ({self.share_limits[group]['max_ratio']}) is not set for the grouping '{group}'.\n"
                        f"max_ratio must be greater than 0 when min_seeding_time is set."
                    )
                    self.notify(err, "Config")
                    raise Failed(err)
                if self.share_limits[group]["max_seeding_time"] > 525600:
                    err = (
                        f"Config Error: max_seeding_time ({self.share_limits[group]['max_seeding_time']}) cannot be set > 1 year "
                        f"(525600 minutes) in qbitorrent. Please adjust the max_seeding_time for the grouping '{group}'."
                    )
                    self.notify(err, "Config")
                    raise Failed(err)
        else:
            if self.commands["share_limits"]:
                err = "Config Error: share_limits. No valid grouping found."
                self.notify(err, "Config")
                raise Failed(err)

        logger.trace(f"Share_limits config: {self.share_limits}")

    def processs_config_recyclebin(self):
        """
        Process the recycle bin configuration data.
        This method ensures that all required recycle bin settings are present and correctly formatted.
        """
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

    def process_config_directories(self):
        """
        Process the directory configuration data.
        This method ensures that all required directory settings are present and correctly formatted.
        """
        # Assign directories
        if "directory" in self.data:
            root_dir = self.util.check_for_attribute(self.data, "root_dir", parent="directory", default_is_none=True)
            if isinstance(root_dir, list):
                root_dir = root_dir[0]
            self.root_dir = os.path.join(root_dir, "")
            remote_dir = self.util.check_for_attribute(
                self.data, "remote_dir", parent="directory", default=self.root_dir, do_print=False, save=False
            )
            if isinstance(remote_dir, list):
                remote_dir = remote_dir[0]
            self.remote_dir = os.path.join(remote_dir, "")
            if self.commands["tag_nohardlinks"] or self.commands["rem_orphaned"]:
                self.remote_dir = self.util.check_for_attribute(
                    self.data,
                    "remote_dir",
                    parent="directory",
                    var_type="path",
                    default=self.root_dir,
                    do_print=False,
                    save=False,
                )
            else:
                if self.recyclebin["enabled"]:
                    self.remote_dir = self.util.check_for_attribute(
                        self.data,
                        "remote_dir",
                        parent="directory",
                        var_type="path",
                        default=self.root_dir,
                        do_print=False,
                        save=False,
                    )
            if not self.remote_dir:
                self.remote_dir = self.root_dir
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

    def process_config_orphaned(self):
        """
        Process the orphaned data configuration.
        This method ensures that all required orphaned data settings are present and correctly formatted.
        """
        # Add Orphaned
        self.orphaned = {}
        self.orphaned["empty_after_x_days"] = self.util.check_for_attribute(
            self.data, "empty_after_x_days", parent="orphaned", var_type="int", default_is_none=True
        )
        self.orphaned["exclude_patterns"] = self.util.check_for_attribute(
            self.data, "exclude_patterns", parent="orphaned", var_type="list", default_is_none=True, do_print=False
        )
        self.orphaned["max_orphaned_files_to_delete"] = self.util.check_for_attribute(
            self.data,
            "max_orphaned_files_to_delete",
            parent="orphaned",
            var_type="int",
            default=50,
            min_int=-1,
        )
        self.orphaned["min_file_age_minutes"] = self.util.check_for_attribute(
            self.data,
            "min_file_age_minutes",
            parent="orphaned",
            var_type="int",
            default=0,
            min_int=0,
        )
        if self.commands["rem_orphaned"]:
            exclude_orphaned = f"**{os.sep}{os.path.basename(self.orphaned_dir.rstrip(os.sep))}{os.sep}*"
            (
                self.orphaned["exclude_patterns"].append(exclude_orphaned)
                if exclude_orphaned not in self.orphaned["exclude_patterns"]
                else self.orphaned["exclude_patterns"]
            )
        if self.recyclebin["enabled"]:
            exclude_recycle = f"**{os.sep}{os.path.basename(self.recycle_dir.rstrip(os.sep))}{os.sep}*"
            (
                self.orphaned["exclude_patterns"].append(exclude_recycle)
                if exclude_recycle not in self.orphaned["exclude_patterns"]
                else self.orphaned["exclude_patterns"]
            )

    def __retry_on_connect(exception):
        return isinstance(exception.__cause__, ConnectionError)

    @retry(
        retry_on_exception=__retry_on_connect,
        stop_max_attempt_number=5,
        wait_exponential_multiplier=30000,
        wait_exponential_max=120000,
    )
    def __connect(self):
        logger.info("Connecting to Qbittorrent...")
        return Qbt(
            self,
            {
                "host": self.util.check_for_attribute(self.data, "host", parent="qbt", throw=True),
                "username": self.util.check_for_attribute(
                    self.data, "user", parent="qbt", default_is_none=True, save=False, do_print=False
                ),
                "password": self.util.check_for_attribute(
                    self.data, "pass", parent="qbt", default_is_none=True, save=False, do_print=False
                ),
            },
        )

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
                                util.path_replace(s, self.root_dir, self.remote_dir),
                                os.path.basename(location_path.rstrip(os.sep)),
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
                location_files = []
                for r_path in location_path_list:
                    try:
                        for path, subdirs, files in os.walk(r_path):
                            for name in files:
                                location_files.append(os.path.join(path, name))
                    except PermissionError as e:
                        logger.warning(f"Permission denied accessing directory {r_path}: {e}. Skipping this directory.")
                        continue
                    except OSError as e:
                        logger.warning(f"Error accessing directory {r_path}: {e}. Skipping this directory.")
                        continue
                location_files = list(set(location_files))  # remove duplicates
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
                            # in seconds (last modified time)
                            last_modified = fileStats[stat.ST_MTIME]
                        except FileNotFoundError:
                            ex = logger.print_line(
                                f"{location} Warning - FileNotFound: No such file or directory: {file} ", "WARNING"
                            )
                            self.notify(ex, "Cleanup Dirs", False)
                            continue
                        except PermissionError as e:
                            logger.warning(f"Permission denied accessing file stats for {file}: {e}")
                            continue
                        except OSError as e:
                            logger.warning(f"Error accessing file stats for {file}: {e}")
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
                            try:
                                size_bytes += os.path.getsize(file)
                            except (PermissionError, OSError) as e:
                                logger.warning(f"Could not get size for {file}: {e}")
                                # Continue without size info

                            if not self.dry_run:
                                try:
                                    os.remove(file)
                                except PermissionError as e:
                                    logger.warning(f"Permission denied deleting {file}: {e}. Skipping file.")
                                    # Remove from files list since we couldn't delete it
                                    if str(filename) in files:
                                        files.remove(str(filename))
                                    num_del -= 1  # Don't count this as a successful deletion
                                    continue
                                except OSError as e:
                                    logger.warning(f"Error deleting {file}: {e}. Skipping file.")
                                    # Remove from files list since we couldn't delete it
                                    if str(filename) in files:
                                        files.remove(str(filename))
                                    num_del -= 1  # Don't count this as a successful deletion
                                    continue
                        prevfolder = re.search(f".*{os.path.basename(location_path.rstrip(os.sep))}", file).group(0)
                    if num_del > 0:
                        if not self.dry_run:
                            for path in location_path_list:
                                if path != location_path:
                                    util.remove_empty_directories(path, self.qbt.get_category_save_paths())
                            # Delete empty folders inside the location_path
                            util.remove_empty_directories(location_path, [location_path])
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
