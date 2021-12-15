#!/usr/bin/python3

import argparse, logging, os, sys, time
from logging.handlers import RotatingFileHandler
from datetime import datetime

try:
    import schedule
    from modules import util
    from modules.config import Config
    from modules.util import GracefulKiller
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
parser.add_argument('-tu', '--tag-update', dest='tag_update', action="store_true", default=False, help='Use this if you would like to update your tags and/or set seed goals/limit upload speed by tag. (Only adds tags to untagged torrents)')
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
stats = {}
args = {}

if os.path.isdir('/config'):
    default_dir = '/config'
else:
    default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

for v in ['run','sch','config_file','log_file','cross_seed','recheck','cat_update','tag_update','rem_unregistered','rem_orphaned','tag_nohardlinks','skip_recycle','dry_run','log_level','divider','screen_width']:
    args[v] = eval(v)

util.separating_character = divider[0]

if screen_width < 90 or screen_width > 300:
    print(f"Argument Error: width argument invalid: {screen_width} must be an integer between 90 and 300 using the default 100")
    screen_width = 100
util.screen_width = screen_width

#Check if Schedule parameter is a number
try:
    sch = int(sch)
except ValueError:
    print(f"Schedule Error: Schedule is not a number. Current value is set to '{sch}'")
    sys.exit(0)

os.makedirs(os.path.join(default_dir, "logs"), exist_ok=True)

logger = logging.getLogger('qBit Manage')
logging.DRYRUN = 25
logging.addLevelName(logging.DRYRUN, 'DRYRUN')
setattr(logger, 'dryrun', lambda dryrun, *args: logger._log(logging.DRYRUN, dryrun, args))
log_lev = getattr(logging, log_level.upper())
logger.setLevel(log_lev)

def fmt_filter(record):
    record.levelname = f"[{record.levelname}]"
    record.filename = f"[{record.filename}:{record.lineno}]"
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

log_path = os.path.join(default_dir, "logs")
file_logger = os.path.join(log_path, log_file)
max_bytes = 1024 * 1024 * 2
file_handler = RotatingFileHandler(file_logger, delay=True, mode="w", maxBytes=max_bytes, backupCount=10, encoding="utf-8")
util.apply_formatter(file_handler)
file_handler.addFilter(fmt_filter)
logger.addHandler(file_handler)
os.chmod(log_path, 0o777)

def start():
    start_time = datetime.now()
    args["time"] = start_time.strftime("%H:%M")
    args["time_obj"] = start_time
    stats_summary = []
    if dry_run:
        start_type = "Dry-"
    else:
        start_type = ""
    util.separator(f"Starting {start_type}Run")
    cfg = None
    global stats
    stats = { 
        "added": 0,
        "deleted": 0,
        "deleted_contents": 0,
        "resumed": 0,
        "rechecked": 0,
        "orphaned":0,
        "recycle_emptied": 0,
        "tagged": 0,
        "untagged":0,
        "categorized": 0,
        "rem_unreg": 0,
        "taggednoHL": 0
    }
    try:
        cfg = Config(default_dir,args)
    except Exception as e:
        util.print_stacktrace()
        util.print_multiline(e,'CRITICAL')
    
    if cfg:
        #Set Category
        num_categorized = cfg.qbt.category()
        stats["categorized"] += num_categorized

        #Set Tags
        num_tagged = cfg.qbt.tags()
        stats["tagged"] += num_tagged
        
        #Remove Unregistered Torrents
        num_deleted,num_deleted_contents = cfg.qbt.rem_unregistered()
        stats["rem_unreg"] += (num_deleted + num_deleted_contents)
        stats["deleted"] += num_deleted
        stats["deleted_contents"] += num_deleted_contents

        #Set Cross Seed
        num_added, num_tagged = cfg.qbt.cross_seed()
        stats["added"] += num_added
        stats["tagged"] += num_tagged

        #Recheck Torrents
        num_resumed, num_rechecked = cfg.qbt.recheck()
        stats["resumed"] += num_resumed
        stats["rechecked"] += num_rechecked

        #Tag NoHardLinks
        num_tagged,num_untagged,num_deleted,num_deleted_contents = cfg.qbt.tag_nohardlinks()
        stats["tagged"] += num_tagged
        stats["taggednoHL"] += num_tagged
        stats["untagged"] += num_untagged
        stats["deleted"] += num_deleted
        stats["deleted_contents"] += num_deleted_contents

        #Remove Orphaned Files
        num_orphaned = cfg.qbt.rem_orphaned()
        stats["orphaned"] += num_orphaned

        #Empty RecycleBin
        recycle_emptied = cfg.empty_recycle()
        stats["recycle_emptied"] += recycle_emptied

    if stats["categorized"] > 0:                stats_summary.append(f"Total Torrents Categorized: {stats['categorized']}")
    if stats["tagged"] > 0:                     stats_summary.append(f"Total Torrents Tagged: {stats['tagged']}")
    if stats["rem_unreg"] > 0:                  stats_summary.append(f"Total Unregistered Torrents Removed: {stats['rem_unreg']}")
    if stats["added"] > 0:                      stats_summary.append(f"Total Torrents Added: {stats['added']}")
    if stats["resumed"] > 0:                    stats_summary.append(f"Total Torrents Resumed: {stats['resumed']}")
    if stats["rechecked"] > 0:                  stats_summary.append(f"Total Torrents Rechecked: {stats['rechecked']}")
    if stats["deleted"] > 0:                    stats_summary.append(f"Total Torrents Deleted: {stats['deleted']}")
    if stats["deleted_contents"] > 0:           stats_summary.append(f"Total Torrents + Contents Deleted : {stats['deleted_contents']}")
    if stats["orphaned"] > 0:                   stats_summary.append(f"Total Orphaned Files: {stats['orphaned']}")
    if stats["taggednoHL"] > 0:                 stats_summary.append(f"Total noHL Torrents Tagged: {stats['taggednoHL']}")
    if stats["untagged"] > 0:                   stats_summary.append(f"Total noHL Torrents untagged: {stats['untagged']}")
    if stats["recycle_emptied"] > 0:            stats_summary.append(f"Total Files Deleted from Recycle Bin: {stats['recycle_emptied']}")

    end_time = datetime.now()
    run_time = str(end_time - start_time).split('.')[0]
    util.separator(f"Finished {start_type}Run\n {os.linesep.join(stats_summary) if len(stats_summary)>0 else ''} \nRun Time: {run_time}")

def end():
    logger.info("Exiting Qbit_manage")
    os.chmod(file_logger, 0o777)
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

    util.separator(loglevel='DEBUG')
    logger.debug(f"    --run (QBT_RUN): {run}")
    logger.debug(f"    --schedule (QBT_SCHEDULE): {sch}")
    logger.debug(f"    --config-file (QBT_CONFIG): {config_file}")
    logger.debug(f"    --log-file (QBT_LOGFILE): {log_file}")
    logger.debug(f"    --cross-seed (QBT_CROSS_SEED): {cross_seed}")
    logger.debug(f"    --recheck (QBT_RECHECK): {recheck}")
    logger.debug(f"    --cat-update (QBT_CAT_UPDATE): {cat_update}")
    logger.debug(f"    --tag-update (QBT_TAG_UPDATE): {tag_update}")
    logger.debug(f"    --rem-unregistered (QBT_REM_UNREGISTERED): {rem_unregistered}")
    logger.debug(f"    --rem-orphaned (QBT_REM_ORPHANED): {rem_orphaned}")
    logger.debug(f"    --tag-nohardlinks (QBT_TAG_NOHARDLINKS): {tag_nohardlinks}")
    logger.debug(f"    --skip-recycle (QBT_SKIP_RECYCLE): {skip_recycle}")
    logger.debug(f"    --dry-run (QBT_DRY_RUN): {dry_run}")
    logger.debug(f"    --log-level (QBT_LOG_LEVEL): {log_level}")
    logger.debug(f"    --divider (QBT_DIVIDER): {divider}")
    logger.debug(f"    --width (QBT_WIDTH): {screen_width}")
    logger.debug("")

    os.chmod(file_logger, 0o777)
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
