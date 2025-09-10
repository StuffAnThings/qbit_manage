# Docker Installation

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
version: "3.7"
services:
  qbit_manage:
    container_name: qbit_manage
    image: ghcr.io/stuffanthings/qbit_manage:latest
    volumes:
      - /mnt/user/appdata/qbit_manage/:/config:rw
      - /mnt/user/data/torrents/:/data/torrents:rw
      - /mnt/user/appdata/qbittorrent/:/qbittorrent/:ro
    ports:
      - "8080:8080"  # Web API port (when enabled)
    environment:
      # Web API Configuration
      - QBT_WEB_SERVER=true     # Set to true to enable web API and web UI
      - QBT_PORT=8080           # Web API port (default: 8080)

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

The Web API and Web UI are enabled by default in this Docker setup.
1. Ensure port 8080 (or your chosen `QBT_PORT`) is mapped using the `ports` section.
2. Access the Web UI at `http://your-host:8080`
3. Access the Web API at `http://your-host:8080/api/run-command`

See the [Web API Documentation](Web-API) and [Web UI Documentation](Web-UI) for detailed usage instructions, security features, and examples.

You will also need to define not just the config volume but the volume to your torrents, this is in order to use the recycling bin, remove orphans and the no hard link options

Here we have `/mnt/user/data/torrents/` mapped to `/data/torrents/` furthermore in the config file associated with it the root_dir is mapped to `/data/torrents/`
We also have `/mnt/user/appdata/qbittorrent/` mapped to `/qbittorrent` and in the config file we associated torrents_dir to `/qbittorrent/data/BT_backup` to use the save_torrents functionality
