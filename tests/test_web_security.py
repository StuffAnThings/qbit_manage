"""End-to-end security tests for the web API, driven through the real ASGI middleware stack."""

import asyncio
import base64
import json
import logging
import multiprocessing
import os
import queue
import stat
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlsplit

import pytest
import ruamel.yaml
from fastapi import HTTPException
from pydantic import ValidationError

from modules import auth
from modules import util
from modules.auth import hash_password
from modules.web_api import REDACTED
from modules.web_api import CommandRequest
from modules.web_api import create_app
from modules.web_api import restore_redacted

CONFIG = """qbt:
  host: localhost:8080
  user: admin
  pass: qbt-secret-pass
notifiarr:
  apikey: notifiarr-secret-key
apprise:
  api_url: http://apprise:8000
  notify_url:
    - discord://secret-webhook-token
webhooks:
  error: https://discord.com/api/webhooks/1/secret-token
  run_start: notifiarr
"""

PASSWORD = "Tr0ub4dor&3x!"
API_KEY = "k" * 43


class Resp:
    def __init__(self, status, body, headers):
        self.status = status
        self.text = body
        self.headers = headers

    def header(self, name):
        return [v for k, v in self.headers if k.lower() == name.lower()]

    def json(self):
        return json.loads(self.text)


async def asend(app, method, path, *, ip="127.0.0.1", headers=(), body=None, content_type="application/json"):
    payload = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    hdrs = [(b"host", b"127.0.0.1:8181")]
    if body is not None and content_type:
        hdrs.append((b"content-type", content_type.encode()))
    names = {k.lower() for k, _ in headers}
    hdrs = [h for h in hdrs if h[0].decode() not in names]
    hdrs += [(k.lower().encode(), v.encode()) for k, v in headers]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": unquote(path.partition("?")[0]),
        "raw_path": path.partition("?")[0].encode(),
        "query_string": path.partition("?")[2].encode(),
        "root_path": "",
        "headers": hdrs,
        "client": (ip, 50000),
        "server": ("testserver", 80),
    }
    out = {"status": None, "body": b"", "headers": []}
    received = {"done": False}

    async def receive():
        if not received["done"]:
            received["done"] = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send_(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
            out["headers"] = [(k.decode(), v.decode()) for k, v in message["headers"]]
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"")

    await app(scope, receive, send_)
    return Resp(out["status"], out["body"].decode("utf-8", "replace"), out["headers"])


def send(app, method, path, **kwargs):
    return asyncio.run(asend(app, method, path, **kwargs))


def call(app, method, path, *, client_ip="127.0.0.1", headers=None, body=None):
    """Compatibility wrapper that returns (status, text)."""
    resp = send(app, method, path, ip=client_ip, headers=list((headers or {}).items()), body=body)
    return resp.status, resp.text


def cookie_of(resp):
    jar = SimpleCookie()
    for value in resp.header("set-cookie"):
        jar.load(value)
    return {k: m.value for k, m in jar.items()}


def cookie_header(cookies):
    return [("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))]


def login(app, ip="127.0.0.1", username="owner", password=PASSWORD):
    resp = send(app, "POST", "/login", ip=ip, body={"username": username, "password": password})
    return resp, cookie_header(cookie_of(resp))


def write_settings(config_dir, **authentication):
    yaml = ruamel.yaml.YAML()
    with open(config_dir / "qbm_settings.yml", "w", encoding="utf-8") as f:
        yaml.dump({"authentication": authentication}, f)


def basic(username="owner", password=PASSWORD):
    return {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}


def local_settings(config_dir, **extra):
    data = {"mode": "local", "username": "owner", "password_hash": hash_password(PASSWORD), "api_key": API_KEY}
    data.update(extra)
    write_settings(config_dir, **data)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    auth._attempts.reset()


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "config.yml").write_text(CONFIG, encoding="utf-8")
    return tmp_path


@pytest.fixture
def local_dir(config_dir):
    local_settings(config_dir)
    return config_dir


def make_app(config_dir, host="127.0.0.1", base_url=""):
    return create_app(
        {"config_dir": str(config_dir), "base_url": base_url, "host": host},
        multiprocessing.Value("b", False),
        multiprocessing.Lock(),
        queue.Queue(),
        queue.Queue(),
        {},
    )


# --- A login is always required ---------------------------------------------------------------------


@pytest.mark.parametrize("ip,host", [("127.0.0.1", "127.0.0.1"), ("203.0.113.9", "203.0.113.1")])
def test_login_required_everywhere(local_dir, ip, host):
    app = make_app(local_dir, host="0.0.0.0")
    resp = send(app, "GET", "/api/configs/config.yml", ip=ip, headers=[("Host", host)])
    assert resp.status == 401
    assert "qbt-secret-pass" not in resp.text


def test_browser_page_redirects_to_login(local_dir):
    resp = send(make_app(local_dir), "GET", "/", headers=[("Accept", "text/html")])
    assert resp.status == 302
    assert resp.header("location") == ["/login"]


def test_login_page_is_public(local_dir):
    resp = send(make_app(local_dir), "GET", "/login")
    assert resp.status == 200 and "<form" in resp.text


def test_session_login_and_cookie_attributes(local_dir):
    app = make_app(local_dir)
    resp, cookie = login(app)
    assert resp.status == 200
    set_cookie = resp.header("set-cookie")[0].lower()
    assert set_cookie.startswith("qbm_session=")
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie and "max-age=" in set_cookie and "path=/" in set_cookie
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie).status == 200


def test_wrong_password_rejected(local_dir):
    app = make_app(local_dir)
    assert login(app, password="wrong")[0].status == 401
    assert login(app, username="intruder")[0].status == 401


def test_cookie_path_follows_base_url(local_dir):
    resp, _ = login_base(make_app(local_dir, base_url="/qbm"), "/qbm")
    assert "path=/qbm" in resp.header("set-cookie")[0].lower()


def login_base(app, base):
    resp = send(app, "POST", f"{base}/login", body={"username": "owner", "password": PASSWORD})
    return resp, cookie_header(cookie_of(resp))


def test_https_only_is_an_explicit_setting(config_dir):
    local_settings(config_dir, https_only=True)
    resp, _ = login(make_app(config_dir))
    assert "secure" in resp.header("set-cookie")[0].lower()


def test_password_change_revokes_old_cookies(local_dir):
    app = make_app(local_dir)
    _, cookie = login(app)
    new = "N3w-Passw0rd!x"
    body = {"mode": "local", "username": "owner", "password": new, "current_password": PASSWORD}
    resp = send(app, "PUT", "/api/security", headers=cookie, body=body)
    assert resp.json()["success"] is True
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie).status == 401
    assert login(app, password=new)[0].status == 200


def test_password_change_requires_current_password(local_dir):
    app = make_app(local_dir)
    _, cookie = login(app)
    body = {"mode": "local", "username": "owner", "password": "N3w-Passw0rd!x", "current_password": "wrong"}
    assert send(app, "PUT", "/api/security", headers=cookie, body=body).json()["success"] is False


def test_session_secret_is_a_separate_private_file(local_dir):
    make_app(local_dir)
    key_files = [p for p in local_dir.iterdir() if p.name.startswith(".qbm_session")]
    assert len(key_files) == 1
    assert stat.S_IMODE(key_files[0].stat().st_mode) == 0o600
    assert key_files[0].read_text().strip() not in (local_dir / "qbm_settings.yml").read_text()
    status, text = call(make_app(local_dir), "GET", f"/api/configs/{key_files[0].name}", headers=basic())
    assert status in (400, 403, 404) and key_files[0].read_text().strip() not in text


# --- Scripts: API key and Basic ---------------------------------------------------------------------


def test_api_key_and_basic_on_api(local_dir):
    app = make_app(local_dir, host="0.0.0.0")
    assert send(app, "GET", "/api/configs/config.yml", ip="203.0.113.9", headers=[("X-Api-Key", API_KEY)]).status == 200
    assert send(app, "GET", "/api/configs/config.yml", ip="203.0.113.9", headers=[("X-API-Key", "x" * 43)]).status == 401
    assert send(app, "GET", "/api/configs/config.yml", ip="203.0.113.9", headers=list(basic().items())).status == 200
    assert send(app, "GET", "/api/configs/config.yml", ip="203.0.113.9", headers=list(basic(password="no").items())).status == 401


def test_api_key_and_basic_do_not_open_the_ui(local_dir):
    resp = send(make_app(local_dir), "GET", "/", headers=[("X-Api-Key", API_KEY), ("Accept", "text/html")])
    assert resp.status == 302


def test_api_key_cannot_change_security_settings(local_dir):
    app = make_app(local_dir)
    body = {"mode": "local", "username": "owner", "generate_api_key": True, "current_password": PASSWORD}
    resp = send(app, "PUT", "/api/security", headers=[("X-Api-Key", API_KEY)], body=body)
    assert resp.status == 403


def test_failed_api_keys_are_rate_limited(local_dir):
    app = make_app(local_dir, host="0.0.0.0")
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        assert send(app, "GET", "/api/version-x", ip="203.0.113.9", headers=[("X-Api-Key", "bad")]).status == 401
    assert send(app, "GET", "/api/version-x", ip="203.0.113.9", headers=[("X-Api-Key", "bad")]).status == 429


def test_api_only_mode_has_no_browser_login(config_dir):
    write_settings(config_dir, mode="api_only", api_key=API_KEY)
    app = make_app(config_dir)
    assert send(app, "GET", "/api/configs/config.yml", headers=[("X-Api-Key", API_KEY)]).status == 200
    assert send(app, "GET", "/", headers=[("Accept", "text/html")]).status == 401
    assert send(app, "GET", "/login").status == 404


# --- External mode ------------------------------------------------------------------------------------


@pytest.mark.parametrize("header", ["Basic !!!", "Basic " + base64.b64encode(b"no-colon").decode(), "Basic"])
def test_malformed_basic_headers_are_401(local_dir, header):
    assert send(make_app(local_dir), "GET", "/api/configs/config.yml", headers=[("Authorization", header)]).status == 401


# --- Fail closed ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content", ["", "{}\n", "authentication: {}\n", "authentication: [unclosed", "authentication: {mode: Basic}\n"]
)
def test_unusable_settings_fail_closed(config_dir, content):
    (config_dir / "qbm_settings.yml").write_text(content, encoding="utf-8")
    resp = send(make_app(config_dir, host="0.0.0.0"), "GET", "/api/configs/config.yml", ip="203.0.113.9")
    assert resp.status == 503 and "qbt-secret-pass" not in resp.text


def test_missing_settings_fail_closed(config_dir):
    assert send(make_app(config_dir), "GET", "/api/configs/config.yml").status == 503


def test_unknown_mode_is_rejected():
    with pytest.raises(ValidationError):
        auth.AuthSettings(mode="Basic")


def test_legacy_settings_migrate_without_local_bypass(config_dir):
    write_settings(
        config_dir, enabled=True, method="basic", bypass_auth_for_local=True, username="owner",
        password_hash=hash_password(PASSWORD), api_key=API_KEY, trusted_proxies=[],
    )  # fmt: skip
    app = make_app(config_dir)
    assert send(app, "GET", "/api/configs/config.yml").status == 401
    assert login(app)[0].status == 200


def test_legacy_auth_disabled_still_requires_a_login(config_dir):
    write_settings(config_dir, enabled=False, method="none")
    assert send(make_app(config_dir), "GET", "/api/configs/config.yml").status == 503


# --- CSRF and Host --------------------------------------------------------------------------------------


def test_no_host_check(local_dir):
    _, cookie = login(make_app(local_dir))
    resp = send(make_app(local_dir), "GET", "/api/configs/config.yml", headers=cookie + [("Host", "qbm.example.com")])
    assert resp.status == 200


def test_writes_need_json_content_type(local_dir):
    app = make_app(local_dir)
    _, cookie = login(app)
    resp = send(app, "POST", "/api/configs/new.yml", headers=cookie, body=b'{"data": {}}', content_type="text/plain")
    assert resp.status in (403, 415)
    assert not (local_dir / "new.yml").exists()


def test_api_key_writes_skip_csrf_checks(local_dir):
    resp = send(
        make_app(local_dir),
        "POST",
        "/api/configs/new.yml",
        headers=[("X-Api-Key", API_KEY)],
        body=b'{"data": {}}',
        content_type="text/plain",
    )
    assert resp.status != 403


def test_framework_docs_routes_disabled(local_dir):
    app = make_app(local_dir)
    _, cookie = login(app)
    for path in ("/openapi.json", "/docs", "/redoc"):
        resp = send(app, "GET", path, headers=cookie)
        assert "openapi" not in resp.text.lower() and "swagger" not in resp.text.lower(), path


@pytest.mark.parametrize("path", ["/api/health/../configs/config.yml", "/static/../api/configs/config.yml"])
def test_skip_auth_prefixes_do_not_reach_protected_routes(local_dir, path):
    resp = send(make_app(local_dir, host="0.0.0.0"), "GET", path, ip="203.0.113.9")
    assert resp.status in (401, 404)
    assert "qbt-secret-pass" not in resp.text


# --- Secret redaction ---------------------------------------------------------------------------


def test_get_config_redacts_secrets(local_dir):
    resp = send(make_app(local_dir), "GET", "/api/configs/config.yml", headers=list(basic().items()))
    data = resp.json()["data"]
    assert data["qbt"]["pass"] == REDACTED
    assert data["notifiarr"]["apikey"] == REDACTED
    assert data["apprise"]["notify_url"] == [REDACTED]
    assert data["webhooks"]["error"] == REDACTED
    for secret in ("qbt-secret-pass", "notifiarr-secret-key", "secret-webhook-token", "secret-token"):
        assert secret not in resp.text


def test_update_config_keeps_redacted_values(local_dir):
    app = make_app(local_dir)
    key = [("X-Api-Key", API_KEY)]
    data = send(app, "GET", "/api/configs/config.yml", headers=key).json()["data"]
    data["qbt"]["host"] = "localhost:8080"
    data["qbt"]["user"] = "admin2"
    assert send(app, "PUT", "/api/configs/config.yml", headers=key, body={"data": data}).status == 200
    saved = (local_dir / "config.yml").read_text(encoding="utf-8")
    assert "admin2" in saved and "qbt-secret-pass" in saved and "discord://secret-webhook-token" in saved
    assert REDACTED not in saved


def test_redacted_secret_refused_when_host_changed(local_dir):
    app = make_app(local_dir)
    key = [("X-Api-Key", API_KEY)]
    data = send(app, "GET", "/api/configs/config.yml", headers=key).json()["data"]
    data["qbt"]["host"] = "attacker.example:8080"
    resp = send(app, "PUT", "/api/configs/config.yml", headers=key, body={"data": data})
    assert resp.status == 400
    assert (
        "qbt-secret-pass" not in (local_dir / "config.yml").read_text().replace("qbt-secret-pass", "", 0)
        or "attacker" not in (local_dir / "config.yml").read_text()
    )


def test_list_redaction_restores_only_unchanged_lists():
    assert restore_redacted({"n": [REDACTED, "b"]}, {"n": ["discord://A", "b"]}) == {"n": ["discord://A", "b"]}
    with pytest.raises(HTTPException) as refused:
        restore_redacted({"n": [REDACTED]}, {"n": ["discord://A", "discord://B"]})
    assert refused.value.status_code == 400 and "Enter the secrets in this list again" in refused.value.detail


def test_missing_stored_key_is_dropped_not_a_400():
    assert restore_redacted({"notifiarr": {"apikey": REDACTED, "instance": "i"}}, {}) == {"notifiarr": {"instance": "i"}}


def test_settings_file_blocked_case_insensitively(local_dir):
    resp = send(make_app(local_dir), "GET", "/api/configs/QBM_SETTINGS.yml", headers=list(basic().items()))
    assert resp.status == 403


# --- Path limits ----------------------------------------------------------------------------------


@pytest.mark.parametrize("config_file", ["/etc/passwd", "../other/config.yml", "..\\config.yml", "sub/config.yml", "C:evil.yml"])
def test_run_command_rejects_paths(config_file):
    with pytest.raises(ValidationError):
        CommandRequest(config_file=config_file, commands=[])


@pytest.mark.parametrize("config_file", ["config.yml", "config*.yml"])
def test_run_command_accepts_names_and_globs(config_file):
    assert CommandRequest(config_file=config_file, commands=[]).config_file == config_file


# --- Startup: first-run credentials ---------------------------------------------------------------------


def test_first_run_generates_a_password_file(tmp_path):
    path = tmp_path / "qbm_settings.yml"
    assert auth.ensure_credentials(path, {}) is True
    password_file = tmp_path / auth.INITIAL_PASSWORD_FILE
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600
    password = password_file.read_text().split()[-1]
    stored = path.read_text()
    assert password not in stored
    loaded = auth.load_settings(path)
    assert loaded.mode == "local" and auth.verify_password(password, loaded.password_hash)


def test_env_credentials_seed_only_when_none_exist(tmp_path):
    path = tmp_path / "qbm_settings.yml"
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": PASSWORD}
    assert auth.ensure_credentials(path, env) is True
    assert auth.verify_password(PASSWORD, auth.load_settings(path).password_hash)
    assert not (tmp_path / auth.INITIAL_PASSWORD_FILE).exists()
    other = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "An0ther-Pass!"}
    auth.ensure_credentials(path, other)
    assert auth.verify_password(PASSWORD, auth.load_settings(path).password_hash)


def test_weak_env_password_is_refused(tmp_path):
    path = tmp_path / "qbm_settings.yml"
    assert auth.ensure_credentials(path, {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "short"}) is False
    assert not path.exists()


def test_first_password_change_deletes_the_generated_file(tmp_path):
    (tmp_path / "config.yml").write_text(CONFIG, encoding="utf-8")
    path = tmp_path / "qbm_settings.yml"
    auth.ensure_credentials(path, {})
    initial = (tmp_path / auth.INITIAL_PASSWORD_FILE).read_text().split()[-1]
    app = make_app(tmp_path)
    _, cookie = login(app, username="admin", password=initial)
    body = {"mode": "local", "username": "admin", "password": "N3w-Passw0rd!x", "current_password": initial}
    assert send(app, "PUT", "/api/security", headers=cookie, body=body).json()["success"] is True
    assert not (tmp_path / auth.INITIAL_PASSWORD_FILE).exists()


# --- Settings files --------------------------------------------------------------------------------------


def test_settings_save_is_atomic(local_dir, monkeypatch):
    path = local_dir / "qbm_settings.yml"
    before = path.read_text()

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(auth.os, "replace", boom)
    assert auth.save_auth_settings(path, auth.load_settings(path)) is False
    assert path.read_text() == before


def test_unparseable_settings_are_never_overwritten(config_dir):
    path = config_dir / "qbm_settings.yml"
    path.write_text("authentication: [unclosed\nschedule: {type: cron}", encoding="utf-8")
    assert auth.save_auth_settings(path, auth.AuthSettings(mode="local")) is False
    assert "schedule" in path.read_text()


def test_scheduler_never_rewrites_unreadable_settings(config_dir):
    from modules.scheduler import Scheduler

    path = config_dir / "qbm_settings.yml"
    path.write_text("authentication: {mode: local, username: owner\n", encoding="utf-8")
    before = path.read_text()
    scheduler = Scheduler(str(config_dir), suppress_logging=True)
    assert scheduler.save_schedule("interval", 60) is False  # the failure reaches the caller
    assert path.read_text() == before


# --- Logging ---------------------------------------------------------------------------------------------


def test_log_values_lose_control_characters():
    assert auth.clean_for_log("ad\nmin\x1b[31m\r") == "ad?min?[31m?"
    assert len(auth.clean_for_log("a" * 500)) <= 100


def test_webhook_and_notify_urls_are_masked_in_logs(monkeypatch):
    from types import SimpleNamespace

    from modules import webhooks
    from modules.webhooks import Webhooks

    registered = []
    monkeypatch.setattr(webhooks.logger, "secret", registered.append, raising=False)
    Webhooks(SimpleNamespace(args={}, commands={}), {"error": ["https://discord.com/api/webhooks/1/token-x"], "function": None})
    assert "https://discord.com/api/webhooks/1/token-x" in registered


# --- OIDC ------------------------------------------------------------------------------------------------


def oidc_settings(**extra):
    base = dict(
        mode="oidc", oidc_metadata_url="https://idp.example/.well-known/openid-configuration", oidc_client_id="qbm",
        oidc_client_secret="s", oidc_sub="user-1", public_url="https://qbm.example.com",
    )  # fmt: skip
    base.update(extra)
    return auth.AuthSettings(**base)


def test_oidc_accepts_the_configured_sub_only():
    assert auth.oidc_identity_allowed({"sub": "user-1"}, oidc_settings())
    assert not auth.oidc_identity_allowed({"sub": "user-2"}, oidc_settings())


def test_oidc_email_needs_email_verified_true():
    settings = oidc_settings(oidc_sub="", oidc_email="me@example.com")
    assert auth.oidc_identity_allowed({"sub": "x", "email": "me@example.com", "email_verified": True}, settings)
    assert not auth.oidc_identity_allowed({"sub": "x", "email": "me@example.com", "email_verified": False}, settings)
    assert not auth.oidc_identity_allowed({"sub": "x", "email": "me@example.com"}, settings)
    assert not auth.oidc_identity_allowed({"sub": "x", "email": "me@example.com", "email_verified": "true"}, settings)


def test_oidc_login_redirect_uses_public_url_and_pkce(config_dir, monkeypatch):
    write_settings(config_dir, **oidc_settings(username="owner").model_dump())
    client = MagicMock()
    client.authorize_redirect = AsyncMock(return_value=auth.RedirectResponse("https://idp.example/authorize"))
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    resp = send(make_app(config_dir), "GET", "/auth/oidc/login", headers=[("Host", "evil.example")])
    assert resp.status == 307 or resp.status == 302
    assert client.authorize_redirect.call_args[0][1] == "https://qbm.example.com/auth/oidc/callback"


def test_oidc_client_uses_pkce_s256_and_discovery():
    client = auth.oidc_client(oidc_settings())
    assert client.client_kwargs["code_challenge_method"] == "S256"
    assert client._server_metadata_url.endswith("openid-configuration")


def test_oidc_callback_logs_in_the_allowed_user(config_dir, monkeypatch):
    write_settings(config_dir, **oidc_settings(username="owner").model_dump())
    client = MagicMock()
    client.authorize_access_token = AsyncMock(return_value={"userinfo": {"sub": "user-1"}})
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    app = make_app(config_dir)
    resp = send(app, "GET", "/auth/oidc/callback")
    assert resp.status in (302, 307)
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie_header(cookie_of(resp))).status == 200
    client.authorize_access_token = AsyncMock(return_value={"userinfo": {"sub": "someone-else"}})
    assert send(app, "GET", "/auth/oidc/callback").status == 403


def test_oidc_local_password_is_off_by_default(config_dir):
    write_settings(config_dir, **oidc_settings(username="owner", password_hash=hash_password(PASSWORD)).model_dump())
    app = make_app(config_dir)
    assert login(app)[0].status == 403
    assert send(app, "GET", "/api/configs/config.yml", headers=list(basic().items())).status == 401
    write_settings(
        config_dir, **oidc_settings(username="owner", password_hash=hash_password(PASSWORD), allow_local_login=True).model_dump()
    )
    assert login(make_app(config_dir))[0].status == 200


# --- Server wiring ----------------------------------------------------------------------------------------


def test_uvicorn_never_rewrites_the_peer_address():
    from modules.web_api import build_uvicorn_config

    config = build_uvicorn_config(object(), "127.0.0.1", 8181)
    assert config.proxy_headers is False


# --- Security settings endpoint ---------------------------------------------------------------------------


def test_security_read_returns_no_secrets(config_dir):
    local_settings(config_dir, oidc_client_secret="CANARY-OIDC-SECRET")
    resp = send(make_app(config_dir), "GET", "/api/security", headers=list(basic().items()))
    data = resp.json()
    assert data["mode"] == "local" and data["has_api_key"] is True and data["has_oidc_client_secret"] is True
    for secret in ("CANARY-OIDC-SECRET", API_KEY, "argon2"):
        assert secret not in resp.text
    assert "bypass_auth_for_local" not in data and "method" not in data


def test_partial_security_update_keeps_other_settings(config_dir):
    local_settings(config_dir, public_url="https://qbm.example.com", https_only=True)
    app = make_app(config_dir)
    body = {"generate_api_key": True, "current_password": PASSWORD}
    resp = send(app, "PUT", "/api/security", headers=list(basic().items()), body=body)
    assert resp.json()["success"] is True and resp.json()["api_key"] != API_KEY
    kept = auth.load_settings(config_dir / "qbm_settings.yml")
    assert kept.public_url == "https://qbm.example.com" and kept.https_only is True


def test_blank_oidc_client_secret_keeps_the_stored_one(config_dir):
    write_settings(
        config_dir, **oidc_settings(username="owner", password_hash=hash_password(PASSWORD), allow_local_login=True).model_dump()
    )
    app = make_app(config_dir)
    body = {"oidc_client_id": "renamed", "current_password": PASSWORD}
    assert send(
        app, "PUT", "/api/security", headers=list(basic().items()) + [("Origin", "http://127.0.0.1:8181")], body=body
    ).json()["success"]
    stored = auth.load_settings(config_dir / "qbm_settings.yml")
    assert stored.oidc_client_id == "renamed" and stored.oidc_client_secret == "s"


# --- Log masking ------------------------------------------------------------------------------------------


def test_notify_and_webhook_urls_never_reach_the_log_file(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from modules import apprise
    from modules import webhooks
    from modules.logs import MyLogger

    log_file = tmp_path / "t.log"
    real = MyLogger("t", str(log_file), "DEBUG", str(tmp_path), 100, "=", False, 1024 * 1024, 1)
    real.add_main_handler()
    monkeypatch.setattr(webhooks, "logger", real)
    monkeypatch.setattr(apprise, "logger", real)
    monkeypatch.setattr(apprise.Apprise, "check_api_url", lambda self: SimpleNamespace(status_code=200))
    hook, notify = "https://canary.invalid/CANARY-WEBHOOK-1", "discord://CANARY-NOTIFY-2"
    webhooks.Webhooks(SimpleNamespace(args={}, commands={}), {"error": [hook], "function": None})
    instance = apprise.Apprise(SimpleNamespace(), {"api_url": "http://apprise:8000", "notify_url": [notify]})
    real.info(f"sending to {hook} and {instance.notify_url}")
    text = log_file.read_text(encoding="utf-8")
    assert "sending to" in text and "CANARY-WEBHOOK-1" not in text and "CANARY-NOTIFY-2" not in text


def test_oidc_login_refuses_cleanly_when_the_provider_is_unreachable(config_dir, monkeypatch):
    write_settings(config_dir, **oidc_settings(username="owner").model_dump())
    client = MagicMock()
    client.authorize_redirect = AsyncMock(side_effect=ConnectionError("All connection attempts failed"))
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    resp = send(make_app(config_dir), "GET", "/auth/oidc/login")
    assert resp.status == 503 and "Traceback" not in resp.text and "connection attempts" not in resp.text


@pytest.mark.parametrize("path", ["/api/version", "/api/get_base_url"])
def test_version_and_base_url_need_a_login(local_dir, path):
    app = make_app(local_dir)
    assert send(app, "GET", path).status == 401
    assert send(app, "GET", path, headers=[("X-Api-Key", API_KEY)]).status == 200


def test_health_stays_public(local_dir):
    assert send(make_app(local_dir), "GET", "/api/health").status == 200


# --- Review round: re-authentication for sensitive changes ----------------------------------------------------


def session_login(app):
    return login(app)[1]


def oidc_only_app(config_dir, monkeypatch, **extra):
    write_settings(config_dir, **oidc_settings(username="", **extra).model_dump())
    client = MagicMock()
    client.authorize_access_token = AsyncMock(return_value={"userinfo": {"sub": "user-1", "auth_time": int(time.time())}})
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    app = make_app(config_dir)
    resp = send(app, "GET", "/auth/oidc/callback")
    return app, cookie_header(cookie_of(resp))


# --- Review round: external-mode CSRF ---------------------------------------------------------------------------


# --- Review round: restore tokens -----------------------------------------------------------------------------


def restore_fixture(local_dir):
    backups = local_dir / ".backups"
    backups.mkdir(exist_ok=True)
    (backups / "config_20260101_000000.yml").write_text(CONFIG.replace("qbt-secret-pass", "old-backup-pass"), encoding="utf-8")
    return [("X-Api-Key", API_KEY)]


def test_restore_without_a_backup_name_keeps_current_secrets(local_dir):
    app = make_app(local_dir)
    key = restore_fixture(local_dir)
    data = send(app, "POST", "/api/configs/config_20260101_000000.yml/restore", headers=key, body={}).json()["data"]
    assert send(app, "PUT", "/api/configs/config.yml", headers=key, body={"data": data}).status == 200
    assert "qbt-secret-pass" in (local_dir / "config.yml").read_text()


@pytest.mark.parametrize("host_changed", [False, True])
def test_saving_a_restored_backup_uses_the_backups_secrets(local_dir, host_changed):
    app = make_app(local_dir)
    key = restore_fixture(local_dir)
    if host_changed:
        (local_dir / "config.yml").write_text(CONFIG.replace("localhost:8080", "newhost:8080"), encoding="utf-8")
    name = "config_20260101_000000.yml"
    data = send(app, "POST", f"/api/configs/{name}/restore", headers=key, body={}).json()["data"]
    body = {"data": data, "restored_from": name}
    assert send(app, "PUT", "/api/configs/config.yml", headers=key, body=body).status == 200
    saved = (local_dir / "config.yml").read_text()
    assert "old-backup-pass" in saved and "qbt-secret-pass" not in saved


def test_save_returns_the_backup_of_the_replaced_config(local_dir):
    key = restore_fixture(local_dir)
    before = (local_dir / "config.yml").read_text()
    body = send(
        make_app(local_dir), "PUT", "/api/configs/config.yml", headers=key, body={"data": {"qbt": {"pass": "new"}}}
    ).json()
    assert (local_dir / ".backups" / body["backup_file"]).read_text() == before


@pytest.mark.parametrize("name", ["../config.yml", "missing.yml"])
def test_restored_from_must_be_a_backup_file(local_dir, name):
    key = restore_fixture(local_dir)
    body = {"data": {"qbt": {"pass": REDACTED}}, "restored_from": name}
    assert send(make_app(local_dir), "PUT", "/api/configs/config.yml", headers=key, body=body).status in (400, 404)


def test_no_server_side_restore_state(local_dir):
    app = make_app(local_dir)
    send(app, "POST", "/api/configs/config_20260101_000000.yml/restore", headers=restore_fixture(local_dir), body={})
    from modules import web_api

    assert not hasattr(web_api.WebAPI, "_restored_backups")


# --- Review round: small checks ---------------------------------------------------------------------------------


def test_email_only_oidc_logs_a_warning(tmp_path, monkeypatch):
    path = tmp_path / "qbm_settings.yml"
    write_settings(tmp_path, **oidc_settings(oidc_sub="", oidc_email="me@example.com").model_dump())
    spy = MagicMock()
    monkeypatch.setattr(auth, "logger", spy)
    assert auth.ensure_credentials(path, {}) is True
    assert "oidc_sub" in spy.warning.call_args[0][0]


def test_settings_writers_share_one_lock(config_dir):

    path = config_dir / "qbm_settings.yml"
    local_settings(config_dir)
    done = threading.Event()

    def save():
        auth.save_auth_settings(path, auth.load_settings(path))
        done.set()

    with auth.settings_lock(path):
        threading.Thread(target=save, daemon=True).start()
        assert done.wait(0.5) is False
    assert done.wait(5) is True


@pytest.mark.parametrize("config_file", ["qbm_settings.yml", "QBM_Settings.YML"])
def test_run_command_rejects_the_settings_file(config_file):
    with pytest.raises(ValidationError):
        CommandRequest(config_file=config_file, commands=[])


def test_glob_matches_never_include_the_settings_file(config_dir):
    local_settings(config_dir)
    assert util.get_matching_config_files("*.yml", str(config_dir)) == ["config.yml"]


def test_login_page_shows_where_the_first_run_password_is(config_dir):
    local_settings(config_dir)
    (config_dir / auth.INITIAL_PASSWORD_FILE).write_text("username: admin\npassword: x\n")
    page = send(make_app(config_dir), "GET", "/login").text
    assert auth.INITIAL_PASSWORD_FILE in page and str(config_dir) not in page and "password: x" not in page
    (config_dir / auth.INITIAL_PASSWORD_FILE).unlink()
    assert auth.INITIAL_PASSWORD_FILE not in send(make_app(config_dir), "GET", "/login").text


def test_web_ui_has_a_logout_button():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "web-ui"
    assert 'id="logout-btn"' in (root / "index.html").read_text()
    assert "/logout" in (root / "js" / "components" / "header.js").read_text()


# --- Review round: 4.x migrations end to end ------------------------------------------------------------------


def test_4x_api_only_moves_to_local_and_keeps_the_key(config_dir):
    path = config_dir / "qbm_settings.yml"
    write_settings(config_dir, enabled=True, method="api_only", api_key=API_KEY)
    assert auth.ensure_credentials(path, {}) is True
    settings = auth.load_settings(path)
    assert settings.mode == "local" and settings.api_key == API_KEY and settings.password_hash
    assert (config_dir / auth.INITIAL_PASSWORD_FILE).exists()
    app = make_app(config_dir)
    assert send(app, "GET", "/api/configs/config.yml", headers=[("X-Api-Key", API_KEY)]).status == 200
    assert send(app, "GET", "/api/configs/config.yml").status == 401


def test_4x_disabled_auth_with_stored_credentials_now_requires_them(config_dir):
    write_settings(config_dir, enabled=False, method="basic", username="owner", password_hash=hash_password(PASSWORD))
    app = make_app(config_dir)
    assert send(app, "GET", "/api/configs/config.yml").status == 401
    assert login(app, password="wrong")[0].status == 401
    assert login(app)[0].status == 200


# --- Review round: OIDC through Authlib's real token path ---------------------------------------------------


@pytest.fixture
def real_oidc(config_dir, monkeypatch):
    """A real Authlib client whose discovery data and token endpoint are replaced; nonce and state run for real."""
    from authlib.integrations.httpx_client import AsyncOAuth2Client
    from joserfc import jwt
    from joserfc.jwk import KeySet
    from joserfc.jwk import RSAKey

    auth._oidc_clients.clear()
    key = RSAKey.generate_key(2048)
    settings = oidc_settings(username="owner")
    write_settings(config_dir, **settings.model_dump())
    client = auth.oidc_client(settings)
    client.server_metadata.update(
        _loaded_at=1,
        issuer="https://idp.example",
        authorization_endpoint="https://idp.example/authorize",
        token_endpoint="https://idp.example/token",
        jwks=KeySet([key]).as_dict(private=False),
        id_token_signing_alg_values_supported=["RS256"],
    )
    state = {"nonce": None, "id_token": True, "claims": {}}

    async def fetch_token(self, url, **kwargs):
        token = {"access_token": "at", "token_type": "Bearer", "expires_in": 60}
        if state["id_token"]:
            claims = {"iss": "https://idp.example", "aud": "qbm", "sub": "user-1", "exp": int(time.time()) + 300,
                      "iat": int(time.time()), "nonce": state["nonce"], "at_hash": None}  # fmt: skip
            claims.update(state["claims"])
            claims = {k: v for k, v in claims.items() if v is not None}
            token["id_token"] = jwt.encode({"alg": "RS256", "kid": key.thumbprint()}, claims, key)
        return token

    monkeypatch.setattr(AsyncOAuth2Client, "fetch_token", fetch_token)
    app = make_app(config_dir)
    started = send(app, "GET", "/auth/oidc/login")
    location = started.header("location")[0]
    from urllib.parse import parse_qs

    query = parse_qs(urlsplit(location).query)
    assert query["code_challenge_method"] == ["S256"] and query["redirect_uri"] == ["https://qbm.example.com/auth/oidc/callback"]
    state["nonce"] = query["nonce"][0]
    return app, cookie_header(cookie_of(started)), query["state"][0], state


def callback(app, cookie, state_value):
    return send(app, "GET", f"/auth/oidc/callback?code=abc&state={state_value}", headers=cookie)


def test_real_oidc_flow_logs_in(real_oidc):
    app, cookie, state_value, _ = real_oidc
    resp = callback(app, cookie, state_value)
    assert resp.status == 302
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie_header(cookie_of(resp))).status == 200


def test_real_oidc_state_mismatch_is_refused(real_oidc):
    app, cookie, _, _ = real_oidc
    assert callback(app, cookie, "forged-state").status == 401


def test_real_oidc_nonce_mismatch_is_refused(real_oidc):
    app, cookie, state_value, state = real_oidc
    state["nonce"] = "not-the-nonce"
    assert callback(app, cookie, state_value).status == 401


def test_real_oidc_missing_id_token_is_refused(real_oidc):
    app, cookie, state_value, state = real_oidc
    state["id_token"] = False
    resp = callback(app, cookie, state_value)
    assert resp.status in (401, 403)
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie_header(cookie_of(resp))).status == 401


def test_real_oidc_other_subject_is_refused(real_oidc):
    app, cookie, state_value, state = real_oidc
    state["claims"] = {"sub": "intruder"}
    assert callback(app, cookie, state_value).status == 403


def test_anonymous_health_is_only_a_status(local_dir):
    resp = send(make_app(local_dir), "GET", "/api/health")
    assert resp.status == 200 and list(resp.json()) == ["status"]
    for word in ("version", "branch", "queue", "directories", str(local_dir)):
        assert word not in resp.text


def test_health_details_need_a_login(local_dir):
    app = make_app(local_dir)
    assert send(app, "GET", "/api/health_details").status == 401
    detail = send(app, "GET", "/api/health_details", headers=[("X-Api-Key", API_KEY)])
    assert detail.status == 200 and "version" in detail.json()


def test_refused_security_changes_use_error_statuses_and_keep_the_body(local_dir):
    app = make_app(local_dir)
    cookie = session_login(app)
    wrong = send(app, "PUT", "/api/security", headers=cookie, body={"password": "N3w-Passw0rd!x", "current_password": "no"})
    assert wrong.status == 403 and wrong.json()["success"] is False and "password" in wrong.json()["message"]
    invalid = send(app, "PUT", "/api/security", headers=cookie, body={"mode": "bogus", "current_password": PASSWORD})
    assert invalid.status == 400 and invalid.json()["success"] is False
    nologin = send(app, "PUT", "/api/security", headers=cookie, body={"mode": "oidc", "current_password": PASSWORD})
    assert nologin.status == 400
    done = send(
        app, "PUT", "/api/security", headers=cookie, body={"public_url": "https://x.example", "current_password": PASSWORD}
    )
    assert done.status == 200 and done.json()["success"] is True


# --- Review round 3 -----------------------------------------------------------------------------------------


def new_cookie(resp, old):
    return cookie_header({**{k: v for k, v in [c.split("=", 1) for c in old[0][1].split("; ")]}, **cookie_of(resp)})


def test_basic_auth_accepts_utf8_passwords(config_dir):
    password = "P\u00e4ssw0rd!\u00fc"
    write_settings(config_dir, mode="local", username="owner", password_hash=hash_password(password))
    token = base64.b64encode(f"owner:{password}".encode()).decode()
    resp = send(make_app(config_dir), "GET", "/api/configs/config.yml", headers=[("Authorization", f"Basic {token}")])
    assert resp.status == 200


def test_scheduler_reports_a_lock_timeout_and_keeps_its_state(config_dir, monkeypatch):
    from modules.scheduler import Scheduler

    def timeout(*_a, **_k):
        raise TimeoutError("busy")

    monkeypatch.setattr(util, "settings_lock", timeout)
    scheduler = Scheduler(str(config_dir), suppress_logging=True)
    scheduler._persistence_disabled = True
    assert scheduler.save_schedule("interval", 60) is False
    assert scheduler._persistence_disabled is True and scheduler.current_schedule is None


def test_list_secret_with_changed_sibling_host_is_refused():
    old = {"apprise": {"api_url": "http://good:8000", "notify_url": ["discord://TOKEN"]}}
    new = {"apprise": {"api_url": "http://attacker:8000", "notify_url": [REDACTED]}}
    with pytest.raises(HTTPException) as exc:
        restore_redacted(new, old)
    assert exc.value.status_code == 400


def test_list_secret_with_unchanged_sibling_host_is_restored():
    old = {"apprise": {"api_url": "http://good:8000", "notify_url": ["discord://TOKEN"]}}
    new = {"apprise": {"api_url": "http://good:8000", "notify_url": [REDACTED]}}
    assert restore_redacted(new, old) == old


# --- Review round 4 -----------------------------------------------------------------------------------------


def test_a_rejected_env_password_is_not_logged(tmp_path):
    spy = MagicMock()
    path = tmp_path / "qbm_settings.yml"
    original, auth.logger = auth.logger, spy
    try:
        assert auth.ensure_credentials(path, {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "weakpass"}) is False
    finally:
        auth.logger = original
    assert "weakpass" not in str(spy.error.call_args_list)


def test_a_truncated_signing_key_is_replaced(tmp_path):
    (tmp_path / auth.SESSION_KEY_FILE).write_text("", encoding="utf-8")
    assert len(auth.session_secret(tmp_path)) >= 32
    assert auth.session_secret(tmp_path) == auth.session_secret(tmp_path)


@pytest.mark.skipif(auth.os.name == "nt", reason="POSIX permissions")
def test_loading_tightens_a_world_readable_settings_file(local_dir):
    path = local_dir / "qbm_settings.yml"
    path.chmod(0o644)
    auth.load_settings(path)
    assert path.stat().st_mode & 0o077 == 0


def test_a_configured_oidc_subject_is_authoritative():
    settings = oidc_settings(oidc_sub="user-1", oidc_email="me@example.com")
    assert not auth.oidc_identity_allowed({"sub": "other", "email": "me@example.com", "email_verified": True}, settings)


def test_api_only_with_a_password_and_no_key_is_usable():
    assert auth.has_credentials(auth.AuthSettings(mode="api_only", username="owner", password_hash=hash_password(PASSWORD)))


def test_function_webhook_urls_are_registered_as_secrets(monkeypatch):
    from modules import webhooks

    seen = []
    monkeypatch.setattr(webhooks, "logger", MagicMock(secret=seen.append))
    webhooks.Webhooks(MagicMock(), {"function": [{"recheck": "https://hooks.example/token-abc"}]})
    assert "https://hooks.example/token-abc" in seen


def test_run_command_config_must_stay_in_the_config_directory(local_dir, tmp_path_factory):
    from modules.web_api import contained_config_path

    outside = tmp_path_factory.mktemp("outside") / "other.yml"
    outside.write_text(CONFIG, encoding="utf-8")
    (local_dir / "link.yml").symlink_to(outside)
    assert contained_config_path(local_dir, "config.yml") == str((local_dir / "config.yml").resolve())
    with pytest.raises(HTTPException) as refused:
        contained_config_path(local_dir, "link.yml")
    assert refused.value.status_code == 400


def test_external_mode_becomes_local_and_keeps_the_key(config_dir):
    path = config_dir / "qbm_settings.yml"
    write_settings(config_dir, mode="external", trusted_proxies=["10.0.0.2"], api_key=API_KEY)
    assert auth.ensure_credentials(path, {}) is True
    settings = auth.load_settings(path)
    assert settings.mode == "local" and settings.api_key == API_KEY and settings.password_hash
    assert (config_dir / auth.INITIAL_PASSWORD_FILE).exists()
    app = make_app(config_dir, host="0.0.0.0")
    assert send(app, "GET", "/api/configs/config.yml", ip="10.0.0.2").status == 401  # a former proxy address gets no pass


def test_4x_external_method_becomes_local(config_dir):
    write_settings(config_dir, enabled=True, method="external", username="owner", password_hash=hash_password(PASSWORD))
    assert auth.load_settings(config_dir / "qbm_settings.yml").mode == "local"


def test_rate_limit_keys_on_the_tcp_peer_and_ignores_forwarded_for(local_dir):
    app = make_app(local_dir, host="0.0.0.0")
    for i in range(auth.MAX_AUTH_ATTEMPTS):
        send(
            app,
            "POST",
            "/login",
            ip="10.0.0.2",
            headers=[("X-Forwarded-For", f"203.0.113.{i}")],
            body={"username": "x", "password": "y"},
        )
    blocked = send(
        app,
        "POST",
        "/login",
        ip="10.0.0.2",
        headers=[("X-Forwarded-For", "198.51.100.1")],
        body={"username": "x", "password": "y"},
    )
    assert blocked.status == 429


# --- Review round: CSRF origin, callback limit, validate, hardening ---------------------------------------------


@pytest.mark.parametrize("value", ["qbm.example.com", "ftp://qbm.example.com", "https://", "//qbm.example.com"])
def test_public_url_must_be_an_http_url_with_a_host(value):
    with pytest.raises(ValidationError):
        auth.AuthSettings(public_url=value)
    with pytest.raises(ValidationError):
        auth.SecuritySettingsRequest(public_url=value)


@pytest.mark.parametrize("value", ["", "https://qbm.example.com", "http://qbm.example.com:8181"])
def test_public_url_accepts_empty_and_http_urls(value):
    assert auth.AuthSettings(public_url=value).public_url == value


def test_failed_oidc_callbacks_do_not_lock_out_the_address(config_dir, monkeypatch):
    write_settings(config_dir, **oidc_settings(username="owner").model_dump())
    client = MagicMock()
    client.authorize_access_token = AsyncMock(side_effect=ValueError("bad code"))
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    app = make_app(config_dir)
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        assert send(app, "GET", "/auth/oidc/callback").status == 401
    assert send(app, "GET", "/auth/oidc/callback").status == 429
    assert not auth.is_rate_limited("127.0.0.1")


def test_validate_reports_a_refused_redaction_as_400(local_dir):
    app = make_app(local_dir)
    key = [("X-Api-Key", API_KEY)]
    data = send(app, "GET", "/api/configs/config.yml", headers=key).json()["data"]
    data["apprise"]["notify_url"] = [data["apprise"]["notify_url"][0], "discord://another"]
    assert send(app, "POST", "/api/configs/config.yml/validate", headers=key, body={"data": data}).status == 400


@pytest.mark.skipif(auth.os.name == "nt", reason="POSIX permissions")
def test_an_existing_signing_key_is_tightened(tmp_path):
    key = tmp_path / auth.SESSION_KEY_FILE
    key.write_text("k" * 48, encoding="utf-8")
    key.chmod(0o644)
    assert auth.session_secret(tmp_path) == "k" * 48
    assert key.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(auth.os.name == "nt", reason="POSIX permissions")
def test_an_existing_initial_password_file_is_tightened(tmp_path):
    password_file = tmp_path / auth.INITIAL_PASSWORD_FILE
    password_file.write_text("old", encoding="utf-8")
    password_file.chmod(0o644)
    assert auth.ensure_credentials(tmp_path / "qbm_settings.yml", {})
    assert password_file.stat().st_mode & 0o077 == 0


def test_every_secret_field_name_is_registered_for_log_masking(local_dir):
    from modules.web_api import WebAPI

    seen = []
    api = WebAPI.__new__(WebAPI)
    from modules import web_api

    web_api.logger = MagicMock(secret=seen.append)
    try:
        api._register_sensitive_fields_as_secrets(
            {
                "qbt": {"pass": "p-1"},
                "notifiarr": {"apikey": "k-1"},
                "x": {"client_secret": "c-1"},
                "apprise": {"notify_url": ["discord://n-1", "slack://n-2"]},
                "webhooks": {"function": {"recheck": ["https://hooks.example/a", "https://hooks.example/b"]}},
            }
        )
    finally:
        web_api.logger = web_api._LoggerProxy()
    wanted = {"p-1", "k-1", "c-1", "discord://n-1", "slack://n-2", "https://hooks.example/a", "https://hooks.example/b"}
    assert wanted <= set(seen)


def test_list_function_webhook_urls_are_registered_as_secrets(monkeypatch):
    from modules import webhooks

    seen = []
    monkeypatch.setattr(webhooks, "logger", MagicMock(secret=seen.append))
    webhooks.Webhooks(MagicMock(), {"function": [{"recheck": ["https://hooks.example/a", "https://hooks.example/b"]}]})
    assert {"https://hooks.example/a", "https://hooks.example/b"} <= set(seen)


@pytest.mark.parametrize("env", [{"QBT_WEB_USERNAME": "owner"}, {"QBT_WEB_PASSWORD": "x"}])
def test_a_half_set_env_login_is_reported(tmp_path, monkeypatch, env):
    from modules import util

    warnings = []
    monkeypatch.setattr(util, "logger", MagicMock(warning=warnings.append, info=lambda *a, **k: None))
    assert auth.ensure_credentials(tmp_path / "qbm_settings.yml", env)
    assert any("QBT_WEB_USERNAME" in w and "QBT_WEB_PASSWORD" in w for w in warnings)


def test_an_oidc_session_needs_no_password_when_local_login_is_off(config_dir, monkeypatch):
    app, cookie = oidc_only_app(config_dir, monkeypatch, password_hash=hash_password(PASSWORD))
    resp = send(app, "PUT", "/api/security", headers=cookie, body={"public_url": "https://other.example.com"})
    assert resp.json()["success"] is True


def test_login_page_names_the_password_file_without_a_path(config_dir):
    local_settings(config_dir)
    (config_dir / auth.INITIAL_PASSWORD_FILE).write_text("x", encoding="utf-8")
    page = send(make_app(config_dir), "GET", "/login").text
    assert auth.INITIAL_PASSWORD_FILE in page and str(config_dir) not in page
    assert "exact path" not in (Path(__file__).parents[1] / "docs" / "Security.md").read_text(encoding="utf-8")


# --- Review round: web UI behavior ------------------------------------------------------------------------------

WEB_UI = Path(__file__).resolve().parents[1] / "web-ui"


def test_the_ui_has_no_dead_api_doc_links_and_logs_in_at_its_own_path():
    app_js = (WEB_UI / "js" / "app.js").read_text(encoding="utf-8")
    assert 'href="/docs"' not in app_js and 'href="/redoc"' not in app_js
    assert "response.status === 401" in app_js and "/login`" in app_js
    assert "openapi.json" not in (WEB_UI / "js" / "api.js").read_text(encoding="utf-8")


def test_saving_security_settings_does_not_redirect_to_login():
    panel = (WEB_UI / "js" / "components" / "security.js").read_text(encoding="utf-8")
    assert "window.location.href" not in panel
    assert "signs out every browser" in panel
    assert "api_only" in panel


# --- Review round: second pass --------------------------------------------------------------------------------


def make_api(config_dir):
    from modules.web_api import WebAPI

    return WebAPI(
        default_dir=str(config_dir),
        args={"config_dir": str(config_dir), "base_url": "", "host": "127.0.0.1"},
        is_running=multiprocessing.Value("b", False),
        is_running_lock=multiprocessing.Lock(),
        web_api_queue=queue.Queue(),
        scheduler_update_queue=queue.Queue(),
        next_scheduled_run_info={},
    )


@pytest.fixture
def trace_log(tmp_path, monkeypatch):
    from modules.logs import MyLogger

    log_file = tmp_path / "trace.log"
    real = MyLogger("trace", str(log_file), "TRACE", str(tmp_path), 100, "=", False, 1024 * 1024, 1)
    real.add_main_handler()
    monkeypatch.setattr(util, "logger", real)
    return log_file


def test_config_writes_never_log_secrets_at_trace(local_dir, trace_log, monkeypatch):
    monkeypatch.setenv("QBM_CANARY_PASS", "env-canary-secret")
    app = make_app(local_dir)
    key = [("X-Api-Key", API_KEY)]
    created = {"qbt": {"host": "http://admin:url-canary-pass@qbt:8080", "pass": "create-canary-pass"}}
    assert send(app, "POST", "/api/configs/new.yml", headers=key, body={"data": created}).status == 200
    updated = {"qbt": {"host": "localhost:8080", "user": "admin", "pass": "!ENV QBM_CANARY_PASS"}}
    body = {"data": updated, "current_password": PASSWORD}  # a new !ENV secret needs the login password
    assert send(app, "PUT", "/api/configs/config.yml", headers=key, body=body).status == 200
    text = trace_log.read_text(encoding="utf-8")
    assert "Full data structure being written" in text
    for canary in ("create-canary-pass", "url-canary-pass", "env-canary-secret"):
        assert canary not in text


def test_validate_never_writes_the_config_file(local_dir, monkeypatch):
    from modules import web_api

    def add_default(default_dir, args):
        path = Path(args["config_file"])
        assert path.is_absolute()
        path.write_text(path.read_text(encoding="utf-8") + "added_default: true\n", encoding="utf-8")

    monkeypatch.setattr(web_api, "Config", add_default)
    app = make_app(local_dir)
    key = restore_fixture(local_dir)
    before = (local_dir / "config.yml").read_text()
    restored = send(app, "POST", "/api/configs/config_20260101_000000.yml/restore", headers=key, body={}).json()
    body = {"data": restored["data"]}
    resp = send(app, "POST", "/api/configs/config.yml/validate", headers=key, body=body).json()
    assert resp["valid"] and resp["config_modified"] and resp["data"]["added_default"] is True
    assert resp["data"]["qbt"]["pass"] == REDACTED  # the backup's secret goes back redacted
    assert (local_dir / "config.yml").read_text() == before
    assert sorted(p.name for p in local_dir.glob("tmp*.yml")) == []
    assert send(app, "PUT", "/api/configs/config.yml", headers=key, body=body).status == 200  # token still unspent


def test_validate_cleans_up_when_the_temp_write_fails(local_dir, monkeypatch):
    from modules import web_api

    def boom(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(web_api.YAML, "save_preserving_format", boom)
    app = make_app(local_dir)
    resp = send(app, "POST", "/api/configs/config.yml/validate", headers=[("X-Api-Key", API_KEY)], body={"data": {}})
    assert resp.status == 500 and list(local_dir.glob("tmp*.yml")) == []


@pytest.mark.parametrize("name", ["qbm_initial_password.txt", "schedule.yml", "secrets.yml", ".session_secret", "notes.txt"])
def test_config_api_refuses_non_config_files(local_dir, name):
    (local_dir / name).write_text("plaintext-canary\n", encoding="utf-8")
    app = make_app(local_dir)
    key = [("X-Api-Key", API_KEY)]
    assert send(app, "GET", f"/api/configs/{name}", headers=key).status in (400, 403)
    assert send(app, "DELETE", f"/api/configs/{name}", headers=key).status in (400, 403)
    assert (local_dir / name).exists()
    backups = local_dir / ".backups"
    assert not backups.exists() or all("plaintext-canary" not in p.read_text() for p in backups.iterdir())


def test_run_command_glob_skips_the_first_run_password_file(local_dir, trace_log, monkeypatch):
    from modules import web_api

    (local_dir / "qbm_initial_password.txt").write_text("pw\n", encoding="utf-8")
    seen = []

    async def fake_run(self, run_args, hashes):
        seen.append(run_args["config_files"][0])
        raise RuntimeError("stop")

    monkeypatch.setattr(web_api.WebAPI, "execute_for_config", fake_run)
    api = make_api(local_dir)
    with pytest.raises(HTTPException):
        asyncio.run(api._execute_command(CommandRequest(config_file="*", commands=["cat_update"])))
    assert "qbm_initial_password.txt" not in seen and seen


def test_run_command_keeps_a_400_for_a_bad_command(local_dir, trace_log):
    api = make_api(local_dir)
    with pytest.raises(HTTPException) as e:
        asyncio.run(api._execute_command(CommandRequest(config_file="config.yml", commands=["not_a_command"])))
    assert e.value.status_code == 400


def test_scheduler_temp_file_is_private_even_if_one_was_left_behind(config_dir):
    from modules.scheduler import Scheduler

    local_settings(config_dir)
    leftover = config_dir / "qbm_settings.yml.tmp"
    leftover.write_text("old\n", encoding="utf-8")
    leftover.chmod(0o644)
    modes = []
    real_save = util.YAML.save

    def spy(self):
        real_save(self)
        modes.append(stat.S_IMODE(Path(self.path).stat().st_mode))

    scheduler = Scheduler(str(config_dir), suppress_logging=True)
    try:
        util.YAML.save = spy
        scheduler._persist_schedule_file("interval", 30)
    finally:
        util.YAML.save = real_save
    assert modes == [0o600]
    assert auth.load_settings(config_dir / "qbm_settings.yml").username == "owner"


def test_restore_refuses_a_symlink_to_a_sibling_with_the_same_prefix(local_dir):
    backups = local_dir / ".backups"
    backups.mkdir()
    sibling = local_dir / ".backups_other"
    sibling.mkdir()
    (sibling / "config_20260101_000000.yml").write_text(CONFIG, encoding="utf-8")
    (backups / "config_20260101_000000.yml").symlink_to(sibling / "config_20260101_000000.yml")
    app = make_app(local_dir)
    resp = send(app, "POST", "/api/configs/config_20260101_000000.yml/restore", headers=[("X-Api-Key", API_KEY)], body={})
    assert resp.status == 400


def test_api_prefix_does_not_match_other_paths(local_dir):
    app = make_app(local_dir)
    assert send(app, "GET", "/api-anything", headers=[("X-Api-Key", API_KEY)]).status == 401
    assert send(app, "GET", "/api-anything", headers=list(basic().items())).status == 401
    assert send(app, "GET", "/api/version", headers=[("X-Api-Key", API_KEY)]).status == 200


def test_oidc_email_must_be_a_string():
    settings = oidc_settings(oidc_sub="", oidc_email="me@example.invalid")
    assert not auth.oidc_identity_allowed({"email": ["me@example.invalid"], "email_verified": True}, settings)


def test_login_page_base_url_is_a_js_string_literal(local_dir):
    app = make_app(local_dir, base_url="/q'b</script>")
    page = send(app, "GET", "/q'b</script>/login").text
    assert "</script>/login" not in page.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert "\"/q'b\\u003c/script>\" + '/login'" in page


def test_auth_store_reloads_when_the_file_is_replaced_with_the_same_size_and_time(config_dir):
    import os

    local_settings(config_dir, public_url="https://a.example.com")
    path = config_dir / "qbm_settings.yml"
    store = auth.AuthStore(path)
    assert store.get().public_url == "https://a.example.com"
    st = path.stat()
    other = config_dir / "other.yml"
    other.write_text(path.read_text().replace("https://a.example.com", "https://b.example.com"), encoding="utf-8")
    os.utime(other, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.replace(other, path)
    assert store.get().public_url == "https://b.example.com"


def test_ui_stops_after_the_login_redirect_and_validate_does_not_reload_from_disk():
    app_js = (WEB_UI / "js" / "app.js").read_text(encoding="utf-8")
    assert "if (!(await this.fetchAppConfig())) return;" in app_js and "return false;" in app_js
    form_js = (WEB_UI / "js" / "components" / "config-form.js").read_text(encoding="utf-8")
    for source in (app_js, form_js):
        assert "const configResponse = { data: response.data };" in source


# --- Proxies, env credentials, file modes, and other hardening ---------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
KEY = [("X-Api-Key", API_KEY)]


def _slow_check(monkeypatch):
    real = auth.check_login
    calls = []

    def slow(*a):
        calls.append(1)
        time.sleep(0.05)
        return real(*a)

    monkeypatch.setattr(auth, "check_login", slow)
    return calls


def test_json_escaped_secrets_never_reach_the_trace_log(local_dir, tmp_path, monkeypatch):
    from modules.logs import MyLogger

    log_file = tmp_path / "trace.log"
    real = MyLogger("trace", str(log_file), "TRACE", str(tmp_path), 100, "=", False, 1024 * 1024, 1)
    real.add_main_handler()
    monkeypatch.setattr(util, "logger", real)
    app = make_app(local_dir)
    secret = 'qu"ote\\back-é-canary'
    body = {"data": {"qbt": {"host": "localhost:8080", "user": "admin", "pass": secret}}}
    assert send(app, "PUT", "/api/configs/config.yml", headers=[("X-Api-Key", API_KEY)], body=body).status == 200
    text = log_file.read_text(encoding="utf-8")
    assert "canary" not in text


def test_logger_masks_the_json_escaped_form_of_a_secret(tmp_path):
    from modules.logs import MyLogger

    log_file = tmp_path / "t.log"
    real = MyLogger("t2", str(log_file), "TRACE", str(tmp_path), 100, "=", False, 1024 * 1024, 1)
    real.add_main_handler()
    real.secrets.add('a"b\\c')
    real.trace(json.dumps({"x": 'a"b\\c'}))
    assert 'a\\"b' not in log_file.read_text(encoding="utf-8")


def test_public_url_path_is_refused_in_a_request():
    with pytest.raises(ValidationError):
        auth.SecuritySettingsRequest(public_url="https://qbm.example.com/qbm")


def test_stored_public_url_path_is_stripped_so_the_callback_is_not_doubled(config_dir, monkeypatch):
    write_settings(
        config_dir,
        mode="oidc",
        public_url="https://qbm.example.com/qbm/",
        oidc_metadata_url="https://idp/.well-known/openid-configuration",
        oidc_client_id="c",
        oidc_sub="s",
    )
    seen = {}

    class Client:
        async def authorize_redirect(self, request, redirect_uri, **kw):
            from fastapi.responses import RedirectResponse

            seen["uri"] = redirect_uri
            return RedirectResponse("https://idp/auth")

    monkeypatch.setattr(auth, "oidc_client", lambda s: Client())
    app = make_app(config_dir, base_url="/qbm")
    send(app, "GET", "/qbm/auth/oidc/login")
    assert seen["uri"] == "https://qbm.example.com/qbm/auth/oidc/callback"


def test_public_url_help_says_scheme_and_host_only():
    js = (ROOT / "web-ui/js/components/security.js").read_text(encoding="utf-8")
    assert "scheme and host only" in js


def test_password_reset_env_enables_local_login_in_oidc_mode(tmp_path):
    path = tmp_path / "qbm_settings.yml"
    write_settings(
        tmp_path,
        mode="oidc",
        username="owner",
        password_hash=hash_password(PASSWORD),
        public_url="https://qbm.example.com",
        oidc_metadata_url="https://idp/x",
        oidc_client_id="c",
        oidc_sub="s",
    )
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "New-Pass-123", "QBT_WEB_PASSWORD_RESET": "true"}
    assert auth.ensure_credentials(path, env)
    assert auth.load_settings(path).allow_local_login is True


def test_public_url_env_is_stored_at_startup(local_dir):
    path = local_dir / "qbm_settings.yml"
    assert auth.ensure_credentials(path, {"QBT_PUBLIC_URL": "https://qbm.example.com"})
    assert auth.load_settings(path).public_url == "https://qbm.example.com"


def test_bad_public_url_env_stops_the_server(local_dir):
    assert not auth.ensure_credentials(local_dir / "qbm_settings.yml", {"QBT_PUBLIC_URL": "qbm.example.com"})


def test_login_page_shows_the_server_reason():
    assert "await r.text()" in auth.LOGIN_PAGE


def test_trusted_proxy_forwarded_for_is_the_rate_limit_key(config_dir):
    local_settings(config_dir, trusted_proxies=["10.0.0.0/8"])
    app = make_app(config_dir, host="0.0.0.0")
    bad = {"username": "x", "password": "y"}
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        send(app, "POST", "/login", ip="10.0.0.2", headers=[("X-Forwarded-For", "203.0.113.5")], body=bad)
    assert send(app, "POST", "/login", ip="10.0.0.2", headers=[("X-Forwarded-For", "203.0.113.5")], body=bad).status == 429
    other = send(app, "POST", "/login", ip="10.0.0.2", headers=[("X-Forwarded-For", "198.51.100.7")], body=bad)
    assert other.status == 401


def test_forwarded_for_from_an_untrusted_peer_is_ignored(config_dir):
    local_settings(config_dir, trusted_proxies=["10.0.0.0/8"])
    app = make_app(config_dir, host="0.0.0.0")
    bad = {"username": "x", "password": "y"}
    for i in range(auth.MAX_AUTH_ATTEMPTS):
        send(app, "POST", "/login", ip="192.0.2.9", headers=[("X-Forwarded-For", f"203.0.113.{i}")], body=bad)
    assert send(app, "POST", "/login", ip="192.0.2.9", headers=[("X-Forwarded-For", "198.51.100.1")], body=bad).status == 429


def test_a_spoofed_left_entry_does_not_escape_the_limit(config_dir):
    local_settings(config_dir, trusted_proxies=["10.0.0.1"])
    app = make_app(config_dir, host="0.0.0.0")
    bad = {"username": "x", "password": "y"}
    for i in range(auth.MAX_AUTH_ATTEMPTS):
        hdr = [("X-Forwarded-For", f"1.2.3.{i}, 203.0.113.5")]
        send(app, "POST", "/login", ip="10.0.0.1", headers=hdr, body=bad)
    hdr = [("X-Forwarded-For", "9.9.9.9, 203.0.113.5")]
    assert send(app, "POST", "/login", ip="10.0.0.1", headers=hdr, body=bad).status == 429


def test_trusted_proxies_env_is_stored_and_validated(local_dir):
    path = local_dir / "qbm_settings.yml"
    assert not auth.ensure_credentials(path, {"QBT_TRUSTED_PROXIES": "not-an-ip"})
    assert auth.ensure_credentials(path, {"QBT_TRUSTED_PROXIES": "10.0.0.1, 172.16.0.0/12"})
    assert auth.load_settings(path).trusted_proxies == ["10.0.0.1", "172.16.0.0/12"]


def test_a_limited_client_is_refused_before_any_password_check(local_dir, monkeypatch):
    app = make_app(local_dir)
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        send(app, "GET", "/api/configs", headers=list(basic(password="wrong").items()))
    calls = _slow_check(monkeypatch)
    assert send(app, "GET", "/api/configs", headers=list(basic().items())).status == 429
    assert login(app)[0].status == 429
    assert calls == []


def test_skipped_env_credentials_log_one_info_line(local_dir, monkeypatch):
    lines = []
    monkeypatch.setattr(util, "logger", logging.getLogger("qbm-test"))
    monkeypatch.setattr(util.logger, "info", lambda m, *a, **k: lines.append(m))
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "Other-Pass-123"}
    assert auth.ensure_credentials(local_dir / "qbm_settings.yml", env)
    assert sum("QBT_WEB_PASSWORD_RESET" in m for m in lines) == 1


def test_docs_explain_reading_the_first_run_password_without_smb():
    doc = (ROOT / "docs/Security.md").read_text(encoding="utf-8")
    assert "docker exec" in doc and "qbm_initial_password.txt" in doc


def test_ui_confirms_before_switching_to_api_only():
    js = (ROOT / "web-ui/js/components/security.js").read_text(encoding="utf-8")
    assert "API only mode has no browser login" in js


def test_host_help_says_a_login_is_always_required():
    src = (ROOT / "qbit_manage.py").read_text(encoding="utf-8")
    host = src.split('"--host",', 1)[1].split("\n)", 1)[0]
    assert "requires web authentication" not in host
    assert "login is always required" in host


NEW_PASSWORD = "N3w-Passw0rd!x"


def test_an_env_reference_saves_with_an_api_key(local_dir):
    (local_dir / "config.yml").write_text("qbt:\n  host: a:8080\n  user: !ENV QBT_USER\n", encoding="utf-8")
    app = make_app(local_dir)
    body = {"data": {"qbt": {"host": "a:8080", "user": "!ENV QBT_USER"}, "settings": {"x": 1}}}
    assert send(app, "PUT", "/api/configs/config.yml", headers=KEY, body=body).status == 200


def test_a_migrated_4x_host_name_proxy_is_dropped_with_a_warning(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(auth, "logger", MagicMock(warning=lambda m, *a, **k: warnings.append(m)))
    write_settings(
        tmp_path, enabled=True, method="basic", username="owner", password_hash=auth.hash_password(PASSWORD),
        trusted_proxies=["swag", "172.18.0.0/16"],
    )  # fmt: skip
    assert auth.ensure_credentials(tmp_path / "qbm_settings.yml", {})
    settings = auth.load_settings(tmp_path / "qbm_settings.yml")
    assert settings.trusted_proxies == ["172.18.0.0/16"]
    assert any("swag" in w for w in warnings)


def test_a_5x_settings_file_with_a_bad_proxy_still_fails_closed(tmp_path):
    write_settings(tmp_path, mode="local", username="owner", password_hash=auth.hash_password(PASSWORD), trusted_proxies=["swag"])
    with pytest.raises(auth.AuthSettingsError):
        auth.load_settings(tmp_path / "qbm_settings.yml")


def test_the_oidc_callback_ignores_the_per_address_limit(tmp_path, monkeypatch):
    write_settings(tmp_path, **oidc_settings(username="owner").model_dump())
    client = MagicMock()
    client.authorize_access_token = AsyncMock(return_value={"userinfo": {"sub": "user-1"}})
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    app = make_app(tmp_path)
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        auth.record_failure("127.0.0.1")
    assert send(app, "GET", "/auth/oidc/callback").status in (302, 307)


def test_a_password_reset_left_set_applies_once(tmp_path):
    path = tmp_path / "qbm_settings.yml"
    write_settings(tmp_path, **oidc_settings(username="owner", password_hash=auth.hash_password(PASSWORD)).model_dump())
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": NEW_PASSWORD, "QBT_WEB_PASSWORD_RESET": "true"}
    assert auth.ensure_credentials(path, env)
    first = auth.load_settings(path)
    first_key = auth.session_secret(tmp_path)
    assert first.allow_local_login and auth.verify_password(NEW_PASSWORD, first.password_hash)
    # The owner turns the break-glass login off again; the next restart must not undo that or sign anyone out.
    auth.save_auth_settings(path, first.model_copy(update={"allow_local_login": False}))
    assert auth.ensure_credentials(path, env)
    second = auth.load_settings(path)
    assert second.allow_local_login is False
    assert auth.session_secret(tmp_path) == first_key  # no sign-out on the second start
    assert second.password_hash == first.password_hash


def test_a_skipped_reset_is_logged(tmp_path, monkeypatch):
    lines = []
    monkeypatch.setattr(auth, "logger", MagicMock(info=lambda m, *a, **k: lines.append(m)))
    path = tmp_path / "qbm_settings.yml"
    local_settings(tmp_path)
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": PASSWORD, "QBT_WEB_PASSWORD_RESET": "true"}
    before = auth.session_secret(tmp_path)
    assert auth.ensure_credentials(path, env)
    assert auth.session_secret(tmp_path) == before
    assert any("QBT_WEB_PASSWORD_RESET" in m and "already" in m for m in lines)


def test_https_only_checkbox_says_it_needs_a_restart():
    js = (ROOT / "web-ui/js/components/security.js").read_text(encoding="utf-8")
    group = js.split('id="https-only-group"', 1)[1].split("</div>\n", 2)
    assert "after a restart" in "".join(group[:2])


posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")


@pytest.fixture
def provider(tmp_path, monkeypatch):
    """A real Authlib client whose token endpoint refuses every code; counts the token requests it receives."""
    from authlib.integrations.httpx_client.oauth2_client import httpx2

    settings = oidc_settings(username="owner")
    write_settings(tmp_path, **settings.model_dump())
    client = auth.oidc_client(settings)
    client.server_metadata.update(
        _loaded_at=1,
        issuer="https://idp.example",
        authorization_endpoint="https://idp.example/authorize",
        token_endpoint="https://idp.example/token",
    )
    token_requests = []

    async def fake_send(self, request, **kwargs):
        if str(request.url) == "https://idp.example/token":
            token_requests.append(request)
            return httpx2.Response(400, json={"error": "invalid_grant"}, request=request)
        return httpx2.Response(404, request=request)

    monkeypatch.setattr(httpx2.AsyncClient, "send", fake_send)
    return make_app(tmp_path), token_requests


def start_login(app, ip="127.0.0.1"):
    started = send(app, "GET", "/auth/oidc/login", ip=ip)
    state = parse_qs(urlsplit(started.header("location")[0]).query)["state"][0]
    return cookie_header(cookie_of(started)), state


def test_an_unissued_oidc_state_never_reaches_the_provider(provider):
    app, token_requests = provider
    cookie, _ = start_login(app)
    assert send(app, "GET", "/auth/oidc/callback?state=forged&code=junk", headers=cookie).status == 401
    assert token_requests == []


def test_an_env_password_reset_removes_the_first_run_password_file(tmp_path):
    local_settings(tmp_path)
    leftover = tmp_path / auth.INITIAL_PASSWORD_FILE
    leftover.write_text("username: admin\npassword: old\n", encoding="utf-8")
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "N3w-Passw0rd!x", "QBT_WEB_PASSWORD_RESET": "true"}
    assert auth.ensure_credentials(tmp_path / "qbm_settings.yml", env)
    assert not leftover.exists()


@posix_only
def test_the_legacy_schedule_migration_writes_a_private_temp_file(tmp_path, monkeypatch):
    from modules import scheduler as scheduler_module
    from modules import util

    modes = []
    real_save = util.YAML.save

    def save(self):
        modes.append(os.stat(self.path).st_mode & 0o777 if os.path.exists(self.path) else None)
        return real_save(self)

    monkeypatch.setattr(util.YAML, "save", save)
    old_umask = os.umask(0o022)
    try:
        sched = scheduler_module.Scheduler(str(tmp_path), suppress_logging=True)
        (tmp_path / "schedule.yml").write_text("type: interval\nvalue: 30\n", encoding="utf-8")
        assert sched._migrate_legacy_schedule_file(suppress_logging=True)
    finally:
        os.umask(old_umask)
    assert modes and modes[-1] == 0o600
    assert (tmp_path / "qbm_settings.yml").stat().st_mode & 0o777 == 0o600


def test_oidc_metadata_url_must_be_https_except_on_loopback():
    with pytest.raises(ValueError):
        auth.SecuritySettingsRequest(oidc_metadata_url="http://idp.example/.well-known/openid-configuration")
    with pytest.raises(ValueError):
        auth.AuthSettings(oidc_metadata_url="http://idp.example/.well-known/openid-configuration")
    for url in ("https://idp.example/x", "http://localhost:9000/x", "http://127.0.0.1/x", "http://[::1]/x"):
        assert auth.SecuritySettingsRequest(oidc_metadata_url=url).oidc_metadata_url == url


def test_a_failed_basic_login_does_not_log_the_username(local_dir, monkeypatch):
    from unittest.mock import MagicMock

    lines = []
    monkeypatch.setattr(auth, "logger", MagicMock(info=lambda m, *a, **k: lines.append(m)))
    app = make_app(local_dir)
    send(app, "GET", "/api/configs", headers=list(basic(username="victim-name", password="wrong").items()))
    assert lines and not any("victim-name" in m for m in lines)


@posix_only
def test_saved_and_created_configs_and_backups_are_private(local_dir):
    os.chmod(local_dir / "config.yml", 0o644)
    app = make_app(local_dir)
    body = {"data": {"qbt": {"host": "localhost:8080", "user": "admin", "pass": "plain"}}}
    assert send(app, "PUT", "/api/configs/config.yml", headers=KEY, body=body).status == 200
    assert (local_dir / "config.yml").stat().st_mode & 0o777 == 0o600
    backups = list((local_dir / ".backups").iterdir())
    assert backups and all(b.stat().st_mode & 0o777 == 0o600 for b in backups)
    assert send(app, "POST", "/api/configs/new.yml", headers=KEY, body=body).status == 200
    assert (local_dir / "new.yml").stat().st_mode & 0o777 == 0o600


def test_validate_config_filename_returns_the_checked_path(local_dir):
    (local_dir / "real.yml").write_text("qbt: {}\n", encoding="utf-8")
    (local_dir / "link.yml").symlink_to(local_dir / "real.yml")
    api = make_api(local_dir)
    assert api._validate_config_filename("link.yml") == (local_dir / "real.yml").resolve()


def test_an_all_trusted_forwarded_chain_cannot_rotate_the_client_address(tmp_path):
    from tests.test_web_security import CONFIG

    (tmp_path / "config.yml").write_text(CONFIG, encoding="utf-8")
    local_settings(tmp_path, trusted_proxies=["10.0.0.0/8"])
    app = make_app(tmp_path, host="0.0.0.0")
    bad = {"username": "x", "password": "y"}
    for i in range(auth.MAX_AUTH_ATTEMPTS):
        send(app, "POST", "/login", ip="10.0.0.1", headers=[("X-Forwarded-For", f"10.9.9.{i}")], body=bad)
    resp = send(app, "POST", "/login", ip="10.0.0.1", headers=[("X-Forwarded-For", "10.9.9.200")], body=bad)
    assert resp.status == 429


def test_logout_ends_this_session_and_a_password_change_signs_out_every_device(local_dir):
    from tests.test_web_security import PASSWORD
    from tests.test_web_security import login

    app = make_app(local_dir)
    _, first = login(app)
    _, second = login(app)
    assert send(app, "POST", "/logout", headers=first, body={}).status == 200
    assert send(app, "GET", "/api/configs/config.yml", headers=second).status == 200
    body = {"password": "N3w-Passw0rd!x", "current_password": PASSWORD}
    assert send(app, "PUT", "/api/security", headers=second, body=body).status == 200
    assert send(app, "GET", "/api/configs/config.yml", headers=second).status == 401
    assert login(app, password="N3w-Passw0rd!x")[0].status == 200


def test_an_env_password_reset_signs_out_every_browser(local_dir):
    app = make_app(local_dir)
    _, cookie = login(app)
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie).status == 200
    env = {"QBT_WEB_USERNAME": "owner", "QBT_WEB_PASSWORD": "N3w-Passw0rd!x", "QBT_WEB_PASSWORD_RESET": "true"}
    assert auth.ensure_credentials(local_dir / "qbm_settings.yml", env)
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie).status == 401


@pytest.mark.parametrize(
    "change",
    [
        {"generate_api_key": True},
        {"clear_api_key": True},
        {"https_only": True},
        {"trusted_proxies": ["10.0.0.0/8"]},
        {"username": "owner2"},
        {"allow_local_login": True},
        {"mode": "oidc", "oidc_metadata_url": "https://evil.example/.well-known/openid-configuration",
         "oidc_client_id": "x", "oidc_sub": "attacker", "public_url": "https://qbm.example.com"},
    ],
)  # fmt: skip
def test_every_security_change_needs_the_current_password(local_dir, change):
    app = make_app(local_dir)
    _, cookie = login(app)
    before = (local_dir / "qbm_settings.yml").read_text()
    resp = send(app, "PUT", "/api/security", headers=cookie, body=change)
    assert resp.status == 403 and resp.json()["message"] == "Enter your current password"
    assert send(app, "PUT", "/api/security", headers=cookie, body={**change, "current_password": "wrong"}).status == 403
    assert (local_dir / "qbm_settings.yml").read_text() == before
    _, other = login(app)
    assert send(app, "PUT", "/api/security", headers=cookie, body={**change, "current_password": PASSWORD}).status == 200
    assert send(app, "GET", "/api/configs/config.yml", headers=other).status == 401  # every session is signed out


def test_an_unchanged_save_needs_no_password(local_dir):
    app = make_app(local_dir)
    _, cookie = login(app)
    assert send(app, "PUT", "/api/security", headers=cookie, body={"https_only": False}).status == 200
    assert send(app, "GET", "/api/configs/config.yml", headers=cookie).status == 200


def test_an_oidc_only_change_needs_a_fresh_oidc_login(config_dir, monkeypatch):
    app, cookie = oidc_only_app(config_dir, monkeypatch)
    real_time = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real_time() + auth.REAUTH_SECONDS + 1)
    resp = send(app, "PUT", "/api/security", headers=cookie, body={"generate_api_key": True})
    assert resp.status == 403 and "Sign in again" in resp.json()["message"]


def test_an_oidc_reauth_without_a_fresh_auth_time_is_refused(config_dir, monkeypatch):
    write_settings(config_dir, **oidc_settings(username="").model_dump())
    client = MagicMock()
    client.authorize_redirect = AsyncMock(return_value=auth.RedirectResponse("https://idp.example/authorize"))
    client.authorize_access_token = AsyncMock(return_value={"userinfo": {"sub": "user-1", "auth_time": 1}})
    monkeypatch.setattr(auth, "oidc_client", lambda settings: client)
    app = make_app(config_dir)
    started = send(app, "GET", "/auth/oidc/login?reauth=1")
    assert client.authorize_redirect.call_args.kwargs == {"prompt": "login", "max_age": 0}
    assert send(app, "GET", "/auth/oidc/callback", headers=cookie_header(cookie_of(started))).status == 401


def test_a_concurrent_security_save_is_refused_not_clobbered(local_dir, monkeypatch):
    app = make_app(local_dir)
    _, cookie = login(app)
    real_save = auth.save_auth_settings

    def other_session_saves_first(path, settings, expected=None):
        assert real_save(path, expected.model_copy(update={"https_only": True}))
        return real_save(path, settings, expected)

    monkeypatch.setattr(auth, "save_auth_settings", other_session_saves_first)
    body = {"trusted_proxies": ["10.0.0.0/8"], "current_password": PASSWORD}
    assert send(app, "PUT", "/api/security", headers=cookie, body=body).status == 500
    assert "10.0.0.0/8" not in (local_dir / "qbm_settings.yml").read_text()


def test_a_session_can_save_an_env_reference_to_a_new_host(local_dir):
    (local_dir / "config.yml").write_text("qbt:\n  host: a:8080\n  pass: !ENV QBT_PASS\n", encoding="utf-8")
    app = make_app(local_dir)
    _, cookie = login(app)
    body = {"data": {"qbt": {"host": "b:8080", "pass": "!ENV QBT_PASS"}}}
    assert send(app, "PUT", "/api/configs/config.yml", headers=cookie, body=body).status == 200


# --- Browser origin checks on writes -----------------------------------------------------------------


@pytest.mark.parametrize(
    "extra,allowed",
    [
        ([], True),  # no browser headers: a script or an old browser
        ([("Sec-Fetch-Site", "same-origin")], True),
        ([("Sec-Fetch-Site", "same-site")], False),  # a sibling subdomain
        ([("Sec-Fetch-Site", "cross-site")], False),
        ([("Sec-Fetch-Site", "cross-site"), ("Origin", "http://127.0.0.1:8181")], False),  # Sec-Fetch-Site decides
        ([("Origin", "http://127.0.0.1:8181")], True),
        ([("Origin", "http://evil.example")], False),
        ([("Origin", "null")], False),
    ],
)
def test_session_writes_must_come_from_this_site(local_dir, extra, allowed):
    app = make_app(local_dir)
    _, cookie = login(app)
    resp = send(app, "POST", "/api/configs/config.yml/backup", headers=cookie + extra, body={})
    assert (resp.status != 403) is allowed, resp.text


def test_a_cross_site_delete_is_refused(local_dir):
    (local_dir / "other.yml").write_text(CONFIG, encoding="utf-8")
    app = make_app(local_dir)
    _, cookie = login(app)
    resp = send(app, "DELETE", "/api/configs/other.yml", headers=cookie + [("Origin", "http://evil.example")])
    assert resp.status == 403
    assert (local_dir / "other.yml").exists()


def test_a_cross_site_login_post_is_refused(local_dir):
    body = {"username": "owner", "password": PASSWORD}
    resp = send(make_app(local_dir), "POST", "/login", headers=[("Sec-Fetch-Site", "cross-site")], body=body)
    assert resp.status == 403


def test_origin_may_match_the_public_url_behind_a_proxy(config_dir):
    local_settings(config_dir, public_url="https://qbm.example.com")
    app = make_app(config_dir)
    _, cookie = login(app)
    ok = send(app, "POST", "/api/configs/config.yml/backup", headers=cookie + [("Origin", "https://qbm.example.com")], body={})
    assert ok.status != 403
    downgraded = [("Origin", "http://qbm.example.com"), ("Host", "qbm.example.com")]
    assert send(app, "POST", "/api/configs/config.yml/backup", headers=cookie + downgraded, body={}).status == 403


def test_api_key_scripts_need_no_content_type_on_bodyless_posts(local_dir):
    resp = send(make_app(local_dir), "POST", "/api/configs/config.yml/backup", headers=[("X-Api-Key", API_KEY)])
    assert resp.status == 200, resp.text


def test_basic_auth_writes_still_need_json_and_origin(local_dir):
    app = make_app(local_dir)
    assert send(app, "POST", "/api/configs/config.yml/backup", headers=list(basic().items())).status == 415
    cross = list(basic().items()) + [("Origin", "http://evil.example")]
    assert send(app, "POST", "/api/configs/config.yml/backup", headers=cross, body={}).status == 403


# --- Password checks under concurrency ---------------------------------------------------------------


def _counting_check(monkeypatch):
    real = auth.check_login
    state = {"calls": 0, "running": 0, "peak": 0}

    def counted(*a):
        state["calls"] += 1
        state["running"] += 1
        state["peak"] = max(state["peak"], state["running"])
        try:
            time.sleep(0.02)
            return real(*a)
        finally:
            state["running"] -= 1

    monkeypatch.setattr(auth, "check_login", counted)
    return state


async def _burst(app, requests):
    return await asyncio.gather(*(asend(app, method, path, **kw) for method, path, kw in requests))


def test_a_burst_of_guesses_cannot_pass_the_limit_together(local_dir, monkeypatch):
    app = make_app(local_dir)
    state = _counting_check(monkeypatch)
    wrong = {"username": "owner", "password": "wrong"}
    burst = [("POST", "/login", {"body": wrong}) for _ in range(15)]
    burst += [("GET", "/api/configs", {"headers": list(basic(password="wrong").items())}) for _ in range(15)]
    statuses = [r.status for r in asyncio.run(_burst(app, burst))]
    assert state["calls"] == auth.MAX_AUTH_ATTEMPTS
    assert statuses.count(429) == 30 - auth.MAX_AUTH_ATTEMPTS


def test_password_checks_run_one_at_a_time(local_dir, monkeypatch):
    app = make_app(local_dir)
    state = _counting_check(monkeypatch)
    burst = [("POST", "/login", {"ip": f"198.51.100.{i}", "body": {"username": "owner", "password": "x"}}) for i in range(8)]
    asyncio.run(_burst(app, burst))
    assert state["calls"] == 8 and state["peak"] == 1


def test_current_password_checks_share_the_login_limit(local_dir, monkeypatch):
    app = make_app(local_dir)
    _, cookie = login(app)
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        send(app, "POST", "/login", body={"username": "owner", "password": "wrong"})
    state = _counting_check(monkeypatch)
    body = {"password": "N3w-" + "Passw0rd!x", "current_password": PASSWORD}
    assert send(app, "PUT", "/api/security", headers=cookie, body=body).status == 429
    assert state["calls"] == 0


# --- OIDC state and limits ----------------------------------------------------------------------------


def test_a_replayed_oidc_callback_never_reaches_the_provider_again(provider):
    app, token_requests = provider
    cookie, state = start_login(app)
    assert send(app, "GET", f"/auth/oidc/callback?state={state}&code=junk", headers=cookie).status == 401
    assert len(token_requests) == 1
    # The pre-callback cookie still carries the state; the server-side copy is gone.
    assert send(app, "GET", f"/auth/oidc/callback?state={state}&code=junk", headers=cookie).status == 401
    assert len(token_requests) == 1


def test_oidc_login_starts_are_limited_per_address(provider):
    app, _ = provider
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        assert send(app, "GET", "/auth/oidc/login", ip="203.0.113.7").status in (302, 307)
    assert send(app, "GET", "/auth/oidc/login", ip="203.0.113.7").status == 429
    assert send(app, "GET", "/auth/oidc/login", ip="203.0.113.8").status in (302, 307)


def test_failed_oidc_callbacks_are_limited_per_address(provider):
    app, token_requests = provider
    for _ in range(auth.MAX_AUTH_ATTEMPTS):
        assert send(app, "GET", "/auth/oidc/callback?state=forged&code=junk", ip="203.0.113.7").status == 401
    cookie, state = start_login(app, ip="203.0.113.7")
    resp = send(app, "GET", f"/auth/oidc/callback?state={state}&code=junk", ip="203.0.113.7", headers=cookie)
    assert resp.status == 429 and token_requests == []


def test_pending_oidc_states_are_capped():
    cache = auth._OidcStateCache()
    for i in range(auth.OIDC_STATE_MAX + 5):
        asyncio.run(cache.set(f"s{i}", "v", 600))
    assert len(cache._items) == auth.OIDC_STATE_MAX
    assert asyncio.run(cache.get("s0")) is None
    assert asyncio.run(cache.get(f"s{auth.OIDC_STATE_MAX + 4}")) == "v"
    assert asyncio.run(cache.get(f"s{auth.OIDC_STATE_MAX + 4}")) is None  # single use
