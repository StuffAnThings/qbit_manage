"""Simplified Scheduler module for qBittorrent-Manage"""

import math
import os
import threading
from datetime import datetime
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import Optional
from typing import Union

from modules.util import YAML

try:
    from croniter import croniter
    from humanize import precisedelta

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    croniter = None
    precisedelta = None

from modules import util

logger = util.logger


class Scheduler:
    """
    Simplified scheduler with built-in persistence support.
    Handles both cron expressions and interval scheduling with automatic persistence to qbm_settings.yml.
    """

    def __init__(self, config_dir: str = "config", suppress_logging: bool = False, read_only: bool = False):
        """Initialize the Scheduler with persistence support."""
        self.config_dir = Path(config_dir)
        self.settings_file = self.config_dir / "qbm_settings.yml"
        # Legacy file path for migration
        self.legacy_schedule_file = self.config_dir / "schedule.yml"
        self.config_dir.mkdir(exist_ok=True, parents=True)

        # Thread-safe components
        self.lock = threading.Lock()
        self.current_schedule: Optional[tuple[str, Union[str, int]]] = None
        self.next_run: Optional[datetime] = None
        self.stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._callback = None
        self._read_only = read_only

        # Persistence disabled flag (stored inside qbm_settings.yml under schedule.disabled)
        self._persistence_disabled = False

        # Load schedule on initialization (will set _persistence_disabled if file says disabled)
        self._load_schedule(suppress_logging=suppress_logging)
        if not suppress_logging:
            logger.debug("Scheduler initialized")

    def _load_schedule(self, suppress_logging: bool = False) -> bool:
        """
        Load schedule from persistent file or environment variable.

        Priority (when not disabled):
        1. qbm_settings.yml file (persistent) - new structure with 'schedule' root key
        2. schedule.yml file (legacy, will be migrated to new format)
        3. QBT_SCHEDULE environment variable (fallback)

        If 'disabled: true' in settings file, skip loading its schedule and fall back to env/none.

        Returns:
            bool: True if schedule loaded successfully
        """
        settings_path = str(self.settings_file)

        # Reset in-memory state; _persistence_disabled will be set if file indicates
        self._persistence_disabled = False

        # Check for new settings file first
        if self.settings_file.exists():
            return self._load_from_settings_file(settings_path, suppress_logging)

        # Check for legacy schedule file and migrate if found
        if self.legacy_schedule_file.exists():
            if self._migrate_legacy_schedule_file(suppress_logging):
                return self._load_from_settings_file(settings_path, suppress_logging)

        if not suppress_logging:
            logger.debug(f"No settings file found at startup (expected path: {settings_path})")
        return self._load_from_environment(suppress_logging)

    def _load_from_settings_file(self, settings_path: str, suppress_logging: bool = False) -> bool:
        """Load schedule from qbm_settings.yml file."""
        try:
            yaml_loader = YAML(settings_path)
            data = yaml_loader.data
            if data and isinstance(data, dict):
                # Handle new structure with 'schedule' root key
                schedule_data = data.get("schedule", {})

                # Read disabled flag first
                if bool(schedule_data.get("disabled")):
                    self._persistence_disabled = True
                    if not suppress_logging:
                        logger.debug(f"Persistent schedule disabled (disabled: true in {settings_path})")

                schedule_type = schedule_data.get("type")
                schedule_value = schedule_data.get("value")

                if not self._persistence_disabled and schedule_type and schedule_value is not None:
                    if self._validate_schedule(schedule_type, schedule_value):
                        self.current_schedule = (schedule_type, schedule_value)
                        if not self._read_only:
                            self.next_run = self._calculate_next_run()
                            next_run_info = calc_next_run(self.next_run)
                            logger.info(f"{next_run_info['next_run_str']}")
                        if not suppress_logging:
                            logger.debug(f"Schedule loaded from file: {schedule_type}={schedule_value} (path={settings_path})")
                        return True
                    else:
                        logger.warning(f"Invalid schedule structure in file {settings_path}: {schedule_data}")
                elif self._persistence_disabled:
                    if not suppress_logging:
                        logger.debug(f"Schedule persistence disabled in {settings_path}")
                    return False
                else:
                    logger.warning(f"qbm_settings.yml missing schedule data at {settings_path}")
            else:
                logger.warning(f"qbm_settings.yml did not contain a dict at {settings_path}")
        except Exception as e:
            logger.error(f"Error loading qbm_settings.yml at {settings_path}: {e}")
        return False

    def _migrate_legacy_schedule_file(self, suppress_logging: bool = False) -> bool:
        """Migrate legacy schedule.yml to new qbm_settings.yml format."""
        try:
            # Read legacy file
            yaml_loader = YAML(str(self.legacy_schedule_file))
            legacy_data = yaml_loader.data

            if legacy_data and isinstance(legacy_data, dict):
                # Create new structure with schedule as root key
                new_data = {
                    "schedule": {
                        "type": legacy_data.get("type"),
                        "value": legacy_data.get("value"),
                        "disabled": legacy_data.get("disabled", False),
                        "updated_at": legacy_data.get("updated_at", datetime.now().isoformat()),
                        # Remove version field from new structure
                    }
                }

                # Write new settings file
                tmp_path = self.settings_file.with_suffix(".yml.tmp")
                yaml_writer = YAML(input_data="")
                yaml_writer.data = new_data
                yaml_writer.path = str(tmp_path)
                yaml_writer.save()
                os.replace(tmp_path, self.settings_file)

                # Remove legacy file
                self.legacy_schedule_file.unlink()

                if not suppress_logging:
                    logger.info("Migrated legacy schedule.yml to qbm_settings.yml")
                return True
            else:
                logger.warning("Invalid legacy schedule.yml structure, skipping migration")
                return False
        except Exception as e:
            logger.error(f"Error migrating legacy schedule.yml: {e}")
            return False

    def _load_from_environment(self, suppress_logging: bool = False) -> bool:
        """Load schedule from environment variable as fallback."""
        # If disabled, do not attempt env override unless we want an environment fallback
        if self._persistence_disabled:
            # Attempt env fallback only if present
            env_schedule = os.getenv("QBT_SCHEDULE")
            if env_schedule:
                if not suppress_logging:
                    logger.debug(f"Attempting environment schedule while disabled: QBT_SCHEDULE={env_schedule!r}")
                if self._validate_schedule("cron", env_schedule):
                    self.current_schedule = ("cron", env_schedule)
                    if not self._read_only:
                        self.next_run = self._calculate_next_run()
                        next_run_info = calc_next_run(self.next_run)
                        logger.info(f"{next_run_info['next_run_str']}")
                    if not suppress_logging:
                        logger.debug(f"Environment schedule active (disabled persistent file): cron={env_schedule}")
                    return True
                else:
                    try:
                        interval = int(env_schedule)
                        if interval > 0:
                            self.current_schedule = ("interval", interval)
                            if not self._read_only:
                                self.next_run = self._calculate_next_run()
                                next_run_info = calc_next_run(self.next_run)
                                logger.info(f"{next_run_info['next_run_str']}")
                            if not suppress_logging:
                                logger.debug(
                                    f"Environment schedule active (disabled persistent file): interval={interval} minutes"
                                )
                            return True
                    except ValueError:
                        pass
            return False

        # Fallback to environment variable (only if not disabled)
        env_schedule = os.getenv("QBT_SCHEDULE")
        if env_schedule:
            if not suppress_logging:
                logger.debug(f"Attempting to load schedule from environment variable QBT_SCHEDULE={env_schedule!r}")
            if self._validate_schedule("cron", env_schedule):
                self.current_schedule = ("cron", env_schedule)
                if not self._read_only:
                    self.next_run = self._calculate_next_run()
                if not suppress_logging:
                    logger.debug(f"Schedule loaded from environment: cron={env_schedule}")
                return True
            else:
                try:
                    interval = int(env_schedule)
                    if interval > 0:
                        self.current_schedule = ("interval", interval)
                        if not self._read_only:
                            self.next_run = self._calculate_next_run()
                        if not suppress_logging:
                            logger.debug(f"Schedule loaded from environment: interval={interval} minutes")
                        return True
                    else:
                        logger.warning(f"QBT_SCHEDULE interval must be > 0 (got {interval})")
                except ValueError:
                    logger.warning(f"Invalid QBT_SCHEDULE environment variable (not cron or positive int): {env_schedule}")

        if not suppress_logging:
            logger.debug("No valid schedule configuration found (file + env both absent/invalid)")
        return False

    def save_schedule(self, schedule_type: str, schedule_value: Union[str, int]) -> bool:
        """
        Save schedule configuration to qbm_settings.yml (includes disabled flag).
        Always re-enables persistence (disabled flag cleared) when an explicit save is requested.
        Uses new structure with 'schedule' root key.
        """
        if not self._validate_schedule(schedule_type, schedule_value):
            logger.error(f"Invalid schedule: {schedule_type}={schedule_value}")
            return False
        try:
            # Requirement: any explicit save (e.g. via WebUI) must re-enable persistence
            if self._persistence_disabled:
                logger.debug("save_schedule: auto re-enabling persistence (was disabled)")
            self._persistence_disabled = False

            self._persist_schedule_file(schedule_type, schedule_value)
            with self.lock:
                self.current_schedule = (schedule_type, schedule_value)
                self.next_run = self._calculate_next_run()
            if self.next_run:
                next_run_info = calc_next_run(self.next_run)
                logger.info(f"Schedule saved and updated: {schedule_type}={schedule_value}")
                logger.info(f"{next_run_info['next_run_str']}")
            else:
                logger.info(f"Schedule saved and updated: {schedule_type}={schedule_value}")
            return True
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
            return False

    def toggle_persistence(self) -> bool:
        """
        Toggle persistent schedule enable/disable (non-destructive, stored in qbm_settings.yml under schedule.disabled).
        Reduced logging (no stack trace).
        """
        try:
            # Load existing file data (if any) to preserve schedule type/value
            existing_type = None
            existing_value = None
            if self.settings_file.exists():
                file_data = self._read_schedule_file()
                if file_data:
                    # Handle new structure with 'schedule' root key
                    schedule_data = file_data.get("schedule", {})
                    existing_type = schedule_data.get("type")
                    existing_value = schedule_data.get("value")

            if not self._persistence_disabled:
                # Disable persistence (set disabled true, keep schedule metadata)
                self._persistence_disabled = True
                self._persist_schedule_file(existing_type, existing_value)  # includes disabled=True
                with self.lock:
                    self.current_schedule = None
                    self.next_run = None
                # Reload with suppressed logging to avoid duplicate lines
                self._load_schedule(suppress_logging=True)
                if self.current_schedule:
                    st, sv = self.current_schedule
                    logger.info(f"Persistence disabled; active {st}={sv} (env fallback)")
                else:
                    logger.info("Persistence disabled; no active schedule")
            else:
                # Enable persistence
                self._persistence_disabled = False
                self._persist_schedule_file(existing_type, existing_value)
                self._load_schedule(suppress_logging=True)
                if self.current_schedule:
                    st, sv = self.current_schedule
                    logger.info(f"Persistence enabled; active {st}={sv}")
                else:
                    logger.info("Persistence enabled; no schedule configured")

            return True
        except Exception as e:
            logger.error(f"Failed to toggle persistent schedule: {e}")
            return False

    def _read_schedule_file(self) -> Optional[dict[str, Any]]:
        """Read qbm_settings.yml data from file without modifying scheduler state."""
        if not self.settings_file.exists():
            return None

        try:
            yaml_loader = YAML(str(self.settings_file))
            data = yaml_loader.data
            if data and isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"Error reading settings file: {e}")
        return None

    def get_schedule_info(self) -> dict[str, Any]:
        """Get detailed schedule information including source, persistence, and disabled state from qbm_settings.yml."""
        with self.lock:
            disabled = self._persistence_disabled
            file_exists = self.settings_file.exists()
            file_data = None
            if file_exists:
                try:
                    file_data = self._read_schedule_file()
                    if file_data:
                        # Handle new structure with 'schedule' root key
                        schedule_data = file_data.get("schedule", {})
                        if bool(schedule_data.get("disabled")) != disabled:
                            # Keep in-memory flag consistent with file if manual edits occurred
                            disabled = bool(schedule_data.get("disabled"))
                            self._persistence_disabled = disabled
                except Exception as e:
                    logger.error(f"Error reading settings file: {e}")

            if not disabled and file_data:
                # Handle new structure with 'schedule' root key
                schedule_data = file_data.get("schedule", {})
                schedule_type = schedule_data.get("type")
                schedule_value = schedule_data.get("value")
                return {
                    "schedule": str(schedule_value),
                    "type": schedule_type,
                    "source": self.settings_file.name,
                    "persistent": True,
                    "file_exists": True,
                    "disabled": False,
                }

            # Disabled or no file schedule active
            if self.current_schedule:
                schedule_type, schedule_value = self.current_schedule
                return {
                    "schedule": str(schedule_value),
                    "type": schedule_type,
                    "source": "QBT_SCHEDULE" if not disabled else "disabled",
                    "persistent": False,
                    "file_exists": file_exists,
                    "disabled": disabled,
                }
            else:
                return {
                    "schedule": None,
                    "type": None,
                    "source": "disabled" if disabled else None,
                    "persistent": False,
                    "file_exists": file_exists,
                    "disabled": disabled,
                }

    def update_schedule(self, schedule_type: str, schedule_value: Union[str, int], suppress_logging: bool = False) -> bool:
        """
        Update the current schedule (temporary, not persistent).

        Args:
            schedule_type: Either 'cron' or 'interval'
            schedule_value: Cron expression string or interval in minutes
            suppress_logging: If True, suppress the update log message

        Returns:
            bool: True if updated successfully
        """
        if not self._validate_schedule(schedule_type, schedule_value):
            logger.error(f"Invalid schedule: {schedule_type}={schedule_value}")
            return False

        try:
            # Store callback before stopping
            callback = self._callback
            was_running = self._is_running

            # Stop current scheduler if running
            if was_running:
                self.stop()

            # Update schedule parameters
            with self.lock:
                self.current_schedule = (schedule_type, schedule_value)
                self.next_run = self._calculate_next_run()

            # Restart scheduler if it was running before
            if was_running and callback:
                self.start(callback)

            if not suppress_logging:
                logger.info(f"Schedule updated (temporary): {schedule_type}={schedule_value}")
            return True

        except Exception as e:
            logger.error(f"Error updating schedule: {e}")
            return False

    def get_status(self) -> dict[str, Any]:
        """Get current scheduler status."""
        with self.lock:
            current_schedule = None
            next_run_str = None
            next_run_time = self.next_run

            if self.current_schedule:
                schedule_type, schedule_value = self.current_schedule
                current_schedule = {"type": schedule_type, "value": schedule_value}

                # Read-only instances should never calculate next run times to prevent drift
                # They should only display the stored next_run time from the main scheduler
                pass

            # Calculate formatted next run string if we have a next run time
            if next_run_time:
                next_run_info = calc_next_run(next_run_time)
                next_run_str = next_run_info.get("next_run_str")

            return {
                "current_schedule": current_schedule,
                "next_run": next_run_time.isoformat() if next_run_time else None,
                "next_run_str": next_run_str,
                "is_running": self._is_running,
            }

    def start(self, callback=None) -> bool:
        """Start the scheduler in a background thread."""
        if self._is_running:
            logger.warning("Scheduler is already running")
            return False

        if not self.current_schedule:
            logger.error("Cannot start scheduler without a schedule")
            return False

        self._callback = callback
        self.stop_event.clear()

        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()

        self._is_running = True
        logger.debug("Scheduler started")
        return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the scheduler gracefully."""
        if not self._is_running:
            return True

        logger.info("Stopping scheduler...")
        self.stop_event.set()

        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=timeout)

            if self._scheduler_thread.is_alive():
                logger.warning(f"Scheduler thread did not stop within {timeout} seconds")
                return False

        self._is_running = False
        logger.debug("Scheduler stopped")
        return True

    def is_running(self) -> bool:
        """Check if scheduler is currently running."""
        return self._is_running

    def get_next_run(self) -> Optional[datetime]:
        """Get the next scheduled run time."""
        with self.lock:
            # Return the stored next_run if it exists and is in the future
            # This preserves the original schedule timing
            if self.next_run and self.next_run > datetime.now():
                return self.next_run
            # Otherwise, calculate a new next run time
            return self._calculate_next_run()

    def get_current_schedule(self) -> Optional[tuple[str, Union[str, int]]]:
        """Get the current schedule configuration."""
        with self.lock:
            return self.current_schedule

    def _validate_schedule(self, schedule_type: str, schedule_value: Union[str, int]) -> bool:
        """Validate schedule parameters."""
        if schedule_type is None:
            return False
        if schedule_type not in ["cron", "interval"]:
            return False

        if schedule_type == "cron":
            if not CRONITER_AVAILABLE:
                logger.error("Cron scheduling requires croniter library")
                return False
            if not isinstance(schedule_value, str):
                return False
            try:
                croniter(schedule_value)
                return True
            except (ValueError, TypeError):
                return False

        elif schedule_type == "interval":
            try:
                if isinstance(schedule_value, str):
                    schedule_value = int(schedule_value)
                return isinstance(schedule_value, (int, float)) and schedule_value > 0
            except (ValueError, TypeError):
                return False

        return False

    def _calculate_next_run(self) -> Optional[datetime]:
        """Calculate the next run time based on current schedule."""
        if not self.current_schedule:
            return None

        schedule_type, schedule_value = self.current_schedule
        now = datetime.now()

        try:
            if schedule_type == "cron":
                if not CRONITER_AVAILABLE:
                    return None
                cron = croniter(schedule_value, now)
                return cron.get_next(datetime)

            elif schedule_type == "interval":
                # For interval schedules, calculate from current time
                # The scheduler loop will handle maintaining proper intervals
                return now + timedelta(minutes=int(schedule_value))

        except Exception as e:
            logger.error(f"Error calculating next run: {e}")

        return None

    def _persist_schedule_file(self, schedule_type: Optional[str], schedule_value: Optional[Union[str, int]]) -> None:
        """
        Internal helper to persist qbm_settings.yml including disabled flag.
        Uses new structure with 'schedule' root key. Preserves other settings in the file.
        If schedule_type/value are None (e.g., user disabled before ever saving), we still write disabled state.
        """
        # Load existing settings file to preserve other settings
        existing_data = {}
        if self.settings_file.exists():
            try:
                yaml_loader = YAML(str(self.settings_file))
                existing_data = yaml_loader.data or {}
            except Exception:
                # If we can't read existing file, start fresh
                existing_data = {}

        # Update schedule section
        schedule_data = {
            "type": schedule_type,
            "value": schedule_value,
            "disabled": self._persistence_disabled,
            "updated_at": datetime.now().isoformat(),
        }

        # Merge with existing data
        existing_data["schedule"] = schedule_data

        tmp_path = self.settings_file.with_suffix(".yml.tmp")
        yaml_writer = YAML(input_data="")
        yaml_writer.data = existing_data
        yaml_writer.path = str(tmp_path)
        yaml_writer.save()
        os.replace(tmp_path, self.settings_file)

    def _scheduler_loop(self):
        """Main scheduler loop running in background thread."""
        logger.debug("Scheduler loop started")

        while not self.stop_event.is_set():
            try:
                with self.lock:
                    current_next_run = self.next_run

                if not current_next_run:
                    if self.stop_event.wait(1.0):
                        break
                    continue

                now = datetime.now()

                if now >= current_next_run:
                    logger.info(f"Executing scheduled task at {now}")

                    # Execute callback if provided
                    if self._callback:
                        try:
                            self._callback()
                        except Exception as e:
                            logger.error(f"Error executing scheduled callback: {e}")

                    # Calculate next run time
                    with self.lock:
                        self.next_run = self._calculate_next_run()
                else:
                    # Sleep until next run or for 1 second, whichever is shorter
                    sleep_time = min(1.0, (current_next_run - now).total_seconds())
                    if sleep_time > 0:
                        if self.stop_event.wait(sleep_time):
                            break

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                if self.stop_event.wait(1.0):
                    break

        logger.debug("Scheduler loop ended")


# Utility functions


@lru_cache(maxsize=1)
def is_valid_cron_syntax(cron_expression):
    """Check if a cron expression is valid"""
    try:
        if CRONITER_AVAILABLE:
            croniter(str(cron_expression))
            return True
        return False
    except (ValueError, KeyError):
        return False


def calc_next_run(next_run_time, run_mode=False):
    """
    Calculate next run time information.

    Args:
        next_run_time: datetime object for the next scheduled run
        run_mode: boolean indicating if running in single-run mode

    Returns:
        dict: Contains next_run datetime and formatted string
    """
    current_time = datetime.now()
    current = current_time.strftime("%I:%M %p")
    time_to_run_str = next_run_time.strftime("%Y-%m-%d %I:%M %p")
    delta_seconds = (next_run_time - current_time).total_seconds()

    # Handle case where next_run_time is in the past
    if delta_seconds <= 0:
        time_until = "0 minutes"
    elif precisedelta:
        time_until = precisedelta(timedelta(minutes=math.ceil(delta_seconds / 60)), minimum_unit="minutes", format="%d")
    else:
        minutes_until = max(0, math.ceil(delta_seconds / 60))
        time_until = f"{minutes_until} minutes"

    if not run_mode:
        return {
            "next_run": next_run_time,
            "next_run_str": f"Current Time: {current} | {time_until} until the next run at {time_to_run_str}",
        }
    else:
        return {"next_run": None, "next_run_str": ""}
