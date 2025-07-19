"""
Centralized error handling for qBittorrent API exceptions
"""

import functools
import time
from typing import Any
from typing import Callable

from qbittorrentapi import APIConnectionError
from qbittorrentapi import APIError
from qbittorrentapi import Conflict409Error
from qbittorrentapi import Forbidden403Error
from qbittorrentapi import HTTP4XXError
from qbittorrentapi import HTTP5XXError
from qbittorrentapi import HTTPError
from qbittorrentapi import InternalServerError500Error
from qbittorrentapi import InvalidRequest400Error
from qbittorrentapi import LoginFailed
from qbittorrentapi import MissingRequiredParameters400Error
from qbittorrentapi import NotFound404Error
from qbittorrentapi import TorrentFileError
from qbittorrentapi import TorrentFileNotFoundError
from qbittorrentapi import TorrentFilePermissionError
from qbittorrentapi import Unauthorized401Error
from qbittorrentapi import UnsupportedMediaType415Error
from qbittorrentapi import UnsupportedQbittorrentVersion

from modules import util

logger = util.logger


class QbitAPIErrorHandler:
    """Centralized handler for qBittorrent API errors"""

    def __init__(self, config=None):
        self.config = config
        self.retry_attempts = 3
        self.retry_delay = 5  # seconds

    def handle_api_error(self, error: Exception, context: str = "") -> bool:
        """
        Handle qBittorrent API errors with appropriate logging and notifications

        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred

        Returns:
            bool: True if the error was handled gracefully, False if it should be re-raised
        """
        error_msg = f"qBittorrent API Error{f' in {context}' if context else ''}: {str(error)}"

        if isinstance(error, Forbidden403Error):
            logger.error(f"{error_msg} - Access forbidden. Check qBittorrent permissions and authentication.")
            if self.config:
                self.config.notify(f"qBittorrent access forbidden: {str(error)}", "API Error", False)
            return True

        elif isinstance(error, LoginFailed):
            logger.error(f"{error_msg} - Login failed. Check qBittorrent credentials.")
            if self.config:
                self.config.notify(f"qBittorrent login failed: {str(error)}", "Authentication Error", False)
            return True

        elif isinstance(error, APIConnectionError):
            logger.error(f"{error_msg} - Connection failed. Check qBittorrent server status.")
            if self.config:
                self.config.notify(f"qBittorrent connection failed: {str(error)}", "Connection Error", False)
            return True

        elif isinstance(error, NotFound404Error):
            logger.warning(f"{error_msg} - Resource not found. This may be expected behavior.")
            if self.config:
                self.config.notify(f"qBittorrent resource not found: {str(error)}", "API Warning", False)
            return True

        elif isinstance(error, Conflict409Error):
            logger.warning(f"{error_msg} - Resource conflict. This may be expected behavior.")
            if self.config:
                self.config.notify(f"qBittorrent resource conflict: {str(error)}", "API Warning", False)
            return True

        elif isinstance(error, TorrentFileNotFoundError):
            logger.error(f"{error_msg} - Torrent file not found.")
            if self.config:
                self.config.notify(f"Torrent file not found: {str(error)}", "File Error", False)
            return True

        elif isinstance(error, TorrentFilePermissionError):
            logger.error(f"{error_msg} - Permission denied for torrent file.")
            if self.config:
                self.config.notify(f"Torrent file permission denied: {str(error)}", "Permission Error", False)
            return True

        elif isinstance(error, TorrentFileError):
            logger.error(f"{error_msg} - Torrent file error.")
            if self.config:
                self.config.notify(f"Torrent file error: {str(error)}", "File Error", False)
            return True

        elif isinstance(error, (MissingRequiredParameters400Error, InvalidRequest400Error)):
            logger.error(f"{error_msg} - Invalid request parameters.")
            if self.config:
                self.config.notify(f"Invalid qBittorrent request parameters: {str(error)}", "Request Error", False)
            return True

        elif isinstance(error, Unauthorized401Error):
            logger.error(f"{error_msg} - Unauthorized access. Check authentication.")
            if self.config:
                self.config.notify(f"qBittorrent unauthorized access: {str(error)}", "Authentication Error", False)
            return True

        elif isinstance(error, UnsupportedMediaType415Error):
            logger.error(f"{error_msg} - Unsupported media type (invalid torrent file/URL).")
            if self.config:
                self.config.notify(f"Unsupported media type: {str(error)}", "Media Error", False)
            return True

        elif isinstance(error, InternalServerError500Error):
            logger.error(f"{error_msg} - qBittorrent internal server error.")
            if self.config:
                self.config.notify(f"qBittorrent server error: {str(error)}", "Server Error", False)
            return True

        elif isinstance(error, UnsupportedQbittorrentVersion):
            logger.error(f"{error_msg} - Unsupported qBittorrent version.")
            if self.config:
                self.config.notify(f"Unsupported qBittorrent version: {str(error)}", "Version Error", False)
            return True

        elif isinstance(error, (HTTPError, HTTP4XXError, HTTP5XXError)):
            # Catch any other HTTP errors we might have missed
            logger.error(f"{error_msg} - HTTP error (status: {getattr(error, 'http_status_code', 'unknown')}).")
            if self.config:
                self.config.notify(f"qBittorrent HTTP error: {str(error)}", "HTTP Error", False)
            return True

        elif isinstance(error, APIError):
            # Catch any other API errors we might have missed
            logger.error(f"{error_msg} - General API error.")
            if self.config:
                self.config.notify(f"qBittorrent API error: {str(error)}", "API Error", False)
            return True

        else:
            # Unknown qBittorrent API error
            logger.error(f"Unknown qBittorrent API error{f' in {context}' if context else ''}: {str(error)}")
            if self.config:
                self.config.notify(f"Unknown qBittorrent error: {str(error)}", "Unknown Error", False)
            return False


def handle_qbit_api_errors(context: str = "", retry_attempts: int = 3, retry_delay: int = 5):
    """
    Decorator to handle qBittorrent API errors with retry logic

    Args:
        context: Description of where the error occurred
        retry_attempts: Number of retry attempts for recoverable errors
        retry_delay: Delay between retry attempts in seconds
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Try to get config from args/kwargs for notifications
            config = None
            if args and hasattr(args[0], "config"):
                config = args[0].config
            elif "config" in kwargs:
                config = kwargs["config"]

            error_handler = QbitAPIErrorHandler(config)

            for attempt in range(retry_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except (
                    APIConnectionError,
                    Forbidden403Error,
                    LoginFailed,
                    NotFound404Error,
                    Conflict409Error,
                    TorrentFileError,
                    TorrentFileNotFoundError,
                    TorrentFilePermissionError,
                    UnsupportedQbittorrentVersion,
                    MissingRequiredParameters400Error,
                    InvalidRequest400Error,
                    Unauthorized401Error,
                    UnsupportedMediaType415Error,
                    InternalServerError500Error,
                    HTTPError,
                    HTTP4XXError,
                    HTTP5XXError,
                    APIError,
                ) as e:
                    # Handle the error
                    handled = error_handler.handle_api_error(e, context)

                    if not handled:
                        # Re-raise if not handled
                        raise

                    # For certain errors, don't retry
                    if isinstance(
                        e,
                        (
                            UnsupportedQbittorrentVersion,
                            MissingRequiredParameters400Error,
                            InvalidRequest400Error,
                            NotFound404Error,
                            Conflict409Error,
                            UnsupportedMediaType415Error,
                            TorrentFileNotFoundError,
                            TorrentFilePermissionError,
                        ),
                    ):
                        logger.info(f"Skipping operation due to {type(e).__name__}")
                        return None

                    # Retry for connection/auth errors
                    if attempt < retry_attempts:
                        logger.info(f"Retrying in {retry_delay} seconds... (attempt {attempt + 1}/{retry_attempts})")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"Max retry attempts ({retry_attempts}) exceeded for {context}")
                        if config:
                            config.notify(f"Max retry attempts exceeded for {context}: {str(e)}", "Retry Error", False)
                        return None

                except Exception as e:
                    # Non-qBittorrent API error, let it propagate
                    logger.error(f"Non-API error in {context}: {str(e)}")
                    if config:
                        config.notify(f"Non-API error in {context}: {str(e)}", "System Error", False)
                    raise

            return None

        return wrapper

    return decorator


def safe_execute_with_qbit_error_handling(func: Callable, context: str = "", *args, **kwargs) -> Any:
    """
    Safely execute a function with qBittorrent API error handling

    Args:
        func: Function to execute
        context: Description of the operation
        *args, **kwargs: Arguments to pass to the function

    Returns:
        Function result or None if an error occurred
    """
    try:
        # Apply the decorator dynamically
        wrapped_func = handle_qbit_api_errors(context)(func)
        return wrapped_func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Unexpected error in {context}: {str(e)}")
        logger.stacktrace()
        # Try to get config from args for notification
        config = None
        if args and hasattr(args[0], "config"):
            config = args[0].config
        elif "config" in kwargs:
            config = kwargs["config"]
        if config:
            config.notify(f"Unexpected error in {context}: {str(e)}", "System Error", False)
        return None
