# Web API Documentation

## Overview

qBit Manage provides a REST API that allows you to trigger commands via HTTP requests. The server uses port 8181 and binds to `127.0.0.1` by default (`0.0.0.0` in Docker). Change them with `--host` and `--port` or `QBT_HOST` and `QBT_PORT`. It is off by default; enable it with `--web-server` or `QBT_WEB_SERVER=true`. Every request needs a login, on any address. See [Security](Security) before you expose it.

## Running the Web Server

### Command Line

```bash
python qbit_manage.py --web-server --host 0.0.0.0 --port 8181
```

### Docker

```yaml
services:
  qbit_manage:
    image: ghcr.io/stuffanthings/qbit_manage:latest
    container_name: qbit_manage
    environment:
      - QBT_WEB_SERVER=true # Enable web server (set to false to disable)
      - QBT_PORT=8181 # Set web server port
    ports:
      - "127.0.0.1:8181:8181" # Publish on the host only
    volumes:
      - /path/to/config:/config
```

## API Endpoints

> A login is always required. Scripts send an API key in the `X-Api-Key` header, or HTTP Basic (`curl -u user:password`). **Exception:** `GET /api/health` is public and returns only `{"status": ...}`. An API key cannot change `/api/security`. Writes need `Content-Type: application/json`. After 10 failed logins or API key attempts in one minute, that client address gets `429` until the minute passes.

### Endpoint Summary

| Endpoint | Method | Auth required |
|---|---|---|
| `/api/run-command` | POST | Yes |
| `/api/configs` | GET | Yes |
| `/api/configs/{filename}` | GET | Yes |
| `/api/configs/{filename}` | POST | Yes |
| `/api/configs/{filename}` | PUT | Yes |
| `/api/configs/{filename}` | DELETE | Yes |
| `/api/configs/{filename}/validate` | POST | Yes |
| `/api/configs/{filename}/backup` | POST | Yes |
| `/api/configs/{filename}/backups` | GET | Yes |
| `/api/configs/{filename}/restore` | POST | Yes |
| `/api/scheduler` | GET | Yes |
| `/api/schedule` | PUT | Yes |
| `/api/schedule/persistence/toggle` | POST | Yes |
| `/api/logs` | GET | Yes |
| `/api/log_files` | GET | Yes |
| `/api/docs` | GET | Yes |
| `/api/version` | GET | Yes |
| `/api/health` | GET | No (status only) |
| `/api/health_details` | GET | Yes |
| `/api/get_base_url` | GET | Yes |
| `/api/security` | GET | Yes |
| `/api/security/status` | GET | Yes |
| `/api/security` | PUT | Yes |
| `/api/security/oidc/test` | POST | Yes (no API key) |
| `/api/security/oidc/link` | POST | Yes (session only) |
| `/api/system/force-reset` | POST | Yes |

---

### Config Management

#### GET /api/configs

List all available config files in the config directory. Sensitive files (`qbm_settings.yml`, `secrets.yml`, etc.) are automatically filtered from results.

**Response:**

```json
{
  "configs": ["config.yml", "config2.yml"],
  "default_config": "config.yml"
}
```

#### GET /api/configs/{filename}

Fetch the contents of a specific config file as a parsed object.

**Response:**

```json
{
  "filename": "config.yml",
  "data": { "qbt": { "host": "localhost:8080" }, "settings": {} },
  "last_modified": "2026-05-21T10:00:00",
  "size": 4096
}
```

`data` mirrors the YAML structure. `!ENV` variable references are preserved as strings in the form `!ENV <VAR>`.

#### POST /api/configs/{filename}

Create a new config file. Returns `409` if the file already exists.

**Request body:**

```json
{
  "data": {
    "qbt": { "host": "localhost:8080", "user": "admin", "pass": "" },
    "settings": { "run_now": false }
  }
}
```

**Response (201-equivalent):**

```json
{ "status": "success", "message": "Configuration 'config2.yml' created successfully" }
```

#### PUT /api/configs/{filename}

Update an existing config file. A timestamped backup is created automatically before writing. Returns `404` if file does not exist.

**Request body** (same shape as POST — full config data object):

```json
{
  "data": {
    "qbt": { "host": "localhost:8080", "user": "admin", "pass": "" },
    "settings": { "run_now": false, "schedule": 1440 },
    "cat": { "movies": "/data/torrents/movies" }
  }
}
```

**Response:**

```json
{ "status": "success", "message": "Configuration 'config.yml' updated successfully" }
```

#### DELETE /api/configs/{filename}

Delete a config file permanently. A backup is created before deletion.

**Response:**

```json
{ "status": "success", "message": "Configuration 'config.yml' deleted successfully" }
```

#### POST /api/configs/{filename}/validate

Validate a config file for correctness by running it through qbit_manage's config parser without executing commands. Validation runs on a temporary copy and never writes the config file. Defaults the parser adds (missing keys are backfilled) come back in `data` for the editor.

**Request body:**

```json
{
  "data": {
    "qbt": { "host": "localhost:8080" },
    "settings": {},
    "cat": {},
    "tracker": {},
    "share_limits": {}
  }
}
```

**Response (valid):**

```json
{
  "valid": true,
  "errors": [],
  "warnings": [],
  "config_modified": false
}
```

**Response (invalid — with errors):**

```json
{
  "valid": false,
  "errors": ["Config Error: qbt.host is required"],
  "warnings": [],
  "config_modified": false
}
```

`config_modified: true` means the parser added defaults; `data` holds the config with them. The file on disk is unchanged.

#### POST /api/configs/{filename}/backup

Create a timestamped backup of the specified config file. Backups are retained up to 30 per config.

**Response:**

```json
{
  "status": "success",
  "message": "Manual backup created successfully",
  "backup_file": "config_20260521_100000.yml"
}
```

#### GET /api/configs/{filename}/backups

List all available backups for the specified config file.

**Response:**

```json
{
  "backups": [
    { "filename": "config_20260521_100000.yml", "created": "2026-05-21T10:00:00", "size": 4096 }
  ]
}
```

#### POST /api/configs/{filename}/restore

Restore a config file from a previously created backup. Pass the backup filename as the request body.

---

### Scheduler

#### GET /api/scheduler

Return the current scheduler status, including schedule expression and next run time.

**Response:**

```json
{
  "current_schedule": { "type": "interval", "value": "1440" },
  "next_run": "2026-05-22T10:00:00.000000",
  "next_run_str": "in 24 hours",
  "is_running": false,
  "source": "env",
  "persistent": false,
  "file_exists": false,
  "disabled": false
}
```

`type` is `"interval"` (minutes) or `"cron"` (cron expression). `source` is `"env"` (from `QBT_SCHEDULE`), `"file"` (persisted via API), or `null`.

#### PUT /api/schedule

Set or update the scheduler's cron/interval expression. The change takes effect immediately and can optionally be persisted across restarts.

**Request body:**

```json
{ "schedule": "1440", "type": "interval" }
```

Or using a cron expression:

```json
{ "schedule": "0 4 * * *", "type": "cron" }
```

`type` is optional — qbit_manage will auto-detect `"interval"` vs `"cron"` if omitted. Interval values must be positive integers (minutes).

**Response:**

```json
{
  "success": true,
  "message": "Schedule saved successfully: interval=1440",
  "schedule": "1440",
  "type": "interval",
  "persistent": true
}
```

#### POST /api/schedule/persistence/toggle

Toggle whether the scheduler's configuration persists across restarts.

---

### Logs

#### GET /api/logs

Fetch recent log content from the log files directory.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | none (all) | Maximum number of lines to return (most recent N lines) |
| `log_filename` | str | `qbit_manage.log` | Name of the log file to read |

**Response:**

```json
{
  "logs": [
    "2026-05-21 10:00:00,000 INFO     | Run started",
    "2026-05-21 10:00:01,123 INFO     | Processing torrent: Example.Torrent"
  ]
}
```

Lines are returned in **chronological order** (oldest first). Use `limit` to cap output for large log files.

`log_filename` accepts the active log (`<stem>.log`, e.g. `qbit_manage.log`) or a rotated log (`<stem>.<N>.log`, e.g. `qbit_manage.1.log`). Any other name returns `400`.

**Example:**

```bash
curl -s "http://localhost:8181/api/logs?limit=50&log_filename=qbit_manage.log" \
  -H "X-API-Key: your_api_key_here"
```

#### GET /api/log_files

List all available log files in the logs directory.

**Response:**

```json
{ "log_files": ["qbit_manage.log", "qbit_manage.1.log"] }
```

---

### System / Misc

#### GET /api/docs
Return documentation metadata for the API (markdown file content).

#### GET /api/version

Return version information for qBit Manage. **Needs a login.** Anonymous monitors get 401; use `/api/health` for a liveness check.

**Response:**

```json
{
  "version": "4.7.1",
  "branch": "master",
  "build": 0,
  "latest_version": "4.7.1",
  "update_available": false
}
```

`update_available: true` when a newer release is available on GitHub. `build` is the git commit count (integer).

#### GET /api/health

Liveness probe. **Public.** Anonymous callers get only the status:

```json
{ "status": "healthy" }
```

#### GET /api/health_details

Full application state. **Needs a login.**

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2026-05-21T10:00:00.000000",
  "version": "4.7.1",
  "branch": "master",
  "application": {
    "web_api_responsive": true,
    "can_accept_requests": true,
    "queue_size": 0,
    "has_queued_requests": false,
    "next_scheduled_run": "2026-05-22T10:00:00.000000",
    "next_scheduled_run_text": "in 24 hours",
    "scheduler_alive": true,
    "last_run": "2026-05-21T09:00:00.000000",
    "last_run_result": "success"
  },
  "directories": {
    "config_dir_exists": true,
    "config_files_count": 1,
    "logs_dir_exists": true,
    "recent_log_entries": 150,
    "last_activity": "Recent activity detected"
  },
  "issues": []
}
```

`status` values: `"healthy"` | `"degraded"` (config/log dir missing) | `"busy"` (run in progress) | `"unhealthy"` (health check itself failed, the scheduler thread is not running, or the scheduler heartbeat is older than 5 minutes). The HTTP status stays 200 in every case; check the `status` field.

`application.scheduler_alive` is `true`/`false` once the scheduler has reported, otherwise `null`. `application.last_run` is the ISO timestamp of the last finished run and `application.last_run_result` is its outcome (for example `"success"`); both are `null` until a run has finished. When the scheduler is down or stale, `issues` contains `"Scheduler is not running"` or `"Scheduler heartbeat is stale"`.

#### GET /api/get_base_url

Return the resolved base URL the server is listening on. **Needs a login.**

**Response:**

```json
{ "baseUrl": "" }
```

Returns empty string when no `--base-url` / `QBT_BASE_URL` is configured.

#### GET /api/security
Return the current security configuration (API key and basic auth settings).

#### GET /api/security/status
Return a summary of whether authentication is enabled and which methods are active.

#### PUT /api/security
Update security settings (mode, username, password, OpenID Connect, API key). A new password needs `current_password` (or a fresh OIDC login in OIDC-only mode). A change signs out every browser. An API key cannot call this endpoint.

#### POST /api/security/oidc/test
Fetch and validate an OpenID Connect discovery URL (`oidc_metadata_url`) from the server, returning the discovered `issuer`. An API key cannot call this endpoint.

#### POST /api/security/oidc/link
Start an authenticated OpenID Connect linking flow for draft provider settings (`public_url`, `oidc_metadata_url`, `oidc_client_id`, optional `oidc_client_secret`) and return an `authorize_url` so the callback detects the user's `sub` claim without changing the active login mode yet. Requires an active browser session (not an API key or HTTP Basic).

#### POST /api/system/force-reset
Force-reset the internal running state. Use when a stuck run has left the system in an inconsistent state.

---

### POST /api/run-command

Execute qBit Manage commands via the API.

#### Request Body

```json
{
  "config_file": "config.yml", // Optional, defaults to "config.yml"
  "commands": ["cat_update", "tag_update"], // Required, list of commands to run
  "hashes": ["<hash1>", "<hash2>"], // Optional, list of torrent hashes to filter by
  "dry_run": false, // Optional, defaults to false
  "skip_cleanup": false, // Optional, defaults to false
  "skip_qb_version_check": false, // Optional, defaults to false
  "log_level": null // Optional, defaults to null (e.g., "info", "debug", "error")
}
```

#### Response

Success:

```json
{
  "status": "success",
  "message": "Commands executed successfully for all configs",
  "results": [
    {
      "config_file": "config.yml",
      "stats": {
        "executed_commands": ["cat_update", "tag_update"],
        "categorized": 5,
        "tagged": 10
      }
    }
  ]
}
```

Queued (when scheduled run is in progress):

```json
{
  "status": "queued",
  "message": "Scheduled run in progress. Request queued.",
  "config_file": "config.yml",
  "commands": ["cat_update", "tag_update"]
}
```

Error:

```json
{
  "detail": "Error message"
}
```

## Available Commands

The following commands can be included in the `commands` array of the API request:

| Command             | Description                                                      | Supports Hashes |
| ------------------- | ---------------------------------------------------------------- | --------------- |
| `cat_update`        | Update categories based on save paths                            | Yes             |
| `tag_update`        | Add tags based on tracker URLs                                   | Yes             |
| `recheck`           | Recheck paused torrents sorted by size and resume completed ones | Yes             |
| `rem_unregistered`  | Remove unregistered torrents                                     | Yes             |
| `tag_tracker_error` | Tag torrents with tracker errors                                 | Yes             |
| `rem_orphaned`      | Remove orphaned files from root directory                        | No              |
| `tag_nohardlinks`   | Tag torrents with no hard links                                  | Yes             |
| `share_limits`      | Apply share limits based on tags/categories                      | Yes             |

Example using multiple commands:

```json
{
  "config_file": "config.yml",
  "commands": ["cat_update", "tag_update", "share_limits"],
  "dry_run": true
}
```

## qBittorrent Integration

qBittorrent can call a program after a torrent is added or finished. You can configure this in `Settings > Downloads > Run external program`.

Example command to run after torrent added/finished:

```bash
#!/bin/bash

# run_qbit_manage_commands.sh
#
# Sends a POST request to qBit Manage with a given torrent hash to trigger
# actions like "tag_update" and "share_limits".
#
# USAGE:
#   ./run_qbit_manage_commands.sh <torrent_hash>
#
# EXAMPLE:
#   ./run_qbit_manage_commands.sh 123ABC456DEF789XYZ
#
# NOTES:
# - Make sure this script is executable: chmod +x run_qbit_manage_commands.sh
# - The torrent hash is typically passed in automatically by qBittorrent via the "%I" variable.
# - All output is logged to run_qbit_manage_commands.log in the same directory as the script,
#   and also printed to stdout.

set -euo pipefail

API_URL="http://qbit_manage:8181/api/run-command"
COMMANDS='["tag_update", "share_limits"]'

if [[ $# -lt 1 || -z "$1" ]]; then
    echo "Usage: $0 <torrent_hash>" >&2
    exit 1
fi

TORRENT_HASH="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/run_qbit_manage_commands.log"

JSON="{\"commands\":${COMMANDS},\"hashes\":[\"${TORRENT_HASH}\"]}"

{
    echo "Sending API call for hash: ${TORRENT_HASH}"
    echo "Payload: ${JSON}"
} | tee -a "${LOG_FILE}"

if curl -fsSL -X POST \
     -H "Content-Type: application/json" \
     -d "${JSON}" \
     "${API_URL}" | tee -a "${LOG_FILE}"; then
    echo "Success" | tee -a "${LOG_FILE}"
else
    echo "Error: qBit Manage API call failed for hash ${TORRENT_HASH}" | tee -a "${LOG_FILE}"
fi
```

To use this script:

1. Save it as a file (e.g., `run_qbit_manage_commands.sh`).
2. Make the script executable:
   ```bash
   chmod +X /path/to/run_qbit_manage_commands.sh
   ```
3. In qBittorrent, configure `Settings > Downloads > Run external program` to execute this script, passing `%I` as an argument:
   ```
   /path/to/run_qbit_manage_commands.sh "%I"
   ```
   The script will create a log file named `run_qbit_manage_commands.log` in the same directory where the script is located.

## Behavior

1. Concurrent Execution:

   - API requests during scheduled runs are automatically queued
   - Queued requests are processed after the scheduled run completes
   - Double-check mechanism prevents race conditions

2. Command Execution:

   - Commands sent to the API are mandatory and the commands defined in ENV variables and in the config file are not used when using the API.
   - All regular command validations apply
   - Dry run mode available for testing

3. Error Handling:
   - Failed requests return appropriate error messages
   - Queue state is preserved even during errors
   - Proper cleanup ensures system stability

## Example Usage

Using curl:

```bash
curl -X POST http://localhost:8181/api/run-command \
  -H "Content-Type: application/json" \
  -d '{
    "config_file": "config.yml",
    "commands": ["cat_update", "tag_update"],
    "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
    "dry_run": false,
    "skip_cleanup": false,
    "skip_qb_version_check": false,
    "log_level": "info"
  }'
```

Include your API key:

```bash
curl -X POST http://localhost:8181/api/run-command \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "config_file": "config.yml",
    "commands": ["cat_update", "tag_update"],
    "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
    "dry_run": false,
    "skip_cleanup": false,
    "skip_qb_version_check": false,
    "log_level": "info"
  }'
```

Or use HTTP Basic with your web login username and password (in OpenID Connect mode only when `allow_local_login` is on):

```bash
curl -X POST http://localhost:8181/api/run-command \
  -u "username:password" \
  -H "Content-Type: application/json" \
  -d '{
    "config_file": "config.yml",
    "commands": ["cat_update", "tag_update"],
    "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
    "dry_run": false,
    "skip_cleanup": false,
    "skip_qb_version_check": false,
    "log_level": "info"
  }'
```

Using Python requests:

```python
import requests

response = requests.post(
    "http://localhost:8181/api/run-command",
    json={
        "config_file": "config.yml",
        "commands": ["cat_update", "tag_update"],
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
        "dry_run": False,
        "skip_cleanup": False,
        "skip_qb_version_check": False,
        "log_level": "info",
    },
)
print(response.json())
```

Include your API key:

```python
import requests

headers = {"X-API-Key": "your_api_key_here"}

response = requests.post(
    "http://localhost:8181/api/run-command",
    headers=headers,
    json={
        "config_file": "config.yml",
        "commands": ["cat_update", "tag_update"],
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
        "dry_run": False,
        "skip_cleanup": False,
        "skip_qb_version_check": False,
        "log_level": "info",
    },
)
print(response.json())
```

Or use HTTP Basic with your web login username and password:

```python
import requests
from requests.auth import HTTPBasicAuth

response = requests.post(
    "http://localhost:8181/api/run-command",
    auth=HTTPBasicAuth("username", "password"),
    json={
        "config_file": "config.yml",
        "commands": ["cat_update", "tag_update"],
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
        "dry_run": False,
        "skip_cleanup": False,
        "skip_qb_version_check": False,
        "log_level": "info",
    },
)
print(response.json())
```

## Command Validation

- All commands must be valid command names from the list above
- Commands are case-sensitive
- Invalid commands will return a 400 error with detail about the invalid command
- Empty command list will return a 400 error
- Commands defined in ENV variables or config files are ignored when using the API
- The API validates commands before execution and during runtime

Example error response for invalid command:

```json
{
  "detail": "Invalid command: invalid_command"
}
```
