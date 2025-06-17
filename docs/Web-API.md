# Web API Documentation

## Overview

qBit Manage provides a REST API that allows you to trigger commands via HTTP requests. The API server runs on port 8080 by default and can be configured using the `--port` option or `QBT_PORT` environment variable.

## Running the Web Server

### Command Line

```bash
python qbit_manage.py --web-server --port 8080
```

### Docker

```yaml
version: "3"
services:
  qbit_manage:
    image: bobokun/qbit_manage:latest
    container_name: qbit_manage
    environment:
      - QBT_WEB_SERVER=true # Enable web server
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
  "dry_run": false, // Optional, defaults to false
  "hashes": ["<hash1>", "<hash2>"] // Optional, list of torrent hashes to filter by
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

| Command             | Description                                                                                       | Supports Hashes |
| ------------------- | ------------------------------------------------------------------------------------------------- | --------------- |
| `cat_update`        | Update categories based on save paths                                                             | Yes             |
| `tag_update`        | Add tags based on tracker URLs                                                                    | Yes             |
| `recheck`           | Recheck paused torrents sorted by size and resume completed ones                                  | Yes             |
| `rem_unregistered`  | Remove unregistered torrents                                                                      | Yes             |
| `tag_tracker_error` | Tag torrents with tracker errors                                                                  | Yes             |
| `rem_orphaned`      | Remove orphaned files from root directory                                                         | No              |
| `tag_nohardlinks`   | Tag torrents with no hard links                                                                   | Yes             |
| `share_limits`      | Apply share limits based on tags/categories                                                       | Yes             |

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
curl -fsSL -X POST -H "Content-Type: application/json" -d "{ \"commands\": [\"tag_update\", \"share_limits\"], \"hashes\": [\"%I\"] }" http://qbit_manage:8080/api/run-command
```
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
    "dry_run": false,
    "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"]
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
        "dry_run": false,
        "hashes": ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"]
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
