#!/usr/bin/python3

import argparse, logging, os, sys, time, shutil, urllib3, stat, fnmatch
from logging.handlers import RotatingFileHandler
from datetime import timedelta,datetime
from collections import Counter
from pathlib import Path

try:
    import yaml, schedule
    from qbittorrentapi import Client, LoginFailed, APIConnectionError
    from modules.docker import GracefulKiller
    from modules import util 
except ModuleNotFoundError:
    print("Requirements Error: Requirements are not installed")
    sys.exit(0)


if sys.version_info[0] != 3 or sys.version_info[1] < 6:
    print("Version Error: Version: %s.%s.%s incompatible please use Python 3.6+" % (sys.version_info[0], sys.version_info[1], sys.version_info[2]))
    sys.exit(0)

parser = argparse.ArgumentParser('qBittorrent Manager.', description='A mix of scripts combined for managing qBittorrent.')
parser.add_argument('-r', '--run', dest='run', action='store_true', default=False, help='Run without the scheduler. Script will exit after completion.')
parser.add_argument('-sch', '--schedule', dest='min',  default='30', type=str, help='Schedule to run every x minutes. (Default set to 30)')
parser.add_argument('-c', '--config-file', dest='configfile', action='store', default='config.yml', type=str,  help='This is used if you want to use a different name for your config.yml. Example: tv.yml')
parser.add_argument('-lf', '--log-file', dest='logfile', action='store',default='activity.log', type=str, help='This is used if you want to use a different name for your log file. Example: tv.log',)
parser.add_argument('-cs', '--cross-seed', dest='cross_seed', action="store_true", default=False, help='Use this after running cross-seed script to add torrents from the cross-seed output folder to qBittorrent')
parser.add_argument('-re', '--recheck', dest='recheck', action="store_true", default=False, help='Recheck paused torrents sorted by lowest size. Resume if Completed.')
parser.add_argument('-cu', '--cat-update', dest='cat_update', action="store_true", default=False, help='Use this if you would like to update your categories.')
parser.add_argument('-tu', '--tag-update', dest='tag_update', action="store_true", default=False, help='Use this if you would like to update your tags. (Only adds tags to untagged torrents)')
parser.add_argument('-ru', '--rem-unregistered', dest='rem_unregistered', action="store_true", default=False, help='Use this if you would like to remove unregistered torrents.')
parser.add_argument('-ro', '--rem-orphaned', dest='rem_orphaned', action="store_true", default=False, help='Use this if you would like to remove unregistered torrents.')
parser.add_argument('-tnhl', '--tag-nohardlinks', dest='tag_nohardlinks', action="store_true", default=False, help='Use this to tag any torrents that do not have any hard links associated with any of the files. This is useful for those that use Sonarr/Radarr which hard link your media files with the torrents for seeding. When files get upgraded they no longer become linked with your media therefore will be tagged with a new tag noHL. You can then safely delete/remove these torrents to free up any extra space that is not being used by your media folder.')
parser.add_argument('-sr', '--skip-recycle', dest='skip_recycle', action="store_true", default=False, help='Use this to skip emptying the Reycle Bin folder.')
parser.add_argument('-dr', '--dry-run', dest='dry_run', action="store_true", default=False, help='If you would like to see what is gonna happen but not actually move/delete or tag/categorize anything.')
parser.add_argument('-ll', '--log-level', dest='log_level', action="store", default='INFO', type=str, help='Change your log level.')
parser.add_argument("-d", "--divider", dest="divider", help="Character that divides the sections (Default: '=')", default="=", type=str)
parser.add_argument("-w", "--width", dest="width", help="Screen Width (Default: 100)", default=100, type=int)
args = parser.parse_args()

def get_arg(env_str, default, arg_bool=False, arg_int=False):
    env_var = os.environ.get(env_str)
    if env_var:
        if arg_bool:
            if env_var is True or env_var is False:
                return env_var
            elif env_var.lower() in ["t", "true"]:
                return True
            else:
                return False
        elif arg_int:
            return int(env_var)
        else:
            return str(env_var)
    else:
        return default

run = get_arg("QBT_RUN", args.run, arg_bool=True)
sch = get_arg("QBT_SCHEDULE", args.min)
config_file = get_arg("QBT_CONFIG", args.configfile)
log_file = get_arg("QBT_LOGFILE", args.logfile)
cross_seed = get_arg("QBT_CROSS_SEED", args.cross_seed, arg_bool=True)
recheck = get_arg("QBT_RECHECK", args.recheck, arg_bool=True)
cat_update = get_arg("QBT_CAT_UPDATE", args.cat_update, arg_bool=True)
tag_update = get_arg("QBT_TAG_UPDATE", args.tag_update, arg_bool=True)
rem_unregistered = get_arg("QBT_REM_UNREGISTERED", args.rem_unregistered, arg_bool=True)
rem_orphaned = get_arg("QBT_REM_ORPHANED", args.rem_orphaned, arg_bool=True)
tag_nohardlinks = get_arg("QBT_TAG_NOHARDLINKS", args.tag_nohardlinks, arg_bool=True)
skip_recycle = get_arg("QBT_SKIP_RECYCLE", args.skip_recycle, arg_bool=True)
dry_run = get_arg("QBT_DRY_RUN", args.dry_run, arg_bool=True)
log_level = get_arg("QBT_LOG_LEVEL", args.log_level)
divider = get_arg("QBT_DIVIDER", args.divider)
screen_width = get_arg("QBT_WIDTH", args.width, arg_int=True)

default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
root_path = '' #Global variable
remote_path = '' #Global variable

util.separating_character = divider[0]

if screen_width < 90 or screen_width > 300:
    print(f"Argument Error: width argument invalid: {screen_width} must be an integer between 90 and 300 using the default 100")
    screen_width = 100
util.screen_width = screen_width


#Check if Schedule parameter is a number
if sch.isnumeric():
    sch = int(sch)
else:
    print(f"Schedule Error: Schedule is not a number. Current value is set to '{sch}'")
    sys.exit(0)

#Config error handling
if not os.path.exists(os.path.join(default_dir, config_file)):
    print(f"Config Error: config not found at {os.path.join(os.path.abspath(default_dir),config_file)}")
    sys.exit(0)

with open(os.path.join(default_dir,config_file), 'r') as cfg_file:
    cfg = yaml.load(cfg_file, Loader=yaml.FullLoader)



#Set root and remote directories
def validate_path():
    global root_path
    global remote_path
    #Assign root_dir
    if 'root_dir' in cfg['directory']:
        root_path = os.path.join(cfg['directory']['root_dir'], '')
    else:
        print('root_dir not defined in config.')
        sys.exit(0)
    #Assign remote_path
    if ('remote_dir' in cfg['directory'] and cfg['directory']['remote_dir'] != ''):
        remote_path = os.path.join(cfg['directory']['remote_dir'], '')
    else:
        remote_path = root_path
    #Check to see if path exists
    if not os.path.exists(remote_path):
        print(f"Config Error: Path does not exist at '{os.path.abspath(remote_path)}'. Is your root_dir/remote_dir correctly defined in the config?")
        sys.exit(0)

#Root_dir/remote_dir error handling
if cross_seed or tag_nohardlinks or rem_orphaned:
   validate_path()
else:
    if 'recyclebin' in cfg and cfg["recyclebin"] != None:
        if 'enabled' in cfg["recyclebin"] and cfg["recyclebin"]['enabled']:
            validate_path()


os.makedirs(os.path.join(default_dir, "logs"), exist_ok=True)
urllib3.disable_warnings()


logger = logging.getLogger('qBit Manage')
logging.DRYRUN = 25
logging.addLevelName(logging.DRYRUN, 'DRY-RUN')
setattr(logger, 'dryrun', lambda dryrun, *args: logger._log(logging.DRYRUN, dryrun, args))
log_lev = getattr(logging, log_level.upper())
logger.setLevel(log_lev)

def fmt_filter(record):
    record.levelname = f"[{record.levelname}]"
    #record.filename = f"[{record.filename}:{record.lineno}]"
    return True

cmd_handler = logging.StreamHandler()
cmd_handler.setLevel(log_level)
logger.addHandler(cmd_handler)

sys.excepthook = util.my_except_hook

version = "Unknown"
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as handle:
    for line in handle.readlines():
        line = line.strip()
        if len(line) > 0:
            version = line
            break


file_logger = os.path.join(default_dir, "logs", log_file)
max_bytes = 1024 * 1024 * 2
file_handler = RotatingFileHandler(file_logger, delay=True, mode="w", maxBytes=max_bytes, backupCount=10, encoding="utf-8")
util.apply_formatter(file_handler)
file_handler.addFilter(fmt_filter)
logger.addHandler(file_handler)

# Actual API call to connect to qbt.
host = cfg['qbt']['host']
if 'user' in cfg['qbt']:
    username = cfg['qbt']['user']
else:
    username = ''
if 'pass' in cfg['qbt']:
    password = cfg['qbt']['pass']
else:
    password = ''

client = Client(host=host, username=username, password=password)
try:
    client.auth_log_in()
except (LoginFailed,APIConnectionError)as e:
    logger.error(e)
    sys.exit(0)

############FUNCTIONS##############
#truncate the value of the torrent url to remove sensitive information
def trunc_val(s, d, n=3):
    return d.join(s.split(d, n)[:n])


#Get category from config file based on path provided
def get_category(path):
    if 'cat' in cfg and cfg["cat"] != None:
        cat_path = cfg["cat"]
        for i, f in cat_path.items():
            if f in path:
                category = i
                return category
    else:
        category = ''
        return category
    category = ''
    logger.warning(f'No categories matched for the save path {path}. Check your config.yml file. - Setting category to NULL')
    return category

#Get tags from config file based on keyword
def get_tags(urls):
    if 'tags' in cfg and cfg["tags"] != None and urls:
        tag_path = cfg['tags']
        for i, f in tag_path.items():
            for url in urls:
                if i in url:
                    tag = f
                    if tag: return tag,trunc_val(url, '/')
    else:
        tag = ('','')
        return tag
    tag = ('','')
    logger.warning(f'No tags matched for {urls}. Check your config.yml file. Setting tag to NULL')
    return tag


#Move files from source to destination, mod variable is to change the date modified of the file being moved
def move_files(src,dest,mod=False):
    dest_path = os.path.dirname(dest)
    if os.path.isdir(dest_path) == False:
        os.makedirs(dest_path)
    shutil.move(src, dest)
    if(mod == True):
        modTime = time.time()
        os.utime(dest,(modTime,modTime))
        

#Remove any empty directories after moving files
def remove_empty_directories(pathlib_root_dir,pattern):
  # list all directories recursively and sort them by path,
  # longest first
  L = sorted(
      pathlib_root_dir.glob(pattern),
      key=lambda p: len(str(p)),
      reverse=True,
  )
  for pdir in L:
    try:
        pdir.rmdir()  # remove directory if empty
    except OSError:
      continue  # catch and continue if non-empty       

# Will create a 2D Dictionary with the torrent name as the key
# torrentdict = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'count':1, 'msg':'[]'...},
#                'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}, 'count':2, 'msg':'[]'...}
# List of dictionary key definitions
# Category = Returns category of the torrent (str)
# save_path = Returns the save path of the torrent (str)
# count = Returns a count of the total number of torrents with the same name (int)
# msg = Returns a list of torrent messages by name (list of str)
# status = Returns the list of status numbers of the torrent by name (0: Tracker is disabled (used for DHT, PeX, and LSD), 1: Tracker has not been contacted yet, 2:Tracker has been contacted and is working, 3:Tracker is updating, 4:Tracker has been contacted, but it is not working (or doesn't send proper replies)
# is_complete = Returns the state of torrent (Returns True if at least one of the torrent with the State is categorized as Complete.)
# first_hash = Returns the hash number of the original torrent (Assuming the torrent list is sorted by date added (Asc))
def get_torrent_info(t_list):
    torrentdict = {}
    for torrent in t_list:
        save_path = torrent.save_path
        category = get_category(save_path)
        is_complete = False
        msg = None
        status = None
        if torrent.name in torrentdict:
            t_count = torrentdict[torrent.name]['count'] + 1
            msg_list = torrentdict[torrent.name]['msg']
            status_list = torrentdict[torrent.name]['status']
            is_complete = True if torrentdict[torrent.name]['is_complete'] == True else torrent.state_enum.is_complete
            first_hash = torrentdict[torrent.name]['first_hash']
        else:
            t_count = 1
            msg_list = []
            status_list = []
            is_complete = torrent.state_enum.is_complete
            first_hash = torrent.hash
        try:
            msg,status = [(x.msg,x.status) for x in torrent.trackers if x.url.startswith('http')][0]
        except IndexError:
            pass
        if msg != None: msg_list.append(msg)
        if status != None: status_list.append(status)
        torrentattr = {'Category': category, 'save_path': save_path, 'count': t_count, 'msg': msg_list, 'status': status_list, 'is_complete': is_complete, 'first_hash':first_hash}
        torrentdict[torrent.name] = torrentattr
    return torrentdict

# Function used to recheck paused torrents sorted by size and resume torrents that are completed 
def set_recheck():
    if recheck:
        util.separator(f"Rechecking Paused Torrents", space=False, border=False)
        #sort by size and paused
        torrent_sorted_list = client.torrents.info(status_filter='paused',sort='size')
        if torrent_sorted_list:
            for torrent in torrent_sorted_list:
                new_tag,t_url = get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                if torrent.tags == '' or ('cross-seed' in torrent.tags and len([e for e in torrent.tags.split(",") if not 'noHL' in e]) == 1): torrent.add_tags(tags=new_tag)
                #Resume torrent if completed
                if torrent.progress == 1:
                    #Check to see if torrent meets AutoTorrentManagement criteria
                    logger.debug(f'Rechecking Torrent to see if torrent meets AutoTorrentManagement Criteria')
                    logger.debug(util.insert_space(f'- Torrent Name: {torrent.name}',2))
                    logger.debug(util.insert_space(f'-- Ratio vs Max Ratio: {torrent.ratio} < {torrent.max_ratio}',4))
                    logger.debug(util.insert_space(f'-- Seeding Time vs Max Seed Time: {timedelta(seconds=torrent.seeding_time)} < {timedelta(minutes=torrent.max_seeding_time)}',4))
                    if torrent.ratio < torrent.max_ratio and (torrent.seeding_time < (torrent.max_seeding_time * 60)):
                        if dry_run:
                            logger.dryrun(f'Not Resuming {new_tag} - {torrent.name}')
                        else:
                            logger.info(f'Resuming {new_tag} - {torrent.name}')
                            torrent.resume()
                #Recheck
                elif torrent.progress == 0 and torrentdict[torrent.name]['is_complete'] and not torrent.state_enum.is_checking:
                    if dry_run:
                        logger.dryrun(f'Not Rechecking {new_tag} - {torrent.name}')
                    else:
                        logger.info(f'Rechecking {new_tag} - {torrent.name}')
                        torrent.recheck()

# Function used to move any torrents from the cross seed directory to the correct save directory
def set_cross_seed():
    if cross_seed:
        util.separator(f"Checking for Cross-Seed Torrents", space=False, border=False)
        # List of categories for all torrents moved
        categories = []
        # Keep track of total torrents moved
        total = 0
        #Track # of torrents tagged that are not cross-seeded
        t_tagged = 0

        if not os.path.exists(os.path.join(cfg['directory']['cross_seed'], '')):
            logger.error(f"Path Error: cross_seed directory not found at {os.path.abspath(os.path.join(cfg['directory']['cross_seed'], ''))}")
            return

        # Only get torrent files
        cs_files = [f for f in os.listdir(os.path.join(cfg['directory']['cross_seed'], '')) if f.endswith('torrent')]
        dir_cs = os.path.join(cfg['directory']['cross_seed'], '')
        dir_cs_out = os.path.join(dir_cs,'qbit_manage_added')
        os.makedirs(dir_cs_out,exist_ok=True)
        for file in cs_files:
            t_name = file.split(']', 2)[2].split('.torrent')[0]
            # Substring Key match in dictionary (used because t_name might not match exactly with torrentdict key)
            # Returned the dictionary of filtered item
            torrentdict_file = dict(filter(lambda item: t_name in item[0], torrentdict.items()))
            if torrentdict_file:
                # Get the exact torrent match name from torrentdict
                t_name = next(iter(torrentdict_file))
                category = torrentdict[t_name]['Category']
                dest = os.path.join(torrentdict[t_name]['save_path'], '')
                src = os.path.join(dir_cs,file)
                dir_cs_out = os.path.join(dir_cs,'qbit_manage_added',file)
                categories.append(category)
                if dry_run:
                    logger.dryrun(f'Not Adding to qBittorrent:')
                    logger.dryrun(util.insert_space(f'Torrent Name: {t_name}',3))
                    logger.dryrun(util.insert_space(f'Category: {category}',7))
                    logger.dryrun(util.insert_space(f'Save_Path: {dest}',6))
                else:
                    if torrentdict[t_name]['is_complete']:
                        client.torrents.add(torrent_files=src,
                                            save_path=dest,
                                            category=category,
                                            tags='cross-seed',
                                            is_paused=True)
                        shutil.move(src, dir_cs_out)
                        logger.info(f'Adding to qBittorrent:')
                        logger.info(util.insert_space(f'Torrent Name: {t_name}',3))
                        logger.info(util.insert_space(f'Category: {category}',7))
                        logger.info(util.insert_space(f'Save_Path: {dest}',6))
                    else:
                        logger.info(f'Found {t_name} in {dir_cs} but original torrent is not complete.')
                        logger.info(f'Not adding to qBittorrent')
            else:
                if dry_run:
                    logger.dryrun(f'{t_name} not found in torrents.')
                else:
                    logger.warning(f'{t_name} not found in torrents.')
        numcategory = Counter(categories)
        #Tag missing cross-seed torrents tags
        for torrent in torrent_list:
            t_name = torrent.name
            if 'cross-seed' not in torrent.tags and torrentdict[t_name]['count'] > 1 and torrentdict[t_name]['first_hash'] != torrent.hash:
                t_tagged += 1
                if dry_run:
                    logger.dryrun(f'Not Adding cross-seed tag to {t_name}')
                else:
                    logger.info(f'Adding cross-seed tag to {t_name}')
                    torrent.add_tags(tags='cross-seed')


        if dry_run:
            for c in numcategory:
                total += numcategory[c]
                if numcategory[c] > 0: logger.dryrun(f'{numcategory[c]} {c} cross-seed .torrents not added.')
            if total > 0: logger.dryrun(f'Total {total} cross-seed .torrents not added.')
            if t_tagged > 0:logger.dryrun(f'Total {t_tagged} cross-seed .torrents not tagged.')
        else:
            for c in numcategory:
                total += numcategory[c]
                if numcategory[c] > 0: logger.info(f'{numcategory[c]} {c} cross-seed .torrents added.')
            if total > 0: logger.info(f'Total {total} cross-seed .torrents added.')
            if t_tagged > 0:logger.info(f'Total {t_tagged} cross-seed .torrents tagged.')

def set_category():
    if cat_update:
        util.separator(f"Updating Categories", space=False, border=False)
        num_cat = 0
        for torrent in torrent_list:
            if torrent.category == '':
                new_cat = get_category(torrent.save_path)
                try:
                    t_url = [trunc_val(x.url, '/') for x in torrent.trackers if x.url.startswith('http')][0]
                except IndexError:
                    t_url = None
                if dry_run:
                    logger.dryrun(util.insert_space(f'Torrent Name: {torrent.name}',3))
                    logger.dryrun(util.insert_space(f'New Category: {new_cat}',3))
                    logger.dryrun(util.insert_space(f'Tracker: {t_url}',8))
                    num_cat += 1
                else:
                    logger.info(util.insert_space(f'- Torrent Name: {torrent.name}',1))
                    logger.info(util.insert_space(f'-- New Category: {new_cat}',5))
                    logger.info(util.insert_space(f'-- Tracker: {t_url}',5))
                    torrent.set_category(category=new_cat)
                    num_cat += 1
        if dry_run:
            if num_cat >= 1:
                logger.dryrun(f'Did not update {num_cat} new categories.')
            else:
                logger.dryrun(f'No new torrents to categorize.')
        else:
            if num_cat >= 1:
                logger.info(f'Updated {num_cat} new categories.')
            else:
                logger.info(f'No new torrents to categorize.')


def set_tags():
    if tag_update:
        util.separator(f"Updating Tags", space=False, border=False)
        num_tags = 0
        for torrent in torrent_list:
            if torrent.tags == '' or ('cross-seed' in torrent.tags and len([e for e in torrent.tags.split(",") if not 'noHL' in e]) == 1):
                new_tag,t_url = get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                if new_tag:
                    if dry_run:
                        logger.dryrun(util.insert_space(f'Torrent Name: {torrent.name}',3))
                        logger.dryrun(util.insert_space(f'New Tag: {new_tag}',8))
                        logger.dryrun(util.insert_space(f'Tracker: {t_url}',8))
                        num_tags += 1
                    else:
                        logger.info(util.insert_space(f'Torrent Name: {torrent.name}',3))
                        logger.info(util.insert_space(f'New Tag: {new_tag}',8))
                        logger.info(util.insert_space(f'Tracker: {t_url}',8))
                        torrent.add_tags(tags=new_tag)
                        num_tags += 1
        if dry_run:
            if num_tags >= 1:
                logger.dryrun(f'Did not update {num_tags} new tags.')
            else:
                logger.dryrun('No new torrents to tag.')
        else:
            if num_tags >= 1:
                logger.info(f'Updated {num_tags} new tags.')
            else:
                logger.info('No new torrents to tag. ')


def set_rem_unregistered():
    if rem_unregistered:
        util.separator(f"Removing Unregistered Torrents", space=False, border=False)
        rem_unr = 0
        del_tor = 0
        pot_unr = ''
        for torrent in torrent_list:
            t_name = torrent.name
            t_count = torrentdict[t_name]['count']
            t_msg = torrentdict[t_name]['msg']
            t_status = torrentdict[t_name]['status']
            for x in torrent.trackers:
                if x.url.startswith('http'):
                    t_url = trunc_val(x.url, '/')
                    msg_up = x.msg.upper()
                    n_info = ''
                    n_d_info = ''

                    n_info += (util.insert_space(f'Torrent Name: {t_name}',3)+'\n')
                    n_info += (util.insert_space(f'Status: {msg_up}',9)+'\n')
                    n_info += (util.insert_space(f'Tracker: {t_url}',8)+'\n')
                    n_info += (util.insert_space(f'Deleted .torrent but NOT content files.',8)+'\n')

                    n_d_info += (util.insert_space(f'Torrent Name: {t_name}',3)+'\n')
                    n_d_info += (util.insert_space(f'Status: {msg_up}',9)+'\n')
                    n_d_info += (util.insert_space(f'Tracker: {t_url}',8)+'\n')
                    n_d_info += (util.insert_space(f'Deleted .torrent AND content files.',8)+'\n')

                    if (x.status == 4 and 'DOWN' not in msg_up and 'UNREACHABLE' not in msg_up):
                        pot_unr += (util.insert_space(f'Torrent Name: {t_name}',3)+'\n')
                        pot_unr += (util.insert_space(f'Status: {msg_up}',9)+'\n')
                    if ('UNREGISTERED' in msg_up or \
                        'TORRENT NOT FOUND' in msg_up or \
                        'TORRENT IS NOT FOUND' in msg_up or \
                        'NOT REGISTERED' in msg_up or \
                        'HTTPS://BEYOND-HD.ME/TORRENTS' in msg_up or \
                        'NOT EXIST' in msg_up or \
                        'UNKNOWN TORRENT' in msg_up or \
                        'REDOWNLOAD' in msg_up or \
                        'PACKS' in msg_up or \
                        'REPACKED' in msg_up or \
                        'PACK' in msg_up or \
                        'TRUMP' in msg_up
                        ) and x.status == 4 and 'DOWN' not in msg_up and 'UNREACHABLE' not in msg_up:
                        if t_count > 1:
                            if dry_run:
                                if '' in t_msg:
                                    util.print_multiline(n_info,"DRYRUN")
                                    rem_unr += 1
                                else:
                                    util.print_multiline(n_d_info,"DRYRUN")
                                    del_tor += 1
                            else:
                                # Checks if any of the original torrents are working
                                if '' in t_msg or 2 in t_status:
                                    util.print_multiline(n_info)
                                    torrent.delete(hash=torrent.hash, delete_files=False)
                                    rem_unr += 1
                                else:
                                    util.print_multiline(n_d_info)
                                    tor_delete_recycle(torrent)
                                    del_tor += 1                                  
                        else:
                            if dry_run:
                                util.print_multiline(n_d_info,"DRYRUN")
                                del_tor += 1
                            else:
                                util.print_multiline(n_d_info)
                                tor_delete_recycle(torrent)
                                del_tor += 1
        if dry_run:
            if rem_unr >= 1 or del_tor >= 1:
                if rem_unr >= 1: logger.dryrun(f'Did not delete {rem_unr} .torrents(s) but not content files.')
                if del_tor >= 1: logger.dryrun(f'Did not delete {del_tor} .torrents(s) AND content files.')
            else:
                logger.dryrun('No unregistered torrents found.')
        else:
            if rem_unr >= 1 or del_tor >= 1:
                if rem_unr >= 1: logger.info(f'Deleted {rem_unr} .torrents(s) but not content files.')
                if del_tor >= 1: logger.info(f'Deleted {del_tor} .torrents(s) AND content files.')   
            else:
                logger.info('No unregistered torrents found.')
        if (len(pot_unr) > 0):
            util.separator(f"Potential Unregistered torrents", space=False, border=False, loglevel='DEBUG')
            util.print_multiline(pot_unr,"DEBUG")

def set_rem_orphaned():
    if rem_orphaned:
        util.separator(f"Checking for Orphaned Files", space=False, border=False)
        global torrent_list
        torrent_files = []
        root_files = []
        orphaned_files = []
        excluded_orphan_files = []
        orphaned_parent_path = set()

        if (remote_path != root_path):
            root_files = [os.path.join(path.replace(remote_path,root_path), name) for path, subdirs, files in os.walk(remote_path) for name in files if os.path.join(remote_path,'orphaned_data') not in path and os.path.join(remote_path,'.RecycleBin') not in path]
        else:
            root_files = [os.path.join(path, name) for path, subdirs, files in os.walk(root_path) for name in files if os.path.join(root_path,'orphaned_data') not in path and os.path.join(root_path,'.RecycleBin') not in path]
        
        #Get an updated list of torrents
        torrent_list = client.torrents.info(sort='added_on')

        for torrent in torrent_list:
            for file in torrent.files:
                torrent_files.append(os.path.join(torrent.save_path,file.name))

        orphaned_files = set(root_files) - set(torrent_files)
        orphaned_files = sorted(orphaned_files)

        if 'orphaned' in cfg and cfg["orphaned"] is not None and 'exclude_patterns' in cfg['orphaned'] and cfg['orphaned']['exclude_patterns'] != '':
            exclude_patterns = cfg['orphaned']['exclude_patterns']
            excluded_orphan_files = [file for file in orphaned_files for exclude_pattern in exclude_patterns if fnmatch.fnmatch(file, exclude_pattern.replace(remote_path,root_path))]

        orphaned_files = set(orphaned_files) - set(excluded_orphan_files)
        util.separator(f"Torrent Files", space=False, border=False, loglevel='DEBUG')
        util.print_multiline("\n".join(torrent_files),'DEBUG')
        util.separator(f"Root Files", space=False, border=False,loglevel='DEBUG')
        util.print_multiline("\n".join(root_files),'DEBUG')
        util.separator(f"Excluded Orphan Files", space=False, border=False,loglevel='DEBUG')
        util.print_multiline("\n".join(excluded_orphan_files),'DEBUG')
        util.separator(f"Orphaned Files", space=False, border=False,loglevel='DEBUG')
        util.print_multiline("\n".join(orphaned_files),'DEBUG')
        util.separator(f"Deleting Orphaned Files", space=False, border=False,loglevel='DEBUG')

        if (orphaned_files):
            if dry_run:
                dir_out = os.path.join(remote_path,'orphaned_data')
                util.separator(f"{len(orphaned_files)} Orphaned files found", space=False, border=False,loglevel='DRYRUN')
                util.print_multiline("\n".join(orphaned_files),'DRYRUN')
                logger.dryrun(f'Did not move {len(orphaned_files)} Orphaned files to {dir_out.replace(remote_path,root_path)}')
            else:
                dir_out = os.path.join(remote_path,'orphaned_data')
                os.makedirs(dir_out,exist_ok=True)

                for file in orphaned_files:
                    src = file.replace(root_path,remote_path)
                    dest = os.path.join(dir_out,file.replace(root_path,''))
                    move_files(src,dest)
                    orphaned_parent_path.add(os.path.dirname(file).replace(root_path,remote_path))
                util.separator(f"{len(orphaned_files)} Orphaned files found", space=False, border=False)
                util.print_multiline("\n".join(orphaned_files))
                logger.info(f'Moved {len(orphaned_files)} Orphaned files to {dir_out.replace(remote_path,root_path)}')
                #Delete empty directories after moving orphan files
                logger.info(f'Cleaning up any empty directories...')
                for parent_path in orphaned_parent_path:
                    remove_empty_directories(Path(parent_path),"**/*")
        else:
            if dry_run:
                logger.dryrun('No Orphaned Files found.')
            else:
                logger.info('No Orphaned Files found.')


def set_tag_nohardlinks():
    if tag_nohardlinks:
        util.separator(f"Tagging Torrents with No Hardlinks", space=False, border=False)
        nohardlinks = cfg['nohardlinks']
        n_info = ''
        t_count = 0 #counter for the number of torrents that has no hard links
        t_del = 0 #counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion
        t_del_cs = 0 #counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion including cross-seeds
        tdel_tags = 0 #counter for number of torrents that previously had no hard links but now have hard links
        tdel_dict = {} #dictionary to track the torrent names and content path that meet the deletion criteria
        t_excl_tags = []#list of tags to exclude based on config.yml

        for category in nohardlinks:
            torrent_list = client.torrents.info(category=category,filter='completed')
            #Convert string to list if only one tag defined.
            if ('exclude_tags' in nohardlinks[category]):
                if isinstance(nohardlinks[category]['exclude_tags'],str):
                    t_excl_tags.append(nohardlinks[category]['exclude_tags'])
                else:
                    t_excl_tags = nohardlinks[category]['exclude_tags']

            if len(torrent_list) == 0:
                logger.error('No torrents found in the category ('+category+') defined in config.yml inside the nohardlinks section. Please check if this matches with any category in qbittorrent and has 1 or more torrents.')
                continue
            for torrent in torrent_list:
                if not dry_run:
                    torrent.resume()    
                if('exclude_tags' in nohardlinks[category] and (any(tag in torrent.tags for tag in t_excl_tags))):
                    #Skip to the next torrent if we find any torrents that are in the exclude tag
                    continue
                else:
                    #Checks for any hard links and not already tagged
                    if (nohardlink(torrent['content_path'].replace(root_path,remote_path))):
                        #Will only tag new torrents that don't have noHL tag
                        if('noHL' not in torrent.tags):
                            t_count += 1
                            n_info += (f"No hard links found! Adding tags noHL\n")
                            n_info += (util.insert_space(f'Torrent Name: {torrent.name}',3)+'\n')

                            if(nohardlinks[category] != None):
                                #set the max seeding time for the torrent
                                if ('max_seeding_time' in nohardlinks[category]):
                                    seeding_time_limit = nohardlinks[category]['max_seeding_time']
                                    n_info += (util.insert_space(f'New Max Seed Time: {str(seeding_time_limit)}',3)+'\n')
                                else:
                                    seeding_time_limit = -2
                                #set the max ratio for the torrent
                                if ('max_ratio' in nohardlinks[category]):
                                    ratio_limit = nohardlinks[category]['max_ratio']
                                    n_info += (util.insert_space(f'New Max Ratio: {str(ratio_limit)}',3)+'\n')
                                else:
                                    ratio_limit = -2
                            else:
                                seeding_time_limit = -2
                                ratio_limit = -2
                            if not dry_run:
                                #set the tag for no hard links
                                torrent.add_tags(tags='noHL')
                                client.torrents_set_share_limits(ratio_limit,seeding_time_limit,torrent.hash)

                        #Cleans up previously tagged noHL torrents
                        else:
                            if(nohardlinks[category] != None):
                                # Deletes torrent with data if cleanup is set to true and meets the ratio/seeding requirements
                                if ('cleanup' in nohardlinks[category] and nohardlinks[category]['cleanup'] and torrent.state_enum.is_paused and len(nohardlinks[category])>0):
                                    t_del += 1
                                    n_info += (f'Torrent Name: {torrent.name} has no hard links found and meets ratio/seeding requirements.\n')
                                    tdel_dict[torrent.name] = torrent['content_path'].replace(root_path,remote_path)
                                    if dry_run:
                                        n_info += (util.insert_space(f'Cleanup flag set to true. NOT Deleting torrent + contents.',6)+'\n')
                                    else:
                                        n_info += (util.insert_space(f'Cleanup flag set to true. Deleting torrent + contents.',6)+'\n')
                
                #Checks to see if previous noHL tagged torrents now have hard links.
                if (not (nohardlink(torrent['content_path'].replace(root_path,remote_path))) and ('noHL' in torrent.tags)):
                    n_info += (f'Previous Tagged noHL Torrent Name: {torrent.name} has hard links found now.\n')
                    n_info += ('Removing tags noHL.\n')
                    n_info += ('Removing ratio and seeding time limits.\n')
                    tdel_tags += 1
                    if not dry_run:
                        #Remove tags and share limits
                        torrent.remove_tags(tags='noHL')
                        client.torrents_set_share_limits(-2,-2,torrent.hash)
                        
            if(nohardlinks[category] != None):
                #loop through torrent list again for cleanup purposes
                if ('cleanup' in nohardlinks[category] and nohardlinks[category]['cleanup']):
                    for torrent in torrent_list:
                        if torrent.name in tdel_dict.keys() and 'noHL' in torrent.tags:
                            #Double check that the content path is the same before we delete anything
                            if torrent['content_path'].replace(root_path,remote_path) == tdel_dict[torrent.name]:
                                t_del_cs += 1
                                if not dry_run:
                                    if (os.path.exists(torrent['content_path'].replace(root_path,remote_path))):
                                        tor_delete_recycle(torrent)
                                    else:
                                        torrent.delete(hash=torrent.hash, delete_files=False)

        if dry_run:
            if t_count >= 1 or len(n_info) > 1:
                util.print_multiline(n_info,"DRYRUN")
                logger.dryrun(f'Did not tag/set ratio limit/seeding time for  {t_count} .torrents(s)')
                if t_del >= 1:
                    logger.dryrun(f'Did not delete {t_del} .torrents(s) or content files.')
                    logger.dryrun(f'Did not delete {t_del_cs} .torrents(s) (including cross-seed) or content files.')
                if tdel_tags >= 1:
                    logger.dryrun(f'Did not delete noHL tags/ remove ratio limit/seeding time for  {tdel_tags} .torrents(s)')
            else:
                logger.dryrun('No torrents to tag with no hard links.')
        else:
            if t_count >= 1 or len(n_info) > 1:
                util.print_multiline(n_info)
                logger.info(f'tag/set ratio limit/seeding time for  {t_count} .torrents(s)')
                if t_del >= 1:
                    logger.info(f'Deleted {t_del} .torrents(s) AND content files.')
                    logger.info(f'Deleted {t_del_cs} .torrents(s) (includes cross-seed torrents) AND content files.')
                if tdel_tags >= 1:
                    logger.info(f'Deleted noHL tags/ remove ratio limit/seeding time for  {tdel_tags} .torrents(s)')
            else:
                logger.info('No torrents to tag with no hard links.')


#will check if there are any hard links if it passes a file or folder
def nohardlink(file):
    check = True
    if (os.path.isfile(file)):
        if (os.stat(file).st_nlink > 1):
            check = False
    else:
        for path, subdirs, files in os.walk(file):
            for x in files:
                if (os.stat(os.path.join(path,x)).st_nlink > 1):
                    check = False
    return check

def tor_delete_recycle(torrent):
    if 'recyclebin' in cfg and cfg["recyclebin"] != None:
        if 'enabled' in cfg["recyclebin"] and cfg["recyclebin"]['enabled']:
            tor_files = []
            #Define torrent files/folders
            for file in torrent.files:
                tor_files.append(os.path.join(torrent.save_path,file.name))

            #Create recycle bin if not exists
            recycle_path = os.path.join(remote_path,'.RecycleBin')
            os.makedirs(recycle_path,exist_ok=True)

            #Move files from torrent contents to Recycle bin
            for file in tor_files:
                src = file.replace(root_path,remote_path)
                dest = os.path.join(recycle_path,file.replace(root_path,''))
                #move files and change date modified
                move_files(src,dest,True)
                util.separator(f"Moving {len(tor_files)} files to RecycleBin", space=False, border=False,loglevel='DEBUG')
                util.print_multiline("\n".join(tor_files),'DEBUG')
                logger.debug(f'Moved {len(tor_files)} files to {recycle_path.replace(remote_path,root_path)}')
            #Delete torrent and files
            torrent.delete(hash=torrent.hash, delete_files=False)
            #Remove any empty directories
            remove_empty_directories(Path(torrent.save_path.replace(root_path,remote_path)),"**/*")
        else:
            torrent.delete(hash=torrent.hash, delete_files=True)
    else:
        logger.error('recyclebin not defined in config.')
        return
                


def set_empty_recycle():
    if not skip_recycle:
        num_del = 0
        n_info = ''
        if 'recyclebin' in cfg and cfg["recyclebin"] != None:
            if 'enabled' in cfg["recyclebin"] and cfg["recyclebin"]['enabled'] and 'empty_after_x_days' in cfg["recyclebin"]:
                if 'root_dir' in cfg['directory']:
                    root_path = os.path.join(cfg['directory']['root_dir'], '')
                else:
                    logger.error('root_dir not defined in config. This is required to use recyclebin feature')
                    return
                
                if ('remote_dir' in cfg['directory'] and cfg['directory']['remote_dir'] != ''):
                    remote_path = os.path.join(cfg['directory']['remote_dir'], '')
                    recycle_path = os.path.join(remote_path,'.RecycleBin')
                else:
                    remote_path = root_path
                    recycle_path = os.path.join(root_path,'.RecycleBin')
                recycle_files = [os.path.join(path, name) for path, subdirs, files in os.walk(recycle_path) for name in files]
                recycle_files = sorted(recycle_files)
                empty_after_x_days = cfg["recyclebin"]['empty_after_x_days']
                if recycle_files:
                    util.separator(f"Emptying Recycle Bin (Files > {empty_after_x_days} days)", space=False, border=False)
                    for file in recycle_files:
                        fileStats = os.stat(file)
                        filename = file.replace(recycle_path,'')
                        last_modified = fileStats[stat.ST_MTIME] # in seconds (last modified time)
                        now = time.time() # in seconds
                        days = (now - last_modified) / (60 * 60 * 24)
                        if (empty_after_x_days <= days):
                            num_del += 1
                            if dry_run:
                                n_info += (f'Did not delete {filename} from the recycle bin. (Last modified {round(days)} days ago).\n')
                            else:
                                n_info += (f'Deleted {filename} from the recycle bin. (Last modified {round(days)} days ago).\n')
                                os.remove(file)
                    if num_del > 0:
                        if dry_run:
                            util.print_multiline(n_info,'DRYRUN')
                            logger.dryrun(f'Did not delete {num_del} files from the Recycle Bin.')
                        else:
                            remove_empty_directories(Path(recycle_path),"**/*")
                            util.print_multiline(n_info)
                            logger.info(f'Deleted {num_del} files from the Recycle Bin.') 
                else:
                    logger.debug('No files found in "' + recycle_path + '"')
            else:
                logger.debug('Recycle bin has been disabled or "empty_after_x_days" var not defined in config.')

        else:
            logger.error('recyclebin not defined in config.')
            return


#Define global parameters
torrent_list = None
torrentdict = None


def start():
    #Global parameters to get the torrent dictionary
    global torrent_list
    global torrentdict
    start_time = datetime.now()
    if dry_run:
        start_type = "Dry-"
    else:
        start_type = ""
    util.separator(f"Starting {start_type}Run")
    util.separator(f"Getting Torrent List", space=False, border=False)
    #Get an updated list of torrents
    torrent_list = client.torrents.info(sort='added_on')
    if recheck or cross_seed or rem_unregistered:
        #Get an updated torrent dictionary information of the torrents
        torrentdict = get_torrent_info(torrent_list)
    set_category()
    set_tags()
    set_rem_unregistered()
    set_cross_seed()
    set_recheck()
    set_rem_orphaned()
    set_tag_nohardlinks()
    set_empty_recycle()
    end_time = datetime.now()
    run_time = str(end_time - start_time).split('.')[0]
    util.separator(f"Finished {start_type}Run\nRun Time: {run_time}")

def end():
    logger.info("Exiting Qbit_manage")
    logger.removeHandler(file_handler)
    sys.exit(0)

if __name__ == '__main__':
    killer = GracefulKiller()
    util.separator()
    logger.info(util.centered("        _     _ _                                            "))
    logger.info(util.centered("       | |   (_) |                                           "))
    logger.info(util.centered("   __ _| |__  _| |_   _ __ ___   __ _ _ __   __ _  __ _  ___ "))
    logger.info(util.centered("  / _` | '_ \| | __| | '_ ` _ \ / _` | '_ \ / _` |/ _` |/ _ \\"))
    logger.info(util.centered(" | (_| | |_) | | |_  | | | | | | (_| | | | | (_| | (_| |  __/"))
    logger.info(util.centered("  \__, |_.__/|_|\__| |_| |_| |_|\__,_|_| |_|\__,_|\__, |\___|"))
    logger.info(util.centered("     | |         ______                            __/ |     "))
    logger.info(util.centered("     |_|        |______|                          |___/      "))
    logger.info(f"    Version: {version}")
    try:
        if run:
            logger.info(f"    Run Mode: Script will exit after completion.")
            start()
        else:
            schedule.every(sch).minutes.do(start)
            logger.info(f"    Scheduled Mode: Running every {sch} minutes.")
            start()
            while not killer.kill_now:
                schedule.run_pending()
                time.sleep(1)
            end()
    except KeyboardInterrupt:
        end()