# Security

The web server serves the Web UI and the Web API. Anyone who gets in can run commands, read your config, and edit your config files. Treat it like an admin panel.

## How it works in 5.0

- The web server is off by default. Turn it on with `--web-server` or `QBT_WEB_SERVER=true`. The desktop app turns it on for you.
- It binds to `127.0.0.1` (this computer only), or to `0.0.0.0` in Docker. Change it with `--host` or `QBT_HOST`.
- A login is always required while the web server is on. There is no exception for this computer or your local network.
- Scripts use an API key (`X-Api-Key` header) or HTTP Basic on `/api`. Neither opens the Web UI, and an API key cannot change security settings.
- Only `GET /api/health` is public, and it returns just `{"status": ...}`. `/api/version` and `/api/get_base_url` need a login.

## Login modes

Set the mode in the Web UI under Security, or under `authentication:` in `qbm_settings.yml` in your config folder.

| Mode | What it does |
|---|---|
| `local` (default) | Login form with a username and password. Only an Argon2 hash is stored. A signed cookie keeps you logged in for 7 days. |
| `oidc` | Single-user OpenID Connect login (for example Authentik). The local password is off unless `allow_local_login: true`. Prefer `oidc_sub`; `oidc_email` trusts the provider's email claim, so use it only with a provider you run yourself. |
| `api_only` | No browser login. API key or Basic only. |

## First login

1. Set `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` before the first start. They create the login only when none exists.
2. With neither set, qbit_manage generates a password and writes it to `qbm_initial_password.txt` in the config folder (readable by you only). The log shows the file path, never the password. The file is deleted when you change the password.
   On Unraid or another host where you cannot open that file over SMB, read it with `docker exec <container> cat /config/qbm_initial_password.txt`, or set `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` instead.
3. The password needs 8 or more characters and 3 of: uppercase letters, lowercase letters, numbers, and special characters (`!@#$%^&*`). Example: `Wh1te-Rabbit!`.

## Behind a reverse proxy

qbit_manage always asks for its own login; a proxy cannot log people in for it. Put the proxy in front for TLS and set `public_url` to the address people type, scheme and host only (for example `https://qbm.example.com`, with no path), so OpenID Connect redirects use it, and set `https_only: true`. `QBT_PUBLIC_URL` sets `public_url` at startup, for a proxy that changes the host name and blocks the first login.

Failed logins are rate limited: 10 failures per client address per minute, counting the login page, HTTP Basic, and API keys. A limited address is refused before the password is checked. By default the client address is the connecting address, which is the proxy's, so all of its clients share one limit. To limit each client on its own, list the proxy in `trusted_proxies` (IP addresses or CIDR networks), or set `QBT_TRUSTED_PROXIES=172.18.0.0/16,10.0.0.1` (applied at startup). qbit_manage then reads the client from `X-Forwarded-For`, but only when the connection comes from a listed proxy. List only proxies you run: a listed address can claim any client address.

## OpenID Connect (Authentik example)

1. In Authentik, create an OAuth2/OpenID provider and application. Set the redirect URI to `https://qbm.example.com/auth/oidc/callback` (add your base URL if you use one).
2. In `qbm_settings.yml`:

```yaml
authentication:
  mode: oidc
  public_url: https://qbm.example.com
  oidc_metadata_url: https://auth.example.com/application/o/qbit-manage/.well-known/openid-configuration
  oidc_client_id: <client id>
  oidc_client_secret: <client secret>
  oidc_sub: <your user's sub claim>
```

3. Use `oidc_email` instead of `oidc_sub` only if your provider marks the address as verified. Only one identity is allowed.

## Upgrading to 5.0

### Breaking changes

- The web server is off by default. Turn it on with `--web-server` or `QBT_WEB_SERVER=true`.
- A login is always required. `bypass_auth_for_local` is gone.
- `QBT_HOST` (and `--host`) is the address the web server binds to, not the qBittorrent address. A 4.x `QBT_HOST` holding a URL, `host:port`, or another machine was ignored before and now stops the web server from binding. Remove it, and set the qBittorrent address in `qbt.host`.
- 4.x `method: api_only` becomes `mode: local`. Your API key keeps working, and a first-run password is written to `qbm_initial_password.txt` for the browser login. To keep a key-only setup, set `mode: api_only` yourself after the upgrade.
- `external` mode is gone. A 4.x or 5.0-develop `external` setting becomes `local`: your API key and username are kept, and a first-run password is written to `qbm_initial_password.txt` if there is no password. `allowed_hosts` is ignored.
- A 4.x `trusted_proxies` entry that is not an IP address or CIDR network is dropped with a warning; the other entries are kept (see Behind a reverse proxy).
- 4.x `enabled: false` with a stored password now requires that password. Forgot it? Set `QBT_WEB_USERNAME`, `QBT_WEB_PASSWORD`, and `QBT_WEB_PASSWORD_RESET=true`, then restart (see Recovery).
- `/docs`, `/redoc`, and `/openapi.json` are gone.
- Unauthenticated `/api` scripts get 401. Send `X-Api-Key` or HTTP Basic.
- Anonymous `/api/version` monitors now get 401. `/api/health` stays public and returns only the status.
- pip and source installs bind to `127.0.0.1`. Pass `--host` (or `QBT_HOST`) for LAN access, and keep the login on.
- Setting a new password needs the current one. A new password, username, or mode signs out every browser. Logging out ends only the browser you used.
- `https_only` takes effect after a restart.

### Steps by install type

Before 5.0.0 the web server was on for installs outside a container, including headless and seedbox installs, and it needed no login. Follow the steps for your install.

**Docker, Unraid, and other containers**

1. Keep `QBT_WEB_SERVER=true` if you use the Web UI.
2. Add `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD`, or read the generated password from `qbm_initial_password.txt` in `/config`.
3. If you used `bypass_auth_for_local`, it is gone: every request needs a login now. The log warns once.
4. Publish the port on the host loopback or a private network, for example `"127.0.0.1:8181:8181"`.
5. Scripts: send `X-Api-Key`, or keep HTTP Basic.

**Python, source, or standalone binary (desktop, headless, or seedbox)**

1. Start with `--web-server` or set `QBT_WEB_SERVER=true` only if you use the Web UI or API. Without it, the log shows a warning and the web server stays off.
2. The default bind is `127.0.0.1`. Reach it from another machine through an SSH tunnel, or set `--host` or `QBT_HOST`.
3. Set `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` before the first start, or read `qbm_initial_password.txt` in the config folder.

**Desktop app**

The app turns the web server on and binds to `127.0.0.1`. The generated password is in `qbm_initial_password.txt` in the app's config folder: `%APPDATA%\qbit-manage` on Windows, `~/Library/Application Support/qbit-manage` on macOS, and `~/.config/qbit-manage` on Linux. The login page names the file while it exists.

**If your web server was reachable by others before 5.0.0**

1. Upgrade and stop the web server.
2. Change the qBittorrent password.
3. Rotate every secret in your config: Notifiarr and Apprise keys, and webhook URLs.
4. Start qbit_manage and set a new login and API key.
5. Check the qBittorrent and qbit_manage logs for activity you do not recognize.

## Recovery

Forgot the password? Set `QBT_WEB_USERNAME`, `QBT_WEB_PASSWORD`, and `QBT_WEB_PASSWORD_RESET=true`, then restart.

Docker:

1. Add the three variables to the compose file and run `docker compose up -d`.
2. Log in, then remove `QBT_WEB_PASSWORD_RESET` and run `docker compose up -d` again.

The reset also ends every existing session.

Locked out of OpenID Connect (provider down or misconfigured)? Use the same three variables. In `oidc` mode the reset also turns on the local break-glass login (`allow_local_login: true`), so the login page shows the password form. Log in, fix the OIDC settings, and turn the break-glass option off again under Security.

If `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` are set while a login exists and `QBT_WEB_PASSWORD_RESET` is not, they are ignored and the log says so. The reset applies once: while the stored login already uses that password, a restart leaves it alone and logs that the variable can be removed.

## Other protections

- Browser writes need a JSON content type and must come from this site: `Sec-Fetch-Site: same-origin`, or, from browsers that do not send it, an `Origin` matching the host or `public_url`. API key requests are exempt.
- The session cookie is `HttpOnly` and `SameSite=Lax`. Set `https_only: true` when you serve over HTTPS.
- The cookie signing key lives in `.qbm_session_key` (readable by you only), outside the config files and their backups.
- The Web UI shows `<redacted>` for passwords, keys, tokens, and webhook URLs. Saving a redacted value keeps the stored one, unless the host or URL beside it changed.
- The framework docs pages (`/docs`, `/redoc`, `/openapi.json`) are off.

See [SECURITY.md](https://github.com/StuffAnThings/qbit_manage/blob/develop/SECURITY.md) for the threat model and how to report a vulnerability privately.
