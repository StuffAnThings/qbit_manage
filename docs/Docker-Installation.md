# Docker Installation

> Last validated against qbit_manage v4.7.1. See [v4 Migration Guide](v4-Migration-Guide.md) for changes since v4.0.

A simple Dockerfile is available in this repo if you'd like to build it yourself.
The official build on github is available [here](https://ghcr.io/StuffAnThings/qbit_manage): <br>
`docker run -it -v <PATH_TO_CONFIG>:/config:rw ghcr.io/stuffanthings/qbit_manage:latest`

* The -v <PATH_TO_CONFIG>:/config:rw mounts the location you choose as a persistent volume to store your files.
  * Change <PATH_TO_CONFIG> to a folder where your config.yml and other files are.
  * The docker image defaults to running the config named config.yml in your persistent volume.
  * Use quotes around the whole thing if your path has spaces i.e. -v "<PATH_TO_CONFIG>:/config:rw"

* Fill out your location for your downloads downloads folder (`Root_Dir`).
   1. qbit_manage needs to be able to view all torrents the way that your qbittorrent views them.
      1. Example: If you have qbittorrent mapped to `/mnt/user/data/:/data` This means that you **MUST** have qbit_managed mapped the same way.
      2. Furthermore, the config file must map the root directory you wish to monitor. This means that in our example of `/data` (which is how qbittorrent views the torrents) that if in your `/data` directory you drill down to `/torrents` that you'll need to update your config file to `/data/torrents`
   2. This could be different depending on your specific setup.
   3. The key takeaways are
      1. Both qbit_manage needs to have the same mappings as qbittorrent
      2. The config file needs to drill down (if required) further to the desired root dir.
* `remote_dir`: is not required and can be commented out with `#`

Please see [Commands](https://github.com/StuffAnThings/qbit_manage/wiki/Commands) for a list of arguments and docker environment variables.

Here is an example of a docker compose

```yaml
services:
  qbit_manage:
    container_name: qbit_manage
    image: ghcr.io/stuffanthings/qbit_manage:latest
    volumes:
      - /mnt/user/appdata/qbit_manage/:/config:rw
      - /mnt/user/data/torrents/:/data/torrents:rw
      - /mnt/user/appdata/qbittorrent/:/qbittorrent/:ro
    ports:
      - "8181:8181"  # Web API port (when enabled)
    environment:
      # Web API Configuration
      - QBT_WEB_SERVER=true     # disabled by default in Docker; set to true to enable
      - QBT_PORT=8181           # Web API port (default: 8181)

      # Scheduler Configuration
      - QBT_RUN=false
      - QBT_SCHEDULE=1440
      - QBT_CONFIG_DIR=/config
      - QBT_LOGFILE=qbit_manage.log

      # Command Flags
      - QBT_RECHECK=false
      - QBT_CAT_UPDATE=false
      - QBT_TAG_UPDATE=false
      - QBT_REM_UNREGISTERED=false
      - QBT_REM_ORPHANED=false
      - QBT_TAG_TRACKER_ERROR=false
      - QBT_TAG_NOHARDLINKS=false
      - QBT_SHARE_LIMITS=false
      - QBT_SKIP_CLEANUP=false
      - QBT_DRY_RUN=false
      - QBT_STARTUP_DELAY=0
      - QBT_SKIP_QB_VERSION_CHECK=false
      - QBT_DEBUG=false
      - QBT_TRACE=false

      # Logging Configuration
      - QBT_LOG_LEVEL=INFO
      - QBT_LOG_SIZE=10
      - QBT_LOG_COUNT=5
      - QBT_DIVIDER==
      - QBT_WIDTH=100
    restart: on-failure:2
```

### Web API and Web UI Usage

In this example compose, the web server is enabled via `QBT_WEB_SERVER=true`. By default in Docker, the web server is **disabled** (per `qbit_manage.py:280-281`: `if web_server is None and not is_docker: web_server = True`). Set `QBT_WEB_SERVER=true` to enable.
1. Ensure port 8181 (or your chosen `QBT_PORT`) is mapped using the `ports` section.
2. Access the Web UI at `http://your-host:8181`
3. Access the Web API at `http://your-host:8181/api/run-command`

See the [Web API Documentation](Web-API) and [Web UI Documentation](Web-UI) for detailed usage instructions, security features, and examples.

You will also need to define not just the config volume but the volume to your torrents, this is in order to use the recycling bin, remove orphans and the no hard link options

Here we have `/mnt/user/data/torrents/` mapped to `/data/torrents/` furthermore in the config file associated with it the root_dir is mapped to `/data/torrents/`
We also have `/mnt/user/appdata/qbittorrent/` mapped to `/qbittorrent` and in the config file we associated torrents_dir to `/qbittorrent/data/BT_backup` to use the save_torrents functionality

---

## Worked Example: End-to-End Docker Deploy with Web UI Enabled

This section walks through a complete deployment using the `develop` image with the web API and web UI enabled.

### 1. docker-compose.yml

```yaml
services:
  qbit_manage:
    container_name: qbit_manage
    image: ghcr.io/stuffanthings/qbit_manage:develop
    volumes:
      - /mnt/data/appdata/qbit_manage:/config:rw   # persistent config, logs, settings
      - /mnt/data/torrents:/data/torrents:rw         # must mirror qBittorrent's path
    ports:
      - "8181:8181"   # Web API / Web UI port
    environment:
      # Identity — match the UID/GID that owns your /mnt/data/torrents files
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York

      # Enable the built-in web server (disabled by default in Docker)
      - QBT_WEB_SERVER=true
      - QBT_PORT=8181

      # Run on a schedule (every 1440 minutes = daily); set QBT_RUN=true for one-shot
      - QBT_RUN=false
      - QBT_SCHEDULE=1440
      - QBT_CONFIG_DIR=/config
      - QBT_LOGFILE=qbit_manage.log

      # Commands to run each cycle (all false = web-API-only mode)
      - QBT_RECHECK=false
      - QBT_CAT_UPDATE=false
      - QBT_TAG_UPDATE=false
      - QBT_REM_UNREGISTERED=false
      - QBT_REM_ORPHANED=false
      - QBT_TAG_TRACKER_ERROR=false
      - QBT_TAG_NOHARDLINKS=false
      - QBT_SHARE_LIMITS=false
      - QBT_SKIP_CLEANUP=false
      - QBT_DRY_RUN=false
      - QBT_STARTUP_DELAY=0
      - QBT_SKIP_QB_VERSION_CHECK=false
      - QBT_DEBUG=false
      - QBT_TRACE=false

      # Logging
      - QBT_LOG_LEVEL=INFO
      - QBT_LOG_SIZE=10
      - QBT_LOG_COUNT=5
    restart: on-failure:2
```

### 2. Bring-Up Commands

```bash
# Start in detached mode and tail logs
docker compose up -d && docker compose logs -f qbit_manage
```

Press `Ctrl+C` to stop following logs; the container keeps running.

### 3. Verify the Server Is Running

The `/api/health` endpoint is **always public** (no auth required):

```bash
curl -s http://localhost:8181/api/health | python3 -m json.tool
```

Expected response shape:

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
    "next_scheduled_run_text": "in 24 hours"
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

`status` values: `healthy` | `degraded` | `busy` | `unhealthy`.

### 4. Reverse-Proxy Snippet

#### SWAG / nginx

```nginx
location /qbitmanage/ {
    proxy_pass          http://qbit_manage:8181/;
    proxy_set_header    Host              $host;
    proxy_set_header    X-Real-IP         $remote_addr;
    proxy_set_header    X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header    X-Forwarded-Proto $scheme;
    proxy_http_version  1.1;
    proxy_set_header    Upgrade           $http_upgrade;
    proxy_set_header    Connection        "upgrade";
    proxy_read_timeout  300s;
}
```

If qbit_manage is on the same Docker network as SWAG, use the service name (`qbit_manage`) instead of `localhost`. Add `--base-url /qbitmanage` (or `QBT_BASE_URL=/qbitmanage`) to the container's environment if mounting at a sub-path.

#### Caddy

```
handle /qbitmanage/* {
    uri strip_prefix /qbitmanage
    reverse_proxy qbit_manage:8181
}
```

### 5. Common Gotchas

| Problem | Cause | Fix |
|---|---|---|
| Web UI returns 404 | Port not mapped in compose | Add `ports: - "8181:8181"` |
| "Permission denied" on torrent files | `PUID`/`PGID` mismatch with qBittorrent host user | Match `PUID`/`PGID` to the UID/GID that owns your torrent data |
| qbit_manage can't see torrents | Volume path differs from qBittorrent's view | Both containers **must** mount the same host path to the **same container path** |
| Health returns `degraded` — "No configuration files found" | `/config` volume is empty | Copy your `config.yml` into the mapped host dir before starting |
| API returns 401 | Auth enabled but no key sent | Include `X-API-Key: <key>` header or use HTTP Basic auth |
