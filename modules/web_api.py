"""Web API module for qBittorrent-Manage"""

from __future__ import annotations

import asyncio
import glob
import os
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from multiprocessing import Queue
from multiprocessing import Value

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from modules import util
from modules.config import Config
from modules.core.category import Category
from modules.core.recheck import ReCheck
from modules.core.remove_orphaned import RemoveOrphaned
from modules.core.remove_unregistered import RemoveUnregistered
from modules.core.share_limits import ShareLimits
from modules.core.tag_nohardlinks import TagNoHardLinks
from modules.core.tags import Tags
from modules.util import get_matching_config_files

logger = util.logger


class CommandRequest(BaseModel):
    """Command request model."""

    config_file: str = "config.yml"
    commands: list[str]
    dry_run: bool = False


async def process_queue_periodically(web_api: WebAPI) -> None:
    """Continuously check and process queued requests."""
    try:
        while True:
            if not web_api.is_running.value and not web_api.web_api_queue.empty():
                logger.info("Processing queued requests...")
                while not web_api.web_api_queue.empty():
                    request = web_api.web_api_queue.get()
                    try:
                        await web_api._execute_command(request)
                        logger.info("Successfully processed queued request")
                    except Exception as e:
                        logger.error(f"Error processing queued request: {str(e)}")
            await asyncio.sleep(1)  # Check every second
    except asyncio.CancelledError:
        logger.info("Queue processing task cancelled")
        raise


@dataclass(frozen=True)
class WebAPI:
    """Web API handler for qBittorrent-Manage."""

    default_dir: str = field(
        default_factory=lambda: (
            "/config"
            if os.path.isdir("/config") and glob.glob(os.path.join("/config", "*.yml"))
            else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        )
    )
    args: dict = field(default_factory=dict)
    app: FastAPI = field(default_factory=FastAPI)
    is_running: Value = field(default=None)
    web_api_queue: Queue = field(default=None)

    def __post_init__(self) -> None:
        """Initialize routes and events."""
        # Initialize routes
        self.app.post("/api/run-command")(self.run_command)

        # Store reference to self in app state for access in event handlers
        self.app.state.web_api = self

        @self.app.on_event("startup")
        async def startup_event():
            """Start background task for queue processing."""
            self.app.state.background_task = asyncio.create_task(process_queue_periodically(self.app.state.web_api))

        @self.app.on_event("shutdown")
        async def shutdown_event():
            """Clean up background task."""
            if hasattr(self.app.state, "background_task"):
                self.app.state.background_task.cancel()
                try:
                    await self.app.state.background_task
                except asyncio.CancelledError:
                    pass

    async def execute_for_config(self, args: dict) -> dict:
        """Execute commands for a specific config file."""
        try:
            cfg = Config(self.default_dir, args)
            qbit_manager = cfg.qbt
            stats = {"executed_commands": []}

            if qbit_manager:
                if args["cat_update"]:
                    stats["categorized"] = Category(qbit_manager).stats
                    stats["executed_commands"].append("cat_update")

                if args["tag_update"]:
                    stats["tagged"] = Tags(qbit_manager).stats
                    stats["executed_commands"].append("tag_update")

                if args["rem_unregistered"] or args["tag_tracker_error"]:
                    rem_unreg = RemoveUnregistered(qbit_manager)
                    stats.update(
                        {
                            "rem_unreg": rem_unreg.stats_deleted + rem_unreg.stats_deleted_contents,
                            "deleted": rem_unreg.stats_deleted,
                            "deleted_contents": rem_unreg.stats_deleted_contents,
                            "tagged_tracker_error": rem_unreg.stats_tagged,
                            "untagged_tracker_error": rem_unreg.stats_untagged,
                        }
                    )
                    stats["executed_commands"].extend([cmd for cmd in ["rem_unregistered", "tag_tracker_error"] if args[cmd]])

                if args["recheck"]:
                    recheck = ReCheck(qbit_manager)
                    stats["rechecked"] = recheck.stats_rechecked
                    stats["resumed"] = recheck.stats_resumed
                    stats["executed_commands"].append("recheck")

                if args["rem_orphaned"]:
                    stats.update(RemoveOrphaned(qbit_manager).stats)
                    stats["executed_commands"].append("rem_orphaned")

                if args["tag_nohardlinks"]:
                    stats.update(TagNoHardLinks(qbit_manager).stats)
                    stats["executed_commands"].append("tag_nohardlinks")

                if args["share_limits"]:
                    stats.update(ShareLimits(qbit_manager).stats)
                    stats["executed_commands"].append("share_limits")

                return stats
            else:
                raise HTTPException(status_code=500, detail=f"Failed to initialize qBittorrent manager for {args['config_file']}")

        except Exception as e:
            logger.error(f"Error executing commands for {args['config_file']}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_command(self, request: CommandRequest) -> dict:
        """Execute the actual command implementation."""
        try:
            logger.separator("Web API Request")
            logger.info(f"Config File: {request.config_file}")
            logger.info(f"Commands: {', '.join(request.commands)}")
            logger.info(f"Dry Run: {request.dry_run}")

            config_files = get_matching_config_files(request.config_file, self.default_dir)
            logger.info(f"Found config files: {', '.join(config_files)}")

            now = datetime.now()
            base_args = self.args.copy()
            base_args.update(
                {
                    "_from_web_api": True,
                    "dry_run": request.dry_run,
                    "time": now.strftime("%H:%M"),
                    "time_obj": now,
                    "run": True,
                }
            )

            command_flags = [
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
            ]
            for flag in command_flags:
                base_args[flag] = False

            for cmd in request.commands:
                if cmd in base_args:
                    base_args[cmd] = True
                else:
                    raise HTTPException(status_code=400, detail=f"Invalid command: {cmd}")

            all_stats = []

            for config_file in config_files:
                run_args = base_args.copy()
                run_args["config_file"] = config_file
                run_args["config_files"] = [config_file]

                config_base = os.path.splitext(config_file)[0]
                logger.add_config_handler(config_base)

                try:
                    stats = await self.execute_for_config(run_args)
                    all_stats.append({"config_file": config_file, "stats": stats})
                finally:
                    logger.remove_config_handler(config_base)

            return {"status": "success", "message": "Commands executed successfully for all configs", "results": all_stats}

        except Exception as e:
            logger.error(f"Error executing commands: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def run_command(self, request: CommandRequest) -> dict:
        """Handle incoming command requests."""
        # First check if a scheduled run is in progress
        if self.is_running.value:
            logger.info("Scheduled run in progress. Queuing web API request...")
            self.web_api_queue.put(request)
            return {
                "status": "queued",
                "message": "Scheduled run in progress. Request queued.",
                "config_file": request.config_file,
                "commands": request.commands,
            }

        # Add a small delay and recheck to handle race conditions
        await asyncio.sleep(0.1)

        # Double-check if a scheduled run started during the delay
        if self.is_running.value:
            logger.info("Scheduled run started. Queuing web API request...")
            self.web_api_queue.put(request)
            return {
                "status": "queued",
                "message": "Scheduled run started. Request queued.",
                "config_file": request.config_file,
                "commands": request.commands,
            }

        # If still no scheduled run, execute the command
        return await self._execute_command(request)


def create_app(args: dict, is_running: Value, web_api_queue: Queue) -> FastAPI:
    """Create and return the FastAPI application."""
    return WebAPI(args=args, is_running=is_running, web_api_queue=web_api_queue).app
