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

import yaml

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
    Handles both cron expressions and interval scheduling with automatic persistence.
    """

    def __init__(self, config_dir: str = "config", suppress_logging: bool = False, read_only: bool = False):
        """Initialize the Scheduler with persistence support."""
        self.config_dir = Path(config_dir)
        self.schedule_file = self.config_dir / "schedule.yml"
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

        # Load schedule on initialization
        self._load_schedule(suppress_logging=suppress_logging)
        if not suppress_logging:
            logger.debug("Scheduler initialized")

    def _load_schedule(self, suppress_logging: bool = False) -> bool:
        """
        Load schedule from persistent file or environment variable.

        Priority:
        1. schedule.yml file (persistent)
        2. QBT_SCHEDULE environment variable (fallback)

        Args:
            suppress_logging: If True, suppress info logging during load

        Returns:
            bool: True if schedule loaded successfully
        """
        # Try loading from schedule.yml first
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and isinstance(data, dict):
                        schedule_type = data.get("type")
                        schedule_value = data.get("value")

                        if schedule_type and schedule_value is not None:
                            if self._validate_schedule(schedule_type, schedule_value):
                                self.current_schedule = (schedule_type, schedule_value)
                                if not self._read_only:
                                    self.next_run = self._calculate_next_run()
                                if not suppress_logging:
                                    logger.info(f"Schedule loaded from file: {schedule_type}={schedule_value}")
                                return True
                            else:
                                logger.warning(f"Invalid schedule in {self.schedule_file}")
            except Exception as e:
                logger.error(f"Error loading schedule.yml: {e}")

        # Fallback to environment variable
        env_schedule = os.getenv("QBT_SCHEDULE")
        if env_schedule:
            # Try as cron first, then as interval
            if self._validate_schedule("cron", env_schedule):
                self.current_schedule = ("cron", env_schedule)
                if not self._read_only:
                    self.next_run = self._calculate_next_run()
                if not suppress_logging:
                    logger.info(f"Schedule loaded from environment: cron={env_schedule}")
                return True
            else:
                try:
                    interval = int(env_schedule)
                    if interval > 0:
                        self.current_schedule = ("interval", interval)
                        if not self._read_only:
                            self.next_run = self._calculate_next_run()
                        if not suppress_logging:
                            logger.info(f"Schedule loaded from environment: interval={interval} minutes")
                        return True
                except ValueError:
                    logger.warning(f"Invalid QBT_SCHEDULE environment variable: {env_schedule}")

        if not suppress_logging:
            logger.debug("No valid schedule configuration found")
        return False

    def save_schedule(self, schedule_type: str, schedule_value: Union[str, int]) -> bool:
        """
        Save schedule configuration to persistent file.

        Args:
            schedule_type: Either 'cron' or 'interval'
            schedule_value: Cron expression string or interval in minutes

        Returns:
            bool: True if saved successfully
        """
        if not self._validate_schedule(schedule_type, schedule_value):
            logger.error(f"Invalid schedule: {schedule_type}={schedule_value}")
            return False

        try:
            data = {"type": schedule_type, "value": schedule_value, "updated_at": datetime.now().isoformat(), "version": 1}

            with open(self.schedule_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

            # Update current schedule
            with self.lock:
                self.current_schedule = (schedule_type, schedule_value)
                self.next_run = self._calculate_next_run()

            # Log with formatted next run information
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

    def delete_schedule(self) -> bool:
        """Delete the persistent schedule file and reload from environment variable."""
        try:
            if self.schedule_file.exists():
                self.schedule_file.unlink()
                logger.info("Persistent schedule deleted")

                # Reload schedule from environment variable
                with self.lock:
                    self.current_schedule = None
                    self.next_run = None

                # Try to load from environment variable
                self._load_schedule()

                if self.current_schedule:
                    logger.info("Scheduler reloaded from environment variable")
                    # Log formatted next run information
                    if self.next_run:
                        next_run_info = calc_next_run(self.next_run)
                        logger.info(f"{next_run_info['next_run_str']}")
                else:
                    logger.info("No environment variable found - scheduler stopped")

            return True
        except Exception as e:
            logger.error(f"Failed to delete schedule file: {e}")
            return False

    def _read_schedule_file(self) -> Optional[dict[str, Any]]:
        """Read schedule data from file without modifying scheduler state."""
        if not self.schedule_file.exists():
            return None

        try:
            with open(self.schedule_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error(f"Error reading schedule file: {e}")
        return None

    def get_schedule_info(self) -> dict[str, Any]:
        """Get detailed schedule information including source and persistence status."""
        with self.lock:
            # Always check file first for most up-to-date data
            if self.schedule_file.exists():
                try:
                    # Read current file contents
                    file_data = self._read_schedule_file()
                    if file_data:
                        schedule_type = file_data.get("type")
                        schedule_value = file_data.get("value")
                        source = self.schedule_file.name  # Show actual filename
                        persistent = True

                        return {
                            "schedule": str(schedule_value),
                            "type": schedule_type,
                            "source": source,
                            "persistent": persistent,
                            "file_exists": True,
                        }
                except Exception as e:
                    logger.error(f"Error reading schedule file: {e}")
                    # Fall through to use in-memory data

            # Fall back to in-memory schedule (environment variable or no schedule)
            if self.current_schedule:
                schedule_type, schedule_value = self.current_schedule
                source = "QBT_SCHEDULE"  # Environment variable
                persistent = False

                return {
                    "schedule": str(schedule_value),
                    "type": schedule_type,
                    "source": source,
                    "persistent": persistent,
                    "file_exists": self.schedule_file.exists(),
                }
            else:
                return {
                    "schedule": None,
                    "type": None,
                    "source": None,
                    "persistent": False,
                    "file_exists": self.schedule_file.exists(),
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
            return self.next_run

    def get_current_schedule(self) -> Optional[tuple[str, Union[str, int]]]:
        """Get the current schedule configuration."""
        with self.lock:
            return self.current_schedule

    def _validate_schedule(self, schedule_type: str, schedule_value: Union[str, int]) -> bool:
        """Validate schedule parameters."""
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
                return now + timedelta(minutes=int(schedule_value))

        except Exception as e:
            logger.error(f"Error calculating next run: {e}")

        return None

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
