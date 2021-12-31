import logging, os, requests, stat, time
from modules import util
from modules.util import Failed, check
from modules.qbittorrent import Qbt
from modules.webhooks import Webhooks
from modules.notifiarr import Notifiarr
from modules.bhd import BeyondHD
from modules.apprise import Apprise
from ruamel import yaml
from retrying import retry

logger = logging.getLogger("qBit Manage")


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

        yaml.YAML().allow_duplicate_keys = True
        try:
            new_config, _, _ = yaml.util.load_yaml_guess_indent(open(self.config_path, encoding="utf-8"))
            if "qbt" in new_config:                         new_config["qbt"] = new_config.pop("qbt")
            new_config["settings"] = new_config.pop("settings") if "settings" in new_config else {}
            if "directory" in new_config:                   new_config["directory"] = new_config.pop("directory")
            new_config["cat"] = new_config.pop("cat") if "cat" in new_config else {}
            if "tracker" in new_config:                     new_config["tracker"] = new_config.pop("tracker")
            elif "tags" in new_config:                      new_config["tracker"] = new_config.pop("tags")
            else:                                           new_config["tracker"] = {}
            if "nohardlinks" in new_config:                 new_config["nohardlinks"] = new_config.pop("nohardlinks")
            if "recyclebin" in new_config:                  new_config["recyclebin"] = new_config.pop("recyclebin")
            if "orphaned" in new_config:                    new_config["orphaned"] = new_config.pop("orphaned")
            if "apprise" in new_config:                     new_config["apprise"] = new_config.pop("apprise")
            if "notifiarr" in new_config:                   new_config["notifiarr"] = new_config.pop("notifiarr")
            if "webhooks" in new_config:
                temp = new_config.pop("webhooks")
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
                hooks("empty_recyclebin")
                new_config["webhooks"] = temp
            if "bhd" in new_config:                         new_config["bhd"] = new_config.pop("bhd")
            yaml.round_trip_dump(new_config, open(self.config_path, "w", encoding="utf-8"), indent=None, block_seq_indent=2)
            self.data = new_config
        except yaml.scanner.ScannerError as e:
            raise Failed(f"YAML Error: {util.tab_new_lines(e)}")
        except Exception as e:
            util.print_stacktrace()
            raise Failed(f"YAML Error: {e}")

        self.session = requests.Session()

        self.settings = {
            "force_auto_tmm": self.util.check_for_attribute(self.data, "force_auto_tmm", parent="settings", var_type="bool", default=False),
        }

        default_function = {
            'cross_seed': None,
            'recheck': None,
            'cat_update': None,
            'tag_update': None,
            'rem_unregistered': None,
            'rem_orphaned': None,
            'tag_nohardlinks': None,
            'empty_recyclebin': None}

        self.webhooks = {
            "error": self.util.check_for_attribute(self.data, "error", parent="webhooks", var_type="list", default_is_none=True),
            "run_start": self.util.check_for_attribute(self.data, "run_start", parent="webhooks", var_type="list", default_is_none=True),
            "run_end": self.util.check_for_attribute(self.data, "run_end", parent="webhooks", var_type="list", default_is_none=True),
            "function": self.util.check_for_attribute(self.data, "function", parent="webhooks", var_type="list", default=default_function)
        }

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
            util.print_stacktrace()
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
        if "nohardlinks" in self.data and self.args['tag_nohardlinks']:
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
                    self.nohardlinks[cat]['limit_upload_speed'] = self.util.check_for_attribute(self.data, "limit_upload_speed", parent="nohardlinks", subparent=cat,
                                                                                                var_type="int", default_int=-1, default_is_none=True, do_print=False)
                else:
                    e = (f"Config Error: Category {cat} is defined under nohardlinks attribute but is not defined in the cat attribute.")
                    self.notify(e, 'Config')
                    raise Failed(e)
        else:
            if self.args["tag_nohardlinks"]:
                e = "Config Error: nohardlinks attribute not found"
                self.notify(e, 'Config')
                raise Failed(e)

        # Add RecycleBin
        self.recyclebin = {}
        self.recyclebin['enabled'] = self.util.check_for_attribute(self.data, "enabled", parent="recyclebin", var_type="bool", default=True)
        self.recyclebin['empty_after_x_days'] = self.util.check_for_attribute(self.data, "empty_after_x_days", parent="recyclebin", var_type="int", default_is_none=True)

        # Add Orphaned
        self.orphaned = {}
        self.orphaned['exclude_patterns'] = self.util.check_for_attribute(self.data, "exclude_patterns", parent="orphaned", var_type="list", default_is_none=True, do_print=False)

        # Assign directories
        if "directory" in self.data:
            self.root_dir = self.util.check_for_attribute(self.data, "root_dir", parent="directory", default_is_none=True)
            self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory", default=self.root_dir)
            if (self.args["cross_seed"] or self.args["tag_nohardlinks"] or self.args["rem_orphaned"]):
                self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory", var_type="path", default=self.root_dir)
            else:
                if self.recyclebin['enabled']:
                    self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory", var_type="path", default=self.root_dir)
            if self.args["cross_seed"]:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory", var_type="path")
            else:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory", default_is_none=True)
            self.recycle_dir = self.util.check_for_attribute(self.data, "recycle_bin", parent="directory", var_type="path", default=os.path.join(self.remote_dir, '.RecycleBin'))
        else:
            e = "Config Error: directory attribute not found"
            self.notify(e, 'Config')
            raise Failed(e)

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
            tracker['url'] = util.trunc_val(urls[0], '/')
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
                            tracker['url'] = util.trunc_val(url, '/')
                            default_tag = tracker['url'].split('/')[2].split(':')[0]
                        except IndexError as e:
                            logger.debug(f"Tracker Url:{url}")
                            logger.debug(e)
                        # If using Format 1 convert to format 2
                        if isinstance(tag_details, str):
                            tracker['tag'] = self.util.check_for_attribute(self.data, tag_url, parent="tracker", default=default_tag)
                            self.util.check_for_attribute(self.data, "tag", parent="tracker", subparent=tag_url, default=tracker['tag'], do_print=False)
                            if tracker['tag'] == default_tag:
                                try:
                                    self.data['tracker'][tag_url]['tag'] = default_tag
                                except Exception:
                                    self.data['tracker'][tag_url] = {'tag': default_tag}
                        # Using Format 2
                        else:
                            tracker['tag'] = self.util.check_for_attribute(self.data, "tag", parent="tracker", subparent=tag_url, default=tag_url)
                            if tracker['tag'] == tag_url: self.data['tracker'][tag_url]['tag'] = tag_url
                            tracker['max_ratio'] = self.util.check_for_attribute(self.data, "max_ratio", parent="tracker", subparent=tag_url,
                                                                                 var_type="float", default_int=-2, default_is_none=True, do_print=False, save=False)
                            tracker['max_seeding_time'] = self.util.check_for_attribute(self.data, "max_seeding_time", parent="tracker", subparent=tag_url,
                                                                                        var_type="int", default_int=-2, default_is_none=True, do_print=False, save=False)
                            tracker['limit_upload_speed'] = self.util.check_for_attribute(self.data, "limit_upload_speed", parent="tracker", subparent=tag_url,
                                                                                          var_type="int", default_int=-1, default_is_none=True, do_print=False, save=False)
                            tracker['notifiarr'] = self.util.check_for_attribute(self.data, "notifiarr", parent="tracker", subparent=tag_url, default_is_none=True, do_print=False, save=False)
                        return (tracker)
        if tracker['url']:
            default_tag = tracker['url'].split('/')[2].split(':')[0]
            tracker['tag'] = self.util.check_for_attribute(self.data, "tag", parent="tracker", subparent=default_tag, default=default_tag)
            try:
                self.data['tracker'][default_tag]['tag'] = default_tag
            except Exception:
                self.data['tracker'][default_tag] = {'tag': default_tag}
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
                if save_path in path:
                    category = cat
                    break
        if not category:
            default_cat = path.split('/')[-2]
            category = str(default_cat)
            self.util.check_for_attribute(self.data, default_cat, parent="cat", default=path)
            self.data['cat'][str(default_cat)] = path
            e = (f'No categories matched for the save path {path}. Check your config.yml file. - Setting category to {default_cat}')
            self.notify(e, 'Category', False)
            logger.warning(e)
        return category

    # Empty the recycle bin
    def empty_recycle(self):
        dry_run = self.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_del = 0
        files = []
        size_bytes = 0
        if not self.args["skip_recycle"]:
            n_info = ''
            if self.recyclebin['enabled'] and self.recyclebin['empty_after_x_days']:
                recycle_files = [os.path.join(path, name) for path, subdirs, files in os.walk(self.recycle_dir) for name in files]
                recycle_files = sorted(recycle_files)
                if recycle_files:
                    util.separator(f"Emptying Recycle Bin (Files > {self.recyclebin['empty_after_x_days']} days)", space=False, border=False)
                    for file in recycle_files:
                        fileStats = os.stat(file)
                        filename = file.replace(self.recycle_dir, '')
                        last_modified = fileStats[stat.ST_MTIME]  # in seconds (last modified time)
                        now = time.time()  # in seconds
                        days = (now - last_modified) / (60 * 60 * 24)
                        if (self.recyclebin['empty_after_x_days'] <= days):
                            num_del += 1
                            n_info += (f"{'Did not delete' if dry_run else 'Deleted'} {filename} from the recycle bin. (Last modified {round(days)} days ago).\n")
                            files += [str(filename)]
                            size_bytes += os.path.getsize(file)
                            if not dry_run: os.remove(file)
                    if num_del > 0:
                        if not dry_run: util.remove_empty_directories(self.recycle_dir, "**/*")
                        body = []
                        body += util.print_multiline(n_info, loglevel)
                        body += util.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {num_del} files ({util.human_readable_size(size_bytes)}) from the Recycle Bin.", loglevel)
                        attr = {
                            "function": "empty_recyclebin",
                            "title": f"Emptying Recycle Bin (Files > {self.recyclebin['empty_after_x_days']} days)",
                            "body": "\n".join(body),
                            "files": files,
                            "empty_after_x_days": self.recyclebin['empty_after_x_days'],
                            "size_in_bytes": size_bytes
                        }
                        self.send_notifications(attr)
                else:
                    logger.debug('No files found in "' + self.recycle_dir + '"')
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
            util.print_stacktrace()
            logger.error(f"Webhooks Error: {e}")

    def notify(self, text, function=None, critical=True):
        for error in util.get_list(text, split=False):
            try:
                self.Webhooks.error_hooks(error, function_error=function, critical=critical)
            except Failed as e:
                util.print_stacktrace()
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
