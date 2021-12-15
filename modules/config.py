import logging, os, requests, stat, time
from modules import util
from modules.util import Failed, check
from modules.qbittorrent import Qbt
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

        yaml.YAML().allow_duplicate_keys = True
        try:
            new_config, _, _ = yaml.util.load_yaml_guess_indent(open(self.config_path, encoding="utf-8"))
            if "qbt" in new_config:                         new_config["qbt"] = new_config.pop("qbt")
            if "directory" in new_config:                   new_config["directory"] = new_config.pop("directory")
            if "cat" in new_config:                         new_config["cat"] = new_config.pop("cat")
            if "tags" in new_config:                        new_config["tags"] = new_config.pop("tags")
            if "nohardlinks" in new_config:                 new_config["nohardlinks"] = new_config.pop("nohardlinks")
            if "recyclebin" in new_config:                  new_config["recyclebin"] = new_config.pop("recyclebin")
            if "orphaned" in new_config:                    new_config["orphaned"] = new_config.pop("orphaned")
            yaml.round_trip_dump(new_config, open(self.config_path, "w", encoding="utf-8"), indent=None, block_seq_indent=2)
            self.data = new_config
        except yaml.scanner.ScannerError as e:
            raise Failed(f"YAML Error: {util.tab_new_lines(e)}")
        except Exception as e:
            util.print_stacktrace()
            raise Failed(f"YAML Error: {e}")

        if self.data["cat"] is None: self.data["cat"] = {}
        if self.data["tags"] is None: self.data["tags"] = {}
        self.session = requests.Session()
        #nohardlinks
        self.nohardlinks = None
        if "nohardlinks" in self.data and self.args['tag_nohardlinks']:
            self.nohardlinks = {}
            for cat in self.data["nohardlinks"]:
                if cat in list(self.data["cat"].keys()):
                    self.nohardlinks[cat] = {}
                    self.nohardlinks[cat]["exclude_tags"] = self.util.check_for_attribute(self.data, "exclude_tags", parent="nohardlinks", subparent=cat, var_type="list", default_is_none=True,do_print=False)
                    self.nohardlinks[cat]["cleanup"] = self.util.check_for_attribute(self.data, "cleanup", parent="nohardlinks", subparent=cat, var_type="bool", default=False,do_print=False)
                    self.nohardlinks[cat]['max_ratio'] = self.util.check_for_attribute(self.data, "max_ratio", parent="nohardlinks", subparent=cat, var_type="float", default_int=-2, default_is_none=True,do_print=False)
                    self.nohardlinks[cat]['max_seeding_time'] = self.util.check_for_attribute(self.data, "max_seeding_time", parent="nohardlinks", subparent=cat, var_type="int", default_int=-2, default_is_none=True,do_print=False)
                    self.nohardlinks[cat]['limit_upload_speed'] = self.util.check_for_attribute(self.data, "limit_upload_speed", parent="nohardlinks", subparent=cat, var_type="int", default_int=-1, default_is_none=True,do_print=False)
                else:
                    raise Failed(f"Config Error: Category {cat} is defined under nohardlinks attribute but is not defined in the cat attriute.")
        else:
            if self.args["tag_nohardlinks"]:
                raise Failed("Config Error: nohardlinks attribute not found")

        #Add RecycleBin
        self.recyclebin = {}
        self.recyclebin['enabled'] = self.util.check_for_attribute(self.data, "enabled", parent="recyclebin",var_type="bool",default=True)
        self.recyclebin['empty_after_x_days'] = self.util.check_for_attribute(self.data, "empty_after_x_days", parent="recyclebin",var_type="int",default_is_none=True)
        
        #Add Orphaned
        self.orphaned = {}
        self.orphaned['exclude_patterns'] = self.util.check_for_attribute(self.data, "exclude_patterns", parent="orphaned",var_type="list",default_is_none=True,do_print=False)

        #Assign directories
        if "directory" in self.data:
            self.root_dir = self.util.check_for_attribute(self.data, "root_dir", parent="directory",default_is_none=True)
            self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory",default=self.root_dir)
            if (self.args["cross_seed"] or self.args["tag_nohardlinks"] or self.args["rem_orphaned"]):
                self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory",var_type="path",default=self.root_dir)
            else:
                if self.recyclebin['enabled']:
                    self.remote_dir = self.util.check_for_attribute(self.data, "remote_dir", parent="directory",var_type="path",default=self.root_dir)
            if self.args["cross_seed"]:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory",var_type="path")
            else:
                self.cross_seed_dir = self.util.check_for_attribute(self.data, "cross_seed", parent="directory",default_is_none=True)
            self.recycle_dir = os.path.join(self.remote_dir,'.RecycleBin')
        else:
            raise Failed("Config Error: directory attribute not found")

        #Connect to Qbittorrent
        self.qbt = None
        if "qbt" in self.data:
                logger.info("Connecting to Qbittorrent...")
                self.qbt = Qbt(self, {
                    "host": self.util.check_for_attribute(self.data, "host", parent="qbt", throw=True),
                    "username": self.util.check_for_attribute(self.data, "user", parent="qbt", default_is_none=True),
                    "password": self.util.check_for_attribute(self.data, "pass", parent="qbt", default_is_none=True)
                })
        else:
            raise Failed("Config Error: qbt attribute not found")

    #Get tags from config file based on keyword
    def get_tags(self,urls):
        tags = {}
        tags['new_tag'] = None
        tags['max_ratio'] = None
        tags['max_seeding_time'] = None
        tags['limit_upload_speed'] = None
        if not urls: return tags
        try:
            tags['url'] = util.trunc_val(urls[0], '/')
        except IndexError as e:
            tags['url'] = None
            logger.debug(f"Tracker Url:{urls}")
            logger.debug(e)
        if 'tags' in self.data and self.data["tags"] is not None:
            tag_values = self.data['tags']
            for tag_url, tag_details in tag_values.items():
                for url in urls:
                    if tag_url in url:
                        try:
                            tags['url'] = util.trunc_val(url, '/')
                            default_tag = tags['url'].split('/')[2].split(':')[0]
                        except IndexError as e:
                            logger.debug(f"Tracker Url:{url}")
                            logger.debug(e)
                        # If using Format 1 convert to format 2
                        if isinstance(tag_details,str):
                            tags['new_tag'] = self.util.check_for_attribute(self.data, tag_url, parent="tags",default=default_tag)
                            self.util.check_for_attribute(self.data, "tag", parent="tags",subparent=tag_url, default=tags['new_tag'],do_print=False)
                            if tags['new_tag'] == default_tag:
                                if self.data["tags"][tag_url] is None: self.data["tags"][tag_url] = {}
                                self.data['tags'][tag_url]['tag'] = default_tag
                        # Using Format 2
                        else:
                            tags['new_tag'] = self.util.check_for_attribute(self.data, "tag", parent="tags", subparent=tag_url, default=tag_url)
                            if tags['new_tag'] == tag_url: self.data['tags'][tag_url]['tag'] = tag_url
                            tags['max_ratio'] = self.util.check_for_attribute(self.data, "max_ratio", parent="tags", subparent=tag_url, var_type="float", default_int=-2, default_is_none=True,do_print=False,save=False)
                            tags['max_seeding_time'] = self.util.check_for_attribute(self.data, "max_seeding_time", parent="tags", subparent=tag_url, var_type="int", default_int=-2, default_is_none=True,do_print=False,save=False)
                            tags['limit_upload_speed'] = self.util.check_for_attribute(self.data, "limit_upload_speed", parent="tags", subparent=tag_url, var_type="int", default_int=-1, default_is_none=True,do_print=False,save=False)
                        return (tags)
        if tags['url']:
            default_tag = tags['url'].split('/')[2].split(':')[0]
            tags['new_tag'] = self.util.check_for_attribute(self.data, "tag", parent="tags",subparent=default_tag, default=default_tag)
            if self.data["tags"][default_tag] is None: self.data["tags"][default_tag] = {}
            self.data['tags'][default_tag]['tag'] = default_tag
            logger.warning(f'No tags matched for {tags["url"]}. Please check your config.yml file. Setting tag to {default_tag}')
        return (tags)

    #Get category from config file based on path provided
    def get_category(self,path):
        category = ''
        path = os.path.join(path,'')
        if "cat" in self.data and self.data["cat"] is not None:
            cat_path = self.data["cat"]
            for cat, save_path in cat_path.items():
                if save_path in path:
                    category = cat
                    break
        if not category:
            default_cat = path.split('/')[-2]
            category = self.util.check_for_attribute(self.data, default_cat, parent="cat",default=path)
            self.data['cat'][str(default_cat)] = path
            logger.warning(f'No categories matched for the save path {path}. Check your config.yml file. - Setting category to {default_cat}')
        return category

    #Empty the recycle bin
    def empty_recycle(self):
        dry_run = self.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_del = 0
        if not self.args["skip_recycle"]:
            n_info = ''
            if self.recyclebin['enabled'] and self.recyclebin['empty_after_x_days']:
                recycle_files = [os.path.join(path, name) for path, subdirs, files in os.walk(self.recycle_dir) for name in files]
                recycle_files = sorted(recycle_files)
                if recycle_files:
                    util.separator(f"Emptying Recycle Bin (Files > {self.recyclebin['empty_after_x_days']} days)", space=False, border=False)
                    for file in recycle_files:
                        fileStats = os.stat(file)
                        filename = file.replace(self.recycle_dir,'')
                        last_modified = fileStats[stat.ST_MTIME] # in seconds (last modified time)
                        now = time.time() # in seconds
                        days = (now - last_modified) / (60 * 60 * 24)
                        if (self.recyclebin['empty_after_x_days'] <= days):
                            num_del += 1
                            n_info += (f"{'Did not delete' if dry_run else 'Deleted'} {filename} from the recycle bin. (Last modified {round(days)} days ago).\n")
                            if not dry_run: os.remove(file)
                    if num_del > 0:
                        if not dry_run: util.remove_empty_directories(self.recycle_dir,"**/*")
                        util.print_multiline(n_info,loglevel)
                        util.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {num_del} files from the Recycle Bin.",loglevel)
                else:
                    logger.debug('No files found in "' + self.recycle_dir + '"')
        return num_del

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def get(self, url, json=None, headers=None, params=None):
        return self.session.get(url, json=json, headers=headers, params=params)

    @retry(stop_max_attempt_number=6, wait_fixed=10000)
    def post(self, url, data=None, json=None, headers=None):
        return self.session.post(url, data=data, json=json, headers=headers)
