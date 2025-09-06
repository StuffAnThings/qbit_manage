"""Authentication module for qBittorrent-Manage web UI"""

import base64
import hashlib
import re
import secrets
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import argon2
import ruamel.yaml
from fastapi import Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pydantic import validator
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from modules import util


class _LoggerProxy:
    def __getattr__(self, name):
        return getattr(util.logger, name)


logger = _LoggerProxy()

# Rate limiter for authentication attempts - using in-memory storage for simplicity
# This tracks failed authentication attempts per IP address
from collections import defaultdict

# Simple in-memory rate limiting for authentication attempts
auth_attempts = defaultdict(list)  # IP -> list of attempt timestamps
MAX_AUTH_ATTEMPTS = 10
AUTH_WINDOW_MINUTES = 1


# Authentication models
class LoginRequest(BaseModel):
    """Login request model."""

    username: str
    password: str


class AuthSettings(BaseModel):
    """Authentication settings model."""

    enabled: bool = False
    method: str = "none"  # none, basic, api_only
    bypass_auth_for_local: bool = False  # Allow access from RFC 1918 private IPs without authentication
    username: str = ""
    password_hash: str = ""
    api_key: str = ""


class AuthResponse(BaseModel):
    """Authentication response model."""

    authenticated: bool
    method: str = ""
    message: str = ""


class SecuritySettingsRequest(BaseModel):
    """Security settings update request model."""

    enabled: bool
    method: str
    bypass_auth_for_local: bool = False
    username: str = ""
    password: str = ""
    generate_api_key: bool = False
    clear_api_key: bool = False

    @validator("username")
    def username_must_be_valid(cls, v):
        if v and (len(v) < 3 or len(v) > 50):
            raise ValueError("Username must be 3-50 characters")
        if v and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        return v

    @validator("password")
    def password_must_be_strong(cls, v):
        if v and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @validator("method")
    def method_must_be_valid(cls, v):
        if v not in ["none", "basic", "api_only"]:
            raise ValueError("Method must be one of: none, basic, api_only")
        return v


# Authentication utilities
def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    ph = argon2.PasswordHasher()
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    ph = argon2.PasswordHasher()
    try:
        ph.verify(hashed, password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def verify_api_key(api_key: str, stored_key: str) -> bool:
    """Verify an API key."""
    return secrets.compare_digest(api_key, stored_key)


def is_rate_limited(request: Request) -> bool:
    """Check if the client IP is rate limited for authentication attempts."""
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now()

    # Clean old attempts (older than the window)
    cutoff_time = now - timedelta(minutes=AUTH_WINDOW_MINUTES)
    auth_attempts[client_ip] = [attempt_time for attempt_time in auth_attempts[client_ip] if attempt_time > cutoff_time]

    # Check if rate limited
    return len(auth_attempts[client_ip]) >= MAX_AUTH_ATTEMPTS


def record_auth_attempt(request: Request):
    """Record a failed authentication attempt."""
    client_ip = request.client.host if request.client else "unknown"
    auth_attempts[client_ip].append(datetime.now())


def authenticate_user(username: str, password: str, settings: AuthSettings) -> bool:
    """Authenticate a user with username and password."""
    if not settings.username or not settings.password_hash:
        return False

    if username != settings.username:
        return False

    return verify_password(password, settings.password_hash)


def is_local_ip(request: Request) -> bool:
    """Check if request is from localhost or RFC 1918 private IP ranges."""
    client_host = request.client.host if request.client else "unknown"

    # Check localhost addresses
    if client_host in ["127.0.0.1", "localhost", "::1"]:
        return True

    # Check RFC 1918 private IP ranges
    try:
        import ipaddress

        ip = ipaddress.ip_address(client_host)

        # RFC 1918 private IP ranges
        private_ranges = [
            ipaddress.ip_network("10.0.0.0/8"),  # 10.0.0.0 - 10.255.255.255
            ipaddress.ip_network("172.16.0.0/12"),  # 172.16.0.0 - 172.31.255.255
            ipaddress.ip_network("192.168.0.0/16"),  # 192.168.0.0 - 192.168.255.255
        ]

        return any(ip in network for network in private_ranges)
    except (ipaddress.AddressValueError, ValueError):
        # If IP parsing fails, assume it's not local
        return False


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for qBit Manage web UI."""

    # Class variable to store all instances for cache clearing
    _instances = []

    def __init__(self, app, settings_path: Path, base_url: str = ""):
        super().__init__(app)
        self.settings_path = settings_path
        self.base_url = base_url
        self._settings_cache = None
        self._last_settings_check = None
        self._settings_cache_duration = timedelta(seconds=1)  # Cache settings for 1 second
        self._last_modified_time = None
        self._file_hash = None  # Store file hash for more reliable change detection
        # Add this instance to the class list
        AuthenticationMiddleware._instances.append(self)

    def _calculate_file_hash(self) -> str:
        """Calculate SHA256 hash of the settings file."""
        try:
            if self.settings_path.exists():
                with open(self.settings_path, "rb") as f:
                    return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            pass
        return None

    def _load_auth_settings(self) -> AuthSettings:
        """Load authentication settings from qbm_settings.yml."""
        current_time = datetime.now()

        # Check if file has been modified using both mtime and hash
        try:
            current_modified_time = self.settings_path.stat().st_mtime
            current_file_hash = self._calculate_file_hash()

            # File has been modified if either mtime changed or hash changed
            file_modified = (self._last_modified_time is not None and current_modified_time > self._last_modified_time) or (
                self._file_hash is not None and current_file_hash != self._file_hash
            )

            if file_modified:
                # File has been modified, clear cache
                self._settings_cache = None
                self._last_settings_check = None
                logger.debug("Settings file modified, clearing cache")
        except (OSError, AttributeError):
            # If we can't check file status, continue with cache logic
            current_modified_time = None
            current_file_hash = None

        # Use cached settings if they're still fresh and file hasn't been modified
        if (
            self._settings_cache is not None
            and self._last_settings_check is not None
            and (current_time - self._last_settings_check) < self._settings_cache_duration
            and not file_modified
        ):
            return self._settings_cache

        try:
            if self.settings_path.exists():
                with open(self.settings_path, encoding="utf-8") as f:
                    data = ruamel.yaml.YAML().load(f) or {}

                auth_data = data.get("authentication", {})
                settings = AuthSettings(**auth_data)

                # Cache the settings
                self._settings_cache = settings
                self._last_settings_check = current_time
                self._last_modified_time = current_modified_time
                self._file_hash = current_file_hash
                return settings
        except Exception as e:
            logger.error(f"Error loading authentication settings: {e}")

        # Return default settings if loading fails
        return AuthSettings()

    def clear_cache(self):
        """Clear the settings cache to force reload on next request."""
        self._settings_cache = None
        self._last_settings_check = None
        self._last_modified_time = None
        self._file_hash = None
        logger.trace("Authentication cache cleared")

    def force_reload_settings(self) -> AuthSettings:
        """Force reload settings from file, bypassing cache."""
        self.clear_cache()
        return self._load_auth_settings()

    @classmethod
    def clear_all_caches(cls):
        """Clear cache for all middleware instances."""
        for instance in cls._instances:
            instance.clear_cache()

    @classmethod
    def force_reload_all_settings(cls) -> list[AuthSettings]:
        """Force reload settings for all middleware instances."""
        results = []
        for instance in cls._instances:
            results.append(instance.force_reload_settings())
        return results

    async def dispatch(self, request: Request, call_next):
        """Process authentication for each request."""
        try:
            settings = self._load_auth_settings()

            # Skip authentication for certain paths
            base_api_path = f"{self.base_url}/api" if self.base_url else "/api"
            base_static_path = f"{self.base_url}/static" if self.base_url else "/static"
            skip_auth_paths = [
                base_static_path,
                f"{base_api_path}/health",
                f"{base_api_path}/version",
                f"{base_api_path}/get_base_url",
                f"{base_api_path}/security",
                "/site.webmanifest",
            ]

            if any(request.url.path.startswith(path) for path in skip_auth_paths):
                return await call_next(request)

            # Check if authentication is required
            auth_required = False
            if settings.enabled:
                if not settings.bypass_auth_for_local or not is_local_ip(request):
                    auth_required = True

            if not auth_required:
                return await call_next(request)

            # Handle different authentication methods
            if settings.method == "basic":
                return await self._handle_basic_auth(request, call_next, settings)
            elif settings.method == "api_only":
                return await self._handle_api_only_auth(request, call_next, settings)
            else:
                # No authentication required
                return await call_next(request)

            # This should never be reached, but just in case
            logger.error("Auth middleware reached end without returning - this should not happen")
            return await call_next(request)

        except RateLimitExceeded:
            # Handle rate limit exceeded
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse("Rate limit exceeded. Try again later.", status_code=429, headers={"Retry-After": "60"})

    async def _handle_basic_auth(self, request: Request, call_next, settings: AuthSettings):
        """Handle HTTP Basic authentication with API key support for API endpoints."""

        # For API endpoints, allow API key authentication
        base_api_path = f"{self.base_url}/api" if self.base_url else "/api"
        if request.url.path.startswith(base_api_path):
            api_key = request.headers.get("X-API-Key")
            if api_key and verify_api_key(api_key, settings.api_key):
                return await call_next(request)

        # For all requests (including API), require Basic authentication
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            # Only log as debug for repeated attempts, not initial visits
            logger.trace("Basic auth: missing or invalid authorization header")
            return self._auth_challenge_response()

        try:
            # Apply rate limiting BEFORE processing credentials
            if is_rate_limited(request):
                logger.debug("Rate limit exceeded for authentication attempt")
                return PlainTextResponse("Rate limit exceeded. Try again later.", status_code=429, headers={"Retry-After": "60"})

            # Decode the base64 encoded credentials
            encoded_credentials = auth_header.split(" ")[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)

            # Verify credentials
            if username == settings.username and verify_password(password, settings.password_hash):
                return await call_next(request)
            else:
                logger.debug("Basic auth: invalid credentials")
                # Record failed authentication attempt
                record_auth_attempt(request)
                return self._auth_challenge_response()

        except Exception:
            logger.debug("Basic auth: error processing credentials")
            # Record failed authentication attempt
            record_auth_attempt(request)
            return self._auth_challenge_response()

    async def _handle_api_only_auth(self, request: Request, call_next, settings: AuthSettings):
        """Handle API-only authentication."""
        # Allow all non-API requests to pass through without authentication
        base_api_path = f"{self.base_url}/api" if self.base_url else "/api"
        if not request.url.path.startswith(base_api_path):
            return await call_next(request)

        # For API requests, require API key authentication
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            logger.debug("API-only auth: missing API key for API request")
            return PlainTextResponse(
                "API key required for API access", status_code=401, headers={"WWW-Authenticate": 'Bearer realm="qBit Manage API"'}
            )

        # Apply rate limiting BEFORE processing API key
        if is_rate_limited(request):
            logger.debug("Rate limit exceeded for API key attempt")
            return PlainTextResponse("Rate limit exceeded. Try again later.", status_code=429, headers={"Retry-After": "60"})

        if not verify_api_key(api_key, settings.api_key):
            logger.debug("API-only auth: invalid API key")
            # Record failed API key attempt
            record_auth_attempt(request)
            return PlainTextResponse(
                "Invalid API key", status_code=401, headers={"WWW-Authenticate": 'Bearer realm="qBit Manage API"'}
            )

        return await call_next(request)

    def _auth_challenge_response(self):
        """Return HTTP 401 challenge response."""
        return PlainTextResponse(
            "Authentication failed", status_code=401, headers={"WWW-Authenticate": 'Basic realm="qBit Manage"'}
        )


def load_auth_settings(settings_path: Path) -> AuthSettings:
    """Load authentication settings from qbm_settings.yml."""
    try:
        if settings_path.exists():
            with open(settings_path, encoding="utf-8") as f:
                data = ruamel.yaml.YAML().load(f) or {}

            auth_data = data.get("authentication", {})
            return AuthSettings(**auth_data)
    except Exception as e:
        logger.error(f"Error loading authentication settings: {e}")

    # Return default settings if loading fails
    return AuthSettings()


def save_auth_settings(settings_path: Path, settings: AuthSettings) -> bool:
    """Save authentication settings to qbm_settings.yml."""
    try:
        # Load existing data
        data = {}
        if settings_path.exists():
            with open(settings_path, encoding="utf-8") as f:
                data = ruamel.yaml.YAML().load(f) or {}

        # Update authentication section
        data["authentication"] = settings.model_dump()

        # Save back to file
        yaml = ruamel.yaml.YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        with open(settings_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        return True
    except Exception as e:
        logger.error(f"Error saving authentication settings: {e}")
        return False
