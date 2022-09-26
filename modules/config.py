import os, requests, stat, time, re
from modules import util
from modules.util import Failed, check, YAML
from modules.qbittorrent import Qbt
from modules.webhooks import Webhooks
from modules.notifiarr import Notifiarr
from modules.bhd import BeyondHD
from modules.apprise import Apprise
from retrying import retry

logger = util.logger


class Config:
    def __init__(self, default_dir, args):
        logger.info("Locating config...")
        self.args = args
        config_file = args["config_file"]
        if config_file and os.path.exists(config_file):                                 self.config_path = os.path.abspath(config_file)
        elif config_file and os.path.exists(os.path.join(default_dir, config_file)):    self.config_path = os.path.abspath(os.path.join(default_dir, config_file))
        elif config_file and not os.path.exists(config_file):                           raise Failed(f"Config Error: config not found at {os.path.abspath(config_file)}")
        elif os.path.exists(os.path.join(default_dir, "config.yml")):                   self.config_path = os.path.abspath(os.path.join(default_dir, "config.yml"))
        else:                                                                           raise Failed(f"Config Error: config not found at {os.path.abspath(default_dir)}")
        logger.info(f"Using {self.config_path} as config")

        self.util = check(self)
        self.default_dir = default_dir
        self.test_mode = args["test"] if "test" in args else False
        self.trace_mode = args["trace"] if "trace" in args else False
        self.start_time = args["time_obj"]

        loaded_yaml = YAML(self.config_path)
        self.data = loaded_yaml.data

        # Replace env variables with config commands
        if "commands" in self.data:
            if self.data["commands"] is not None:
                logger.info(f"Commands found in {config_file}, ignoring env variables and using config commands instead.")
                self.commands = self.data.pop("commands")
                if 'dry_run' not in self.commands:
                    self.commands['dry_run'] = args['dry_run'] if 'dry_run' in args else False
                # Add default any missing commands as False
                for v in [
                    'cross_seed',
                    'recheck',
                    'cat_update',
                    'tag_update',
                    'rem_unregistered',
                    'tag_tracker_error',
                    'rem_orphaned',
                    'tag_nohardlinks',
                    'skip_cleanup'
                ]:
                    if v not in self.commands:
                        self.commands[v] = False

                logger.debug(f"    --cross-seed (QBT_CROSS_SEED): {self.commands['cross_seed']}")
                logger.debug(f"    --recheck (QBT_RECHECK): {self.commands['recheck']}")
                logger.debug(f"    --cat-update (QBT_CAT_UPDATE): {self.commands['cat_update']}")
                logger.debug(f"    --tag-update (QBT_TAG_UPDATE): {self.commands['tag_update']}")
                logger.debug(f"    --rem-unregistered (QBT_REM_UNREGISTERED): {self.commands['rem_unregistered']}")
                logger.debug(f"    --tag-tracker-error (QBT_TAG_TRACKER_ERROR): {self.commands['tag_tracker_error']}")
                logger.debug(f"    --rem-orphaned (QBT_REM_ORPHANED): {self.commands['rem_orphaned']}")
                logger.debug(f"    --tag-nohardlinks (QBT_TAG_NOHARDLINKS): {self.commands['tag_nohardlinks']}")
                logger.debug(f"    --skip-cleanup (QBT_SKIP_CLEANUP): {self.commands['skip_cleanup']}")
                logger.debug(f"    --dry-run (QBT_DRY_RUN): {self.commands['dry_run']}")
        else:
            self.commands = args

        if "qbt" in self.data:                         self.data["qbt"] = self.data.pop("qbt")
        self.data["settings"] = self.data.pop("settings") if "settings" in self.data else {}
        if "directory" in self.data:                   self.data["directory"] = self.data.pop("directory")
        self.data["cat"] = self.data.pop("cat") if "cat" in self.data else {}
        if "cat_change" in self.data:                  self.data["cat_change"] = self.data.pop("cat_change")
        if "tracker" in self.data:                     self.data["tracker"] = self.data.pop("tracker")
        elif "tags" in self.data:                      self.data["tracker"] = self.data.pop("tags")
        else:                                           self.data["tracker"] = {}
        if "nohardlinks" in self.data:                 self.data["nohardlinks"] = self.data.pop("nohardlinks")
        if "recyclebin" in self.data:                  self.data["recyclebin"] = self.data.pop("recyclebin")
        if "orphaned" in self.data:                    self.data["orphaned"] = self.data.pop("orphaned")
        if "apprise" in self.data:                     self.data["apprise"] = self.data.pop("apprise")
        if "notifiarr" in self.data:                   self.data["notifiarr"] = self.data.pop("notifiarr")
        if "webhooks" in self.data:
            temp = self.data.pop("webhooks")
            if 'function' not in temp or ('function' in temp and temp['function'] is None): temp["function"] = {}

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
        if "bhd" in self.data:                         self.data["bhd"] = self.data.pop("bhd")

        self.session = requests.Session()

        self.settings = {
            "force_auto_tmm": self.util.check_for_attribute(self.data, "force_auto_tmm", parent="settings", var_type="bool", default=False),
            "tracker_error_tag": self.util.check_for_attribute(self.data, "tracker_error_tag", parent="settings", default='issue')
        }
        default_ignore_tags = ['noHL', self.settings["tracker_error_tag"], 'cross-seed']
        self.settings["ignoreTags_OnUpdate"] = self.util.check_for_attribute(self.data, "ignoreTags_OnUpdate", parent="settings", default=default_ignore_tags, var_type="list")

        default_function = {
            'cross_seed': None,
            'recheck': None,
            'cat_update': None,
            'tag_update': None,
            'rem_unregistered': None,
            'tag_tracker_error': None,
            'rem_orphaned': None,
            'tag_nohardlinks': None,
            'cleanup_dirs': None,
        }

        self.webhooks = {
            "error": self.util.check_for_attribute(self.data, "error", parent="webhooks", var_type="list", default_is_none=True),
            "run_start": self.util.check_for_attribute(self.data, "run_start", parent="webhooks", var_type="list", default_is_none=True),
            "run_end": self.util.check_for_attribute(self.data, "run_end", parent="webhooks", var_type="list", default_is_none=True),
            "function": self.util.check_for_attribute(self.data, "function", parent="webhooks", var_type="list", default=default_function)
        }
        for func in default_function:
            self.util.check_for_attribute(self.data, func, parent="webhooks", subparent="function", default_is_none=True)

        self.cat_change = self.data["cat_change"] if "cat_change" in self.data else {}

        self.AppriseFactory = None
        if "apprise" in self.data:
            if self.data["apprise"] is not None:
                logger.info("Connecting to Apprise...")
                try:
                    self.AppriseFactory = Apprise(self, {
                        "api_url": self.util.check_for_attribute(self.data, "api_url", parent="apprise", var_type="url", throw=True),
                        "notify_url": self.util.check_for_attribute(self.data, "notify_url", parent="apprise", var_type="list", throw=True),
                    })
                except Failed as e:
                    logger.error(e)
                logger.info(f"Apprise Connection {'Failed' if self.AppriseFactory is None else 'Successful'}")

        self.NotifiarrFactory = None
        if "notifiarr" in self.data:
            if self.data["notifiarr"] is not None:
                logger.info("Connecting to Notifiarr...")
                try:
                    self.NotifiarrFactory = Notifiarr(self, {
                        "apikey": self.util.check_for_attribute(self.data, "apikey", parent="notifiarr", throw=True),
                        "develop": self.util.check_for_attribute(self.data, "develop", parent="notifiarr", var_type="bool", default=False, do_print=False, save=False),
                        "test": self.util.check_for_attribute(self.data, "test", parent="notifiarr", var_type="bool", default=False, do_print=False, save=False),
                        "instance": self.util.check_for_attribute(self.data, "instance", parent="notifiarr", default=False, do_print=False, save=False)
                    })
                except Failed as e:
                    logger.error(e)
                logger.info(f"Notifiarr Connection {'Failed' if self.NotifiarrFactory is None else 'Successful'}")

        self.Webhooks = Webhooks(self, self.webhooks, notifiarr=self.NotifiarrFactory, apprise=self.AppriseFactory)
        try:
            self.Webhooks.start_time_hooks(self.start_time)
        except Failed as e:
            logger.stacktrace()
            logger.error(f"Webhooks Error: {e}")

        self.BeyondHD = None
        if "bhd" in self.data:
            if self.data["bhd"] is not None:
                logger.info("Connecting to BHD API...")
                try:
                    self.BeyondHD = BeyondHD(self, {
                        "apikey": self.util.check_for_attribute(self.data, "apikey", parent="bhd", throw=True)
                    })
                except Failed as e:
                    logger.error(e)
                    self.notify(e, 'BHD')
                logger.info(f"BHD Connection {'Failed' if self.BeyondHD is None else 'Successful'}")

        # nohardlinks
        self.nohardlinks = None
        if "nohardlinks" in self.data and self.commands['tag_nohardlinks']:
            self.nohardlinks = {}
            for cat in self.data["nohardlinks"]:
                if cat in list(self.data["cat"].keys()):
                    self.nohardlinks[cat] = {}
                    self.nohardlinks[cat]["exclude_tags"] = self.util.check_for_attribute(self.data, "exclude_tags", parent="nohardlinks", subparent=cat,
                                                                                          var_type="list", default_is_none=True, do_print=False)
                    self.nohardlinks[cat]["cleanup"] = self.util.check_for_attribute(self.data, "cleanup", parent="nohardlinks", subparent=cat, var_type="bool", default=False, do_print=False)
                    self.nohardlinks[cat]['max_ratio'] = self.util.check_for_attribute(self.data, "max_ratio", parent="nohardlinks", subparent=cat,
                                                                                       var_type="float", default_int=-2, default_is_none=True, do_print=False)
                    self.nohardlinks[cat]['max_seeding_time'] = self.util.check_for_attribute(self.data, "max_seeding_time", parent="nohardlinks", subparent=cat,
                                                                                              var_type="int", default_int=-2, default_is_none=True, do_print=False)
                    self.nohardlinks[cat]['min_seeding_time'] = self.util.check_for_attribute(self.data, "min_seeding_time", parent="nohardlinks", subparent=cat,
                                                                                              var_type="int", default_int=0, default=0, do_print=False)
                    self.nohardlinks[cat]['limit_upload_speed'] = self.util.check_for_attribute(self.data, "limit_upload_speed", parent="nohardlinks", subparent=cat,
                                                                                                var_type="int", default_int=-1, default_is_none=True, do_print=False)
                else:
                    e = (f"Config Error: Category {cat} is defined under nohardlinks attribute but is not defined in the cat attribute.")
                    self.notify(e, 'Config')
                    raise Failed(e)
        else:
            if self.commands["tag_nohardlinks"]:
                e = "Config Error: nohardlinks attribute not found"
                self.notify(e, 'Config')
                raise Failed(e)

        # Add RecycleBin
        self.recyclebin = {}
        self.recyclebin['enabled'] = self.util.check_for_attribute(self.data, "enabled", parent="recyclebin", var_type="bool", default=True)
        self.recyclebin['empty_after_x_days'] = self.util.check_for_attribute(self.data, "empty_after_x_days", parent="recyclebin", var_type="int", default_is_none=True)
        self.recyclebin['save_torrents'] = self.util.check_for_attribute(self.data, "save_torrents", parent="recyclebin", var_type="bool", default=False)
        self.recyclebin['split_by_category'] = self.util.check_for_attribute(self.data, "split_by_category", parent="recyclebin", var_type="bool", default=False)

        # Assign directories
        if "directory" in self.data:
            self.root_dir = os.path.join(self.util.check_for_attribute(self.data, "root_dir", parent="directory", default_is_none=True), '')
            self.remote_dir = os.path.join(self.util.check_for_attribute(self.data, "remote_dir", parent="directory", default=self.root_dir), '')
            if (self.commands["cross_seed"] or self.commands["tag_nohardlinks"] or self.commands["rem_orphaned"]):
                self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory", var_type="path", default=self.root_dir)
            else:
                if self.recyclebin['enabled']:
                    self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory", var_type="path", default=self.root_dir)
            if self.commands["cross_seed"]:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory", var_type="path")
            else:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory", default_is_none=True)
            if self.commands["rem_orphaned"]:
                if "orphaned_dir" in self.data["directory"] and self.data["directory"]["orphaned_dir"] is not None:
                    default_orphaned = os.path.join(self.remote_dir, os.path.basename(self.data['directory']['orphaned_dir'].rstrip(os.sep)))
                else:
                    default_orphaned = os.path.join(self.remote_dir, 'orphaned_data')
                self.orphaned_dir = self.util.check_for_attribute(self.data, "orphaned_dir", parent="directory", var_type="path", default=default_orphaned, make_dirs=True)
            else:
                self.orphaned_dir = None
            if self.recyclebin['enabled']:
                if "recycle_bin" in self.data["directory"] and self.data["directory"]["recycle_bin"] is not None:
                    default_recycle = os.path.join(self.remote_dir, os.path.basename(self.data['directory']['recycle_bin'].rstrip(os.sep)))
                else:
                    default_recycle = os.path.join(self.remote_dir, '.RecycleBin')
                if self.recyclebin['split_by_category']:
                    self.recycle_dir = self.util.check_for_attribute(self.data, "recycle_bin", parent="directory", default=default_recycle)
                else:
                    self.recycle_dir = self.util.check_for_attribute(self.data, "recycle_bin", parent="directory", var_type="path", default=default_recycle, make_dirs=True)
            else:
                self.recycle_dir = None
            if self.recyclebin['enabled'] and self.recyclebin['save_torrents']:
                self.torrents_dir = self.util.check_for_attribute(self.data, "torrents_dir", parent="directory", var_type="path")
                if not any(File.endswith(".torrent") for File in os.listdir(self.torrents_dir)):
                    e = f"Config Error: The location {self.torrents_dir} does not contain any .torrents"
                    self.notify(e, 'Config')
                    raise Failed(e)
            else:
                self.torrents_dir = self.util.check_for_attribute(self.data, "torrents_dir", parent="directory", default_is_none=True)
        else:
            e = "Config Error: directory attribute not found"
            self.notify(e, 'Config')
            raise Failed(e)

        # Add Orphaned
        self.orphaned = {}
        self.orphaned['empty_after_x_days'] = self.util.check_for_attribute(self.data, "empty_after_x_days", parent="orphaned", var_type="int", default_is_none=True)
        self.orphaned['exclude_patterns'] = self.util.check_for_attribute(self.data, "exclude_patterns", parent="orphaned", var_type="list", default_is_none=True, do_print=False)
        exclude_orphaned = f"**{os.sep}{os.path.basename(self.orphaned_dir.rstrip(os.sep))}{os.sep}*"
        self.orphaned['exclude_patterns'].append(exclude_orphaned) if exclude_orphaned not in self.orphaned['exclude_patterns'] else self.orphaned['exclude_patterns']
        if self.recyclebin['enabled']:
            exclude_recycle = f"**{os.sep}{os.path.basename(self.recycle_dir.rstrip(os.sep))}{os.sep}*"
            self.orphaned['exclude_patterns'].append(exclude_recycle) if exclude_recycle not in self.orphaned['exclude_patterns'] else self.orphaned['exclude_patterns']

        # Connect to Qbittorrent
        self.qbt = None
        if "qbt" in self.data:
            logger.info("Connecting to Qbittorrent...")
            self.qbt = Qbt(self, {
                "host": self.util.check_for_attribute(self.data, "host", parent="qbt", throw=True),
                "username": self.util.check_for_attribute(self.data, "user", parent="qbt", default_is_none=True),
                "password": self.util.check_for_attribute(self.data, "pass", parent="qbt", default_is_none=True)
            })
        else:
            e = "Config Error: qbt attribute not found"
            self.notify(e, 'Config')
            raise Failed(e)

    # Get tags from config file based on keyword
    def get_tags(self, urls):
        tracker = {}
        tracker['tag'] = None
        tracker['max_ratio'] = None
        tracker['max_seeding_time'] = None
        tracker['limit_upload_speed'] = None
        tracker['notifiarr'] = None
        tracker['url'] = None
        if not urls: return tracker
        try:
            tracker['url'] = util.trunc_val(urls[0], os.sep)
        except IndexError as e:
            tracker['url'] = None
            logger.debug(f"Tracker Url:{urls}")
            logger.debug(e)
        if 'tracker' in self.data and self.data["tracker"] is not None:
            tag_values = self.data['tracker']
            for tag_url, tag_details in tag_values.items():
                for url in urls:
                    if tag_url in url:
                        try:
                            tracker['url'] = util.trunc_val(url, os.sep)
                            default_tag = tracker['url'].split(os.sep)[2].split(':')[0]
                        except IndexError as e:
                            logger.debug(f"Tracker Url:{url}")
                            logger.debug(e)
                        # If using Format 1 convert to format 2
                        if isinstance(tag_details, str):
                            tracker['tag'] = self.util.check_for_attribute(self.data, tag_url, parent="tracker", default=default_tag, var_type="list")
                            self.util.check_for_attribute(self.data, "tag", parent="tracker", subparent=tag_url, default=tracker['tag'], do_print=False, var_type="list")
                            if tracker['tag'] == default_tag:
                                try:
                                    self.data['tracker'][tag_url]['tag'] = [default_tag]
                                except Exception:
                                    self.data['tracker'][tag_url] = {'tag': [default_tag]}
                        # Using Format 2
                        else:
                            tracker['tag'] = self.util.check_for_attribute(self.data, "tag", parent="tracker", subparent=tag_url, default=tag_url, var_type="list")
                            if tracker['tag'] == [tag_url]: self.data['tracker'][tag_url]['tag'] = [tag_url]
                            if isinstance(tracker['tag'], str): tracker['tag'] = [tracker['tag']]
                            tracker['max_ratio'] = self.util.check_for_attribute(self.data, "max_ratio", parent="tracker", subparent=tag_url,
                                                                                 var_type="float", default_int=-2, default_is_none=True, do_print=False, save=False)
                            tracker['max_seeding_time'] = self.util.check_for_attribute(self.data, "max_seeding_time", parent="tracker", subparent=tag_url,
                                                                                        var_type="int", default_int=-2, default_is_none=True, do_print=False, save=False)
                            tracker['limit_upload_speed'] = self.util.check_for_attribute(self.data, "limit_upload_speed", parent="tracker", subparent=tag_url,
                                                                                          var_type="int", default_int=-1, default_is_none=True, do_print=False, save=False)
                            tracker['notifiarr'] = self.util.check_for_attribute(self.data, "notifiarr", parent="tracker", subparent=tag_url, default_is_none=True, do_print=False, save=False)
                        return (tracker)
        if tracker['url']:
            default_tag = tracker['url'].split(os.sep)[2].split(':')[0]
            tracker['tag'] = self.util.check_for_attribute(self.data, "tag", parent="tracker", subparent=default_tag, default=default_tag, var_type="list")
            if isinstance(tracker['tag'], str): tracker['tag'] = [tracker['tag']]
            try:
                self.data['tracker'][default_tag]['tag'] = [default_tag]
            except Exception:
                self.data['tracker'][default_tag] = {'tag': [default_tag]}
            e = (f'No tags matched for {tracker["url"]}. Please check your config.yml file. Setting tag to {default_tag}')
            self.notify(e, 'Tag', False)
            logger.warning(e)
        return (tracker)

    # Get category from config file based on path provided
    def get_category(self, path):
        category = ''
        path = os.path.join(path, '')
        if "cat" in self.data and self.data["cat"] is not None:
            cat_path = self.data["cat"]
            for cat, save_path in cat_path.items():
                if os.path.join(save_path, '') == path:
                    category = cat
                    break

        if not category:
            default_cat = path.split(os.sep)[-2]
            category = str(default_cat)
            self.util.check_for_attribute(self.data, default_cat, parent="cat", default=path)
            self.data['cat'][str(default_cat)] = path
            e = (f'No categories matched for the save path {path}. Check your config.yml file. - Setting category to {default_cat}')
            self.notify(e, 'Category', False)
            logger.warning(e)
        return category

    # Empty old files from recycle bin or orphaned
    def cleanup_dirs(self, location):
        dry_run = self.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_del = 0
        files = []
        size_bytes = 0
        skip = self.commands["skip_cleanup"]
        if location == "Recycle Bin":
            enabled = self.recyclebin['enabled']
            empty_after_x_days = self.recyclebin['empty_after_x_days']
            function = "cleanup_dirs"
            location_path = self.recycle_dir

        elif location == "Orphaned Data":
            enabled = self.commands["rem_orphaned"]
            empty_after_x_days = self.orphaned['empty_after_x_days']
            function = "cleanup_dirs"
            location_path = self.orphaned_dir

        if not skip:
            if enabled and empty_after_x_days:
                if location == "Recycle Bin" and self.recyclebin['split_by_category']:
                    if "cat" in self.data and self.data["cat"] is not None:
                        save_path = list(self.data["cat"].values())
                        cleaned_save_path = [os.path.join(s.replace(self.root_dir, self.remote_dir), os.path.basename(location_path.rstrip(os.sep))) for s in save_path]
                        location_path_list = [location_path]
                        for dir in cleaned_save_path:
                            if os.path.exists(dir): location_path_list.append(dir)
                    else:
                        e = (f'No categories defined. Checking {location} directory {location_path}.')
                        self.notify(e, f'Empty {location}', False)
                        logger.warning(e)
                        location_path_list = [location_path]
                else:
                    location_path_list = [location_path]
                location_files = [os.path.join(path, name) for r_path in location_path_list for path, subdirs, files in os.walk(r_path) for name in files]
                location_files = sorted(location_files)
                if location_files:
                    body = []
                    logger.separator(f"Emptying {location} (Files > {empty_after_x_days} days)", space=True, border=True)
                    prevfolder = ''
                    for file in location_files:
                        folder = re.search(f".*{os.path.basename(location_path.rstrip(os.sep))}", file).group(0)
                        if folder != prevfolder: body += logger.separator(f"Searching: {folder}", space=False, border=False)
                        fileStats = os.stat(file)
                        filename = os.path.basename(file)
                        last_modified = fileStats[stat.ST_MTIME]  # in seconds (last modified time)
                        now = time.time()  # in seconds
                        days = (now - last_modified) / (60 * 60 * 24)
                        if (empty_after_x_days <= days):
                            num_del += 1
                            body += logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {filename} from {folder} (Last modified {round(days)} days ago).", loglevel)
                            files += [str(filename)]
                            size_bytes += os.path.getsize(file)
                            if not dry_run: os.remove(file)
                        prevfolder = re.search(f".*{os.path.basename(location_path.rstrip(os.sep))}", file).group(0)
                    if num_del > 0:
                        if not dry_run:
                            for path in location_path_list:
                                util.remove_empty_directories(path, "**/*")
                        body += logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {num_del} files ({util.human_readable_size(size_bytes)}) from the {location}.", loglevel)
                        attr = {
                            "function": function,
                            "location": location,
                            "title": f"Emptying {location} (Files > {empty_after_x_days} days)",
                            "body": "\n".join(body),
                            "files": files,
                            "empty_after_x_days": empty_after_x_days,
                            "size_in_bytes": size_bytes
                        }
                        self.send_notifications(attr)
                else:
                    logger.debug(f'No files found in "{(",".join(location_path_list))}"')
        return num_del

    def send_notifications(self, attr):
        try:
            function = attr['function']
            config_webhooks = self.Webhooks.function_webhooks
            config_function = None
            for key in config_webhooks:
                if key in function:
                    config_function = key
                    break
            if config_function:
                self.Webhooks.function_hooks([config_webhooks[config_function]], attr)
        except Failed as e:
            logger.stacktrace()
            logger.error(f"Webhooks Error: {e}")

    def notify(self, text, function=None, critical=True):
        for error in util.get_list(text, split=False):
            try:
                self.Webhooks.error_hooks(error, function_error=function, critical=critical)
            except Failed as e:
                logger.stacktrace()
                logger.error(f"Webhooks Error: {e}")

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
