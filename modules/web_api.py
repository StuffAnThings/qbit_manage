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
from modules.util import format_stats_summary
from modules.util import get_matching_config_files

logger = util.logger


class CommandRequest(BaseModel):
    """Command request model."""

    config_file: str = "config.yml"
    commands: list[str]
    hashes: list[str] = field(default_factory=list)
    dry_run: bool = False


async def process_queue_periodically(web_api: WebAPI) -> None:
    """Continuously check and process queued requests."""
    try:
        while True:
            # Use multiprocessing-safe check for is_running with timeout
            is_currently_running = True  # Default to assuming running if we can't check
            try:
                if web_api.is_running_lock.acquire(timeout=0.1):
                    try:
                        is_currently_running = web_api.is_running.value
                    finally:
                        web_api.is_running_lock.release()
            except Exception:
                # If we can't acquire the lock, assume something is running
                pass

            if not is_currently_running and not web_api.web_api_queue.empty():
                logger.info("Processing queued requests...")
                while not web_api.web_api_queue.empty():
                    try:
                        request = web_api.web_api_queue.get_nowait()
                        try:
                            await web_api._execute_command(request)
                            logger.info("Successfully processed queued request")
                        except Exception as e:
                            logger.error(f"Error processing queued request: {str(e)}")
                    except:
                        # Queue is empty, break out of inner loop
                        break
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
    is_running_lock: object = field(default=None)  # multiprocessing.Lock
    web_api_queue: Queue = field(default=None)
    next_scheduled_run_info: dict = field(default_factory=dict)

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

    async def execute_for_config(self, args: dict, hashes: list[str]) -> dict:
        """Execute commands for a specific config file."""
        try:
            cfg = Config(self.default_dir, args)
            qbit_manager = cfg.qbt
            stats = {
                "executed_commands": [],
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

            if qbit_manager:
                # Execute qBittorrent commands using shared function
                from modules.util import execute_qbit_commands

                execute_qbit_commands(qbit_manager, args, stats, hashes=hashes)

                return stats, cfg
            else:
                raise HTTPException(status_code=500, detail=f"Failed to initialize qBittorrent manager for {args['config_file']}")

        except Exception as e:
            logger.stacktrace()
            logger.error(f"Error executing commands for {args['config_file']}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def _execute_command(self, request: CommandRequest) -> dict:
        """Execute the actual command implementation."""
        try:
            logger.separator("Web API Request")
            logger.info(f"Config File: {request.config_file}")
            logger.info(f"Commands: {', '.join(request.commands)}")
            logger.info(f"Dry Run: {request.dry_run}")
            logger.info(f"Hashes: {', '.join(request.hashes) if request.hashes else 'None'}")

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
                    "hashes": request.hashes,
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

                config_start_time = datetime.now()  # Record start time for this config file

                try:
                    stats, cfg_obj = await self.execute_for_config(run_args, request.hashes)
                    all_stats.append({"config_file": config_file, "stats": stats})
                    stats_output = format_stats_summary(stats, cfg_obj)

                    config_end_time = datetime.now()  # Record end time for this config file
                    config_run_time = str(config_end_time - config_start_time).split(".", maxsplit=1)[0]  # Calculate run time

                    run_mode_message = ""
                    if self.next_scheduled_run_info:
                        run_mode_message = f"\nNext Scheduled Run: {self.next_scheduled_run_info['next_run_str']}"

                    body = logger.separator(
                        f"Finished WebAPI Run\n"
                        f"Config File: {config_file}\n"
                        f"{os.linesep.join(stats_output) if len(stats_output) > 0 else ''}"
                        f"\nRun Time: {config_run_time}\n{run_mode_message}"  # Include run time and next scheduled run
                    )

                    # Execute end time webhooks
                    try:
                        next_run = self.next_scheduled_run_info.get("next_run")
                        cfg_obj.webhooks_factory.end_time_hooks(
                            config_start_time, config_end_time, config_run_time, next_run, stats, body[0]
                        )
                    except Exception as webhook_error:
                        logger.error(f"Webhook error: {str(webhook_error)}")
                finally:
                    logger.remove_config_handler(config_base)

            return {"status": "success", "message": "Commands executed successfully for all configs", "results": all_stats}

        except Exception as e:
            logger.stacktrace()
            logger.error(f"Error executing commands: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            # Reset flag with proper synchronization
            try:
                with self.is_running_lock:
                    self.is_running.value = False
            except Exception as e:
                # If we can't acquire the lock, force reset anyway as a safety measure
                logger.error(f"Could not acquire lock in finally block: {e}. Force resetting is_running.value")
                self.is_running.value = False

    async def run_command(self, request: CommandRequest) -> dict:
        """Handle incoming command requests."""
        # Use atomic check-and-set operation
        try:
            if self.is_running_lock.acquire(timeout=0.1):
                try:
                    if self.is_running.value:
                        logger.info("Another run is in progress. Queuing web API request...")
                        self.web_api_queue.put(request)
                        return {
                            "status": "queued",
                            "message": "Another run is in progress. Request queued.",
                            "config_file": request.config_file,
                            "commands": request.commands,
                        }
                    # Atomic operation: set flag to True
                    self.is_running.value = True
                finally:
                    # Release lock immediately after atomic operation
                    self.is_running_lock.release()
            else:
                # If we can't acquire the lock quickly, assume another run is in progress
                self.web_api_queue.put(request)
                return {
                    "status": "queued",
                    "message": "Another run is in progress. Request queued.",
                    "config_file": request.config_file,
                    "commands": request.commands,
                }
        except Exception as e:
            logger.error(f"Error acquiring lock: {str(e)}")
            # If there's any error with locking, queue the request as a safety measure
            self.web_api_queue.put(request)
            return {
                "status": "queued",
                "message": "Lock error occurred. Request queued.",
                "config_file": request.config_file,
                "commands": request.commands,
            }

        # Execute the command outside the lock
        try:
            return await self._execute_command(request)
        except HTTPException as e:
            # Ensure is_running is reset if an HTTPException occurs
            with self.is_running_lock:
                self.is_running.value = False
            raise e
        except Exception as e:
            # Ensure is_running is reset if any other exception occurs
            with self.is_running_lock:
                self.is_running.value = False
            logger.stacktrace()
            logger.error(f"Error in run_command during execution: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


def create_app(
    args: dict, is_running: bool, is_running_lock: object, web_api_queue: Queue, next_scheduled_run_info: dict
) -> FastAPI:
    """Create and return the FastAPI application."""
    return WebAPI(
        args=args,
        is_running=is_running,
        is_running_lock=is_running_lock,
        web_api_queue=web_api_queue,
        next_scheduled_run_info=next_scheduled_run_info,
    ).app
