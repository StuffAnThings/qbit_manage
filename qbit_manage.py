#!/usr/bin/python3
"""qBittorrent Manager."""
import argparse
import glob
import os
import sys
import time
from datetime import datetime
from datetime import timedelta

try:
    import schedule
    from modules.logs import MyLogger
except ModuleNotFoundError:
    print("Requirements Error: Requirements are not installed")
    sys.exit(0)

REQUIRED_VERSION = (3, 8, 1)
REQUIRED_VERSION_STR = ".".join(str(x) for x in REQUIRED_VERSION)
current_version = sys.version_info

if current_version < (REQUIRED_VERSION):
    print(
        "Version Error: Version: %s.%s.%s incompatible with qbit_manage please use Python %s+"
        % (current_version[0], current_version[1], current_version[2], REQUIRED_VERSION_STR)
    )
    sys.exit(0)

parser = argparse.ArgumentParser("qBittorrent Manager.", description="A mix of scripts combined for managing qBittorrent.")
parser.add_argument("-db", "--debug", dest="debug", help=argparse.SUPPRESS, action="store_true", default=False)
parser.add_argument("-tr", "--trace", dest="trace", help=argparse.SUPPRESS, action="store_true", default=False)
parser.add_argument(
    "-r",
    "--run",
    dest="run",
    action="store_true",
    default=False,
    help="Run without the scheduler. Script will exit after completion.",
)
parser.add_argument(
    "-sch",
    "--schedule",
    dest="min",
    default="1440",
    type=str,
    help="Schedule to run every x minutes. (Default set to 1440 (1 day))",
)
parser.add_argument(
    "-sd",
    "--startup-delay",
    dest="startupDelay",
    default="0",
    type=str,
    help="Set delay in seconds on the first run of a schedule (Default set to 0)",
)
parser.add_argument(
    "-c",
    "--config-file",
    dest="configfiles",
    action="store",
    default="config.yml",
    type=str,
    help="This is used if you want to use a different name for your config.yml or if you want to load multiple"
    "config files using *. Example: tv.yml or config*.yml",
)
parser.add_argument(
    "-lf",
    "--log-file",
    dest="logfile",
    action="store",
    default="qbit_manage.log",
    type=str,
    help="This is used if you want to use a different name for your log file. Example: tv.log",
)
parser.add_argument(
    "-cs",
    "--cross-seed",
    dest="cross_seed",
    action="store_true",
    default=False,
    help="Use this after running cross-seed script to add torrents from the cross-seed output folder to qBittorrent",
)
parser.add_argument(
    "-re",
    "--recheck",
    dest="recheck",
    action="store_true",
    default=False,
    help="Recheck paused torrents sorted by lowest size. Resume if Completed.",
)
parser.add_argument(
    "-cu",
    "--cat-update",
    dest="cat_update",
    action="store_true",
    default=False,
    help="Use this if you would like to update your categories.",
)
parser.add_argument(
    "-tu",
    "--tag-update",
    dest="tag_update",
    action="store_true",
    default=False,
    help="Use this if you would like to update your tags and/or set seed goals/limit upload speed by tag."
    " (Only adds tags to untagged torrents)",
)
parser.add_argument(
    "-ru",
    "--rem-unregistered",
    dest="rem_unregistered",
    action="store_true",
    default=False,
    help="Use this if you would like to remove unregistered torrents.",
)
parser.add_argument(
    "-tte",
    "--tag-tracker-error",
    dest="tag_tracker_error",
    action="store_true",
    default=False,
    help="Use this if you would like to tag torrents that do not have a working tracker.",
)
parser.add_argument(
    "-ro",
    "--rem-orphaned",
    dest="rem_orphaned",
    action="store_true",
    default=False,
    help="Use this if you would like to remove unregistered torrents.",
)
parser.add_argument(
    "-tnhl",
    "--tag-nohardlinks",
    dest="tag_nohardlinks",
    action="store_true",
    default=False,
    help="Use this to tag any torrents that do not have any hard links associated with any of the files. "
    "This is useful for those that use Sonarr/Radarr which hard link your media files with the torrents for seeding. "
    "When files get upgraded they no longer become linked with your media therefore will be tagged with a new tag noHL. "
    "You can then safely delete/remove these torrents to free up any extra space that is not being used by your media folder.",
)
parser.add_argument(
    "-sc",
    "--skip-cleanup",
    dest="skip_cleanup",
    action="store_true",
    default=False,
    help="Use this to skip cleaning up Recycle Bin/Orphaned directory.",
)
parser.add_argument(
    "-dr",
    "--dry-run",
    dest="dry_run",
    action="store_true",
    default=False,
    help="If you would like to see what is gonna happen but not actually move/delete or tag/categorize anything.",
)
parser.add_argument(
    "-ll", "--log-level", dest="log_level", action="store", default="INFO", type=str, help="Change your log level."
)
parser.add_argument(
    "-d", "--divider", dest="divider", help="Character that divides the sections (Default: '=')", default="=", type=str
)
parser.add_argument("-w", "--width", dest="width", help="Screen Width (Default: 100)", default=100, type=int)
args = parser.parse_args()


def get_arg(env_str, default, arg_bool=False, arg_int=False):
    """Get argument from environment variable or command line argument."""
    env_vars = [env_str] if not isinstance(env_str, list) else env_str
    final_value = None
    for env_var in env_vars:
        env_value = os.environ.get(env_var)
        if env_value is not None:
            final_value = env_value
            break
    if final_value is not None:
        if arg_bool:
            if final_value is True or final_value is False:
                return final_value
            elif final_value.lower() in ["t", "true"]:
                return True
            else:
                return False
        elif arg_int:
            return int(final_value)
        else:
            return str(final_value)
    else:
        return default


run = get_arg("QBT_RUN", args.run, arg_bool=True)
sch = get_arg("QBT_SCHEDULE", args.min)
startupDelay = get_arg("QBT_STARTUP_DELAY", args.startupDelay)
config_files = get_arg("QBT_CONFIG", args.configfiles)
log_file = get_arg("QBT_LOGFILE", args.logfile)
cross_seed = get_arg("QBT_CROSS_SEED", args.cross_seed, arg_bool=True)
recheck = get_arg("QBT_RECHECK", args.recheck, arg_bool=True)
cat_update = get_arg("QBT_CAT_UPDATE", args.cat_update, arg_bool=True)
tag_update = get_arg("QBT_TAG_UPDATE", args.tag_update, arg_bool=True)
rem_unregistered = get_arg("QBT_REM_UNREGISTERED", args.rem_unregistered, arg_bool=True)
tag_tracker_error = get_arg("QBT_TAG_TRACKER_ERROR", args.tag_tracker_error, arg_bool=True)
rem_orphaned = get_arg("QBT_REM_ORPHANED", args.rem_orphaned, arg_bool=True)
tag_nohardlinks = get_arg("QBT_TAG_NOHARDLINKS", args.tag_nohardlinks, arg_bool=True)
skip_cleanup = get_arg("QBT_SKIP_CLEANUP", args.skip_cleanup, arg_bool=True)
dry_run = get_arg("QBT_DRY_RUN", args.dry_run, arg_bool=True)
log_level = get_arg("QBT_LOG_LEVEL", args.log_level)
divider = get_arg("QBT_DIVIDER", args.divider)
screen_width = get_arg("QBT_WIDTH", args.width, arg_int=True)
debug = get_arg("QBT_DEBUG", args.debug, arg_bool=True)
trace = get_arg("QBT_TRACE", args.trace, arg_bool=True)

if debug:
    log_level = "DEBUG"
if trace:
    log_level = "TRACE"

stats = {}
args = {}

if os.path.isdir("/config") and glob.glob(os.path.join("/config", config_files)):
    default_dir = "/config"
else:
    default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")


if "*" not in config_files:
    config_files = [config_files]
else:
    glob_configs = glob.glob(os.path.join(default_dir, config_files))
    if glob_configs:
        config_files = [os.path.split(x)[-1] for x in glob_configs]
    else:
        print(f"Config Error: Unable to find any config files in the pattern '{config_files}'.")
        sys.exit(0)


for v in [
    "run",
    "sch",
    "startupDelay",
    "config_files",
    "log_file",
    "cross_seed",
    "recheck",
    "cat_update",
    "tag_update",
    "rem_unregistered",
    "tag_tracker_error",
    "rem_orphaned",
    "tag_nohardlinks",
    "skip_cleanup",
    "dry_run",
    "log_level",
    "divider",
    "screen_width",
    "debug",
    "trace",
]:
    args[v] = eval(v)

if screen_width < 90 or screen_width > 300:
    print(f"Argument Error: width argument invalid: {screen_width} must be an integer between 90 and 300 using the default 100")
    screen_width = 100

# Check if Schedule parameter is a number
try:
    sch = int(sch)
except ValueError:
    print(f"Schedule Error: Schedule is not a number. Current value is set to '{sch}'")
    sys.exit(0)

# Check if StartupDelay parameter is a number
try:
    startupDelay = int(startupDelay)
except ValueError:
    print(f"startupDelay Error: startupDelay is not a number. Current value is set to '{startupDelay}'")
    sys.exit(0)


logger = MyLogger("qBit Manage", log_file, log_level, default_dir, screen_width, divider[0], False)
from modules import util  # noqa

util.logger = logger
from modules.config import Config  # noqa
from modules.util import GracefulKiller  # noqa
from modules.util import Failed  # noqa


def my_except_hook(exctype, value, tbi):
    """Handle uncaught exceptions"""
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tbi)
    else:
        logger.critical("Uncaught Exception", exc_info=(exctype, value, tbi))


sys.excepthook = my_except_hook

version = "Unknown"
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as handle:
    for line in handle.readlines():
        line = line.strip()
        if len(line) > 0:
            version = line
            break


def start_loop():
    """Start the main loop"""
    if len(config_files) == 1:
        args["config_file"] = config_files[0]
        start()
    else:
        for config_file in config_files:
            args["config_file"] = config_file
            config_base = os.path.splitext(config_file)[0]
            logger.add_config_handler(config_base)
            start()
            logger.remove_config_handler(config_base)


def start():
    """Start the run"""
    start_time = datetime.now()
    args["time"] = start_time.strftime("%H:%M")
    args["time_obj"] = start_time
    stats_summary = []
    logger.separator("Starting Run")
    cfg = None
    body = ""
    run_time = ""
    end_time = None
    next_run = None
    global stats
    stats = {
        "added": 0,
        "deleted": 0,
        "deleted_contents": 0,
        "resumed": 0,
        "rechecked": 0,
        "orphaned": 0,
        "recycle_emptied": 0,
        "orphaned_emptied": 0,
        "tagged": 0,
        "categorized": 0,
        "rem_unreg": 0,
        "tagged_tracker_error": 0,
        "untagged_tracker_error": 0,
        "tagged_noHL": 0,
        "untagged_noHL": 0,
    }

    def finished_run():
        """Handle the end of a run"""
        nonlocal end_time, start_time, stats_summary, run_time, next_run, body
        end_time = datetime.now()
        run_time = str(end_time - start_time).split(".", maxsplit=1)[0]
        _, nxt_run = calc_next_run(sch, True)
        next_run_str = nxt_run["next_run_str"]
        next_run = nxt_run["next_run"]
        body = logger.separator(
            f"Finished Run\n{os.linesep.join(stats_summary) if len(stats_summary)>0 else ''}"
            f"\nRun Time: {run_time}\n{next_run_str if len(next_run_str)>0 else ''}".replace("\n\n", "\n").rstrip()
        )[0]
        return next_run, body

    try:
        cfg = Config(default_dir, args)
    except Exception as ex:
        if "Qbittorrent Error" in ex.args[0]:
            logger.print_line(ex, "CRITICAL")
            logger.print_line("Exiting scheduled Run.", "CRITICAL")
            finished_run()
            return None
        else:
            logger.stacktrace()
            logger.print_line(ex, "CRITICAL")

    if cfg:
        # Set Category
        num_categorized = cfg.qbt.category()
        stats["categorized"] += num_categorized

        # Set Tags
        num_tagged = cfg.qbt.tags()
        stats["tagged"] += num_tagged

        # Remove Unregistered Torrents
        num_deleted, num_deleted_contents, num_tagged, num_untagged = cfg.qbt.rem_unregistered()
        stats["rem_unreg"] += num_deleted + num_deleted_contents
        stats["deleted"] += num_deleted
        stats["deleted_contents"] += num_deleted_contents
        stats["tagged_tracker_error"] += num_tagged
        stats["untagged_tracker_error"] += num_untagged
        stats["tagged"] += num_tagged

        # Set Cross Seed
        num_added, num_tagged = cfg.qbt.cross_seed()
        stats["added"] += num_added
        stats["tagged"] += num_tagged

        # Recheck Torrents
        num_resumed, num_rechecked = cfg.qbt.recheck()
        stats["resumed"] += num_resumed
        stats["rechecked"] += num_rechecked

        # Tag NoHardLinks
        num_tagged, num_untagged, num_deleted, num_deleted_contents = cfg.qbt.tag_nohardlinks()
        stats["tagged"] += num_tagged
        stats["tagged_noHL"] += num_tagged
        stats["untagged_noHL"] += num_untagged
        stats["deleted"] += num_deleted
        stats["deleted_contents"] += num_deleted_contents

        # Remove Orphaned Files
        num_orphaned = cfg.qbt.rem_orphaned()
        stats["orphaned"] += num_orphaned

        # Empty RecycleBin
        recycle_emptied = cfg.cleanup_dirs("Recycle Bin")
        stats["recycle_emptied"] += recycle_emptied

        # Empty Orphaned Directory
        orphaned_emptied = cfg.cleanup_dirs("Orphaned Data")
        stats["orphaned_emptied"] += orphaned_emptied

    if stats["categorized"] > 0:
        stats_summary.append(f"Total Torrents Categorized: {stats['categorized']}")
    if stats["tagged"] > 0:
        stats_summary.append(f"Total Torrents Tagged: {stats['tagged']}")
    if stats["rem_unreg"] > 0:
        stats_summary.append(f"Total Unregistered Torrents Removed: {stats['rem_unreg']}")
    if stats["tagged_tracker_error"] > 0:
        stats_summary.append(f"Total {cfg.settings['tracker_error_tag']} Torrents Tagged: {stats['tagged_tracker_error']}")
    if stats["untagged_tracker_error"] > 0:
        stats_summary.append(f"Total {cfg.settings['tracker_error_tag']} Torrents untagged: {stats['untagged_tracker_error']}")
    if stats["added"] > 0:
        stats_summary.append(f"Total Torrents Added: {stats['added']}")
    if stats["resumed"] > 0:
        stats_summary.append(f"Total Torrents Resumed: {stats['resumed']}")
    if stats["rechecked"] > 0:
        stats_summary.append(f"Total Torrents Rechecked: {stats['rechecked']}")
    if stats["deleted"] > 0:
        stats_summary.append(f"Total Torrents Deleted: {stats['deleted']}")
    if stats["deleted_contents"] > 0:
        stats_summary.append(f"Total Torrents + Contents Deleted : {stats['deleted_contents']}")
    if stats["orphaned"] > 0:
        stats_summary.append(f"Total Orphaned Files: {stats['orphaned']}")
    if stats["tagged_noHL"] > 0:
        stats_summary.append(f"Total noHL Torrents Tagged: {stats['tagged_noHL']}")
    if stats["untagged_noHL"] > 0:
        stats_summary.append(f"Total noHL Torrents untagged: {stats['untagged_noHL']}")
    if stats["recycle_emptied"] > 0:
        stats_summary.append(f"Total Files Deleted from Recycle Bin: {stats['recycle_emptied']}")
    if stats["orphaned_emptied"] > 0:
        stats_summary.append(f"Total Files Deleted from Orphaned Data: {stats['orphaned_emptied']}")

    finished_run()
    if cfg:
        try:
            cfg.webhooks_factory.end_time_hooks(start_time, end_time, run_time, next_run, stats, body)
        except Failed as err:
            logger.stacktrace()
            logger.error(f"Webhooks Error: {err}")


def end():
    """Ends the program"""
    logger.info("Exiting Qbit_manage")
    logger.remove_main_handler()
    sys.exit(0)


def calc_next_run(schd, write_out=False):
    """Calculates the next run time based on the schedule"""
    current = datetime.now().strftime("%H:%M")
    seconds = schd * 60
    time_to_run = datetime.now() + timedelta(minutes=schd)
    time_to_run_str = time_to_run.strftime("%H:%M")
    new_seconds = (datetime.strptime(time_to_run_str, "%H:%M") - datetime.strptime(current, "%H:%M")).total_seconds()
    next_run = {}
    if run is False:
        next_run["next_run"] = time_to_run
        if new_seconds < 0:
            new_seconds += 86400
        if (seconds is None or new_seconds < seconds) and new_seconds > 0:
            seconds = new_seconds
        if seconds is not None:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            time_until = f"{hours} Hour{'s' if hours > 1 else ''}{' and ' if minutes > 1 else ''}" if hours > 0 else ""
            time_until += f"{minutes} Minute{'s' if minutes > 1 else ''}" if minutes > 0 else ""
            if write_out:
                next_run["next_run_str"] = f"Current Time: {current} | {time_until} until the next run at {time_to_run_str}"
    else:
        next_run["next_run"] = None
        next_run["next_run_str"] = ""
    return time_until, next_run


if __name__ == "__main__":
    killer = GracefulKiller()
    logger.add_main_handler()
    logger.separator()
    logger.info_center("        _     _ _                                            ")  # noqa: W605
    logger.info_center("       | |   (_) |                                           ")  # noqa: W605
    logger.info_center("   __ _| |__  _| |_   _ __ ___   __ _ _ __   __ _  __ _  ___ ")  # noqa: W605
    logger.info_center("  / _` | '_ \\| | __| | '_ ` _ \\ / _` | '_ \\ / _` |/ _` |/ _ \\")  # noqa: W605
    logger.info_center(" | (_| | |_) | | |_  | | | | | | (_| | | | | (_| | (_| |  __/")  # noqa: W605
    logger.info_center(r"  \__, |_.__/|_|\__| |_| |_| |_|\__,_|_| |_|\__,_|\__, |\___|")  # noqa: W605
    logger.info_center("     | |         ______                            __/ |     ")  # noqa: W605
    logger.info_center("     |_|        |______|                          |___/      ")  # noqa: W605
    logger.info(f"    Version: {version}")

    logger.separator(loglevel="DEBUG")
    logger.debug(f"    --run (QBT_RUN): {run}")
    logger.debug(f"    --schedule (QBT_SCHEDULE): {sch}")
    logger.debug(f"    --startup-delay (QBT_STARTUP_DELAY): {startupDelay}")
    logger.debug(f"    --config-file (QBT_CONFIG): {config_files}")
    logger.debug(f"    --log-file (QBT_LOGFILE): {log_file}")
    logger.debug(f"    --cross-seed (QBT_CROSS_SEED): {cross_seed}")
    logger.debug(f"    --recheck (QBT_RECHECK): {recheck}")
    logger.debug(f"    --cat-update (QBT_CAT_UPDATE): {cat_update}")
    logger.debug(f"    --tag-update (QBT_TAG_UPDATE): {tag_update}")
    logger.debug(f"    --rem-unregistered (QBT_REM_UNREGISTERED): {rem_unregistered}")
    logger.debug(f"    --tag-tracker-error (QBT_TAG_TRACKER_ERROR): {tag_tracker_error}")
    logger.debug(f"    --rem-orphaned (QBT_REM_ORPHANED): {rem_orphaned}")
    logger.debug(f"    --tag-nohardlinks (QBT_TAG_NOHARDLINKS): {tag_nohardlinks}")
    logger.debug(f"    --skip-cleanup (QBT_SKIP_CLEANUP): {skip_cleanup}")
    logger.debug(f"    --dry-run (QBT_DRY_RUN): {dry_run}")
    logger.debug(f"    --log-level (QBT_LOG_LEVEL): {log_level}")
    logger.debug(f"    --divider (QBT_DIVIDER): {divider}")
    logger.debug(f"    --width (QBT_WIDTH): {screen_width}")
    logger.debug(f"    --debug (QBT_DEBUG): {debug}")
    logger.debug(f"    --trace (QBT_TRACE): {trace}")
    logger.debug("")
    try:
        if run:
            logger.info("    Run Mode: Script will exit after completion.")
            start_loop()
        else:
            schedule.every(sch).minutes.do(start_loop)
            time_str, _ = calc_next_run(sch)
            logger.info(f"    Scheduled Mode: Running every {time_str}.")
            if startupDelay:
                logger.info(f"     Startup Delay: Initial Run will start after {startupDelay} seconds")
                time.sleep(startupDelay)
            start_loop()
            while not killer.kill_now:
                schedule.run_pending()
                time.sleep(60)
            end()
    except KeyboardInterrupt:
        end()
