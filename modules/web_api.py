"""Web API module for qBittorrent-Manage"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from multiprocessing import Queue
from multiprocessing.sharedctypes import Synchronized
from pathlib import Path
from typing import Any
from typing import Optional
from typing import Union

import ruamel.yaml
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import PlainTextResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from humanize import precisedelta
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from modules import util
from modules.auth import AuthenticationMiddleware
from modules.auth import AuthSettings
from modules.auth import SecuritySettingsRequest
from modules.auth import authenticate_user
from modules.auth import generate_api_key
from modules.auth import hash_password
from modules.auth import is_local_ip
from modules.auth import load_auth_settings
from modules.auth import save_auth_settings
from modules.auth import verify_api_key
from modules.config import Config
from modules.scheduler import Scheduler
from modules.util import YAML
from modules.util import EnvStr
from modules.util import execute_qbit_commands
from modules.util import format_stats_summary
from modules.util import get_matching_config_files


class _LoggerProxy:
    def __getattr__(self, name):
        return getattr(util.logger, name)


logger = _LoggerProxy()


class CommandRequest(BaseModel):
    """Command request model."""

    config_file: str = "config.yml"
    commands: list[str]
    hashes: list[str] = field(default_factory=list)
    dry_run: bool = False
    skip_cleanup: bool = False
    skip_qb_version_check: bool = False
    log_level: Optional[str] = None


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
    config_modified: bool = False


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: str  # healthy, degraded, busy, unhealthy
    timestamp: str
    version: str = "Unknown"
    branch: str = "Unknown"
    application: dict = {}  # web_api_responsive, can_accept_requests, queue_size, etc.
    directories: dict = {}  # config/logs directory status and activity info
    issues: list[str] = []
    error: Optional[str] = None


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
                # Set is_running flag to prevent concurrent execution
                try:
                    if web_api.is_running_lock.acquire(timeout=0.1):
                        try:
                            web_api.is_running.value = True
                            object.__setattr__(web_api, "_last_run_start", datetime.now())
                        finally:
                            web_api.is_running_lock.release()
                    else:
                        # If we can't acquire the lock, skip processing this cycle
                        continue
                except Exception:
                    # If there's an error setting the flag, skip processing this cycle
                    continue
                try:
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
                finally:
                    # Always reset is_running flag after processing queue
                    try:
                        with web_api.is_running_lock:
                            web_api.is_running.value = False
                            object.__setattr__(web_api, "_last_run_start", None)
                    except Exception as e:
                        logger.error(f"Error resetting is_running flag after queue processing: {str(e)}")
            await asyncio.sleep(1)  # Check every second
    except asyncio.CancelledError:
        logger.info("Queue processing task cancelled")
        raise


async def watch_settings_file(web_api: WebAPI) -> None:
    """Monitor the settings file for changes and reload authentication settings."""
    settings_path = Path(web_api.default_dir) / "qbm_settings.yml"
    last_hash = None

    try:
        while True:
            try:
                if settings_path.exists():
                    # Calculate current file hash
                    with open(settings_path, "rb") as f:
                        current_hash = hashlib.sha256(f.read()).hexdigest()

                    # If hash has changed, reload authentication settings
                    if last_hash is not None and current_hash != last_hash:
                        logger.info("Settings file changed, reloading authentication settings")
                        AuthenticationMiddleware.force_reload_all_settings()

                    last_hash = current_hash
                else:
                    last_hash = None
            except Exception as e:
                logger.error(f"Error monitoring settings file: {e}")
                last_hash = None

            await asyncio.sleep(0.5)  # Check every 500ms for changes
    except asyncio.CancelledError:
        logger.info("Settings file watching task cancelled")
        raise


@dataclass(frozen=True)
class WebAPI:
    """Web API handler for qBittorrent-Manage."""

    default_dir: str
    args: dict = field(default_factory=dict)
    app: FastAPI = field(default=None)
    is_running: Synchronized[bool] = field(default=None)
    is_running_lock: object = field(default=None)  # multiprocessing.Lock
    web_api_queue: Queue = field(default=None)
    scheduler_update_queue: Queue = field(default=None)  # Queue for scheduler updates to main process
    next_scheduled_run_info: dict = field(default_factory=dict)
    scheduler: object = field(default=None)  # Scheduler instance

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
            # Startup: Start background tasks
            app.state.web_api = self
            app.state.queue_task = asyncio.create_task(process_queue_periodically(self))
            app.state.settings_watcher_task = asyncio.create_task(watch_settings_file(self))
            yield
            # Shutdown: Clean up background tasks
            for task_name in ["queue_task", "settings_watcher_task"]:
                if hasattr(app.state, task_name):
                    task = getattr(app.state, task_name)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        # Create app with lifespan context manager
        app = FastAPI(lifespan=lifespan)
        object.__setattr__(self, "app", app)

        # Ensure default dir is initialized
        try:
            object.__setattr__(self, "default_dir", util.ensure_config_dir_initialized(self.default_dir))
        except Exception as e:
            logger.error(f"Failed to initialize default_dir '{self.default_dir}': {e}")

        # Initialize paths during startup
        object.__setattr__(self, "config_path", Path(self.default_dir))
        object.__setattr__(self, "logs_path", Path(self.default_dir) / "logs")
        object.__setattr__(self, "backup_path", Path(self.default_dir) / ".backups")

        # Configure CORS - restrict to prevent unauthorized cross-origin access
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[],  # No cross-origin requests allowed by default
            allow_credentials=False,  # Disable credentials to prevent CSRF via CORS
            allow_methods=["GET", "POST", "PUT", "DELETE"],  # Explicit allowed methods
            allow_headers=["Authorization", "Content-Type", "X-API-Key"],  # Explicit allowed headers
        )

        # Configure Rate Limiting
        limiter = Limiter(key_func=get_remote_address)
        self.app.state.limiter = limiter
        self.app.add_middleware(SlowAPIMiddleware)

        # Add Security Headers Middleware
        @self.app.middleware("http")
        async def add_security_headers(request: Request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return response

        # Configure Authentication Middleware
        settings_path = Path(self.default_dir) / "qbm_settings.yml"
        self.app.add_middleware(AuthenticationMiddleware, settings_path=settings_path, base_url=base_url)
        logger.info(f"Authentication middleware configured with settings path: {settings_path}")

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

        # Schedule management routes
        api_router.get("/scheduler")(self.get_scheduler_status)
        api_router.put("/schedule")(self.update_schedule)
        api_router.post("/schedule/persistence/toggle")(self.toggle_schedule_persistence)

        api_router.get("/logs")(self.get_logs)
        api_router.get("/log_files")(self.list_log_files)
        api_router.get("/docs")(self.get_documentation)
        api_router.get("/version")(self.get_version)
        api_router.get("/health")(self.health_check)
        api_router.get("/get_base_url")(self.get_base_url)

        # Authentication routes
        api_router.get("/security")(self.get_security_settings)
        api_router.get("/security/status")(self.get_security_status)
        api_router.put("/security")(self.update_security_settings)

        # System management routes
        api_router.post("/system/force-reset")(self.force_reset_running_state)

        # Include the API router with the appropriate prefix
        api_prefix = base_url + "/api" if base_url else "/api"
        self.app.include_router(api_router, prefix=api_prefix)

        # Mount static files for web UI
        web_ui_dir = util.runtime_path("web-ui")
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
                return RedirectResponse(url=base_url + "/", status_code=302)

            # Otherwise, serve the web UI normally
            web_ui_path = util.runtime_path("web-ui", "index.html")
            if web_ui_path.exists():
                return FileResponse(str(web_ui_path))
            raise HTTPException(status_code=404, detail="Web UI not found")

        # If base URL is configured, also handle the base URL path
        if base_url:

            @self.app.get(base_url + "/")
            async def serve_base_url_index():
                web_ui_path = util.runtime_path("web-ui", "index.html")
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
                web_ui_path = util.runtime_path("web-ui", "index.html")
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

                execute_qbit_commands(qbit_manager, args, stats, hashes=hashes)

                return stats, cfg
            else:
                raise HTTPException(status_code=500, detail=f"Failed to initialize qBittorrent manager for {args['config_file']}")

        except Exception as e:
            logger.stacktrace()
            logger.error(f"Error executing commands for {args['config_file']}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_version(self) -> dict:
        """Get the current qBit Manage version with update availability details."""
        try:
            version, branch = util.get_current_version()
            latest_version = util.current_version(version, branch=branch)
            update_available = False
            latest_version_str = None

            if latest_version and (version[1] != latest_version[1] or (version[2] and version[2] < latest_version[2])):
                update_available = True
                latest_version_str = latest_version[0]

            return {
                "version": version[0],
                "branch": branch,
                "build": version[2],
                "latest_version": latest_version_str or version[0],
                "update_available": update_available,
            }
        except Exception as e:
            logger.error(f"Error getting version: {str(e)}")
            return {
                "version": "Unknown",
                "branch": "Unknown",
                "build": 0,
                "latest_version": None,
                "update_available": False,
            }

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

            # Define sensitive files to filter out
            sensitive_files = {"qbm_settings.yml", "secrets.yml", "credentials.yml", "auth.yml", "keys.yml", "passwords.yml"}

            # Filter out sensitive configuration files
            filtered_configs = [f for f in config_files if f not in sensitive_files]

            # Determine default config
            default_config = "config.yml"
            if "config.yml" not in filtered_configs and filtered_configs:
                default_config = filtered_configs[0]

            return ConfigListResponse(configs=sorted(filtered_configs), default_config=default_config)
        except Exception as e:
            logger.error(f"Error listing configs: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_config(self, filename: str) -> ConfigResponse:
        """Get a specific configuration file."""
        try:
            # Validate filename to prevent path traversal and block sensitive files
            config_file_path = self._validate_config_filename(filename)

            # Explicitly block access to sensitive settings file
            if filename == "qbm_settings.yml":
                raise HTTPException(status_code=403, detail="Access to settings file is forbidden")

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
            # Validate filename to prevent path traversal
            config_file_path = self._validate_config_filename(filename)

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
            # Validate filename to prevent path traversal
            config_file_path = self._validate_config_filename(filename)

            if not config_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Configuration file '{filename}' not found")

            # Create backup
            await self._create_backup(config_file_path)

            # Register sensitive fields as secrets for automatic redaction in logs
            self._register_sensitive_fields_as_secrets(request.data)

            # Debug: Log what we received from frontend (secrets will be automatically redacted)
            logger.trace(f"[DEBUG] Raw data received from frontend: {json.dumps(request.data, indent=2, default=str)}")

            # Convert !ENV syntax back to EnvStr objects for proper YAML serialization
            config_data_for_save = self._restore_env_objects(request.data)

            # Debug: Log what we have after restoration (secrets will be automatically redacted)
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
            # Validate filename to prevent path traversal
            config_file_path = self._validate_config_filename(filename)

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
        """Validate a configuration using a temporary file, but persist changes if defaults are added."""
        try:
            errors = []
            warnings = []
            config_modified = False

            # Get the actual config file path
            config_path = self.config_path / filename
            if not config_path.exists():
                raise HTTPException(status_code=404, detail=f"Config file '{filename}' not found")

            # Load original config
            original_yaml = None
            try:
                original_yaml = YAML(str(config_path))
            except Exception as e:
                logger.error(f"Error reading original config: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to read original config: {str(e)}")

            # Create temporary config file for validation
            temp_config_path = None
            try:
                # Create a temporary file in the same directory as the config
                temp_fd, temp_path = tempfile.mkstemp(suffix=".yml", dir=str(config_path.parent))
                temp_config_path = Path(temp_path)

                # Convert !ENV strings back to EnvStr objects before saving
                processed_data = self._restore_env_objects(request.data)

                # Write to temporary file for validation
                temp_yaml = YAML(str(temp_config_path))
                temp_yaml.data = processed_data
                temp_yaml.save_preserving_format(processed_data)

                # Close the file descriptor
                os.close(temp_fd)

            except Exception as e:
                logger.error(f"Error creating temporary config: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to create temporary config: {str(e)}")

            # Create validation args using the temporary file
            now = datetime.now()
            temp_args = self.args.copy()
            temp_args["config_file"] = temp_config_path.name  # Use temp file name
            temp_args["_from_web_api"] = True
            temp_args["validation_mode"] = True  # Flag to indicate this is validation, not a real run
            temp_args["time"] = now.strftime("%H:%M")
            temp_args["time_obj"] = now
            temp_args["run"] = True

            try:
                logger.separator("Configuration Validation Check", space=False, border=False)

                # Try to load config using existing validation logic
                try:
                    Config(self.default_dir, temp_args)
                except Exception as e:
                    errors.append(str(e))
                    logger.separator("Configuration Validation Failed", space=False, border=False)
                valid = len(errors) == 0
                if valid:
                    logger.separator("Configuration Valid", space=False, border=False)

                # Check if temp config was modified during validation
                try:
                    # Reload the temp config to see if it was modified
                    modified_temp_yaml = YAML(str(temp_config_path))
                    modified_temp_data = modified_temp_yaml.data.copy() if modified_temp_yaml.data else {}

                    # Compare the data structures
                    if processed_data != modified_temp_data:
                        config_modified = True
                        logger.info("Configuration was modified during validation (defaults added)")

                        # If config was modified, copy the changes to the original file
                        try:
                            original_yaml.data = modified_temp_data
                            original_yaml.save_preserving_format(modified_temp_data)
                            logger.info("Successfully applied validation changes to original config")
                        except Exception as copy_error:
                            logger.error(f"Failed to copy changes to original config: {str(copy_error)}")
                            # Don't fail the validation if we can't copy changes
                except Exception as e:
                    logger.warning(f"Error checking if config was modified: {str(e)}")

            except Exception as e:
                logger.error(f"Validation failed: {str(e)}")
                raise
            finally:
                # Clean up temporary file
                try:
                    if temp_config_path and temp_config_path.exists():
                        temp_config_path.unlink()
                        logger.debug(f"Cleaned up temporary config file: {temp_config_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temporary config file: {str(cleanup_error)}")

            # Create response with modification info
            response_data = {"valid": valid, "errors": errors, "warnings": warnings, "config_modified": config_modified}

            logger.info(f"Validation response: {response_data}")
            return ValidationResponse(**response_data)
        except Exception as e:
            logger.error(f"Error validating config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _write_yaml_config(self, config_path: Path, data: dict[str, Any]):
        """Write configuration data to YAML file while preserving formatting and comments."""

        try:
            logger.trace(f"Attempting to write config to: {config_path}")
            logger.trace(f"[DEBUG] Full data structure being written: {json.dumps(data, indent=2, default=str)}")

            logger.trace(f"Data to write: {data}")

            # Convert !ENV strings back to EnvStr objects
            processed_data = self._restore_env_objects(data)

            # Use the custom YAML class with format preservation
            if config_path.exists():
                # Load existing file to preserve formatting
                yaml_writer = YAML(path=str(config_path))
                yaml_writer.save_preserving_format(processed_data)
            else:
                # Create new file with standard formatting
                yaml_writer = YAML(input_data="")
                yaml_writer.data = processed_data
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
                        if (
                            hasattr(self, "_last_run_start")
                            and self._last_run_start is not None
                            and (datetime.now() - self._last_run_start).total_seconds() > 3600
                        ):
                            logger.warning("Previous run appears to be stuck. Forcing reset of is_running flag.")
                            self.is_running.value = False
                            object.__setattr__(self, "_last_run_start", None)  # Clear the stuck timestamp
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
                    object.__setattr__(self, "_last_run_start", datetime.now())  # Track when this run started
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
            # Reset is_running flag if it was set before the error occurred
            try:
                with self.is_running_lock:
                    self.is_running.value = False
            except Exception:
                # If we can't acquire the lock to reset, log it but continue
                logger.warning("Could not acquire lock to reset is_running flag after error")
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
                object.__setattr__(self, "_last_run_start", None)  # Clear the timestamp
            return result
        except HTTPException as e:
            # Ensure is_running is reset if an HTTPException occurs
            with self.is_running_lock:
                self.is_running.value = False
                object.__setattr__(self, "_last_run_start", None)  # Clear the timestamp
            raise e
        except Exception as e:
            # Ensure is_running is reset if any other exception occurs
            with self.is_running_lock:
                self.is_running.value = False
                object.__setattr__(self, "_last_run_start", None)  # Clear the timestamp
            logger.stacktrace()
            logger.error(f"Error in run_command during execution: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def force_reset_running_state(self) -> dict[str, Any]:
        """Force reset the is_running state. Use this to recover from stuck states."""
        try:
            with self.is_running_lock:
                was_running = self.is_running.value
                self.is_running.value = False
                object.__setattr__(self, "_last_run_start", None)

            logger.warning(f"Forced reset of is_running state. Was running: {was_running}")
            return {
                "status": "success",
                "message": f"Running state reset. Was previously running: {was_running}",
                "was_running": was_running,
            }
        except Exception as e:
            logger.error(f"Error forcing reset of running state: {str(e)}")
            return {"status": "error", "message": f"Failed to reset running state: {str(e)}", "was_running": None}

    async def get_logs(self, limit: Optional[int] = None, log_filename: Optional[str] = None) -> dict[str, Any]:
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

    async def get_documentation(self, file: str):
        """Get documentation content from markdown files."""
        try:
            # Sanitize the file path to prevent directory traversal
            safe_filename = os.path.basename(file)

            # Only allow markdown files
            if not safe_filename.endswith(".md"):
                raise HTTPException(status_code=400, detail="Only markdown files are allowed")

            # Construct the path to the docs directory
            docs_path = util.runtime_path("docs", safe_filename)

            if not docs_path.exists():
                raise HTTPException(status_code=404, detail=f"Documentation file not found: {safe_filename}")

            # Read and return the file content
            with open(docs_path, encoding="utf-8") as f:
                content = f.read()

            return PlainTextResponse(content=content, media_type="text/markdown")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error reading documentation file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error reading documentation: {str(e)}")

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

    async def restore_config_from_backup(self, filename: str) -> dict:
        """Restore configuration from a backup file."""
        try:
            # Use the filename from the URL path as the backup file to restore
            backup_filename = filename
            if not backup_filename:
                raise HTTPException(status_code=400, detail="filename is required")

            # Security: Validate and sanitize the backup_filename to prevent path traversal
            # Remove any path separators and parent directory references
            sanitized_backup_filename = os.path.basename(backup_filename)
            if not sanitized_backup_filename or sanitized_backup_filename != backup_filename:
                raise HTTPException(status_code=400, detail="Invalid filename: path traversal not allowed")

            # Additional validation: ensure the backup filename doesn't contain dangerous characters
            if any(char in sanitized_backup_filename for char in ["..", "/", "\\", "\0"]):
                raise HTTPException(status_code=400, detail="Invalid filename: contains forbidden characters")

            # Construct the backup file path safely
            backup_file_path = self.backup_path / sanitized_backup_filename

            # Security: Ensure the resolved path is still within the backup directory
            try:
                backup_file_path = backup_file_path.resolve()
                backup_dir_resolved = self.backup_path.resolve()
                if not str(backup_file_path).startswith(str(backup_dir_resolved)):
                    raise HTTPException(status_code=400, detail="Invalid filename: path traversal not allowed")
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid filename: unable to resolve path")

            if not backup_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Backup file '{sanitized_backup_filename}' not found")

            # Load backup data
            yaml_loader = YAML(str(backup_file_path))
            backup_data = yaml_loader.data

            # Convert EnvStr objects back to !ENV syntax for frontend display
            backup_data_for_frontend = self._preserve_env_syntax(backup_data)

            return {
                "status": "success",
                "message": f"Backup '{sanitized_backup_filename}' loaded successfully",
                "data": backup_data_for_frontend,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error restoring config '{filename}' from backup: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _preserve_env_syntax(self, data):
        """Convert EnvStr objects back to !ENV syntax for frontend display"""

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

    def _is_sensitive_config_file(self, filename: str) -> bool:
        """Check if a config file is sensitive and should be protected from API operations."""
        sensitive_files = {"qbm_settings.yml"}
        return filename in sensitive_files

    def _validate_config_filename(self, filename: str) -> Path:
        """Validate filename and return safe path to prevent path traversal attacks."""

        # Reject empty or None filenames
        if not filename or not isinstance(filename, str):
            raise HTTPException(status_code=400, detail="Invalid filename")

        # Reject filenames with path separators or starting with dot
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise HTTPException(status_code=400, detail="Invalid filename: path traversal detected")

        # Enforce filename pattern (alphanumeric, underscore, hyphen, dot only)
        if not re.match(r"^[A-Za-z0-9_.-]{1,64}$", filename):
            raise HTTPException(status_code=400, detail="Invalid filename: contains invalid characters")

        # Check if this is a sensitive file that should be blocked
        if self._is_sensitive_config_file(filename):
            raise HTTPException(status_code=403, detail=f"Access denied to sensitive configuration file '{filename}'")

        # Resolve the path and ensure it stays within config directory
        config_file_path = self.config_path / filename
        try:
            # Use resolve() to get absolute path and check if it's within config_path
            resolved_path = config_file_path.resolve()
            if not resolved_path.is_relative_to(self.config_path):
                raise HTTPException(status_code=403, detail="Access denied: path outside config directory")
        except (OSError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid filename")

        return config_file_path

    def _register_sensitive_fields_as_secrets(self, data):
        """Register sensitive fields as secrets for automatic redaction in logs."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in ["password", "password_hash", "api_key", "secret", "token", "key"]:
                    if isinstance(value, str) and value:
                        logger.secret(value)
                else:
                    self._register_sensitive_fields_as_secrets(value)
        elif isinstance(data, list):
            for item in data:
                self._register_sensitive_fields_as_secrets(item)

    async def get_scheduler_status(self) -> dict:
        """Get complete scheduler status including schedule configuration and persistence information."""
        try:
            # Always create a fresh scheduler instance to get current state

            fresh_scheduler = Scheduler(self.default_dir, suppress_logging=True, read_only=True)

            # Get schedule info with persistence details (uses fresh file reading)
            schedule_info = fresh_scheduler.get_schedule_info()

            # Get runtime status from shared scheduler if available, otherwise from fresh instance
            if self.scheduler:
                status = self.scheduler.get_status()
            else:
                status = fresh_scheduler.get_status()

            # Use shared next run information to prevent timing drift
            shared_next_run = None
            shared_next_run_str = None
            if hasattr(self, "next_scheduled_run_info") and self.next_scheduled_run_info:
                next_run_datetime = self.next_scheduled_run_info.get("next_run")
                shared_next_run_str = self.next_scheduled_run_info.get("next_run_str")
                # Convert datetime to ISO string
                if next_run_datetime:
                    shared_next_run = (
                        next_run_datetime.isoformat() if hasattr(next_run_datetime, "isoformat") else next_run_datetime
                    )

            # Build current_schedule object from schedule_info
            current_schedule = None
            if schedule_info.get("schedule"):
                current_schedule = {"type": schedule_info.get("type"), "value": schedule_info.get("schedule")}

            return {
                "current_schedule": current_schedule,
                "next_run": shared_next_run,
                "next_run_str": shared_next_run_str,
                "is_running": status.get("is_running", False),
                "source": schedule_info.get("source"),
                "persistent": schedule_info.get("persistent", False),
                "file_exists": schedule_info.get("file_exists", False),
                "disabled": schedule_info.get("disabled", False),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting scheduler status: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_schedule(self, request: Request) -> dict:
        """Update and persist schedule configuration with diagnostic instrumentation."""
        try:
            correlation_id = uuid.uuid4().hex[:12]
            client_host = "n/a"
            if getattr(request, "client", None):
                try:
                    client_host = request.client.host  # type: ignore[attr-defined]
                except Exception:
                    pass

            # Extract schedule data from FastAPI Request
            schedule_data = await request.json()
            schedule_value = (schedule_data.get("schedule") or "").strip()
            schedule_type = (schedule_data.get("type") or "").strip()

            logger.debug(
                f"UPDATE /schedule cid={correlation_id} client={client_host} "
                f"payload_raw_type={type(schedule_data).__name__} value={schedule_value!r} type_hint={schedule_type!r}"
            )

            if not schedule_value:
                raise HTTPException(status_code=400, detail="Schedule value is required")

            # Auto-detect type if not provided
            if not schedule_type:
                schedule_type, parsed_value = self._parse_schedule(schedule_value)
                if not schedule_type:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid schedule format. Must be a cron expression or interval in minutes",
                    )
            else:
                # Validate provided type
                if schedule_type not in ["cron", "interval"]:
                    raise HTTPException(status_code=400, detail="Schedule type must be 'cron' or 'interval'")
                # Parse & validate value
                if schedule_type == "interval":
                    try:
                        parsed_value = int(schedule_value)
                        if parsed_value <= 0:
                            raise ValueError("Interval must be positive")
                    except ValueError:
                        raise HTTPException(status_code=400, detail="Invalid interval value")
                else:
                    parsed_value = schedule_value  # cron

            scheduler = Scheduler(self.default_dir, suppress_logging=True, read_only=True)
            existed_before = scheduler.settings_file.exists()
            prev_contents = None
            if existed_before:
                try:
                    with open(scheduler.settings_file, encoding="utf-8", errors="ignore") as f:
                        prev_contents = f.read().strip()
                except Exception:
                    prev_contents = "<read_error>"

            success = scheduler.save_schedule(schedule_type, str(parsed_value))
            new_size = None
            if scheduler.settings_file.exists():
                try:
                    new_size = scheduler.settings_file.stat().st_size
                except Exception:
                    pass

            if not success:
                logger.error(f"UPDATE /schedule cid={correlation_id} failed to save schedule")
                raise HTTPException(status_code=500, detail="Failed to save schedule")

            logger.debug(
                f"UPDATE /schedule cid={correlation_id} persisted path={scheduler.settings_file} "
                f"existed_before={existed_before} new_exists={scheduler.settings_file.exists()} "
                f"new_size={new_size} prev_hash={hash(prev_contents) if prev_contents else None}"
            )

            # Send update to main process via IPC queue
            if self.scheduler_update_queue:
                try:
                    update_data = {"type": schedule_type, "value": parsed_value, "cid": correlation_id}
                    self.scheduler_update_queue.put(update_data)
                    logger.debug(f"UPDATE /schedule cid={correlation_id} IPC sent")
                except Exception as e:
                    logger.error(f"Failed IPC scheduler update cid={correlation_id}: {e}")

            return {
                "success": True,
                "message": f"Schedule saved successfully: {schedule_type}={parsed_value}",
                "schedule": str(parsed_value),
                "type": schedule_type,
                "persistent": True,
                "correlationId": correlation_id,
            }

        except HTTPException:
            raise
        except ValueError as e:
            logger.error(f"Validation error updating schedule: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error updating schedule: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_schedule_persistence(self, request: Request) -> dict:
        """
        Toggle persistent schedule enable/disable (non-destructive) with diagnostics.
        """
        try:
            correlation_id = uuid.uuid4().hex[:12]
            scheduler = Scheduler(self.default_dir, suppress_logging=True, read_only=True)
            file_exists_before = scheduler.settings_file.exists()

            # Execute toggle (scheduler emits single summary line internally)
            success = scheduler.toggle_persistence()
            if not success:
                raise HTTPException(status_code=500, detail="Failed to toggle persistence")

            disabled_after = getattr(scheduler, "_persistence_disabled", False)
            action = "disabled" if disabled_after else "enabled"

            # Notify main process with new explicit type (minimal logging)
            if self.scheduler_update_queue:
                try:
                    update_data = {"type": "toggle_persistence", "value": None, "cid": correlation_id}
                    self.scheduler_update_queue.put(update_data)
                except Exception as e:
                    logger.error(f"Failed to send scheduler toggle notification: {e}")

            return {
                "success": True,
                "message": f"Persistent schedule {action}",
                "correlationId": correlation_id,
                "fileExistedBefore": file_exists_before,
                "disabled": disabled_after,
                "action": action,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error toggling persistent schedule: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _parse_schedule(self, schedule_value: str) -> tuple[Optional[str], Optional[Union[str, int]]]:
        """
        Parse schedule value to determine type and validate format.

        Args:
            schedule_value: Raw schedule string from request

        Returns:
            tuple: (schedule_type, parsed_value) or (None, None) if invalid
        """
        try:
            # Try to parse as interval (integer minutes)
            interval_minutes = int(schedule_value)
            if interval_minutes > 0:
                return "interval", interval_minutes
        except ValueError:
            pass

        # Try to parse as cron expression
        # Basic validation: should have 5 parts (minute hour day month weekday)
        cron_parts = schedule_value.split()
        if len(cron_parts) == 5:
            # Additional validation could be added here
            # For now, we'll let the scheduler validate it
            return "cron", schedule_value

        return None, None

    def _update_next_run_info(self, next_run: datetime):
        """Update the shared next run info dictionary."""
        try:
            current_time = datetime.now()
            current = current_time.strftime("%I:%M %p")
            time_to_run_str = next_run.strftime("%Y-%m-%d %I:%M %p")
            delta_seconds = (next_run - current_time).total_seconds()
            time_until = precisedelta(timedelta(minutes=math.ceil(delta_seconds / 60)), minimum_unit="minutes", format="%d")

            next_run_info = {
                "next_run": next_run,
                "next_run_str": f"Current Time: {current} | {time_until} until the next run at {time_to_run_str}",
            }
            self.next_scheduled_run_info.update(next_run_info)

        except Exception as e:
            logger.error(f"Error updating next run info: {str(e)}")

    # Authentication methods

    async def get_security_settings(self) -> AuthSettings:
        """Get current security settings."""
        try:
            settings_path = Path(self.default_dir) / "qbm_settings.yml"
            settings = load_auth_settings(settings_path)

            # Don't return sensitive information for security
            settings.password_hash = "***" if settings.password_hash else ""
            # Don't return API key for security - it should only be shown once when generated
            settings.api_key = ""

            return settings
        except Exception as e:
            logger.error(f"Error getting security settings: {str(e)}")
            return AuthSettings()

    async def get_security_status(self) -> dict:
        """Get security status information without sensitive data."""
        try:
            settings_path = Path(self.default_dir) / "qbm_settings.yml"
            settings = load_auth_settings(settings_path)

            return {
                "has_api_key": bool(settings.api_key and settings.api_key.strip()),
                "method": settings.method,
                "enabled": settings.enabled,
            }
        except Exception as e:
            logger.error(f"Error getting security status: {str(e)}")
            return {"has_api_key": False, "method": "none", "enabled": False}

    async def update_security_settings(self, request: SecuritySettingsRequest, req: Request) -> dict[str, Any]:
        """Update security settings."""
        try:
            settings_path = Path(self.default_dir) / "qbm_settings.yml"
            current_settings = load_auth_settings(settings_path)

            # Capture original values before any modifications for audit logging
            original_settings = {
                "enabled": current_settings.enabled,
                "method": current_settings.method,
                "bypass_auth_for_local": current_settings.bypass_auth_for_local,
                "trusted_proxies": current_settings.trusted_proxies,
                "username": current_settings.username,
                "api_key": current_settings.api_key,
            }

            # DEBUG: Log the request data to understand what's being sent
            logger.trace(
                f"Security settings update request: current_api_key={bool(request.current_api_key)}, "
                f"current_username={bool(request.current_username)}, "
                f"current_password={bool(request.current_password)}"
            )
            logger.trace(
                f"Current settings: method={current_settings.method}, "
                f"has_api_key={bool(current_settings.api_key)}, "
                f"has_username={bool(current_settings.username)}"
            )

            # Check if this is initial setup (no authentication currently configured)
            is_initial_setup = not current_settings.enabled or (
                current_settings.method == "none" and not current_settings.username and not current_settings.api_key
            )

            # Check if client is local and bypass_auth_for_local is enabled
            if current_settings.bypass_auth_for_local and is_local_ip(req, current_settings.trusted_proxies):
                logger.trace("Local client with bypass_auth_for_local enabled, skipping credential verification")
                auth_verified = True
            elif is_initial_setup:
                # Allow initial setup without credentials when no authentication is configured
                logger.trace("Initial authentication setup detected, skipping credential verification")
                auth_verified = True
            else:
                # Verify current credentials for reauthentication
                auth_verified = False

            # First, try credentials provided in the request body
            # Try API key verification first
            if not auth_verified and request.current_api_key and current_settings.api_key:
                logger.trace("Attempting API key verification from request body")
                if verify_api_key(request.current_api_key, current_settings.api_key):
                    auth_verified = True
                    logger.trace("API key verification successful")
                else:
                    logger.trace("API key verification failed")
                    return {"success": False, "message": "Invalid current API key"}

            # If API key not provided or invalid, try username/password
            if not auth_verified and request.current_username and request.current_password:
                logger.trace("Attempting username/password verification from request body")
                if authenticate_user(request.current_username, request.current_password, current_settings):
                    auth_verified = True
                    logger.trace("Username/password verification successful")
                else:
                    logger.trace("Username/password verification failed")
                    return {"success": False, "message": "Invalid current username or password"}

            # If no credentials in request body, try to extract from request headers
            if not auth_verified:
                logger.trace("No credentials in request body, attempting to extract from headers")

                # Try API key from header
                api_key_header = req.headers.get("X-API-Key")
                if api_key_header and current_settings.api_key:
                    logger.trace("Attempting API key verification from X-API-Key header")
                    if verify_api_key(api_key_header, current_settings.api_key):
                        auth_verified = True
                        logger.trace("API key verification from header successful")

                # If API key header didn't work, try Basic auth from Authorization header
                if not auth_verified:
                    auth_header = req.headers.get("Authorization")
                    if auth_header and auth_header.startswith("Basic "):
                        logger.trace("Attempting Basic auth verification from Authorization header")
                        try:
                            import base64

                            encoded_credentials = auth_header.split(" ")[1]
                            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
                            username, password = decoded_credentials.split(":", 1)

                            if authenticate_user(username, password, current_settings):
                                auth_verified = True
                                logger.trace("Basic auth verification from header successful")
                            else:
                                logger.trace("Basic auth verification from header failed")
                        except Exception as e:
                            logger.warning(f"Error parsing Basic auth header: {e}")

            # If neither method worked and it's not initial setup, require authentication
            if not auth_verified and not is_initial_setup:
                logger.warning("No valid current credentials provided for security settings update")
                return {"success": False, "message": "Current credentials required to update security settings"}

            # Update settings
            current_settings.enabled = request.enabled
            current_settings.method = request.method
            current_settings.bypass_auth_for_local = request.bypass_auth_for_local
            current_settings.trusted_proxies = request.trusted_proxies
            current_settings.username = request.username

            # Handle password
            if request.password:
                current_settings.password_hash = hash_password(request.password)

            # Handle API key generation
            if request.generate_api_key:
                current_settings.api_key = generate_api_key()

            # Handle API key clearing
            if hasattr(request, "clear_api_key") and request.clear_api_key:
                current_settings.api_key = ""

            # Save settings
            if save_auth_settings(settings_path, current_settings):
                # Force reload authentication settings to ensure immediate effect
                AuthenticationMiddleware.force_reload_all_settings()

                # Audit log the security changes by comparing original with updated values
                changes = []
                if original_settings["enabled"] != current_settings.enabled:
                    changes.append(f"enabled: {original_settings['enabled']} -> {current_settings.enabled}")
                if original_settings["method"] != current_settings.method:
                    changes.append(f"method: {original_settings['method']} -> {current_settings.method}")
                if original_settings["bypass_auth_for_local"] != current_settings.bypass_auth_for_local:
                    changes.append(
                        f"bypass_auth_for_local: {original_settings['bypass_auth_for_local']} -> "
                        f"{current_settings.bypass_auth_for_local}"
                    )
                if original_settings["trusted_proxies"] != current_settings.trusted_proxies:
                    changes.append(
                        f"trusted_proxies: {original_settings['trusted_proxies']} -> {current_settings.trusted_proxies}"
                    )
                if original_settings["username"] != current_settings.username:
                    changes.append(f"username: {original_settings['username']} -> {current_settings.username}")
                if request.password:
                    changes.append("password: [CHANGED]")
                if request.generate_api_key:
                    changes.append("api_key: [GENERATED]")
                if request.clear_api_key:
                    changes.append("api_key: [CLEARED]")

                if changes:
                    logger.info(f"Security settings updated: {', '.join(changes)}")

                logger.info("Authentication settings reloaded after update")
                return {
                    "success": True,
                    "message": "Security settings updated successfully",
                    "api_key": current_settings.api_key if request.generate_api_key else None,
                }
            else:
                return {"success": False, "message": "Failed to save security settings"}

        except Exception as e:
            logger.error(f"Error updating security settings: {str(e)}")
            return {"success": False, "message": f"Error updating security settings: {str(e)}"}


def create_app(
    args: dict,
    is_running: bool,
    is_running_lock: object,
    web_api_queue: Queue,
    scheduler_update_queue: Queue,
    next_scheduled_run_info: dict,
    scheduler: object = None,
) -> FastAPI:
    """Create and return the FastAPI application."""
    # Get default_dir from args, which should be set by qbit_manage.py
    default_dir = args.get("config_dir")
    if not default_dir:
        # Fallback if not provided
        default_dir = util.ensure_config_dir_initialized(
            util.get_default_config_dir(
                args.config_files,
            )
        )

    return WebAPI(
        default_dir=default_dir,
        args=args,
        is_running=is_running,
        is_running_lock=is_running_lock,
        web_api_queue=web_api_queue,
        scheduler_update_queue=scheduler_update_queue,
        next_scheduled_run_info=next_scheduled_run_info,
        scheduler=scheduler,
    ).app
