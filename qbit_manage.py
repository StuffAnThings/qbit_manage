#!/usr/bin/env python3
"""qBittorrent Manager."""
import argparse
import glob
import math
import os
import platform
import sys
import time
from datetime import datetime
from datetime import timedelta
from functools import lru_cache

try:
    import schedule
    from croniter import croniter
    from humanize import precisedelta

    from modules.logs import MyLogger
except ModuleNotFoundError:
    print("Requirements Error: Requirements are not installed")
    sys.exit(1)

REQUIRED_VERSION = (3, 8, 1)
REQUIRED_VERSION_STR = ".".join(str(x) for x in REQUIRED_VERSION)
current_version = sys.version_info

if current_version < (REQUIRED_VERSION):
    print(
        "Version Error: Version: %s.%s.%s incompatible with qbit_manage please use Python %s+"
        % (current_version[0], current_version[1], current_version[2], REQUIRED_VERSION_STR)
    )
    sys.exit(1)

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
    dest="schedule",
    default="1440",
    type=str,
    help=(
        "Schedule to run every x minutes. (Default set to 1440 (1 day))."
        "Can also customize schedule via cron syntax (See https://crontab.guru/examples.html)"
    ),
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
    help=(
        "This is used if you want to use a different name for your config.yml or if you want to load multiple"
        "config files using *. Example: tv.yml or config*.yml"
    ),
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
    help=(
        "Use this if you would like to update your tags and/or set seed goals/limit upload speed by tag."
        " (Only adds tags to untagged torrents)"
    ),
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
    help="Use this if you would like to remove orphaned files.",
)
parser.add_argument(
    "-tnhl",
    "--tag-nohardlinks",
    dest="tag_nohardlinks",
    action="store_true",
    default=False,
    help=(
        "Use this to tag any torrents that do not have any hard links associated with any of the files. "
        "This is useful for those that use Sonarr/Radarr which hard link your media files with the torrents for seeding. "
        "When files get upgraded they no longer become linked with your media therefore will be tagged with a new tag noHL. "
        "You can then safely delete/remove these torrents to free up any extra space that is not being used by your media folder."
    ),
)
parser.add_argument(
    "-sl",
    "--share-limits",
    dest="share_limits",
    action="store_true",
    default=False,
    help=(
        "Use this to help apply and manage your torrent share limits based on your tags/categories."
        "This can apply a max ratio, seed time limits to your torrents or limit your torrent upload speed as well."
        "Share limits are applied in the order of priority specified."
    ),
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
    "-svc",
    "--skip-qb-version-check",
    dest="skip_qb_version_check",
    action="store_true",
    default=False,
    # help="Bypass qBittorrent/libtorrent version compatibility check. "
    # "You run the risk of undesirable behavior and will receive no support.",
    help=argparse.SUPPRESS,
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
parser.add_argument(
    "-ls", "--log-size", dest="log_size", action="store", default=10, type=int, help="Maximum log size per file (in MB)"
)
parser.add_argument(
    "-lc", "--log-count", dest="log_count", action="store", default=5, type=int, help="Maximum mumber of logs to keep"
)
args = parser.parse_args()


static_envs = []
test_value = None


def get_arg(env_str, default, arg_bool=False, arg_int=False):
    global test_value
    env_vars = [env_str] if not isinstance(env_str, list) else env_str
    final_value = None
    static_envs.extend(env_vars)
    for env_var in env_vars:
        env_value = os.environ.get(env_var)
        if env_var == "BRANCH_NAME":
            test_value = env_value
        if env_value is not None:
            final_value = env_value
            break
    if final_value or (arg_int and final_value == 0):
        if arg_bool:
            if final_value is True or final_value is False:
                return final_value
            elif final_value.lower() in ["t", "true"]:
                return True
            else:
                return False
        elif arg_int:
            try:
                return int(final_value)
            except ValueError:
                return default
        else:
            return str(final_value)
    else:
        return default


@lru_cache(maxsize=1)
def is_valid_cron_syntax(cron_expression):
    try:
        croniter(str(cron_expression))
        return True
    except (ValueError, KeyError):
        return False


try:
    from git import InvalidGitRepositoryError
    from git import Repo

    try:
        git_branch = Repo(path=".").head.ref.name  # noqa
    except InvalidGitRepositoryError:
        git_branch = None
except ImportError:
    git_branch = None

env_version = get_arg("BRANCH_NAME", "master")
is_docker = get_arg("QBM_DOCKER", False, arg_bool=True)
run = get_arg("QBT_RUN", args.run, arg_bool=True)
sch = get_arg("QBT_SCHEDULE", args.schedule)
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
share_limits = get_arg("QBT_SHARE_LIMITS", args.share_limits, arg_bool=True)
skip_cleanup = get_arg("QBT_SKIP_CLEANUP", args.skip_cleanup, arg_bool=True)
skip_qb_version_check = get_arg("QBT_SKIP_QB_VERSION_CHECK", args.skip_qb_version_check, arg_bool=True)
dry_run = get_arg("QBT_DRY_RUN", args.dry_run, arg_bool=True)
log_level = get_arg("QBT_LOG_LEVEL", args.log_level)
log_size = get_arg("QBT_LOG_SIZE", args.log_size, arg_int=True)
log_count = get_arg("QBT_LOG_COUNT", args.log_count, arg_int=True)
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
        sys.exit(1)


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
    "share_limits",
    "skip_cleanup",
    "skip_qb_version_check",
    "dry_run",
    "log_level",
    "log_size",
    "log_count",
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
    if not is_valid_cron_syntax(sch):
        print(f"Invalid Schedule: Please use a valid cron schedule or integer (minutes). Current value is set to '{sch}'")
        sys.exit(1)

# Check if StartupDelay parameter is a number
try:
    startupDelay = int(startupDelay)
except ValueError:
    print(f"startupDelay Error: startupDelay is not a number. Current value is set to '{startupDelay}'")
    sys.exit(1)


logger = MyLogger("qBit Manage", log_file, log_level, default_dir, screen_width, divider[0], False, log_size, log_count)
from modules import util  # noqa

util.logger = logger
from modules.config import Config  # noqa
from modules.core.category import Category  # noqa
from modules.core.cross_seed import CrossSeed  # noqa
from modules.core.recheck import ReCheck  # noqa
from modules.core.remove_orphaned import RemoveOrphaned  # noqa
from modules.core.remove_unregistered import RemoveUnregistered  # noqa
from modules.core.share_limits import ShareLimits  # noqa
from modules.core.tag_nohardlinks import TagNoHardLinks  # noqa
from modules.core.tags import Tags  # noqa
from modules.util import Failed  # noqa
from modules.util import GracefulKiller  # noqa


def my_except_hook(exctype, value, tbi):
    """Handle uncaught exceptions"""
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tbi)
    else:
        logger.critical("Uncaught Exception", exc_info=(exctype, value, tbi))


sys.excepthook = my_except_hook

version = ("Unknown", "Unknown", 0)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as handle:
    for line in handle.readlines():
        line = line.strip()
        if len(line) > 0:
            version = util.parse_version(line)
            break
branch = util.guess_branch(version, env_version, git_branch)
if branch is None:
    branch = "Unknown"
version = (version[0].replace("develop", branch), version[1].replace("develop", branch), version[2])


def start_loop(first_run=False):
    """Start the main loop"""
    if len(config_files) == 1:
        args["config_file"] = config_files[0]
        if not first_run:
            print_logo(logger)
        start()
    else:
        for config_file in config_files:
            args["config_file"] = config_file
            config_base = os.path.splitext(config_file)[0]
            logger.add_config_handler(config_base)
            if not first_run:
                print_logo(logger)
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
        "updated_share_limits": 0,
        "cleaned_share_limits": 0,
    }

    def finished_run():
        """Handle the end of a run"""
        nonlocal end_time, start_time, stats_summary, run_time, next_run, body
        end_time = datetime.now()
        run_time = str(end_time - start_time).split(".", maxsplit=1)[0]
        if run is False:
            if is_valid_cron_syntax(sch):  # Simple check to guess if it's a cron syntax
                next_run_time = schedule_from_cron(sch)
            else:
                delta = timedelta(minutes=sch)
                logger.info(f"    Scheduled Mode: Running every {precisedelta(delta)}.")
                next_run_time = schedule_every_x_minutes(sch)
        else:
            next_run_time = datetime.now()
        nxt_run = calc_next_run(next_run_time)
        next_run_str = nxt_run["next_run_str"]
        next_run = nxt_run["next_run"]
        body = logger.separator(
            f"Finished Run\n{os.linesep.join(stats_summary) if len(stats_summary) > 0 else ''}"
            f"\nRun Time: {run_time}\n{next_run_str if len(next_run_str) > 0 else ''}".replace("\n\n", "\n").rstrip()
        )[0]
        return next_run, body

    try:
        cfg = Config(default_dir, args)
        qbit_manager = cfg.qbt
    except Exception as ex:
        logger.stacktrace()
        logger.print_line(ex, "CRITICAL")
        logger.print_line("Exiting scheduled Run.", "CRITICAL")
        finished_run()
        return None

    if qbit_manager:
        # Set Category
        if cfg.commands["cat_update"]:
            stats["categorized"] += Category(qbit_manager).stats

        # Set Tags
        if cfg.commands["tag_update"]:
            stats["tagged"] += Tags(qbit_manager).stats

        # Set Cross Seed
        if cfg.commands["cross_seed"]:
            cross_seed = CrossSeed(qbit_manager)
            stats["added"] += cross_seed.stats_added
            stats["tagged"] += cross_seed.stats_tagged

        # Remove Unregistered Torrents and tag errors
        if cfg.commands["rem_unregistered"] or cfg.commands["tag_tracker_error"]:
            rem_unreg = RemoveUnregistered(qbit_manager)
            stats["rem_unreg"] += rem_unreg.stats_deleted + rem_unreg.stats_deleted_contents
            stats["deleted"] += rem_unreg.stats_deleted
            stats["deleted_contents"] += rem_unreg.stats_deleted_contents
            stats["tagged_tracker_error"] += rem_unreg.stats_tagged
            stats["untagged_tracker_error"] += rem_unreg.stats_untagged
            stats["tagged"] += rem_unreg.stats_tagged

        # Recheck Torrents
        if cfg.commands["recheck"]:
            recheck = ReCheck(qbit_manager)
            stats["resumed"] += recheck.stats_resumed
            stats["rechecked"] += recheck.stats_rechecked

        # Tag NoHardLinks
        if cfg.commands["tag_nohardlinks"]:
            no_hardlinks = TagNoHardLinks(qbit_manager)
            stats["tagged"] += no_hardlinks.stats_tagged
            stats["tagged_noHL"] += no_hardlinks.stats_tagged
            stats["untagged_noHL"] += no_hardlinks.stats_untagged

        # Set Share Limits
        if cfg.commands["share_limits"]:
            share_limits = ShareLimits(qbit_manager)
            stats["tagged"] += share_limits.stats_tagged
            stats["updated_share_limits"] += share_limits.stats_tagged
            stats["deleted"] += share_limits.stats_deleted
            stats["deleted_contents"] += share_limits.stats_deleted_contents
            stats["cleaned_share_limits"] += share_limits.stats_deleted + share_limits.stats_deleted_contents

        # Remove Orphaned Files
        if cfg.commands["rem_orphaned"]:
            stats["orphaned"] += RemoveOrphaned(qbit_manager).stats

        # Empty RecycleBin
        stats["recycle_emptied"] += cfg.cleanup_dirs("Recycle Bin")

        # Empty Orphaned Directory
        stats["orphaned_emptied"] += cfg.cleanup_dirs("Orphaned Data")

    if stats["categorized"] > 0:
        stats_summary.append(f"Total Torrents Categorized: {stats['categorized']}")
    if stats["tagged"] > 0:
        stats_summary.append(f"Total Torrents Tagged: {stats['tagged']}")
    if stats["rem_unreg"] > 0:
        stats_summary.append(f"Total Unregistered Torrents Removed: {stats['rem_unreg']}")
    if stats["tagged_tracker_error"] > 0:
        stats_summary.append(f"Total {cfg.tracker_error_tag} Torrents Tagged: {stats['tagged_tracker_error']}")
    if stats["untagged_tracker_error"] > 0:
        stats_summary.append(f"Total {cfg.tracker_error_tag} Torrents untagged: {stats['untagged_tracker_error']}")
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
        stats_summary.append(f"Total {cfg.nohardlinks_tag} Torrents Tagged: {stats['tagged_noHL']}")
    if stats["untagged_noHL"] > 0:
        stats_summary.append(f"Total {cfg.nohardlinks_tag} Torrents untagged: {stats['untagged_noHL']}")
    if stats["updated_share_limits"] > 0:
        stats_summary.append(f"Total Share Limits Updated: {stats['updated_share_limits']}")
    if stats["cleaned_share_limits"] > 0:
        stats_summary.append(f"Total Torrents Removed from Meeting Share Limits: {stats['cleaned_share_limits']}")
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


def calc_next_run(next_run_time):
    """Calculates the next run time based on the schedule"""
    current_time = datetime.now()
    current = current_time.strftime("%I:%M %p")
    time_to_run_str = next_run_time.strftime("%Y-%m-%d %I:%M %p")
    delta_seconds = (next_run_time - current_time).total_seconds()
    time_until = precisedelta(timedelta(minutes=math.ceil(delta_seconds / 60)), minimum_unit="minutes", format="%d")
    next_run = {}
    if run is False:
        next_run["next_run"] = next_run_time
        next_run["next_run_str"] = f"Current Time: {current} | {time_until} until the next run at {time_to_run_str}"
    else:
        next_run["next_run"] = None
        next_run["next_run_str"] = ""
    return next_run


def schedule_from_cron(cron_expression):
    schedule.clear()
    base_time = datetime.now()
    try:
        iter = croniter(cron_expression, base_time)
        next_run_time = iter.get_next(datetime)
    except Exception as e:
        logger.error(f"Invalid Cron Syntax: {cron_expression}. {e}")
        logger.stacktrace()
        sys.exit(1)
    delay = (next_run_time - base_time).total_seconds()
    schedule.every(delay).seconds.do(start_loop)
    return next_run_time


def schedule_every_x_minutes(min):
    schedule.clear()
    schedule.every(min).minutes.do(start_loop)
    next_run_time = datetime.now() + timedelta(minutes=min)
    return next_run_time


def print_logo(logger):
    global is_docker, version, git_branch
    logger.separator()
    logger.info_center("        _     _ _                                            ")  # noqa: W605
    logger.info_center("       | |   (_) |                                           ")  # noqa: W605
    logger.info_center("   __ _| |__  _| |_   _ __ ___   __ _ _ __   __ _  __ _  ___ ")  # noqa: W605
    logger.info_center("  / _` | '_ \\| | __| | '_ ` _ \\ / _` | '_ \\ / _` |/ _` |/ _ \\")  # noqa: W605
    logger.info_center(" | (_| | |_) | | |_  | | | | | | (_| | | | | (_| | (_| |  __/")  # noqa: W605
    logger.info_center(r"  \__, |_.__/|_|\__| |_| |_| |_|\__,_|_| |_|\__,_|\__, |\___|")  # noqa: W605
    logger.info_center("     | |         ______                            __/ |     ")  # noqa: W605
    logger.info_center("     |_|        |______|                          |___/      ")  # noqa: W605
    system_ver = "Docker" if is_docker else f"Python {platform.python_version()}"
    logger.info(f"    Version: {version[0]} ({system_ver}){f' (Git: {git_branch})' if git_branch else ''}")
    latest_version = util.current_version(version, branch=branch)
    new_version = (
        latest_version[0]
        if latest_version and (version[1] != latest_version[1] or (version[2] and version[2] < latest_version[2]))
        else None
    )
    if new_version:
        logger.info(f"    Newest Version: {new_version}")
    logger.info(f"    Platform: {platform.platform()}")


if __name__ == "__main__":
    killer = GracefulKiller()
    logger.add_main_handler()
    print_logo(logger)
    try:
        if run:
            run_mode_message = "    Run Mode: Script will exit after completion."
            logger.info(run_mode_message)
            start_loop(True)
        else:
            if is_valid_cron_syntax(sch):  # Simple check to guess if it's a cron syntax
                run_mode_message = f"    Scheduled Mode: Running cron '{sch}'"
                next_run_time = schedule_from_cron(sch)
                next_run = calc_next_run(next_run_time)
                run_mode_message += f"\n     {next_run['next_run_str']}"
                logger.info(run_mode_message)
            else:
                delta = timedelta(minutes=sch)
                run_mode_message = f"    Scheduled Mode: Running every {precisedelta(delta)}."
                next_run_time = schedule_every_x_minutes(sch)
                if startupDelay:
                    run_mode_message += f"\n    Startup Delay: Initial Run will start after {startupDelay} seconds"
                    logger.info(run_mode_message)
                    time.sleep(startupDelay)
                else:
                    logger.info(run_mode_message)
                start_loop(True)

            while not killer.kill_now:
                next_run = calc_next_run(next_run_time)
                schedule.run_pending()
                logger.trace(f"    Pending Jobs: {schedule.get_jobs()}")
                time.sleep(60)
            end()
    except KeyboardInterrupt:
        end()