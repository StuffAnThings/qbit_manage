"""Authentication for the qBit Manage web server.

A login is always required while the web server is on. Modes:
  local     login form that checks an Argon2 hash and sets a signed session cookie
  oidc      single-user OpenID Connect login (Authlib); the local password is break-glass only
  api_only  X-Api-Key or HTTP Basic on /api, no browser login

Every mode also accepts the API key (X-Api-Key) and HTTP Basic on /api. Failed logins are limited per client
address. Browser writes need a JSON content type and must come from this site (Sec-Fetch-Site, else Origin);
API key requests are exempt.
"""

import asyncio
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import tempfile
import threading
import time
import weakref
from base64 import b64decode
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import argon2
import httpx2
import itsdangerous
import ruamel.yaml
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic
from fastapi.security import HTTPBasicCredentials
from fastapi.security.utils import get_authorization_scheme_param
from limits import RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import ValidationError
from pydantic import field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from modules import util
from modules.util import settings_lock  # noqa: F401  (re-exported: one lock for every qbm_settings.yml writer)


class _LoggerProxy:
    def __getattr__(self, name):
        return getattr(util.logger, name)


logger = _LoggerProxy()

MODES = ("local", "oidc", "api_only")
LEGACY_METHODS = {"basic": "local", "external": "local", "api_only": "local", "none": "local"}
MAX_AUTH_ATTEMPTS = 10
INITIAL_PASSWORD_FILE = "qbm_initial_password.txt"
SESSION_KEY_FILE = ".qbm_session_key"
SESSION_COOKIE = "qbm_session"
SESSION_MAX_AGE = 7 * 24 * 3600
REAUTH_SECONDS = 300  # an OIDC-only owner must have signed in this recently to change security settings
UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
BODY_METHODS = ("POST", "PUT", "PATCH")

_attempts = MemoryStorage()  # expired entries are dropped by the storage
_limiter = MovingWindowRateLimiter(_attempts)
_FAILURE_LIMIT = RateLimitItemPerMinute(MAX_AUTH_ATTEMPTS)  # failed logins per client address per minute


class _Utf8Basic(HTTPBasic):
    """HTTPBasic parsing with UTF-8 credentials (RFC 7617; the stock class decodes ASCII only)."""

    async def __call__(self, request):
        try:
            return await super().__call__(request)
        except HTTPException as refusal:
            scheme, param = get_authorization_scheme_param(request.headers.get("Authorization"))
            try:
                username, separator, password = b64decode(param).decode("utf-8").partition(":")
            except ValueError:  # not base64 or not UTF-8
                raise refusal from None
            if scheme.lower() != "basic" or not separator:
                raise refusal from None
            return HTTPBasicCredentials(username=username, password=password)


_basic = _Utf8Basic(auto_error=False)


def _clean_error(e: Exception) -> str:
    """An error message without the rejected input values (a pydantic error repeats them, passwords included)."""
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors(include_input=False))
    return str(e)


class AuthSettingsError(ValueError):
    """The authentication settings are missing, unreadable, or unusable."""


# --- Settings ------------------------------------------------------------------------------------------


def check_public_url(v: str, strip_path: bool = False) -> str:
    """Empty, or an http(s) URL with a host and no path (the base URL is added to it for the OIDC callback).

    A stored value has its path stripped so an existing install keeps working; a new value with a path is refused.
    """
    if v:
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("public_url must start with http:// or https:// and include a host name")
        if (parts.path.strip("/") or parts.query or parts.fragment) and not strip_path:
            raise ValueError("public_url takes the scheme and host only, for example https://qbm.example.com")
        v = f"{parts.scheme}://{parts.netloc}"
    return v


def check_metadata_url(v: str) -> str:
    """Empty, or an https URL. Plain http is allowed only to a loopback host (a provider on the same machine)."""
    if v:
        parts = urlsplit(v)
        host = (parts.hostname or "").lower()
        try:
            loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not host or not (parts.scheme == "https" or (parts.scheme == "http" and loopback)):
            raise ValueError("oidc_metadata_url must be an https:// URL (http:// only for localhost)")
    return v


def check_trusted_proxies(v: list) -> list:
    """Each entry must be an IP address or a CIDR network."""
    for entry in v:
        try:
            ipaddress.ip_network(str(entry).strip(), strict=False)
        except ValueError:
            raise ValueError(f"trusted_proxies entry {str(entry)[:50]!r} is not an IP address or CIDR network") from None
    return [str(entry).strip() for entry in v]


def check_password_strength(v: str) -> str:
    """Raise ValueError unless v is 8+ characters with 3 of: upper, lower, digit, special (!@#$%^&*)."""
    if v:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        kinds = [bool(re.search(p, v)) for p in (r"[A-Z]", r"[a-z]", r"\d", r"[!@#$%^&*]")]
        if sum(kinds) < 3:
            raise ValueError(
                "Password must contain at least 3 of: uppercase letters, lowercase letters, numbers, "
                "special characters (!@#$%^&*)"
            )
    return v


class AuthSettings(BaseModel):
    """The `authentication` section of qbm_settings.yml."""

    model_config = ConfigDict(extra="ignore")

    mode: str = "local"
    username: str = ""
    password_hash: str = ""
    api_key: str = ""
    public_url: str = ""
    https_only: bool = False
    allow_local_login: bool = False  # oidc break-glass
    oidc_metadata_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_sub: str = ""
    oidc_claim_first_login: bool = False
    trusted_proxies: list[str] = []  # peers whose X-Forwarded-For names the client

    @field_validator("public_url")
    @classmethod
    def public_url_must_be_a_url(cls, v):
        return check_public_url(v, strip_path=True)

    @field_validator("trusted_proxies")
    @classmethod
    def trusted_proxies_must_be_networks(cls, v):
        return check_trusted_proxies(v)

    @field_validator("oidc_metadata_url")
    @classmethod
    def metadata_url_must_be_https(cls, v):
        return check_metadata_url(v)

    @field_validator("mode")
    @classmethod
    def mode_must_be_known(cls, v):
        if v not in MODES:
            raise ValueError(f"mode must be one of: {', '.join(MODES)}")
        return v


class SecuritySettingsRequest(BaseModel):
    """Security settings update request."""

    mode: str = ""
    method: str = ""  # legacy name for mode
    username: str = ""
    password: str = ""
    current_password: str = ""
    public_url: str = ""
    https_only: bool = False
    allow_local_login: bool = False
    oidc_metadata_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_sub: str = ""
    oidc_claim_first_login: bool = False
    trusted_proxies: list[str] = []
    generate_api_key: bool = False
    clear_api_key: bool = False

    @field_validator("public_url")
    @classmethod
    def public_url_must_be_a_url(cls, v):
        return check_public_url(v)

    @field_validator("trusted_proxies")
    @classmethod
    def trusted_proxies_must_be_networks(cls, v):
        return check_trusted_proxies(v)

    @field_validator("oidc_metadata_url")
    @classmethod
    def metadata_url_must_be_https(cls, v):
        return check_metadata_url(v)

    @field_validator("username")
    @classmethod
    def username_must_be_valid(cls, v):
        if v and not re.fullmatch(r"[a-zA-Z0-9_-]{3,50}", v):
            raise ValueError("Username must be 3-50 letters, numbers, underscores, or hyphens")
        return v

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v):
        return check_password_strength(v)


class OidcDiscoveryRequest(BaseModel):
    """OpenID Connect discovery check request."""

    oidc_metadata_url: str = ""

    @field_validator("oidc_metadata_url")
    @classmethod
    def metadata_url_must_be_https(cls, v):
        return check_metadata_url(v)


def _read_yaml(path: Path) -> dict:
    """Parse a settings file; a missing or empty file is {}. Raises on invalid YAML."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = ruamel.yaml.YAML(typ="safe").load(f) or {}
    if not isinstance(data, dict):
        raise AuthSettingsError("settings file is not a mapping")
    return data


def _normalize(section) -> dict:
    """Map the 4.x keys (enabled, method, bypass_auth_for_local) to the current ones."""
    if not isinstance(section, dict):
        raise AuthSettingsError("authentication section is missing")
    section = dict(section)
    legacy = "mode" not in section or section.get("mode") == "external"
    if legacy and isinstance(section.get("trusted_proxies"), list):
        # 4.x accepted host names here and never used them; refusing them now would stop the web server on upgrade.
        kept = []
        for entry in section["trusted_proxies"]:
            try:
                kept.extend(check_trusted_proxies([entry]))
            except ValueError:
                logger.warning(
                    f"trusted_proxies entry {clean_for_log(entry, 50)!r} is not an IP address or CIDR network; dropped"
                )
        section["trusted_proxies"] = kept
    if "method" in section and "mode" not in section:
        method = section.pop("method")
        if method not in LEGACY_METHODS:
            raise AuthSettingsError(f"unknown method {method!r}")
        section["mode"] = "local" if section.get("enabled") is False else LEGACY_METHODS[method]
    if section.pop("bypass_auth_for_local", False):
        logger.warning("bypass_auth_for_local was removed in 5.0: every request needs a login now.")
    if section.get("mode") == "external":
        section["mode"] = "local"
        logger.warning(
            "External mode was removed in 5.0; using local login (see qbm_initial_password.txt if no password was set)."
        )
    for key in ("enabled", "method"):
        section.pop(key, None)
    return section


def has_credentials(s: AuthSettings) -> bool:
    """True when the settings let someone in through their mode."""
    local = bool(s.username and s.password_hash)
    if s.mode == "local":
        return local
    if s.mode == "oidc":
        return bool(s.oidc_metadata_url and s.oidc_client_id and s.public_url and (s.oidc_sub or s.oidc_claim_first_login))
    return bool(s.api_key) or local


def load_settings(path: Path) -> AuthSettings:
    """Load usable authentication settings or raise AuthSettingsError."""
    if os.name != "nt" and path.exists():
        try:
            if path.stat().st_mode & 0o077:
                os.chmod(path, 0o600)  # holds the API key and OIDC secret; an upgrade can leave it world-readable
        except OSError as e:
            logger.warning(f"Could not restrict permissions on {path}: {e}")
    try:
        settings = AuthSettings(**_normalize(_read_yaml(path).get("authentication")))
    except AuthSettingsError:
        raise
    except Exception as e:
        raise AuthSettingsError(str(e)) from e
    if not has_credentials(settings):
        raise AuthSettingsError("no usable credentials for mode " + settings.mode)
    return settings


def dump_auth_settings(settings: AuthSettings) -> dict:
    """Serialize authentication settings for qbm_settings.yml, omitting empty/default optional keys."""
    return {"mode": settings.mode, **settings.model_dump(exclude_defaults=True)}


def save_auth_settings(path: Path, settings: AuthSettings, expected: AuthSettings | None = None) -> bool:
    """Write the authentication section atomically (0600), keeping the rest of the file.

    With `expected`, the write is refused when the stored section no longer equals it (another session saved first).
    """
    tmp = None
    try:
        with settings_lock(path):
            data = _read_yaml(path)  # an unparseable file is never overwritten
            if expected is not None and AuthSettings(**_normalize(data.get("authentication"))) != expected:
                logger.warning("Security settings changed while this change was being made; not saved")
                return False
            data["authentication"] = dump_auth_settings(settings)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".qbm_settings.", suffix=".tmp")  # created 0600
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                ruamel.yaml.YAML().dump(data, f)
            os.replace(tmp, path)
        return True
    except Exception as e:
        logger.error(f"Error saving authentication settings: {e}")
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
        return False


class AuthStore:
    """Settings reader that reparses qbm_settings.yml only when the file changes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._key = None
        self._settings = None
        self._lock = threading.Lock()

    def get(self):
        """Return the settings, or None when they are unusable (callers fail closed)."""
        with self._lock:
            try:
                st = self.path.stat()
                key = (st.st_mtime_ns, st.st_size, st.st_ino)
            except OSError:
                self._key, self._settings = None, None
                return None
            if key != self._key:
                try:
                    self._settings = load_settings(self.path)
                except AuthSettingsError as e:
                    logger.error(f"Authentication settings unusable, denying web requests until fixed: {e}")
                    self._settings = None
                self._key = key
            return self._settings

    def save(self, settings: AuthSettings, expected: AuthSettings | None = None) -> bool:
        ok = save_auth_settings(self.path, settings, expected)  # not under self._lock: the file lock can wait
        with self._lock:
            self._key = None
        return ok


# --- Credentials ---------------------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return argon2.PasswordHasher().hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return argon2.PasswordHasher().verify(hashed, password)
    except (argon2.exceptions.VerificationError, argon2.exceptions.InvalidHashError):
        return False


_DUMMY_HASH = hash_password("dummy-password-for-constant-time")


def check_login(username: str, password: str, settings: AuthSettings) -> bool:
    """Check a username and password; spends the same time when the user is unknown."""
    if not settings.username or not settings.password_hash:
        verify_password(password, _DUMMY_HASH)
        return False
    user_ok = hmac.compare_digest(username.encode(), settings.username.encode())
    pass_ok = verify_password(password, settings.password_hash if user_ok else _DUMMY_HASH)
    return user_ok and pass_ok


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def api_key_ok(key: str, settings: AuthSettings) -> bool:
    return bool(settings.api_key) and hmac.compare_digest(key.encode(), settings.api_key.encode())


def clean_for_log(value, limit: int = 100) -> str:
    """Make a client-supplied value safe for one log line."""
    return re.sub(r"[\x00-\x1f\x7f]", "?", str(value))[:limit]


# --- Session key -----------------------------------------------------------------------------------------


_session_keys: dict = {}  # config dir -> signing key; a rotation in this process updates it, so requests read no file


def _write_key(key_path: Path) -> str:
    key = secrets.token_urlsafe(48)
    fd, tmp = tempfile.mkstemp(dir=key_path.parent, prefix=".qbm_key.")  # created 0600
    with os.fdopen(fd, "w") as f:
        f.write(key)
    os.replace(tmp, key_path)
    _session_keys[key_path.parent.resolve()] = key
    return key


def session_secret(config_dir: Path) -> str:
    """Return the cookie signing key, kept in its own 0600 file outside qbm_settings.yml."""
    key_path = Path(config_dir) / SESSION_KEY_FILE
    key = key_path.read_text(encoding="utf-8").strip() if key_path.exists() else ""
    if len(key) < 32:  # missing, empty, or truncated by a crash: make a new one rather than sign with a weak key
        return _write_key(key_path)
    if os.name != "nt" and key_path.stat().st_mode & 0o077:
        os.chmod(key_path, 0o600)
    _session_keys[key_path.parent.resolve()] = key
    return key


def rotate_session_secret(config_dir: Path) -> None:
    """Replace the cookie signing key, which signs out every browser."""
    _write_key(Path(config_dir) / SESSION_KEY_FILE)


class RotatingSessionMiddleware(SessionMiddleware):
    """Starlette's session cookie, re-keyed when the key file changes (a password change signs out every device)."""

    def __init__(self, app, config_dir: Path, **kwargs):
        self.config_dir = Path(config_dir).resolve()
        self._key = session_secret(self.config_dir)
        super().__init__(app, secret_key=self._key, **kwargs)

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            key = _session_keys.get(self.config_dir, self._key)
            if key != self._key:
                self._key, self.signer = key, itsdangerous.TimestampSigner(key)
        await super().__call__(scope, receive, send)


# --- First run and environment credentials ------------------------------------------------------------


def ensure_credentials(path: Path, env) -> bool:
    """Make sure a login exists before the web server starts. Returns False when it cannot start safely.

    QBT_WEB_USERNAME and QBT_WEB_PASSWORD seed the login when none exists; QBT_WEB_PASSWORD_RESET=true
    replaces an existing password. With neither, a password is generated into a 0600 file.
    """
    try:
        raw = _read_yaml(path).get("authentication")
        settings = AuthSettings(**_normalize(raw)) if raw else AuthSettings()
    except Exception as e:
        logger.error(f"Web server not started: cannot read the authentication settings in {path}: {_clean_error(e)}")
        return False
    if settings.mode == "oidc" and settings.oidc_claim_first_login and not settings.oidc_sub:
        logger.warning(
            "oidc_claim_first_login is enabled: the next successful OpenID Connect sign-in will be bound as the allowed user."
        )
    overrides = {}
    if env.get("QBT_PUBLIC_URL"):
        overrides["public_url"] = env["QBT_PUBLIC_URL"].strip()
    if env.get("QBT_TRUSTED_PROXIES"):
        overrides["trusted_proxies"] = [e for e in env["QBT_TRUSTED_PROXIES"].split(",") if e.strip()]
    if overrides:
        try:
            SecuritySettingsRequest(**overrides)
            updated = AuthSettings(**{**settings.model_dump(), **overrides})
        except ValueError as e:
            logger.error(f"Web server not started: QBT_PUBLIC_URL/QBT_TRUSTED_PROXIES rejected: {_clean_error(e)}")
            return False
        if updated != settings:
            if raw and not save_auth_settings(path, updated):
                return False
            raw = raw or updated.model_dump()
            settings = updated
            logger.info(f"Web settings set from {', '.join('QBT_' + k.upper() for k in overrides)}")
    username, password = env.get("QBT_WEB_USERNAME", ""), env.get("QBT_WEB_PASSWORD", "")
    if bool(username) != bool(password):
        logger.warning("QBT_WEB_USERNAME and QBT_WEB_PASSWORD must both be set; ignoring the one that is set.")
    reset = str(env.get("QBT_WEB_PASSWORD_RESET", "")).lower() in ("1", "true", "t", "yes")
    has_login = bool(settings.username and settings.password_hash)
    if reset and has_login and username == settings.username and verify_password(password, settings.password_hash):
        if settings.mode == "oidc" and not settings.allow_local_login:
            # Recovery with the existing password: open break-glass, but sign no one out (the password is unchanged).
            settings.allow_local_login = True
            if not save_auth_settings(path, settings):
                return False
            logger.warning(
                "QBT_WEB_PASSWORD_RESET turned on the local break-glass login for OpenID Connect mode. Unset it, or "
                "break-glass turns on again at every start."
            )
            return True
        # Left set after a reset, it would otherwise sign everyone out on every restart.
        logger.info("QBT_WEB_PASSWORD_RESET ignored: the stored login already uses this password. Unset it.")
        reset, username, password = False, "", ""
    if username and password and (reset or not has_login):
        try:
            SecuritySettingsRequest(username=username, password=password)
        except ValueError as e:
            logger.error(f"Web server not started: QBT_WEB_USERNAME/QBT_WEB_PASSWORD rejected: {_clean_error(e)}")
            return False
        settings.username, settings.password_hash = username, hash_password(password)
        if reset and settings.mode == "oidc" and not settings.allow_local_login:
            settings.allow_local_login = True  # recovery when the OIDC provider is unreachable or misconfigured
            logger.warning("QBT_WEB_PASSWORD_RESET turned on the local break-glass login for OpenID Connect mode.")
        if not save_auth_settings(path, settings):
            return False
        rotate_session_secret(path.parent)  # sign out every session, OIDC ones included
        (path.parent / INITIAL_PASSWORD_FILE).unlink(missing_ok=True)  # its password no longer works
        logger.info("Web login set from QBT_WEB_USERNAME/QBT_WEB_PASSWORD")
        return True
    if username and password:
        logger.info("QBT_WEB_USERNAME/QBT_WEB_PASSWORD ignored: a login exists. Set QBT_WEB_PASSWORD_RESET=true to replace it.")
    if has_credentials(settings):
        return True
    if raw and settings.mode != "local":
        logger.error(f"Web server not started: authentication mode {settings.mode} is not fully configured in {path}")
        return False
    password = secrets.token_urlsafe(15)
    settings.mode, settings.username, settings.password_hash = "local", "admin", hash_password(password)
    password_file = path.parent / INITIAL_PASSWORD_FILE
    fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        if os.name != "nt":
            os.fchmod(fd, 0o600)  # the mode argument above applies only when the file is new
        f.write(f"username: admin\npassword: {password}\n")
    if not save_auth_settings(path, settings):
        return False
    logger.info(f"First run: generated a web login. Read the password from {password_file}; it is deleted when you change it.")
    return True


def web_server_off_notice(path: Path) -> str:
    """One WARNING line for installs that used the web UI before 5.0, where the web server is now off by default."""
    try:
        if "authentication" in _read_yaml(path):
            return "The web server is off. Since 5.0.0 it must be enabled with --web-server or QBT_WEB_SERVER=true."
    except Exception:
        pass
    return ""


# --- Client address and rate limiting -------------------------------------------------------------------


def _networks(entries) -> list:
    return [ipaddress.ip_network(e, strict=False) for e in entries]


def _trusted(address: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return False
    return any(ip in n for n in networks)


def client_ip(request: Request, settings: "AuthSettings | None" = None) -> str:
    """The client address. The TCP peer, unless the peer is a trusted proxy: then the right-most X-Forwarded-For
    entry that is not itself a trusted proxy (entries further left are client-supplied and can be forged)."""
    peer = request.client.host if request.client else "unknown"
    networks = _networks(settings.trusted_proxies) if settings and settings.trusted_proxies else []
    if not networks or not _trusted(peer, networks):
        return peer
    hops = [h.strip() for h in ",".join(request.headers.getlist("x-forwarded-for")).split(",") if h.strip()]
    for hop in reversed(hops):
        if not _trusted(hop, networks):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer
    return peer  # every hop is a trusted proxy; the left-most entry could still be client-supplied


def is_rate_limited(ip: str) -> bool:
    return not _limiter.test(_FAILURE_LIMIT, ip)


def record_failure(ip: str) -> None:
    _limiter.hit(_FAILURE_LIMIT, ip)


# One password check or hash at a time for the whole process, per event loop. Each Argon2 call takes 64 MiB, and the
# limit check, the check, and the failure count must run as one step or a burst of guesses all pass the limit together.
_password_locks = weakref.WeakKeyDictionary()


def _password_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _password_locks.get(loop)
    if lock is None:
        lock = _password_locks[loop] = asyncio.Lock()
    return lock


async def password_ok(ip: str, username: str, password: str, settings: AuthSettings):
    """Check a password against the per-address failure limit. Returns True, False, or None when limited."""
    async with _password_lock():
        if is_rate_limited(ip):
            return None
        if await run_in_threadpool(check_login, username, password, settings):
            return True
        record_failure(ip)
        return False


async def hash_password_async(password: str) -> str:
    async with _password_lock():
        return await run_in_threadpool(hash_password, password)


def _limited_response():
    return PlainTextResponse("Rate limit exceeded. Try again later.", status_code=429, headers={"Retry-After": "60"})


# --- OIDC ----------------------------------------------------------------------------------------------

OIDC_STATE_MAX = 1000
OIDC_CLIENTS_MAX = 64
OIDC_DISCOVERY_MAX_BYTES = 256 * 1024


class _OidcStateCache:
    """Authlib's server-side store for pending OIDC logins (state, nonce, PKCE verifier).

    The session cookie keeps only a marker, so a copied pre-callback cookie cannot replay a state: get() removes
    the entry. At most OIDC_STATE_MAX logins are pending; the oldest is dropped first.
    """

    def __init__(self):
        self._items = {}  # key -> (expiry, value), in insertion order

    async def peek(self, key):
        entry = self._items.get(key)
        if not entry:
            return None
        expires, value = entry
        if expires <= time.monotonic():
            self._items.pop(key, None)
            return None
        return value

    async def get(self, key):
        expires, value = self._items.pop(key, (0, None))
        return value if expires > time.monotonic() else None

    async def set(self, key, value, expires_in):
        now = time.monotonic()
        self._items = {k: v for k, v in self._items.items() if v[0] > now}
        while len(self._items) >= OIDC_STATE_MAX:
            del self._items[next(iter(self._items))]
        self._items[key] = (now + expires_in, value)

    async def delete(self, key):
        self._items.pop(key, None)


_oidc_states = _OidcStateCache()
_oidc_link_pending = _OidcStateCache()
_oidc_link_results = _OidcStateCache()
_oidc_clients = {}


def hit_oidc_limit(bucket: str, ip: str) -> bool:
    """Record and check an OIDC rate-limit hit for a given bucket and client IP."""
    return _limiter.hit(_FAILURE_LIMIT, bucket, ip)


def resolve_oidc_client_secret(submitted_secret: str, metadata_url: str, client_id: str, stored: AuthSettings) -> str:
    """Use the submitted secret, or keep the stored secret only when the provider URL and client ID are unchanged."""
    if submitted_secret:
        return submitted_secret
    if metadata_url == stored.oidc_metadata_url and client_id == stored.oidc_client_id:
        return stored.oidc_client_secret
    return ""


async def discover_oidc_provider(metadata_url: str) -> dict:
    """Fetch and validate an OIDC discovery document, returning key endpoints."""
    chunks = []
    total = 0
    async with httpx2.AsyncClient(timeout=10.0) as client:
        async with client.stream("GET", metadata_url, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > OIDC_DISCOVERY_MAX_BYTES:
                    raise ValueError("Discovery document is too large")
                chunks.append(chunk)
    data = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Discovery endpoint did not return a JSON object")
    for required in ("issuer", "authorization_endpoint", "token_endpoint"):
        val = data.get(required)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Discovery document is missing {required}")
    check_metadata_url(data["authorization_endpoint"])
    check_metadata_url(data["token_endpoint"])
    return {"issuer": data["issuer"], "authorization_endpoint": data["authorization_endpoint"]}


async def create_oidc_link_url(request: Request, base_url: str, draft: AuthSettings) -> str:
    """Start an OIDC authorization flow bound to the current authenticated session to detect the user's sub."""
    redirect_uri = f"{draft.public_url.rstrip('/')}{base_url}/auth/oidc/callback"
    response = await oidc_client(draft).authorize_redirect(request, redirect_uri)
    location = response.headers["location"]
    check_metadata_url(location)
    state = parse_qs(urlsplit(location).query).get("state", [""])[0]
    if not state:
        raise ValueError("Authorization URL did not include a state parameter")
    link_token = secrets.token_urlsafe(24)
    request.session["oidc_link_token"] = link_token
    await _oidc_link_pending.set(state, (link_token, draft), 600)
    return location


async def peek_oidc_link_result(result_id: str):
    """Return the pending OIDC link (draft_settings, summary) without consuming it."""
    return await _oidc_link_results.peek(result_id) if result_id else None


async def consume_oidc_link_result(result_id: str):
    """Return and remove the pending OIDC link (draft_settings, summary)."""
    return await _oidc_link_results.get(result_id) if result_id else None


def oidc_client(settings: AuthSettings):
    """Authlib client for the configured provider: discovery document, authorization code flow with PKCE S256.

    Authlib keeps the state, nonce, and PKCE verifier in _oidc_states, each usable once, and rejects an ID token
    whose nonce claim differs.
    """
    from authlib.integrations.starlette_client import OAuth

    key = (settings.oidc_metadata_url, settings.oidc_client_id, settings.oidc_client_secret)
    if key not in _oidc_clients:
        while len(_oidc_clients) >= OIDC_CLIENTS_MAX:
            del _oidc_clients[next(iter(_oidc_clients))]
        _oidc_clients[key] = OAuth(cache=_oidc_states).register(
            name="oidc",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            server_metadata_url=settings.oidc_metadata_url,
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )
    return _oidc_clients[key]


def oidc_identity_allowed(userinfo: dict, settings: AuthSettings) -> bool:
    """Single user: matches the linked subject (sub) claim."""
    return bool(settings.oidc_sub) and hmac.compare_digest(str(userinfo.get("sub", "")).encode(), settings.oidc_sub.encode())


# --- Middleware and routes -----------------------------------------------------------------------------


def _start_session(request: Request, identity: str, proved_at: int | None = None) -> None:
    request.session.clear()
    request.session["u"] = identity
    # When the person last proved who they are. For OIDC this is the provider's auth_time claim, or 0 (not fresh).
    request.session["t"] = int(time.time()) if proved_at is None else proved_at


def session_is_fresh(request: Request) -> bool:
    try:
        return time.time() - int(request.session.get("t", 0)) <= REAUTH_SECONDS
    except (TypeError, ValueError):
        return False


def json_write_ok(request: Request) -> bool:
    """A write with a body must be JSON. A cross-site form cannot send that type without a CORS preflight."""
    if request.method not in BODY_METHODS:
        return True
    return request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"


def same_origin_ok(request: Request, settings: AuthSettings) -> bool:
    """The write came from this site's own pages. Sec-Fetch-Site decides when the browser sends it (same-site
    includes sibling subdomains, so only same-origin passes); older browsers fall back to Origin."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site.strip().lower() in ("same-origin", "none")
    origin = request.headers.get("origin")
    if origin is None:
        return True  # not a browser, or one too old to send either header; the JSON type check still applies
    parts = urlsplit(origin)
    if origin == "null" or not parts.scheme or not parts.netloc:  # sandboxed frames, file:, and data: send Origin: null
        return False
    if settings.public_url:
        public = urlsplit(settings.public_url)
        if parts.netloc == public.netloc:  # a proxy forwards this Host, so the scheme must decide
            return parts.scheme == public.scheme
    if settings.https_only and parts.scheme != "https":
        return False
    host = request.headers.get("host", "")
    return bool(host) and parts.netloc == host


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Requires a login for every request except health, static files, and the login routes."""

    def __init__(self, app, store: AuthStore, base_url: str = ""):
        super().__init__(app)
        self.store = store
        self.base_url = base_url
        self.api = f"{base_url}/api"
        self.public_get = tuple(f"{base_url}{p}" for p in ("/static", "/api/health", "/site.webmanifest"))
        self.login_paths = {f"{base_url}{p}" for p in ("/login", "/auth/oidc/login", "/auth/oidc/callback")}

    def _is_api(self, path: str) -> bool:
        return path == self.api or path.startswith(self.api + "/")

    async def _identify(self, request: Request, settings: AuthSettings, ip: str):
        """Return how the request proved itself (api_key, basic, session), None, or "limited"."""
        if self._is_api(request.url.path):
            key = request.headers.get("x-api-key")
            basic = request.headers.get("authorization", "").lower().startswith("basic ")
            if (key is not None or basic) and is_rate_limited(ip):
                return "limited"
            if key is not None:
                if api_key_ok(key, settings):
                    return "api_key"
                record_failure(ip)
                logger.info(f"API key rejected for {clean_for_log(request.url.path)} from {ip}")
                return None
            if basic:
                try:
                    credentials = await _basic(request)
                except HTTPException:
                    credentials = None
                if credentials and (settings.mode != "oidc" or settings.allow_local_login):
                    ok = await password_ok(ip, credentials.username, credentials.password, settings)
                    if ok is None:
                        return "limited"
                    if ok:
                        return "basic"
                else:
                    record_failure(ip)
                logger.info(f"Basic auth failed for {clean_for_log(request.url.path)} from {ip}")
                return None
        if settings.mode != "api_only" and request.session.get("u"):
            return "session"
        return None

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in self.public_get):
            return await call_next(request)
        settings = self.store.get()
        if settings is None:
            return PlainTextResponse("Authentication settings could not be used", status_code=503)
        if request.method in UNSAFE_METHODS and not (self._is_api(path) and "x-api-key" in request.headers):
            # A cross-site page cannot set X-Api-Key without a CORS preflight, so those requests skip these checks.
            if not json_write_ok(request):
                return PlainTextResponse("Writes need Content-Type: application/json", status_code=415)
            if not same_origin_ok(request, settings):
                logger.info(f"Cross-site write refused for {clean_for_log(path)} from {client_ip(request, settings)}")
                return PlainTextResponse("Cross-site request refused", status_code=403)
        if path in self.login_paths:
            return await call_next(request)
        how = await self._identify(request, settings, client_ip(request, settings))
        if how == "limited":
            return _limited_response()
        if how is None:
            wants_page = request.method == "GET" and "text/html" in request.headers.get("accept", "")
            if wants_page and settings.mode != "api_only" and not self._is_api(path):
                return RedirectResponse(f"{self.base_url}/login", status_code=302)
            return PlainTextResponse("Authentication required", status_code=401)
        request.state.auth_method = how
        return await call_next(request)


_LOGIN_PLACEHOLDERS = re.compile(r"__(BASE_HREF|BASE_JS|SUBTITLE|OIDC|DIVIDER|LOCAL)__")
_LOGIN_HTML_PATH = util.runtime_path("web-ui", "login.html")
LOGIN_PAGE = _LOGIN_HTML_PATH.read_text(encoding="utf-8") if _LOGIN_HTML_PATH.is_file() else ""


def _render_login_shell(base_url: str, *, subtitle: str, oidc: str = "", divider: str = "", local: str = "") -> str:
    base_href = html.escape(base_url)
    base_js = json.dumps(base_url).replace("<", "\\u003c")  # a JS string literal that cannot close the script tag
    values = {
        "BASE_HREF": base_href,
        "BASE_JS": base_js,
        "SUBTITLE": html.escape(subtitle),
        "OIDC": oidc,
        "DIVIDER": divider,
        "LOCAL": local,
    }
    return _LOGIN_PLACEHOLDERS.sub(lambda m: values[m.group(1)], LOGIN_PAGE)


def _oidc_error(
    base_url: str,
    status_code: int,
    title: str,
    message: str,
    *,
    hint: str = "",
    back_to_security: bool = False,
):
    if not LOGIN_PAGE:
        return PlainTextResponse(message, status_code=status_code)
    err_html = f'<div class="login-error" role="alert">{html.escape(message)}</div>'
    if hint:
        err_html += f'<p class="login-notice">{html.escape(hint)}</p>'
    back_href = f"{base_url}/#security" if back_to_security else f"{base_url}/login"
    back_label = "Back to Security Settings" if back_to_security else "Back to sign in"
    btn_html = f'<a class="btn btn-primary login-btn" href="{html.escape(back_href)}">{back_label}</a>'
    return HTMLResponse(
        _render_login_shell(base_url, subtitle=title, oidc=err_html, local=btn_html),
        status_code=status_code,
    )


def build_auth_router(store: AuthStore, base_url: str) -> APIRouter:
    router = APIRouter()

    def unusable():
        return PlainTextResponse("Authentication settings could not be used", status_code=503)

    @router.get("/login")
    async def login_page(request: Request):
        settings = store.get()
        if settings is None:
            return unusable()
        if settings.mode == "api_only":
            return PlainTextResponse("Not found", status_code=404)
        base_href = html.escape(base_url)
        has_local = settings.mode != "oidc" or settings.allow_local_login
        oidc = (
            '<div class="login-oidc">'
            f'<a class="btn btn-primary login-btn login-oidc-btn" href="{base_href}/auth/oidc/login">'
            '<span id="oidc-login-icon" aria-hidden="true"></span><span>Sign in with OpenID Connect</span></a></div>'
            if settings.mode == "oidc"
            else ""
        )
        divider = '<div class="login-divider"><span>or sign in locally</span></div>' if oidc and has_local else ""
        local = ""
        if (store.path.parent / INITIAL_PASSWORD_FILE).exists():
            local += (
                '<p class="login-notice" role="status">'
                f"The first-run password is in <code>{html.escape(INITIAL_PASSWORD_FILE)}</code> in the config folder.</p>"
            )
        if has_local:
            btn_class = "btn btn-secondary login-btn" if oidc else "btn btn-primary login-btn"
            autofocus = "" if oidc else " autofocus"
            local += (
                '<form id="login-form" class="login-form">'
                '<div class="form-group">'
                '<label for="login-username" class="form-label">Username</label>'
                f'<input id="login-username" name="username" class="form-input" autocomplete="username" required{autofocus}>'
                "</div>"
                '<div class="form-group">'
                '<label for="login-password" class="form-label">Password</label>'
                '<div class="password-input-group">'
                '<input id="login-password" name="password" type="password" '
                'class="form-input hide-password-toggle" autocomplete="current-password" required>'
                '<button type="button" id="password-toggle" class="password-toggle" '
                'aria-label="Show password" aria-pressed="false"></button>'
                "</div>"
                "</div>"
                '<div id="msg" class="login-error hidden" role="alert" aria-live="polite"></div>'
                f'<button type="submit" id="login-submit" class="{btn_class}">Sign in</button>'
                "</form>"
            )
        subtitle = "Sign in with your identity provider" if oidc and not has_local else "Sign in to continue"
        return HTMLResponse(_render_login_shell(base_url, subtitle=subtitle, oidc=oidc, divider=divider, local=local))

    @router.post("/login")
    async def login(request: Request):
        settings = store.get()
        if settings is None:
            return unusable()
        if settings.mode == "api_only":
            return PlainTextResponse("Not found", status_code=404)
        if settings.mode == "oidc" and not settings.allow_local_login:
            return PlainTextResponse("Use the OpenID Connect login", status_code=403)
        ip = client_ip(request, settings)
        if is_rate_limited(ip):
            return _limited_response()
        try:
            body = await request.json()
            username, password = str(body.get("username", "")), str(body.get("password", ""))
        except Exception:
            return PlainTextResponse("Invalid request", status_code=400)
        ok = await password_ok(ip, username, password, settings)
        if ok is None:
            return _limited_response()
        if not ok:
            logger.info(f"Login failed for user={clean_for_log(username)} from {ip}")
            return PlainTextResponse("Authentication failed", status_code=401)
        _start_session(request, settings.username)
        return JSONResponse({"success": True})

    @router.post("/logout")
    async def logout(request: Request):
        request.session.clear()
        return JSONResponse({"success": True})

    @router.get("/auth/oidc/login")
    async def oidc_login(request: Request):
        settings = store.get()
        if settings is None or settings.mode != "oidc":
            return PlainTextResponse("Not found", status_code=404)
        redirect_uri = f"{settings.public_url.rstrip('/')}{base_url}/auth/oidc/callback"
        if not _limiter.hit(_FAILURE_LIMIT, "oidc_login", client_ip(request, settings)):
            return _limited_response()
        extra = {"prompt": "login", "max_age": 0} if request.query_params.get("reauth") else {}
        try:
            response = await oidc_client(settings).authorize_redirect(request, redirect_uri, **extra)
            request.session["reauth"] = bool(extra)  # never carry an abandoned re-auth into an ordinary login
            return response
        except Exception as e:
            logger.error(f"OIDC provider unreachable or misconfigured: {clean_for_log(e)}")
            return _oidc_error(
                base_url,
                503,
                "Login provider unavailable",
                "The OpenID Connect provider is currently unreachable or misconfigured.",
            )

    async def _handle_oidc_link_callback(request: Request, ip: str, draft: AuthSettings):
        if not _limiter.test(_FAILURE_LIMIT, "oidc_callback", ip):
            return _limited_response()
        if request.query_params.get("error"):
            _limiter.hit(_FAILURE_LIMIT, "oidc_callback", ip)
            return _oidc_error(
                base_url,
                401,
                "OpenID Connect link failed",
                "The identity provider refused or cancelled the sign-in request.",
                back_to_security=True,
            )
        try:
            token = await oidc_client(draft).authorize_access_token(request)
            userinfo = token.get("userinfo") or {}
        except Exception as e:
            _limiter.hit(_FAILURE_LIMIT, "oidc_callback", ip)
            logger.info(f"OIDC link failed from {ip}: {clean_for_log(e)}")
            return _oidc_error(
                base_url,
                401,
                "OpenID Connect link failed",
                "Could not verify the sign-in response from the provider. Check your Client ID, Client Secret, and Redirect URI.",
                back_to_security=True,
            )
        sub = str(userinfo.get("sub") or "").strip()
        if not sub:
            return _oidc_error(
                base_url,
                403,
                "OpenID Connect link failed",
                "The identity provider did not return a user subject (sub) claim.",
                back_to_security=True,
            )
        result_id = secrets.token_urlsafe(24)
        summary = {
            "sub": sub,
            "email": str(userinfo.get("email") or "") if userinfo.get("email_verified") is True else "",
            "preferred_username": str(userinfo.get("preferred_username") or userinfo.get("name") or ""),
            "public_url": draft.public_url,
            "oidc_metadata_url": draft.oidc_metadata_url,
            "oidc_client_id": draft.oidc_client_id,
            "has_client_secret": bool(draft.oidc_client_secret),
        }
        await _oidc_link_results.set(result_id, (draft, summary), 600)
        request.session["oidc_link_result_id"] = result_id
        logger.info(f"OIDC account linked for sub={clean_for_log(sub)} from {ip}")
        return RedirectResponse(f"{base_url}/#security", status_code=302)

    @router.get("/auth/oidc/callback")
    async def oidc_callback(request: Request):
        settings = store.get()
        if settings is None:
            return unusable()
        # A separate bucket from passwords, so failed callbacks behind a shared proxy cannot block the password login.
        ip = client_ip(request, settings)
        state = request.query_params.get("state", "")
        pending_link = await _oidc_link_pending.peek(state) if state else None
        if pending_link is not None:
            if not _limiter.test(_FAILURE_LIMIT, "oidc_callback", ip):
                return _limited_response()
            link_token, draft = pending_link
            session_token = str(request.session.get("oidc_link_token", ""))
            if not request.session.get("u") or not session_token or not hmac.compare_digest(session_token, link_token):
                _limiter.hit(_FAILURE_LIMIT, "oidc_callback", ip)
                return _oidc_error(
                    base_url,
                    401,
                    "OpenID Connect link failed",
                    "Your linking session is missing or expired. Return to Security Settings and try again.",
                    back_to_security=True,
                )
            await _oidc_link_pending.delete(state)
            request.session.pop("oidc_link_token", None)
            return await _handle_oidc_link_callback(request, ip, draft)
        if settings.mode != "oidc":
            return PlainTextResponse("Not found", status_code=404)
        if not _limiter.test(_FAILURE_LIMIT, "oidc_callback", ip):
            return _limited_response()
        try:
            token = await oidc_client(settings).authorize_access_token(request)
            userinfo = token.get("userinfo") or {}
        except Exception as e:
            _limiter.hit(_FAILURE_LIMIT, "oidc_callback", ip)
            logger.info(f"OIDC login failed from {ip}: {clean_for_log(e)}")
            return _oidc_error(base_url, 401, "Sign-in failed", "OpenID Connect authentication failed. Please try again.")
        sub = str(userinfo.get("sub") or "").strip()
        try:
            auth_time = int(userinfo.get("auth_time", 0))
        except (TypeError, ValueError):
            auth_time = 0
        reauth_stale = bool(request.session.get("reauth") and time.time() - auth_time > REAUTH_SECONDS)
        claiming = bool(settings.oidc_claim_first_login and not settings.oidc_sub)
        if claiming:
            if not sub:
                logger.info(f"OIDC first-login claim refused from {ip}: empty sub claim")
                return _oidc_error(
                    base_url,
                    403,
                    "Account not allowed",
                    "The identity provider did not return a user subject (sub) claim.",
                )
        elif not oidc_identity_allowed(userinfo, settings):
            logger.info(f"OIDC login refused for sub={clean_for_log(userinfo.get('sub', ''))} from {ip}")
            return _oidc_error(
                base_url,
                403,
                "Account not allowed",
                "This OpenID Connect account is not allowed to access this instance.",
                hint=(
                    "Sign in locally (if break-glass is enabled) and use Security Settings to re-link your "
                    "OpenID Connect account."
                ),
            )
        if reauth_stale:
            logger.info(f"OIDC re-authentication refused from {ip}: the provider did not confirm a fresh login")
            return _oidc_error(
                base_url,
                401,
                "Re-authentication required",
                "The identity provider did not confirm a fresh login.",
            )
        if claiming:
            claimed = settings.model_copy(update={"oidc_sub": sub, "oidc_claim_first_login": False})
            if not await run_in_threadpool(store.save, claimed, settings):
                logger.info(f"OIDC first-login claim lost race for sub={clean_for_log(sub)} from {ip}")
                return _oidc_error(base_url, 403, "Account not allowed", "This account is not allowed.")
            logger.warning(f"OIDC first-login claimed by sub={clean_for_log(sub)} from {ip}; oidc_claim_first_login disabled")
        # A future auth_time would keep the session fresh until that time
        _start_session(request, f"oidc:{sub}", proved_at=min(auth_time, int(time.time())))
        return RedirectResponse(f"{base_url}/", status_code=302)

    return router
