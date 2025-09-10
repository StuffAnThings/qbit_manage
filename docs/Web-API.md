# Web API Documentation

## Overview

qBit Manage provides a REST API that allows you to trigger commands via HTTP requests. The API server runs at 8080, listening to all hostnames, by default and can be configured using the `--host` and `--port` options or `QBT_HOST` and `QBT_PORT` environment variables.

## Running the Web Server

### Command Line

```bash
python qbit_manage.py --web-server --host 0.0.0.0 --port 8080
```

### Docker

```yaml
version: "3"
services:
  qbit_manage:
    image: bobokun/qbit_manage:latest
    container_name: qbit_manage
    environment:
      - QBT_WEB_SERVER=true # Enable web server (set to false to disable)
      - QBT_HOST=0.0.0.0 # Set web server host
      - QBT_PORT=8080 # Set web server port
    ports:
      - "8080:8080" # Map container port to host
    volumes:
      - /path/to/config:/config
```

## API Endpoints

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

API_URL="http://qbit_manage:8080/api/run-command"
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
curl -X POST http://localhost:8080/api/run-command \
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

If authentication is enabled, include your API key:

```bash
curl -X POST http://localhost:8080/api/run-command \
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

Alternatively, if Basic Authentication is enabled and you don't have an API key:

```bash
curl -X POST http://localhost:8080/api/run-command \
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
    "http://localhost:8080/api/run-command",
    json={
        "config_file": "config.yml",
        "commands": ["cat_update", "tag_update"],
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
        "dry_run": False,
        "skip_cleanup": False,
        "skip_qb_version_check": False,
        "log_level": "info"
    }
)
print(response.json())
```

If authentication is enabled, include your API key:

```python
import requests

headers = {"X-API-Key": "your_api_key_here"}

response = requests.post(
    "http://localhost:8080/api/run-command",
    headers=headers,
    json={
        "config_file": "config.yml",
        "commands": ["cat_update", "tag_update"],
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
        "dry_run": False,
        "skip_cleanup": False,
        "skip_qb_version_check": False,
        "log_level": "info"
    }
)
print(response.json())
```

Alternatively, if Basic Authentication is enabled:

```python
import requests
from requests.auth import HTTPBasicAuth

response = requests.post(
    "http://localhost:8080/api/run-command",
    auth=HTTPBasicAuth("username", "password"),
    json={
        "config_file": "config.yml",
        "commands": ["cat_update", "tag_update"],
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
        "dry_run": False,
        "skip_cleanup": False,
        "skip_qb_version_check": False,
        "log_level": "info"
    }
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
