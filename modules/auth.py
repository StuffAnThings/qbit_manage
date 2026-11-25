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
from urllib.parse import urlsplit

import argon2
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
    oidc_email: str = ""
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
    oidc_email: str = ""
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
        return bool(s.oidc_metadata_url and s.oidc_client_id and s.public_url and (s.oidc_sub or s.oidc_email))
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
            data["authentication"] = settings.model_dump()
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


def _write_key(key_path: Path) -> str:
    key = secrets.token_urlsafe(48)
    fd, tmp = tempfile.mkstemp(dir=key_path.parent, prefix=".qbm_key.")  # created 0600
    with os.fdopen(fd, "w") as f:
        f.write(key)
    os.replace(tmp, key_path)
    return key


def session_secret(config_dir: Path) -> str:
    """Return the cookie signing key, kept in its own 0600 file outside qbm_settings.yml."""
    key_path = Path(config_dir) / SESSION_KEY_FILE
    key = key_path.read_text(encoding="utf-8").strip() if key_path.exists() else ""
    if len(key) < 32:  # missing, empty, or truncated by a crash: make a new one rather than sign with a weak key
        return _write_key(key_path)
    if os.name != "nt" and key_path.stat().st_mode & 0o077:
        os.chmod(key_path, 0o600)
    return key


def rotate_session_secret(config_dir: Path) -> None:
    """Replace the cookie signing key, which signs out every browser."""
    _write_key(Path(config_dir) / SESSION_KEY_FILE)


class RotatingSessionMiddleware(SessionMiddleware):
    """Starlette's session cookie, re-keyed when the key file changes (a password change signs out every device)."""

    def __init__(self, app, config_dir: Path, **kwargs):
        self.config_dir = Path(config_dir)
        self._key = session_secret(self.config_dir)
        super().__init__(app, secret_key=self._key, **kwargs)

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            key = session_secret(self.config_dir)
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
    if settings.mode == "oidc" and settings.oidc_email and not settings.oidc_sub:
        logger.warning(
            "oidc_email without oidc_sub trusts the provider's email claim. Use it only with a provider you run "
            "yourself, and prefer oidc_sub."
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
        # Left set after a reset, it would otherwise sign everyone out and re-open break-glass on every restart.
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


class _OidcStateCache:
    """Authlib's server-side store for pending OIDC logins (state, nonce, PKCE verifier).

    The session cookie keeps only a marker, so a copied pre-callback cookie cannot replay a state: get() removes
    the entry. At most OIDC_STATE_MAX logins are pending; the oldest is dropped first.
    """

    def __init__(self):
        self._items = {}  # key -> (expiry, value), in insertion order

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
_oidc_clients = {}


def oidc_client(settings: AuthSettings):
    """Authlib client for the configured provider: discovery document, authorization code flow with PKCE S256.

    Authlib keeps the state, nonce, and PKCE verifier in _oidc_states, each usable once, and rejects an ID token
    whose nonce claim differs.
    """
    from authlib.integrations.starlette_client import OAuth

    key = (settings.oidc_metadata_url, settings.oidc_client_id, settings.oidc_client_secret)
    if key not in _oidc_clients:
        _oidc_clients[key] = OAuth(cache=_oidc_states).register(
            name="oidc",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            server_metadata_url=settings.oidc_metadata_url,
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )
    return _oidc_clients[key]


def oidc_identity_allowed(userinfo: dict, settings: AuthSettings) -> bool:
    """Single user: the configured sub, or the configured email when the provider says it is verified."""
    if settings.oidc_sub:  # a configured subject is authoritative; the email is only for installs without one
        return hmac.compare_digest(str(userinfo.get("sub", "")).encode(), settings.oidc_sub.encode())
    email = userinfo.get("email")
    return bool(
        settings.oidc_email
        and isinstance(email, str)
        and userinfo.get("email_verified") is True
        and email.lower() == settings.oidc_email.lower()
    )


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


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>qBit Manage login</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>
<h1>qBit Manage</h1>{oidc}{local}
<script>
const form = document.getElementById('login-form');
if (form) form.addEventListener('submit', async (e) => {{
  e.preventDefault();
  const r = await fetch({base_js} + '/login', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{username: form.username.value, password: form.password.value}})}});
  if (r.ok) location.href = {base_js} + '/';
  else document.getElementById('msg').textContent = r.status === 401 ? 'Login failed' : await r.text();
}});
</script></body></html>"""


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
        oidc = (
            f'<p><a href="{html.escape(base_url)}/auth/oidc/login">Sign in with OpenID Connect</a></p>'
            if settings.mode == "oidc"
            else ""
        )
        local = ""
        if (store.path.parent / INITIAL_PASSWORD_FILE).exists():
            local += (
                f"<p>The first-run password is in <code>{html.escape(INITIAL_PASSWORD_FILE)}</code> in the config folder.</p>"
            )
        if settings.mode != "oidc" or settings.allow_local_login:
            local += (
                '<form id="login-form"><label>Username <input name="username" autocomplete="username"></label> '
                '<label>Password <input name="password" type="password" autocomplete="current-password"></label> '
                '<button type="submit">Sign in</button> <span id="msg"></span></form>'
            )
        base_js = json.dumps(base_url).replace("<", "\\u003c")  # a JS string literal that cannot close the script tag
        return HTMLResponse(LOGIN_PAGE.format(base_js=base_js, oidc=oidc, local=local))

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
            return PlainTextResponse("The login provider is unavailable", status_code=503)

    @router.get("/auth/oidc/callback")
    async def oidc_callback(request: Request):
        settings = store.get()
        if settings is None or settings.mode != "oidc":
            return PlainTextResponse("Not found", status_code=404)
        # A separate bucket from passwords, so failed callbacks behind a shared proxy cannot block the password login.
        ip = client_ip(request, settings)
        if not _limiter.test(_FAILURE_LIMIT, "oidc_callback", ip):
            return _limited_response()
        try:
            token = await oidc_client(settings).authorize_access_token(request)
            userinfo = token.get("userinfo") or {}
        except Exception as e:
            _limiter.hit(_FAILURE_LIMIT, "oidc_callback", ip)
            logger.info(f"OIDC login failed from {ip}: {clean_for_log(e)}")
            return PlainTextResponse("Authentication failed", status_code=401)
        if not oidc_identity_allowed(userinfo, settings):
            logger.info(f"OIDC login refused for sub={clean_for_log(userinfo.get('sub', ''))} from {ip}")
            return PlainTextResponse("This account is not allowed", status_code=403)
        try:
            auth_time = int(userinfo.get("auth_time", 0))
        except (TypeError, ValueError):
            auth_time = 0
        if request.session.get("reauth") and time.time() - auth_time > REAUTH_SECONDS:
            logger.info(f"OIDC re-authentication refused from {ip}: the provider did not confirm a fresh login")
            return PlainTextResponse("Authentication failed", status_code=401)
        # A future auth_time would keep the session fresh until that time
        _start_session(request, f"oidc:{userinfo.get('sub', '')}", proved_at=min(auth_time, int(time.time())))
        return RedirectResponse(f"{base_url}/", status_code=302)

    return router
