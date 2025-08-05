#!/usr/bin/env python3
"""qBittorrent Manager."""

import argparse
import glob
import multiprocessing
import os
import platform
import sys
import time
from datetime import datetime
from datetime import timedelta
from multiprocessing import Manager

from modules.scheduler import Scheduler
from modules.scheduler import calc_next_run
from modules.scheduler import is_valid_cron_syntax
from modules.util import execute_qbit_commands
from modules.util import format_stats_summary
from modules.util import get_arg
from modules.util import get_matching_config_files

try:
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
        f"Version Error: Version: {current_version[0]}.{current_version[1]}.{current_version[2]} incompatible with "
        f"qbit_manage please use Python {REQUIRED_VERSION_STR}+"
    )
    sys.exit(1)

parser = argparse.ArgumentParser("qBittorrent Manager.", description="A mix of scripts combined for managing qBittorrent.")
parser.add_argument(
    "-ws",
    "--web-server",
    dest="web_server",
    action="store_true",
    default=False,
    help="Start the webUI server to handle command requests via HTTP API.",
)
parser.add_argument(
    "-p",
    "--port",
    dest="port",
    type=int,
    default=8080,
    help="Port number for the web server (default: 8080).",
)
parser.add_argument(
    "-b",
    "--base-url",
    dest="base_url",
    type=str,
    default="",
    help="Base URL path for the web UI (e.g., '/qbit-manage'). Default is empty (root).",
)
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
web_server = get_arg("QBT_WEB_SERVER", args.web_server, arg_bool=True)
port = get_arg("QBT_PORT", args.port, arg_int=True)
base_url = get_arg("QBT_BASE_URL", args.base_url)
run = get_arg("QBT_RUN", args.run, arg_bool=True)
sch = get_arg("QBT_SCHEDULE", args.schedule)
startupDelay = get_arg("QBT_STARTUP_DELAY", args.startupDelay)
config_files = get_arg("QBT_CONFIG", args.configfiles)
log_file = get_arg("QBT_LOGFILE", args.logfile)
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
scheduler = None  # Global scheduler instance

if os.path.isdir("/config") and glob.glob(os.path.join("/config", config_files)):
    default_dir = "/config"
else:
    default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

config_files = get_matching_config_files(config_files, default_dir)


for v in [
    "run",
    "sch",
    "startupDelay",
    "config_files",
    "log_file",
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
    "web_server",
    "port",
    "base_url",
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
from modules.core.recheck import ReCheck  # noqa
from modules.core.remove_orphaned import RemoveOrphaned  # noqa
from modules.core.remove_unregistered import RemoveUnregistered  # noqa
from modules.core.share_limits import ShareLimits  # noqa
from modules.core.tag_nohardlinks import TagNoHardLinks  # noqa
from modules.core.tags import Tags  # noqa
from modules.util import Failed  # noqa
from modules.util import GracefulKiller  # noqa
from modules.web_api import CommandRequest  # noqa


def my_except_hook(exctype, value, tbi):
    """Handle uncaught exceptions"""
    if issubclass(exctype, KeyboardInterrupt):
        sys.__excepthook__(exctype, value, tbi)
    else:
        logger.critical("Uncaught Exception", exc_info=(exctype, value, tbi))


sys.excepthook = my_except_hook

version, branch = util.get_current_version()


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
            config_base = os.path.splitext(os.path.basename(config_file))[0]
            logger.add_config_handler(config_base)
            if not first_run:
                print_logo(logger)
            start()
            logger.remove_config_handler(config_base)


def start():
    """Start the run"""
    global is_running, is_running_lock, web_api_queue, next_scheduled_run_info_shared
    # Acquire lock only briefly to set the flag, then release immediately
    with is_running_lock:
        is_running.value = True  # Set flag to indicate a run is in progress
    start_time = datetime.now()
    args["time"] = start_time.strftime("%H:%M")
    args["time_obj"] = start_time
    stats_summary = []
    logger.separator("Starting Run")
    cfg = None
    body = ""
    run_time = ""
    end_time = None
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

    def finished_run(next_scheduled_run_info_shared):
        """Handle the end of a run"""
        nonlocal end_time, start_time, stats_summary, run_time, body
        end_time = datetime.now()
        run_time = str(end_time - start_time).split(".", maxsplit=1)[0]

        def next_run_from_scheduler():
            """Best-effort retrieval of scheduler's authoritative next_run."""
            try:
                if scheduler and scheduler.is_running():
                    return scheduler.get_next_run()
            except Exception:
                pass
            return None

        def next_run_from_config():
            """Compute next run strictly in the future based on current schedule config."""
            now_local = datetime.now()
            try:
                if scheduler and getattr(scheduler, "current_schedule", None):
                    stype, sval = scheduler.current_schedule
                    if stype == "cron":
                        from croniter import croniter

                        cron = croniter(sval, now_local)
                        nxt = cron.get_next(datetime)
                        while nxt <= now_local:
                            nxt = cron.get_next(datetime)
                        return nxt
                    if stype == "interval":
                        return now_local + timedelta(minutes=int(sval))
            except Exception:
                pass
            return now_local

        # Decide next run time
        if run is False:
            # Prefer scheduler's next_run first
            nxt_time = next_run_from_scheduler()
            if not nxt_time:
                nxt_time = next_run_from_config()

            # Guard: if cron and computed time isn't strictly in the future, advance
            try:
                if scheduler and getattr(scheduler, "current_schedule", None):
                    stype_chk, sval_chk = scheduler.current_schedule
                    if stype_chk == "cron":
                        now_guard = datetime.now()
                        if nxt_time <= now_guard:
                            from croniter import croniter

                            cron = croniter(sval_chk, now_guard)
                            nxt_time = cron.get_next(datetime)
                            while nxt_time <= now_guard:
                                nxt_time = cron.get_next(datetime)
            except Exception:
                pass

            # If within 30s of "now", prefer authoritative scheduler time to avoid "0 minutes"
            sched_next = next_run_from_scheduler()
            if sched_next:
                if (nxt_time - datetime.now()).total_seconds() <= 30:
                    nxt_time = sched_next
        else:
            # Single-run mode (explicit run) - show nothing imminent
            nxt_time = datetime.now()

        # Publish resolved next run
        nxt_run = calc_next_run(nxt_time, run)
        next_scheduled_run_info_shared.update(nxt_run)

        summary = os.linesep.join(stats_summary) if stats_summary else ""
        next_run_str = next_scheduled_run_info_shared.get("next_run_str", "")
        msg = (
            (f"Finished Run\n{summary}\nRun Time: {run_time}\n{next_run_str if next_run_str else ''}")
            .replace("\n\n", "\n")
            .rstrip()
        )
        body = logger.separator(msg)[0]
        return body

    try:
        cfg = Config(default_dir, args)
        qbit_manager = cfg.qbt
    except Exception as ex:
        logger.stacktrace()
        logger.print_line(ex, "CRITICAL")
        logger.print_line("Exiting scheduled Run.", "CRITICAL")
        finished_run(next_scheduled_run_info_shared)
        return None

    if qbit_manager:
        # Execute qBittorrent commands using shared function with error handling
        try:
            execute_qbit_commands(qbit_manager, cfg.commands, stats, hashes=None)
        except Exception as ex:
            logger.error(f"Error executing qBittorrent commands: {str(ex)}")
            logger.stacktrace()
            if cfg:
                cfg.notify(f"qBittorrent command execution failed: {str(ex)}", "Execution Error", False)

        # Empty RecycleBin
        stats["recycle_emptied"] += cfg.cleanup_dirs("Recycle Bin")

        # Empty Orphaned Directory
        stats["orphaned_emptied"] += cfg.cleanup_dirs("Orphaned Data")

    stats_summary = format_stats_summary(stats, cfg)

    finished_run(next_scheduled_run_info_shared)
    if cfg:
        try:
            next_run = next_scheduled_run_info_shared.get("next_run")
            cfg.webhooks_factory.end_time_hooks(start_time, end_time, run_time, next_run, stats, body)
            # Release flag after all cleanup is complete
            with is_running_lock:
                is_running.value = False
        except Failed as err:
            logger.stacktrace()
            logger.error(f"Webhooks Error: {err}")
            # Release flag even if webhooks fail
            with is_running_lock:
                is_running.value = False
            logger.info("Released lock for web API requests despite webhook error")


def end():
    """Ends the program"""
    logger.info("Exiting Qbit_manage")
    logger.remove_main_handler()
    sys.exit(0)


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
        # Initialize the Scheduler
        scheduler = Scheduler(args.get("config_dir", "config"))
        globals()["scheduler"] = scheduler  # Make scheduler globally accessible
        logger.debug("Scheduler initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {e}")
        raise

    try:

        def run_web_server(
            port,
            process_args,
            is_running,
            is_running_lock,
            web_api_queue,
            scheduler_update_queue,
            next_scheduled_run_info_shared,
            scheduler,
        ):
            """Run web server in a separate process with shared args"""
            try:
                import uvicorn

                from modules.web_api import create_app

                # Create FastAPI app instance with process args and shared state
                app = create_app(
                    process_args,
                    is_running,
                    is_running_lock,
                    web_api_queue,
                    scheduler_update_queue,
                    next_scheduled_run_info_shared,
                    scheduler,
                )

                # Configure uvicorn settings
                config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", access_log=False)

                # Run the server
                server = uvicorn.Server(config)
                server.run()
            except ImportError:
                logger.critical("Web server dependencies not installed. Please install with: pip install qbit_manage[web]")
                sys.exit(1)
            except KeyboardInterrupt:
                pass

        manager = Manager()
        is_running = manager.Value("b", False)  # 'b' for boolean, initialized to False
        is_running_lock = manager.Lock()  # Separate lock for is_running synchronization
        web_api_queue = manager.Queue()
        scheduler_update_queue = manager.Queue()  # Queue for scheduler updates from web API
        next_scheduled_run_info_shared = manager.dict()

        # Start web server if enabled and not in run mode
        web_process = None
        if web_server:
            logger.separator("Starting Web Server")
            logger.info(f"Web API server running on http://0.0.0.0:{port}")
            if base_url:
                logger.info(f"Access the WebUI at http://localhost:{port}/{base_url.lstrip('/')}")
                logger.info(f"Root path http://localhost:{port}/ will redirect to the WebUI")
            else:
                logger.info(f"Access the WebUI at http://localhost:{port}")

            # Create a copy of args to pass to the web server process
            process_args = args.copy()
            process_args["web_server"] = True  # Indicate this is for the web server
            # Create a read-only scheduler for the web server process
            # This scheduler can provide status information (for webAPI) but cannot execute tasks
            web_scheduler = Scheduler(default_dir, suppress_logging=True, read_only=True)

            web_process = multiprocessing.Process(
                target=run_web_server,
                args=(
                    port,
                    process_args,
                    is_running,
                    is_running_lock,
                    web_api_queue,
                    scheduler_update_queue,
                    next_scheduled_run_info_shared,
                    web_scheduler,
                ),
            )
            web_process.start()
            logger.info("Web server started in separate process")

        # Handle normal run modes
        if run:
            run_mode_message = "    Run Mode: Script will exit after completion."
            logger.info(run_mode_message)
            start_loop(True)
        else:
            # Local helper to centralize scheduled mode behavior
            def run_scheduled_mode(schedule_type_local, schedule_value_local, source_text_local, already_configured=False):
                # Build base message and ensure schedule is configured when needed
                if schedule_type_local == "cron":
                    run_msg = f"   Scheduled Mode: Running cron '{schedule_value_local}' (from {source_text_local})"
                    if not already_configured:
                        scheduler.update_schedule("cron", schedule_value_local)
                else:
                    interval_minutes_local = int(schedule_value_local)
                    delta_local = timedelta(minutes=interval_minutes_local)
                    run_msg = f"   Scheduled Mode: Running every {precisedelta(delta_local)} (from {source_text_local})."
                    if not already_configured:
                        # Ensure interval schedule is set so next_run is available
                        scheduler.update_schedule("interval", interval_minutes_local)

                # Compute next run info for logging/UI
                nr_time = scheduler.get_next_run()
                nr_info = calc_next_run(nr_time)
                next_scheduled_run_info_shared.update(nr_info)

                if schedule_type_local == "interval" and startupDelay:
                    run_msg += f"\n    Startup Delay: Initial Run will start after {startupDelay} seconds"
                    run_msg += f"\n     {nr_info['next_run_str']}"
                    logger.info(run_msg)
                    time.sleep(startupDelay)
                    # Execute first run immediately after startup delay
                    start_loop()
                    # Reset baseline for subsequent interval runs
                    scheduler.update_schedule("interval", int(schedule_value_local), suppress_logging=True)
                else:
                    run_msg += f"\n     {nr_info['next_run_str']}"
                    logger.info(run_msg)

                # Start scheduler for subsequent runs
                scheduler.start(callback=start_loop)

            # Check if scheduler already has a schedule loaded from schedule.yml
            current_schedule = scheduler.get_current_schedule()
            if current_schedule:
                # Scheduler already loaded a schedule - determine the actual source
                schedule_info = scheduler.get_schedule_info()
                schedule_type, schedule_value = current_schedule
                source = schedule_info.get("source", "unknown")
                source_text = "persistent file" if source == "schedule.yml" else "environment"

                # Use helper; already_configured=True because Scheduler loaded it
                run_scheduled_mode(schedule_type, schedule_value, source_text, already_configured=True)

            elif sch is None or sch == "":
                # No schedule from file or environment - scheduler remains unscheduled for web UI configuration
                logger.info("    Web UI Mode: No schedule provided. Scheduler available for configuration via web interface.")
                # Start the scheduler without a schedule (it will remain idle until configured via web UI)
                scheduler.start(callback=start_loop)
            else:
                # Use environment variable schedule as fallback
                if is_valid_cron_syntax(sch):
                    # configure via helper (will call update_schedule itself)
                    run_scheduled_mode("cron", sch, "environment", already_configured=False)
                else:
                    # configure via helper (will call update_schedule itself)
                    run_scheduled_mode("interval", sch, "environment", already_configured=False)

            # Simple loop to handle scheduler updates from web API and keep the process alive
            while not killer.kill_now:
                # Check for scheduler updates from web API
                if not scheduler_update_queue.empty():
                    try:
                        update_data = scheduler_update_queue.get_nowait()
                        schedule_type = update_data["type"]
                        schedule_value = update_data["value"]

                        if schedule_type == "delete":
                            logger.debug("Received scheduler delete notification from web API")
                            success = scheduler.delete_schedule()
                            if success:
                                logger.debug("Main process scheduler reloaded after deletion")
                            else:
                                logger.error("Failed to reload main process scheduler after deletion")
                        else:
                            logger.debug(f"Received scheduler update from web API: {schedule_type} = {schedule_value}")
                            success = scheduler.update_schedule(schedule_type, schedule_value, suppress_logging=True)
                            if success:
                                logger.debug("Main process scheduler updated successfully")
                            else:
                                logger.error("Failed to update main process scheduler")
                    except Exception as e:
                        logger.error(f"Error processing scheduler update: {e}")

                # Update shared dictionary with current scheduler status
                next_run_time = scheduler.get_next_run()
                if next_run_time:
                    next_run_info = calc_next_run(next_run_time)
                    next_scheduled_run_info_shared.update(next_run_info)

                # Sleep for a reasonable interval
                time.sleep(30)

            # Stop the scheduler gracefully
            scheduler.stop()
            if web_process:
                web_process.terminate()
                web_process.join()
            end()
    except KeyboardInterrupt:
        scheduler.stop()
        if web_process:
            web_process.terminate()
            web_process.join()
        end()
