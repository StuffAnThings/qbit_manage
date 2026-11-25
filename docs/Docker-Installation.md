# Docker Installation

The image is `ghcr.io/stuffanthings/qbit_manage`. A Dockerfile is in the repo if you want to build it yourself.

```bash
docker run -it -v <PATH_TO_CONFIG>:/config:rw ghcr.io/stuffanthings/qbit_manage:latest
```

- `<PATH_TO_CONFIG>` is the folder that holds your `config.yml`. The image reads `config.yml` from `/config`.
- Quote the whole mapping if the path has spaces.
- qbit_manage must see your files at the same path as qBittorrent. If qBittorrent maps `/mnt/user/data/:/data`, map it the same way here.
- Set `root_dir` in the config to the folder you want to manage, for example `/data/torrents`.
- `remote_dir` is optional. Comment it out if you do not need it.

## Example compose file

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
      - "127.0.0.1:8181:8181"  # only if you turn the web server on
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
      - QBT_WEB_SERVER=true    # off by default
      - QBT_WEB_USERNAME=admin # creates the login on first start
      - QBT_WEB_PASSWORD=Wh1te-Rabbit! # replace it; 8+ characters, 3 of upper/lower/number/special
      - QBT_RUN=false
      - QBT_SCHEDULE=1440
      - QBT_CONFIG_DIR=/config
      - QBT_LOGFILE=qbit_manage.log
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
      - QBT_LOG_LEVEL=INFO
    restart: on-failure:2
```

- Mount every folder you want the recycle bin, orphan removal, and no-hardlink tagging to reach.
- To use `torrents_dir`, mount the qBittorrent data folder and point `torrents_dir` at `BT_backup` inside it.
- See [Commands](Commands) for every variable.

## Web UI and Web API

The web server is off unless you set `QBT_WEB_SERVER=true`. A login is always required. Set `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` before the first start, or read the generated password from `/config/qbm_initial_password.txt`. Read [Security](Security) before you turn it on.

1. Set `QBT_WEB_SERVER=true`.
2. Publish the port. The example above binds it to the Docker host only.
3. Open `http://<host>:8181` for the Web UI. The API is under `/api`.

To check that it runs, call the health endpoint. It needs no login.

```bash
curl -s http://localhost:8181/api/health
```

The `status` value is `healthy`, `degraded`, `busy`, or `unhealthy`.

## Upgrading to 5.0

1. Keep `QBT_WEB_SERVER=true` if you use the Web UI.
2. Add `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD`, or read `/config/qbm_initial_password.txt`.
3. `bypass_auth_for_local` is gone, and so is `external` mode: it becomes `local`, with a password in `/config/qbm_initial_password.txt` if none was set.
4. Run `docker compose up -d`.

## Reverse proxy

Put a reverse proxy in front of the web server for TLS. qbit_manage keeps its own login; set `public_url` to the address people type (see [Security](Security#behind-a-reverse-proxy)). If you serve it under a sub-path, set `QBT_BASE_URL` to that path.

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

```
handle /qbitmanage/* {
    uri strip_prefix /qbitmanage
    reverse_proxy qbit_manage:8181
}
```

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Web UI does not load | Web server is off, or the port is not published | Set `QBT_WEB_SERVER=true` and add the `ports` entry |
| Permission denied on torrent files | `PUID` and `PGID` do not match the file owner | Use the UID and GID that own your torrent data |
| qbit_manage cannot see torrents | Paths differ from qBittorrent's | Mount the same host path at the same container path |
| Health is `degraded`: no configuration files | `/config` is empty | Copy `config.yml` into the mapped folder |
| Locked out | Forgot the password | Add `QBT_WEB_PASSWORD_RESET=true` with the username and a new password, run `docker compose up -d`, log in, then remove the reset variable. See [Security](Security#recovery) |
| API returns 401 | Authentication is on and no key was sent | Send the `X-API-Key` header, or use basic auth |
