"""Web API module for qBittorrent-Manage"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import re
import shutil
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from multiprocessing import Queue
from multiprocessing.sharedctypes import Synchronized
from pathlib import Path
from typing import Any
from typing import Optional

import ruamel.yaml
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules import util
from modules.config import Config
from modules.util import YAML
from modules.util import format_stats_summary
from modules.util import get_matching_config_files

logger = util.logger


class CommandRequest(BaseModel):
    """Command request model."""

    config_file: str = "config.yml"
    commands: list[str]
    hashes: list[str] = field(default_factory=list)
    dry_run: bool = False
    skip_cleanup: bool = False
    skip_qb_version_check: bool = False
    log_level: Optional[str] = None  # noqa: UP045


class ConfigRequest(BaseModel):
    """Configuration request model."""

    data: dict[str, Any]


class ConfigListResponse(BaseModel):
    """Configuration list response model."""

    configs: list[str]
    default_config: str


class ConfigResponse(BaseModel):
    """Configuration response model."""

    filename: str
    data: dict[str, Any]
    last_modified: str
    size: int


class ValidationResponse(BaseModel):
    """Configuration validation response model."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: str  # healthy, degraded, busy, unhealthy
    timestamp: str
    version: str = "Unknown"
    branch: str = "Unknown"
    application: dict = {}  # web_api_responsive, can_accept_requests, queue_size, etc.
    directories: dict = {}  # config/logs directory status and activity info
    issues: list[str] = []
    error: Optional[str] = None  # noqa: UP045


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
    app: FastAPI = field(default=None)
    is_running: Synchronized[bool] = field(default=None)
    is_running_lock: object = field(default=None)  # multiprocessing.Lock
    web_api_queue: Queue = field(default=None)
    next_scheduled_run_info: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize routes and events."""
        # Initialize FastAPI app with root_path if base_url is provided
        base_url = self.args.get("base_url", "")
        if base_url and not base_url.startswith("/"):
            base_url = "/" + base_url

        # Create lifespan context manager for startup/shutdown events
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Handle application startup and shutdown events."""
            # Startup: Start background task for queue processing
            app.state.web_api = self
            app.state.background_task = asyncio.create_task(process_queue_periodically(self))
            yield
            # Shutdown: Clean up background task
            if hasattr(app.state, "background_task"):
                app.state.background_task.cancel()
                try:
                    await app.state.background_task
                except asyncio.CancelledError:
                    pass

        # Create app with lifespan context manager
        app = FastAPI(lifespan=lifespan)
        object.__setattr__(self, "app", app)

        # Initialize paths during startup
        object.__setattr__(self, "config_path", Path(self.default_dir))
        object.__setattr__(self, "logs_path", Path(self.default_dir) / "logs")
        object.__setattr__(self, "backup_path", Path(self.default_dir) / ".backups")

        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Create API router with clean route definitions
        api_router = APIRouter()

        # Define all API routes on the router
        api_router.post("/run-command")(self.run_command)

        # Configuration management routes
        api_router.get("/configs")(self.list_configs)
        api_router.get("/configs/{filename}")(self.get_config)
        api_router.post("/configs/{filename}")(self.create_config)
        api_router.put("/configs/{filename}")(self.update_config)
        api_router.delete("/configs/{filename}")(self.delete_config)
        api_router.post("/configs/{filename}/validate")(self.validate_config)
        api_router.post("/configs/{filename}/backup")(self.backup_config)
        api_router.get("/configs/{filename}/backups")(self.list_config_backups)
        api_router.post("/configs/{filename}/restore")(self.restore_config_from_backup)
        api_router.get("/logs")(self.get_logs)
        api_router.get("/log_files")(self.list_log_files)
        api_router.get("/version")(self.get_version)
        api_router.get("/health")(self.health_check)
        api_router.get("/get_base_url")(self.get_base_url)

        # Include the API router with the appropriate prefix
        api_prefix = base_url + "/api" if base_url else "/api"
        self.app.include_router(api_router, prefix=api_prefix)

        # Mount static files for web UI
        web_ui_dir = Path(__file__).parent.parent / "web-ui"
        if web_ui_dir.exists():
            if base_url:
                # When base URL is configured, mount static files at the base URL path
                self.app.mount(f"{base_url}/static", StaticFiles(directory=str(web_ui_dir)), name="base_static")
            else:
                # Default static file mounting
                self.app.mount("/static", StaticFiles(directory=str(web_ui_dir)), name="static")

        # Root route to serve web UI
        @self.app.get("/")
        async def serve_index():
            # If base URL is configured, redirect to the base URL path
            if base_url:
                from fastapi.responses import RedirectResponse

                return RedirectResponse(url=base_url + "/", status_code=302)

            # Otherwise, serve the web UI normally
            web_ui_path = Path(__file__).parent.parent / "web-ui" / "index.html"
            if web_ui_path.exists():
                return FileResponse(str(web_ui_path))
            raise HTTPException(status_code=404, detail="Web UI not found")

        # If base URL is configured, also handle the base URL path
        if base_url:

            @self.app.get(base_url + "/")
            async def serve_base_url_index():
                web_ui_path = Path(__file__).parent.parent / "web-ui" / "index.html"
                if web_ui_path.exists():
                    return FileResponse(str(web_ui_path))
                raise HTTPException(status_code=404, detail="Web UI not found")

        # Catch-all route for SPA routing (must be last)
        @self.app.get("/{full_path:path}")
        async def catch_all(full_path: str):
            # Determine what paths should be excluded from SPA routing
            api_path = f"{base_url.lstrip('/')}/api" if base_url else "api"
            static_path = f"{base_url.lstrip('/')}/static" if base_url else "static"

            # For any non-API route that doesn't start with api/ or static/, serve the index.html (SPA routing)
            if not full_path.startswith(f"{api_path}/") and not full_path.startswith(f"{static_path}/"):
                web_ui_path = Path(__file__).parent.parent / "web-ui" / "index.html"
                if web_ui_path.exists():
                    return FileResponse(str(web_ui_path))

            raise HTTPException(status_code=404, detail="Not found")

        # Note: Lifespan events are now handled in the lifespan context manager above

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

    async def get_version(self) -> dict:
        """Get the current qBit Manage version using centralized util function"""
        try:
            version, branch = util.get_current_version()
            return {"version": version[0]}
        except Exception as e:
            logger.error(f"Error getting version: {str(e)}")
            return {"version": "Unknown"}

    async def health_check(self) -> HealthCheckResponse:
        """Health check endpoint providing application status information."""
        try:
            # Get basic application info
            version, branch = util.get_current_version()

            # Check queue status - this is more meaningful than the running flag
            # since the health check itself can't run while commands are executing
            queue_size = 0
            has_queued_requests = False
            try:
                queue_size = self.web_api_queue.qsize()
                has_queued_requests = queue_size > 0
            except Exception:
                queue_size = None
                has_queued_requests = None

            # Check if we can acquire the lock (indicates if something is running)
            # This is a non-blocking check that won't interfere with operations
            can_acquire_lock = False
            try:
                can_acquire_lock = self.is_running_lock.acquire(timeout=0.001)  # Very short timeout
                if can_acquire_lock:
                    self.is_running_lock.release()
            except Exception:
                can_acquire_lock = None

            # Check if config directory exists and has configs
            config_files_count = 0
            config_dir_exists = self.config_path.exists()
            if config_dir_exists:
                try:
                    config_files = []
                    for pattern in ["*.yml", "*.yaml"]:
                        config_files.extend([f.name for f in self.config_path.glob(pattern)])
                    config_files_count = len(config_files)
                except Exception:
                    config_files_count = None

            # Check if logs directory exists
            logs_dir_exists = self.logs_path.exists()

            # Check if we can read the most recent log file for additional health info
            recent_log_entries = 0
            last_log_time = None
            if logs_dir_exists:
                try:
                    log_file_path = self.logs_path / "qbit_manage.log"
                    if log_file_path.exists():
                        # Get last few lines to check recent activity
                        with open(log_file_path, encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                            recent_log_entries = len(lines)
                            if lines:
                                # Try to extract timestamp from last log entry
                                last_line = lines[-1].strip()
                                if last_line:
                                    # Basic check for recent activity (last line exists)
                                    last_log_time = "Recent activity detected"
                except Exception:
                    pass

            # Determine overall health status
            status = "healthy"
            issues = []

            if not config_dir_exists:
                status = "degraded"
                issues.append("Config directory not found")
            elif config_files_count == 0:
                status = "degraded"
                issues.append("No configuration files found")

            if not logs_dir_exists:
                if status == "healthy":
                    status = "degraded"
                issues.append("Logs directory not found")

            # If we can't acquire the lock, it likely means something is running
            if can_acquire_lock is False:
                if status == "healthy":
                    status = "busy"  # New status to indicate active processing

            # Get current timestamp
            current_time = datetime.now().isoformat()

            # Extract next scheduled run information
            next_run_text = None
            next_run_timestamp = None
            if self.next_scheduled_run_info:
                next_run_text = self.next_scheduled_run_info.get("next_run_str")
                # Get the actual datetime object for the next run
                next_run_datetime = self.next_scheduled_run_info.get("next_run")
                if next_run_datetime:
                    try:
                        next_run_timestamp = next_run_datetime.isoformat()
                    except Exception:
                        # If it's not a datetime object, try to parse it
                        pass

            health_info = {
                "status": status,
                "timestamp": current_time,
                "version": version[0] if version else "Unknown",
                "branch": branch if branch else "Unknown",
                "application": {
                    "web_api_responsive": True,  # If we're responding, the web API is working
                    "can_accept_requests": can_acquire_lock,  # Whether new requests can be processed immediately
                    "queue_size": queue_size,
                    "has_queued_requests": has_queued_requests,
                    "next_scheduled_run": next_run_timestamp,
                    "next_scheduled_run_text": next_run_text,
                },
                "directories": {
                    "config_dir_exists": config_dir_exists,
                    "config_files_count": config_files_count,
                    "logs_dir_exists": logs_dir_exists,
                    "recent_log_entries": recent_log_entries,
                    "last_activity": last_log_time,
                },
                "issues": issues,
            }

            return health_info

        except Exception as e:
            logger.error(f"Error in health check: {str(e)}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "issues": ["Health check failed"],
            }

    async def get_base_url(self) -> dict:
        """Get the configured base URL for the web UI."""
        return {"baseUrl": self.args.get("base_url", "")}

    async def _execute_command(self, request: CommandRequest) -> dict:
        """Execute the actual command implementation."""
        try:
            original_log_level = logger.get_level()
            if request.log_level:
                logger.set_level(request.log_level)
            logger.separator("Web API Request")
            logger.info(f"Config File: {request.config_file}")
            if request.log_level:
                logger.info(f"Log Level: {request.log_level}")
            logger.info(f"Commands: {', '.join(request.commands)}")
            logger.info(f"Dry Run: {request.dry_run}")
            logger.info(f"Hashes: {', '.join(request.hashes) if request.hashes else ''}")
            if request.skip_cleanup is not None:
                logger.info(f"Skip Cleanup: {request.skip_cleanup}")
            if request.skip_qb_version_check is not None:
                logger.info(f"Skip qBittorrent Version Check: {request.skip_qb_version_check}")

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

            # Handle optional boolean flags that override command list
            if request.skip_cleanup is not None:
                base_args["skip_cleanup"] = request.skip_cleanup
            if request.skip_qb_version_check is not None:
                base_args["skip_qb_version_check"] = request.skip_qb_version_check

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
            if "original_log_level" in locals() and logger.get_level() != original_log_level:
                logger.set_level(logging.getLevelName(original_log_level))
            # Reset flag with proper synchronization
            try:
                with self.is_running_lock:
                    self.is_running.value = False
            except Exception as e:
                # If we can't acquire the lock, force reset anyway as a safety measure
                logger.error(f"Could not acquire lock in finally block: {e}. Force resetting is_running.value")
                self.is_running.value = False

    async def list_configs(self) -> ConfigListResponse:
        """list available configuration files."""
        try:
            config_files = []

            # Find all .yml and .yaml files in config directory
            for pattern in ["*.yml", "*.yaml"]:
                config_files.extend([f.name for f in self.config_path.glob(pattern)])

            # Determine default config
            default_config = "config.yml"
            if "config.yml" not in config_files and config_files:
                default_config = config_files[0]

            return ConfigListResponse(configs=sorted(config_files), default_config=default_config)
        except Exception as e:
            logger.error(f"Error listing configs: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config(self, filename: str) -> ConfigResponse:
        """Get a specific configuration file."""
        try:
            config_file_path = self.config_path / filename

            if not config_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Configuration file '{filename}' not found")

            # Load YAML data
            yaml_loader = YAML(str(config_file_path))
            config_data = yaml_loader.data

            # Convert EnvStr objects back to !ENV syntax for frontend display
            config_data_for_frontend = self._preserve_env_syntax(config_data)

            # Get file stats
            stat = config_file_path.stat()

            return ConfigResponse(
                filename=filename,
                data=config_data_for_frontend,
                last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                size=stat.st_size,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def create_config(self, filename: str, request: ConfigRequest) -> dict:
        """Create a new configuration file."""
        try:
            config_file_path = self.config_path / filename

            if config_file_path.exists():
                raise HTTPException(status_code=409, detail=f"Configuration file '{filename}' already exists")

            # Create backup directory if it doesn't exist
            self.backup_path.mkdir(exist_ok=True)

            # Write YAML file
            self._write_yaml_config(config_file_path, request.data)

            return {"status": "success", "message": f"Configuration '{filename}' created successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_config(self, filename: str, request: ConfigRequest) -> dict:
        """Update an existing configuration file."""
        try:
            config_file_path = self.config_path / filename

            if not config_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Configuration file '{filename}' not found")

            # Create backup
            await self._create_backup(config_file_path)

            # Debug: Log what we received from frontend
            logger.trace(f"[DEBUG] Raw data received from frontend: {json.dumps(request.data, indent=2, default=str)}")

            # Convert !ENV syntax back to EnvStr objects for proper YAML serialization
            config_data_for_save = self._restore_env_objects(request.data)

            # Debug: Log what we have after restoration
            logger.trace(f"[DEBUG] Data after _restore_env_objects: {json.dumps(config_data_for_save, indent=2, default=str)}")

            # Write updated YAML file
            self._write_yaml_config(config_file_path, config_data_for_save)

            return {"status": "success", "message": f"Configuration '{filename}' updated successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_config(self, filename: str) -> dict:
        """Delete a configuration file."""
        try:
            config_file_path = self.config_path / filename

            if not config_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Configuration file '{filename}' not found")

            # Create backup before deletion
            await self._create_backup(config_file_path)

            # Delete file
            config_file_path.unlink()

            return {"status": "success", "message": f"Configuration '{filename}' deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def validate_config(self, filename: str, request: ConfigRequest) -> ValidationResponse:
        """Validate a configuration."""
        try:
            errors = []
            warnings = []

            # Create temporary config for validation
            now = datetime.now()
            temp_args = self.args.copy()
            temp_args["config_file"] = filename
            temp_args["_from_web_api"] = True
            temp_args["time"] = now.strftime("%H:%M")
            temp_args["time_obj"] = now
            temp_args["run"] = True

            # Write temporary config file for validation
            temp_config_path = self.config_path / f".temp_{filename}"
            try:
                self._write_yaml_config(temp_config_path, request.data)

                # Try to load config using existing validation logic
                try:
                    Config(self.default_dir, temp_args)
                except Exception as e:
                    errors.append(str(e))

            finally:
                # Clean up temporary file
                if temp_config_path.exists():
                    temp_config_path.unlink()

            return ValidationResponse(valid=len(errors) == 0, errors=errors, warnings=warnings)
        except Exception as e:
            logger.error(f"Error validating config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _write_yaml_config(self, config_path: Path, data: dict[str, Any]):
        """Write configuration data to YAML file."""
        from modules.util import YAML

        try:
            logger.trace(f"Attempting to write config to: {config_path}")
            logger.trace(f"[DEBUG] Full data structure being written: {json.dumps(data, indent=2, default=str)}")

            logger.trace(f"Data to write: {data}")

            # Use the custom YAML class with !ENV representer
            # Create YAML instance without loading existing file (we're writing new data)
            yaml_writer = YAML(input_data="")  # Pass empty string to avoid file loading
            yaml_writer.data = data
            yaml_writer.path = str(config_path)
            yaml_writer.save()

            logger.info(f"Successfully wrote config to: {config_path}")
        except ruamel.yaml.YAMLError as e:
            logger.error(f"YAML Error writing config to {config_path}: {e}")
            raise HTTPException(status_code=500, detail=f"YAML serialization error: {e}")
        except Exception as e:
            logger.error(f"Error writing config to {config_path}: {e}")
            raise HTTPException(status_code=500, detail=f"File write error: {e}")

    async def _create_backup(self, config_path: Path):
        """Create a backup of the configuration file."""
        self.backup_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{config_path.stem}_{timestamp}{config_path.suffix}"
        backup_file_path = self.backup_path / backup_name

        shutil.copy2(config_path, backup_file_path)
        logger.info(f"Created backup: {backup_file_path}")
        await self._cleanup_backups(config_path)

    async def _cleanup_backups(self, config_path: Path):
        """Clean up old backups for a configuration file, keeping the last 30."""
        try:
            if not self.backup_path.exists():
                return

            config_stem = config_path.stem
            config_suffix = config_path.suffix.lstrip(".")
            # Regex to precisely match backups for THIS config file.
            # Format: {stem}_{YYYYMMDD}_{HHMMSS}.{suffix}
            backup_re = re.compile(f"^{re.escape(config_stem)}_(\\d{{8}}_\\d{{6}})\\.{re.escape(config_suffix)}$")

            config_backups = [f for f in self.backup_path.iterdir() if f.is_file() and backup_re.match(f.name)]

            # sort by name descending, which works for YYYYMMDD_HHMMSS format
            sorted_backups = sorted(config_backups, key=lambda p: p.name, reverse=True)

            num_to_keep = 30
            if len(sorted_backups) > num_to_keep:
                files_to_delete = sorted_backups[num_to_keep:]
                logger.info(f"Cleaning up {len(files_to_delete)} old backups for '{config_path.name}'...")
                for f in files_to_delete:
                    try:
                        f.unlink()
                        logger.debug(f"Deleted old backup: {f.name}")
                    except OSError as e:
                        logger.warning(f"Could not delete old backup {f.name}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during backup cleanup: {e}")

    async def run_command(self, request: CommandRequest) -> dict:
        """Handle incoming command requests."""
        # Use atomic check-and-set operation
        try:
            if self.is_running_lock.acquire(timeout=0.1):
                try:
                    if self.is_running.value:
                        # Check if the process has been stuck for too long
                        if hasattr(self, "_last_run_start") and (datetime.now() - self._last_run_start).total_seconds() > 3600:
                            logger.warning("Previous run appears to be stuck. Forcing reset of is_running flag.")
                            self.is_running.value = False
                        else:
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
                    self._last_run_start = datetime.now()  # Track when this run started
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
            result = await self._execute_command(request)
            # Ensure is_running is reset after successful execution
            with self.is_running_lock:
                self.is_running.value = False
            return result
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

    async def get_logs(self, limit: Optional[int] = None, log_filename: Optional[str] = None) -> dict[str, Any]:  # noqa: UP045
        """Get recent logs from the log file."""
        if not self.logs_path.exists():
            logger.warning(f"Log directory not found: {self.logs_path}")
            return {"logs": []}

        # If no specific log_filename is provided, default to qbit_manage.log
        if log_filename is None:
            log_filename = "qbit_manage.log"

        log_file_path = self.logs_path / log_filename

        if not log_file_path.exists():
            logger.warning(f"Log file not found: {log_file_path}")
            return {"logs": []}

        logs = []
        try:
            with open(log_file_path, encoding="utf-8", errors="ignore") as f:
                # Read lines in reverse to get recent logs efficiently
                for line in reversed(f.readlines()):
                    logs.append(line.strip())
                    if limit is not None and len(logs) >= limit:
                        break
            logs.reverse()  # Put them in chronological order
            return {"logs": logs}
        except Exception as e:
            logger.error(f"Error reading log file {log_file_path}: {str(e)}")
            logger.stacktrace()
            raise HTTPException(status_code=500, detail=f"Failed to read log file: {str(e)}")

    async def list_log_files(self) -> dict:
        """List available log files."""
        if not self.logs_path.exists():
            logger.warning(f"Log directory not found: {self.logs_path}")
            return {"log_files": []}

        log_files = []
        try:
            for file_path in self.logs_path.iterdir():
                if file_path.is_file() and file_path.suffix == ".log":
                    log_files.append(file_path.name)
            return {"log_files": sorted(log_files)}
        except Exception as e:
            logger.error(f"Error listing log files in {self.logs_path}: {str(e)}")
            logger.stacktrace()
            raise HTTPException(status_code=500, detail=f"Error listing log files: {str(e)}")

    async def backup_config(self, filename: str) -> dict:
        """Create a manual backup of a configuration file."""
        try:
            config_file_path = self.config_path / filename

            if not config_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Configuration file '{filename}' not found")

            # Create backup
            await self._create_backup(config_file_path)

            # Generate backup filename for response
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{config_file_path.stem}_{timestamp}{config_file_path.suffix}"

            return {"status": "success", "message": "Manual backup created successfully", "backup_file": backup_name}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating backup for '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def list_config_backups(self, filename: str) -> dict:
        """List available backups for a configuration file."""
        try:
            if not self.backup_path.exists():
                return {"backups": []}

            # Find backup files for this config
            config_stem = Path(filename).stem
            config_suffix = Path(filename).suffix.lstrip(".")
            # Regex to precisely match backups for THIS config file.
            backup_re = re.compile(f"^{re.escape(config_stem)}_(\\d{{8}}_\\d{{6}})\\.{re.escape(config_suffix)}$")
            backup_files = [f for f in self.backup_path.iterdir() if f.is_file() and backup_re.match(f.name)]

            backups = []
            for backup_file in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True):
                # Extract timestamp from filename (format: config_YYYYMMDD_HHMMSS.yml)
                try:
                    name_parts = backup_file.stem.split("_")
                    if len(name_parts) >= 3:
                        date_str = name_parts[-2]  # YYYYMMDD
                        time_str = name_parts[-1]  # HHMMSS
                        timestamp_str = f"{date_str}_{time_str}"
                        timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    else:
                        # Fallback to file modification time
                        timestamp = datetime.fromtimestamp(backup_file.stat().st_mtime)

                    backups.append(
                        {"filename": backup_file.name, "timestamp": timestamp.isoformat(), "size": backup_file.stat().st_size}
                    )
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse backup timestamp from {backup_file.name}: {e}")
                    # Include backup with file modification time as fallback
                    timestamp = datetime.fromtimestamp(backup_file.stat().st_mtime)
                    backups.append(
                        {"filename": backup_file.name, "timestamp": timestamp.isoformat(), "size": backup_file.stat().st_size}
                    )

            return {"backups": backups}

        except Exception as e:
            logger.error(f"Error listing backups for '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def restore_config_from_backup(self, filename: str, request: dict) -> dict:
        """Restore configuration from a backup file."""
        try:
            backup_filename = request.get("backup_id")
            if not backup_filename:
                raise HTTPException(status_code=400, detail="backup_id is required")

            backup_file_path = self.backup_path / backup_filename

            if not backup_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Backup file '{backup_filename}' not found")

            # Load backup data
            yaml_loader = YAML(str(backup_file_path))
            backup_data = yaml_loader.data

            # Convert EnvStr objects back to !ENV syntax for frontend display
            backup_data_for_frontend = self._preserve_env_syntax(backup_data)

            return {
                "status": "success",
                "message": f"Backup '{backup_filename}' loaded successfully",
                "data": backup_data_for_frontend,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error restoring config '{filename}' from backup: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _preserve_env_syntax(self, data):
        """Convert EnvStr objects back to !ENV syntax for frontend display"""
        from modules.util import EnvStr

        if isinstance(data, EnvStr):
            # Return the original !ENV syntax
            return f"!ENV {data.env_var}"
        elif isinstance(data, dict):
            # Recursively process dictionary values
            return {key: self._preserve_env_syntax(value) for key, value in data.items()}
        elif isinstance(data, list):
            # Recursively process list items
            return [self._preserve_env_syntax(item) for item in data]
        else:
            # Return other types as-is
            return data

    def _restore_env_objects(self, data):
        """Convert !ENV syntax back to EnvStr objects for proper YAML serialization."""
        import os

        from modules.util import EnvStr

        if isinstance(data, str) and data.startswith("!ENV "):
            env_var = data[5:]  # Remove "!ENV " prefix
            env_value = os.getenv(env_var, "")
            return EnvStr(env_var, env_value)
        elif isinstance(data, dict):
            return {key: self._restore_env_objects(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._restore_env_objects(item) for item in data]
        else:
            return data

    def _log_env_str_values(self, data, path):
        """Helper method to log EnvStr values for debugging"""
        from modules.util import EnvStr

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                if isinstance(value, EnvStr):
                    logger.debug(f"  {current_path}: EnvStr(env_var='{value.env_var}', resolved='{str(value)}')")
                elif isinstance(value, (dict, list)):
                    self._log_env_str_values(value, current_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                if isinstance(item, EnvStr):
                    logger.debug(f"  {current_path}: EnvStr(env_var='{item.env_var}', resolved='{str(item)}')")
                elif isinstance(item, (dict, list)):
                    self._log_env_str_values(item, current_path)


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
