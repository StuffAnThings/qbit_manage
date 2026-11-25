# Security

## Reporting a vulnerability

Report vulnerabilities privately through GitHub: **Security > Report a vulnerability** on
this repository. Do not open a public issue, pull request, or discussion for a
vulnerability. Include the version, how the web server is started, and the smallest steps
that show the problem. Maintainers reply in the private report and publish an advisory
after a fixed release is available.

## Threat model

The web UI can read and write every config file, and a config holds the qBittorrent
password, notification keys, and webhook URLs. A config write can also point the orphan
and recycle cleanup at any directory the process can write. Treat web UI access as full
access to the qBittorrent account and to the files of the user that runs qBit Manage.

## Secure defaults

| Area | Default |
| --- | --- |
| Web server | Off. Enable with `--web-server` or `QBT_WEB_SERVER=true`. The desktop app enables it. |
| Bind address | `127.0.0.1`; `0.0.0.0` in Docker, where the port mapping decides exposure. `QBT_HOST` and `--host` change it |
| Login | Always required while the web server is on, on every address. There is no local-network exemption |
| Modes | `local` (Argon2 login, signed session cookie), `oidc` (single user, Authlib, PKCE S256), `api_only` |
| First run | A generated password is written to `qbm_initial_password.txt` (owner-only) and deleted on the first password change. `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` seed the login when none exists; `QBT_WEB_PASSWORD_RESET=true` replaces it |
| Scripts | `X-Api-Key` header or HTTP Basic on `/api` only. An API key cannot change security settings |
| Session cookie | `qbm_session`, `HttpOnly`, `SameSite=Lax`, path = base URL, 7 days, `https_only` setting. Logout ends that browser's session. Any security settings change, or `QBT_WEB_PASSWORD_RESET`, signs out every browser. The signing key is in `.qbm_session_key` (owner-only) |
| Peer address | Uvicorn runs with `proxy_headers=False`. Rate limits and logs use the raw TCP peer, or, when that peer is in `trusted_proxies` (`QBT_TRUSTED_PROXIES`), the right-most `X-Forwarded-For` entry that is not a trusted proxy |
| CSRF | Browser writes need a JSON content type and `Sec-Fetch-Site: same-origin`; browsers that do not send it need an `Origin` matching the host or `public_url`. API key requests are exempt |
| Broken settings | Unreadable, empty, or unknown-mode settings deny every request (HTTP 503) |
| Settings writes | Atomic; the scheduler never rewrites the authentication section |
| Secret redaction | Config and backup reads return `<redacted>` for passwords, keys, tokens, `notify_url`, and webhook URLs. A save keeps the stored value, unless the host or URL beside it changed. Notification and webhook URLs are masked in logs |
| Rate limits | 10 failed logins, Basic, or API key attempts per minute per client address |
| Config file names | Plain names inside the config directory only (no `/`, `\`, `:`, or `..`); `qbm_settings.yml` is never served |
| Framework API docs | `/docs`, `/redoc`, and `/openapi.json` are disabled |

## Upgrading

Before 5.0.0 the web server was on for non-Docker installs and needed no login. In 5.0.0
it is off by default and always needs a login. See the wiki page "Security", section
"Upgrading to 5.0", for each install type. Hand installs that relied on the old automatic
start must pass `--web-server`. `bypass_auth_for_local` was removed.
