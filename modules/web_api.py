"""Web API module for qBittorrent-Manage"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import queue
import re
import shutil
import tempfile
import uuid
from collections import deque
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
from urllib.parse import urlsplit

import ruamel.yaml
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from humanize import precisedelta
from pydantic import BaseModel
from pydantic import field_validator
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from modules import util
from modules.auth import INITIAL_PASSWORD_FILE
from modules.auth import SESSION_COOKIE
from modules.auth import SESSION_MAX_AGE
from modules.auth import AuthenticationMiddleware
from modules.auth import AuthSettings
from modules.auth import AuthStore
from modules.auth import RotatingSessionMiddleware
from modules.auth import SecuritySettingsRequest
from modules.auth import build_auth_router
from modules.auth import client_ip
from modules.auth import generate_api_key
from modules.auth import has_credentials
from modules.auth import hash_password_async
from modules.auth import password_ok
from modules.auth import rotate_session_secret
from modules.auth import session_is_fresh
from modules.auth import session_secret
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

LOG_FILE_PATTERN = re.compile(r"^(?P<base>.+?)(?:\.(?P<rotation>\d+))?\.log$")

REDACTED = "<redacted>"
# Files in the config folder that the config API never lists, reads, writes, deletes, or runs.
SENSITIVE_CONFIG_FILES = {
    "qbm_settings.yml",
    "schedule.yml",
    "secrets.yml",
    "credentials.yml",
    "auth.yml",
    "keys.yml",
    "passwords.yml",
}
SECRET_KEYS = {"pass", "password", "password_hash", "apikey", "api_key", "token", "secret", "client_secret", "notify_url"}


def _is_secret(key, value, in_webhooks: bool) -> bool:
    if not isinstance(value, str) or not value or value.startswith("!ENV "):
        return False
    if str(key).lower() in SECRET_KEYS:
        return True
    # Webhook URLs (Discord, Slack, ...) carry their token in the URL itself.
    return in_webhooks and value.lower().startswith(("http://", "https://"))


def redact_secrets(data, key=None, in_webhooks=False):
    """Return a copy of config data with secret values replaced by REDACTED."""
    if isinstance(data, dict):
        return {k: redact_secrets(v, k, in_webhooks or str(k).lower() == "webhooks") for k, v in data.items()}
    if isinstance(data, list):
        return [redact_secrets(item, key, in_webhooks) for item in data]
    return REDACTED if _is_secret(key, data, in_webhooks) else data


_DROP = object()
_HOST_KEYS = ("host", "url", "api_url", "base_url")


def _has_redacted(value):
    return value == REDACTED or (isinstance(value, list) and any(_has_redacted(v) for v in value))


def contained_config_path(default_dir, name: str) -> str:
    """The resolved path of a config file, which must sit inside the config directory (a symlink may not leave it)."""
    for directory in (Path("/config"), Path(default_dir)):  # the same order as get_matching_config_files
        path = (directory / name).resolve()
        if path.is_file() and path.is_relative_to(directory.resolve()):
            return str(path)
    raise HTTPException(status_code=400, detail=f"Config file {name!r} is not inside the config directory")


def _restore(new, old):
    if isinstance(new, dict):
        old_dict = old if isinstance(old, dict) else {}
        out = {}
        for key, value in new.items():
            restored = _restore(value, old_dict.get(key))
            if restored is not _DROP:
                out[key] = restored
        host_changed = any(k in new and old_dict.get(k) != new[k] for k in _HOST_KEYS)
        if host_changed and any(_has_redacted(v) for v in new.values()):
            raise HTTPException(status_code=400, detail="Enter the secret again when you change the host or URL it belongs to")
        return out
    if isinstance(new, list):
        same = isinstance(old, list) and len(old) == len(new)
        if not same and _has_redacted(new):
            raise HTTPException(status_code=400, detail="Enter the secrets in this list again")
        items = [_restore(v, old[i] if same else None) for i, v in enumerate(new)]
        return [v for v in items if v is not _DROP]
    if new == REDACTED:
        return _DROP if old is None else old
    return new


def restore_redacted(new, old):
    """Put the stored value back where the client sent REDACTED unchanged.

    A list holding a redacted value is refused when its length changed. A redacted value with no stored
    counterpart is dropped. A redacted secret whose host or URL changed is refused.
    """
    restored = _restore(new, old)
    return {} if restored is _DROP else restored


class CommandRequest(BaseModel):
    """Command request model."""

    config_file: str = "config.yml"
    commands: list[str]
    hashes: list[str] = field(default_factory=list)
    dry_run: bool = False
    skip_cleanup: bool = False
    skip_qb_version_check: bool = False
    log_level: Optional[str] = None

    @field_validator("config_file")
    @classmethod
    def config_file_must_be_a_name(cls, v):
        if not v or any(c in v for c in "/\\:") or ".." in v or os.path.isabs(v):
            raise ValueError("config_file must be a file name or pattern inside the config directory")
        if v.casefold() in util.RESERVED_FILES:
            raise ValueError("config_file cannot name the settings file")
        return v


class ConfigRequest(BaseModel):
    """Configuration request model."""

    data: dict[str, Any]
    restored_from: Optional[str] = None  # a backup the data was loaded from: its secrets fill the <redacted> values


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
    data: Optional[dict] = None  # the redacted config with the added defaults, for the editor to show and save


SCHEDULER_HEARTBEAT_MAX_AGE = timedelta(minutes=5)


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
                        except queue.Empty:
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
            yield
            # Shutdown: Clean up background tasks
            for task_name in ["queue_task"]:
                if hasattr(app.state, task_name):
                    task = getattr(app.state, task_name)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        # Create app with lifespan context manager
        app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
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

        # Login and the JSON-write check. The session middleware is added last so it runs first.
        session_secret(Path(self.default_dir))  # the cookie key file exists from startup
        settings_path = Path(self.default_dir) / "qbm_settings.yml"
        auth_store = AuthStore(settings_path)
        object.__setattr__(self, "auth_store", auth_store)
        self.app.add_middleware(AuthenticationMiddleware, store=auth_store, base_url=base_url)
        current_auth = auth_store.get()
        self.app.add_middleware(
            RotatingSessionMiddleware,
            config_dir=Path(self.default_dir),
            session_cookie=SESSION_COOKIE,
            path=base_url or "/",
            same_site="lax",
            https_only=bool(current_auth and current_auth.https_only),
            max_age=SESSION_MAX_AGE,
        )
        self.app.include_router(build_auth_router(auth_store, base_url), prefix=base_url)

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
        api_router.get("/health")(self.public_health)
        api_router.get("/health_details")(self.health_details)
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

    async def public_health(self) -> dict:
        """Anonymous health probe: the status only. No version, branch, paths, or log reads."""
        return {"status": (await self.health_check(detailed=False))["status"]}

    async def health_details(self) -> HealthCheckResponse:
        """Full health information; needs a login."""
        return await self.health_check()

    async def health_check(self, detailed: bool = True) -> HealthCheckResponse:
        """Health check providing application status information."""
        try:
            # Get basic application info
            version, branch = util.get_current_version() if detailed else (None, None)

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
            if logs_dir_exists and detailed:
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

            scheduler_alive = None
            last_run = None
            last_run_result = None
            if self.next_scheduled_run_info:
                scheduler_alive = self.next_scheduled_run_info.get("scheduler_alive")
                last_run = self.next_scheduled_run_info.get("last_run")
                last_run_result = self.next_scheduled_run_info.get("last_run_result")
                heartbeat = self.next_scheduled_run_info.get("scheduler_heartbeat")
                if scheduler_alive is False:
                    status = "unhealthy"
                    issues.append("Scheduler is not running")
                elif heartbeat and datetime.now() - datetime.fromisoformat(heartbeat) > SCHEDULER_HEARTBEAT_MAX_AGE:
                    status = "unhealthy"
                    issues.append("Scheduler heartbeat is stale")

            if not detailed:
                return {"status": status}

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
                    "scheduler_alive": scheduler_alive,
                    "last_run": last_run,
                    "last_run_result": last_run_result,
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

            config_files = [
                name
                for name in get_matching_config_files(request.config_file, self.default_dir)
                if not self._is_sensitive_config_file(name)
            ]
            if not config_files:
                raise HTTPException(status_code=400, detail=f"No config file matches {request.config_file!r}")
            config_paths = {name: contained_config_path(self.default_dir, name) for name in config_files}
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
                run_args["config_file"] = config_paths[
                    config_file
                ]  # an absolute path, so Config never looks in the working directory
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

        except HTTPException:
            raise
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

            filtered_configs = [f for f in config_files if not self._is_sensitive_config_file(f)]

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
            if self._is_sensitive_config_file(filename):
                raise HTTPException(status_code=403, detail="Access to settings file is forbidden")

            if not config_file_path.exists():
                raise HTTPException(status_code=404, detail=f"Configuration file '{filename}' not found")

            # Load YAML data
            yaml_loader = YAML(str(config_file_path))
            config_data = yaml_loader.data

            # Convert EnvStr objects back to !ENV syntax for frontend display
            config_data_for_frontend = redact_secrets(self._preserve_env_syntax(config_data))

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

            data = restore_redacted(request.data, None)  # a placeholder with nothing stored behind it is dropped

            # Create backup directory if it doesn't exist
            self.backup_path.mkdir(exist_ok=True)

            config_data_for_save = self._restore_env_objects(data)
            self._register_sensitive_fields_as_secrets(config_data_for_save)
            self._write_yaml_config(config_file_path, config_data_for_save)

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

            stored = self._preserve_env_syntax(YAML(str(self._secret_source(config_file_path, request))).data)
            request.data = restore_redacted(request.data, stored)

            # Create backup
            backup_name = await self._create_backup(config_file_path)

            # Convert !ENV syntax back to EnvStr objects for proper YAML serialization
            config_data_for_save = self._restore_env_objects(request.data)
            # Registered after !ENV resolution, so the resolved values are masked too
            self._register_sensitive_fields_as_secrets(config_data_for_save)

            # The redacted copy: json.dumps escapes quotes, backslashes, and non-ASCII, so a logged secret can
            # differ from the registered one
            logger.trace(
                f"[DEBUG] Data received from frontend: {json.dumps(redact_secrets(request.data), indent=2, default=str)}"
            )

            # Write updated YAML file
            self._write_yaml_config(config_file_path, config_data_for_save)

            return {
                "status": "success",
                "message": f"Configuration '{filename}' updated successfully",
                "backup_file": backup_name,
            }
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
        """Validate a configuration using a temporary file; defaults Config adds are returned, not saved."""
        try:
            errors = []
            warnings = []
            config_modified = False

            # Get the actual config file path
            config_path = self._validate_config_filename(filename)
            if not config_path.exists():
                raise HTTPException(status_code=404, detail=f"Config file '{filename}' not found")

            source = self._preserve_env_syntax(YAML(str(self._secret_source(config_path, request))).data)
            unredacted = restore_redacted(request.data, source)

            temp_config_path = None
            try:
                # A temporary file in the config directory, closed before the YAML writer opens it by name
                temp_fd, temp_path = tempfile.mkstemp(suffix=".yml", dir=str(config_path.parent))
                os.close(temp_fd)
                temp_config_path = Path(temp_path)
                try:
                    processed_data = self._restore_env_objects(unredacted)
                    temp_yaml = YAML(str(temp_config_path))
                    temp_yaml.data = processed_data
                    temp_yaml.save_preserving_format(processed_data)
                except Exception as e:
                    logger.error(f"Error creating temporary config: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Failed to create temporary config: {str(e)}")

                # Create validation args using the temporary file
                now = datetime.now()
                temp_args = self.args.copy()
                temp_args["config_file"] = str(temp_config_path)  # an absolute path, as in _execute_command
                temp_args["_from_web_api"] = True
                temp_args["validation_mode"] = True  # Flag to indicate this is validation, not a real run
                temp_args["time"] = now.strftime("%H:%M")
                temp_args["time_obj"] = now
                temp_args["run"] = True
                commands = processed_data.get("commands")
                # A commands section replaces env/CLI commands in a normal run, with missing keys defaulting to False.
                if isinstance(commands, dict):
                    temp_args["skip_qb_version_check"] = str(commands.get("skip_qb_version_check")).lower() == "true"

                logger.separator("Configuration Validation Check", space=False, border=False)
                try:
                    Config(self.default_dir, temp_args)
                except Exception as e:
                    errors.append(str(e))
                    logger.separator("Configuration Validation Failed", space=False, border=False)
                valid = len(errors) == 0
                if valid:
                    logger.separator("Configuration Valid", space=False, border=False)

                # Defaults that Config added go back to the editor, never to the config file: Validate does not save.
                modified_data = None
                try:
                    modified_temp_data = YAML(str(temp_config_path)).data or {}
                    if processed_data != modified_temp_data:
                        config_modified = True
                        modified_data = redact_secrets(self._preserve_env_syntax(modified_temp_data))
                        logger.info("Configuration was modified during validation (defaults added)")
                except Exception as e:
                    logger.warning(f"Error checking if config was modified: {str(e)}")
            finally:
                try:
                    if temp_config_path and temp_config_path.exists():
                        temp_config_path.unlink()
                        logger.debug(f"Cleaned up temporary config file: {temp_config_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temporary config file: {str(cleanup_error)}")

            # Create response with modification info
            response_data = {
                "valid": valid,
                "errors": errors,
                "warnings": warnings,
                "config_modified": config_modified,
                "data": modified_data,
            }

            logger.info(f"Validation response: valid={valid} errors={errors} config_modified={config_modified}")
            return ValidationResponse(**response_data)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error validating config '{filename}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _write_yaml_config(self, config_path: Path, data: dict[str, Any]):
        """Write configuration data to YAML file while preserving formatting and comments."""

        try:
            # Convert !ENV strings back to EnvStr objects
            processed_data = self._restore_env_objects(data)
            # Every caller's secrets, including resolved !ENV values, are masked before anything is logged
            self._register_sensitive_fields_as_secrets(processed_data)

            logger.trace(f"Attempting to write config to: {config_path}")
            logger.trace(
                f"[DEBUG] Full data structure being written: {json.dumps(redact_secrets(processed_data), indent=2, default=str)}"
            )

            existed = config_path.exists()
            if not existed:  # created private: config files hold passwords and API keys
                os.close(os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            elif os.name != "nt":
                os.chmod(config_path, 0o600)
            # Use the custom YAML class with format preservation
            if existed:
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

    async def _create_backup(self, config_path: Path) -> str:
        """Create a backup of the configuration file and return its name."""
        self.backup_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{config_path.stem}_{timestamp}{config_path.suffix}"
        backup_file_path = self.backup_path / backup_name

        # Created 0600 before the copy: a backup holds the same secrets as the config
        os.close(os.open(backup_file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
        if os.name != "nt":
            os.chmod(backup_file_path, 0o600)
        shutil.copyfile(config_path, backup_file_path)
        logger.info(f"Created backup: {backup_file_path}")
        await self._cleanup_backups(config_path)
        return backup_name

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
        # If no specific log_filename is provided, default to qbit_manage.log
        if log_filename is None:
            log_filename = "qbit_manage.log"

        log_file_path = self._validate_log_filename(log_filename)

        effective_limit = limit if limit is not None and limit > 0 else None
        try:
            with open(log_file_path, encoding="utf-8", errors="ignore") as f:
                # Bounded deque keeps memory usage proportional to the limit
                # instead of loading the whole file when only the tail is needed.
                tail = deque(maxlen=effective_limit)
                for line in f:
                    tail.append(line.strip())
            return {"logs": list(tail)}
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
                try:
                    self._validate_log_filename(file_path.name)
                except HTTPException:
                    continue
                log_files.append(file_path.name)
            return {"log_files": sorted(log_files, key=self._log_file_sort_key)}
        except Exception as e:
            logger.error(f"Error listing log files in {self.logs_path}: {str(e)}")
            logger.stacktrace()
            raise HTTPException(status_code=500, detail=f"Error listing log files: {str(e)}")

    def _validate_log_filename(self, filename: str) -> Path:
        """Return a contained, existing log path for an active or rotated log."""
        match = LOG_FILE_PATTERN.fullmatch(filename) if isinstance(filename, str) else None
        if (
            not filename
            or not isinstance(filename, str)
            or Path(filename).is_absolute()
            or Path(filename).name != filename
            or "\\" in filename
            or not match
            or match.group("base").endswith(".log")
        ):
            raise HTTPException(status_code=400, detail="Invalid log filename")

        logs_root = self.logs_path.resolve()
        try:
            log_file_path = (logs_root / filename).resolve()
        except (OSError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid log filename")

        if not log_file_path.is_relative_to(logs_root):
            raise HTTPException(status_code=400, detail="Invalid log filename: path outside logs directory")
        if not log_file_path.is_file():
            raise HTTPException(status_code=404, detail=f"Log file '{filename}' not found")
        return log_file_path

    @staticmethod
    def _log_file_sort_key(filename: str) -> tuple[str, int]:
        """Sort active logs before their numbered rotations."""
        match = LOG_FILE_PATTERN.fullmatch(filename)
        if match is None:
            return filename.casefold(), -1
        rotation_text = match.group("rotation")
        rotation = int(rotation_text) if rotation_text is not None else -1
        return match.group("base").casefold(), rotation

    async def backup_config(self, filename: str) -> dict:
        """Create a manual backup of a configuration file."""
        try:
            config_file_path = self._validate_config_filename(filename)

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

    def _secret_source(self, config_path: Path, request: ConfigRequest) -> Path:
        return self._backup_file(request.restored_from) if request.restored_from else config_path

    def _backup_file(self, name: str) -> Path:
        """The path of a backup file, which must be a plain file name inside the backups directory."""
        if not name or os.path.basename(name) != name or any(c in name for c in ["..", "/", "\\", "\0"]):
            raise HTTPException(status_code=400, detail="Invalid filename: path traversal not allowed")
        path = (self.backup_path / name).resolve()
        if not path.is_relative_to(self.backup_path.resolve()):  # a string prefix would accept .backups_other/
            raise HTTPException(status_code=400, detail="Invalid filename: path traversal not allowed")
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Backup file '{name}' not found")
        return path

    async def restore_config_from_backup(self, filename: str) -> dict:
        """Restore configuration from a backup file."""
        try:
            backup_file_path = self._backup_file(filename)
            sanitized_backup_filename = backup_file_path.name

            # Load backup data
            yaml_loader = YAML(str(backup_file_path))
            backup_data = yaml_loader.data

            # Convert EnvStr objects back to !ENV syntax for frontend display
            backup_data = self._preserve_env_syntax(backup_data)
            backup_data_for_frontend = redact_secrets(backup_data)

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
        # Only YAML configs: this also keeps out the first-run password file and the session and key files.
        name = filename.lower()
        return name in SENSITIVE_CONFIG_FILES or not name.endswith((".yml", ".yaml"))

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
            if not resolved_path.is_relative_to(self.config_path.resolve()):
                raise HTTPException(status_code=403, detail="Access denied: path outside config directory")
        except (OSError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid filename")

        return resolved_path  # the checked path, so a symlink swapped after the check cannot redirect the write

    def _register_sensitive_fields_as_secrets(self, data, key=None, in_webhooks=False):
        """Register sensitive fields as secrets for automatic redaction in logs."""
        if isinstance(data, dict):
            for k, value in data.items():
                self._register_sensitive_fields_as_secrets(value, k, in_webhooks or str(k).lower() == "webhooks")
        elif isinstance(data, list):
            for item in data:
                self._register_sensitive_fields_as_secrets(item, key, in_webhooks)
        elif _is_secret(key, data, in_webhooks) or (str(key).lower() == "key" and isinstance(data, str) and data):
            logger.secret(data)
        elif isinstance(data, str) and "@" in data:
            try:
                password = urlsplit(data if "://" in data else f"//{data}").password  # user:pass@host
            except ValueError:
                password = None
            if password:
                logger.secret(password)

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

    async def get_security_settings(self) -> dict:
        """Current security settings without secrets."""
        settings = self.auth_store.get()
        if settings is None:
            return {"mode": "", "usable": False}
        data = settings.model_dump(exclude={"password_hash", "api_key", "oidc_client_secret"})
        data.update(
            usable=True,
            has_password=bool(settings.password_hash),
            # The same rule as _reauth_problem: a leftover hash in OIDC-only mode cannot confirm a change.
            reauth_with_password=bool(settings.password_hash) and (settings.mode != "oidc" or settings.allow_local_login),
            has_api_key=bool(settings.api_key),
            has_oidc_client_secret=bool(settings.oidc_client_secret),
        )
        return data

    async def get_security_status(self) -> dict:
        """Security status without sensitive data."""
        settings = self.auth_store.get()
        return {
            "has_api_key": bool(settings and settings.api_key),
            "mode": settings.mode if settings else "",
            "method": settings.mode if settings else "",
            "enabled": settings is not None,
        }

    async def _reauth_problem(self, settings, request: SecuritySettingsRequest, req: Request) -> str:
        """Why a change is refused, or "" when the caller has just proved who they are."""
        if settings.password_hash and (settings.mode != "oidc" or settings.allow_local_login):
            if not request.current_password:  # nothing to check yet: ask for it without spending a guess
                return "Enter your current password"
            ok = await password_ok(client_ip(req, settings), settings.username, request.current_password, settings)
            if ok is None:
                return "Too many failed attempts. Try again later."
            return "" if ok else "Current password is wrong"
        if getattr(req.state, "auth_method", "") != "session" or not session_is_fresh(req):
            return "Sign in again with OpenID Connect, then retry within 5 minutes"
        return ""

    async def update_security_settings(self, request: SecuritySettingsRequest, req: Request):
        """Update security settings. An API key cannot call this.

        Every change needs the current password, or a fresh OIDC login when there is no usable local password, and
        rotates the session key, which signs out every browser.
        """
        if getattr(req.state, "auth_method", "") == "api_key":
            raise HTTPException(status_code=403, detail="Security settings cannot be changed with an API key")
        settings = self.auth_store.get()
        if settings is None:
            return _refused(503, "Authentication settings are unusable; fix qbm_settings.yml")
        updated = settings.model_copy(deep=True)
        try:
            updated.mode = request.mode or {"basic": "local", "api_only": "api_only", "external": "local"}.get(
                request.method, settings.mode
            )
            for name in (
                "public_url",
                "https_only",
                "allow_local_login",
                "oidc_metadata_url",
                "oidc_client_id",
                "oidc_sub",
                "oidc_email",
                "trusted_proxies",
            ):
                if name in request.model_fields_set:  # a field the client did not send keeps its value
                    setattr(updated, name, getattr(request, name))
            if request.oidc_client_secret:
                updated.oidc_client_secret = request.oidc_client_secret
            if request.username:
                updated.username = request.username
            AuthSettings.model_validate(updated.model_dump())
        except ValueError as e:
            return _refused(400, str(e))

        changed = (
            bool(request.password)
            or request.generate_api_key
            or request.clear_api_key
            or bool(request.oidc_client_secret)
            or updated != settings
        )
        if changed:
            problem = await self._reauth_problem(settings, request, req)
            if problem:
                return _refused(429 if problem.startswith("Too many") else 403, problem)
        if request.password:
            updated.password_hash = await hash_password_async(request.password)
        if request.generate_api_key:
            updated.api_key = generate_api_key()
        if request.clear_api_key:
            updated.api_key = ""
        if not has_credentials(updated):
            return _refused(400, "These settings leave no way to log in")
        if not await run_in_threadpool(self.auth_store.save, updated, settings):
            return _refused(
                500, "Failed to save security settings; they may have changed in another session, so reload and retry"
            )
        if changed:
            rotate_session_secret(Path(self.default_dir))
        if request.password:
            (Path(self.default_dir) / INITIAL_PASSWORD_FILE).unlink(missing_ok=True)
        logger.info(f"Security settings updated by {getattr(req.state, 'auth_method', 'unknown')} login")
        return {
            "success": True,
            "message": "Security settings updated successfully",
            "api_key": updated.api_key if request.generate_api_key else None,
        }


def _refused(status: int, message: str) -> JSONResponse:
    """A refused security change: an error status that keeps the {success, message} body."""
    return JSONResponse(status_code=status, content={"success": False, "message": message})


def build_uvicorn_config(app, host: str, port: int):
    """Uvicorn config that never lets request headers rewrite the peer address: auth reads the raw TCP peer."""
    import uvicorn

    return uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False, proxy_headers=False)


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
