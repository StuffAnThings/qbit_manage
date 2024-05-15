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

Below is a list of the docker environment variables
| Docker Environment Variable | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                | Default Value |
| :-------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------ |
| QBT_RUN                     | Run without the scheduler. Script will exit after completion.                                                                                                                                                                                                                                                                                                                                                                                              | False         |
| QBT_SCHEDULE                | Schedule to run every x minutes. (Default set to 1440)                                                                                                                                                                                                                                                                                                                                                                                                       | 1440          |
| QBT_STARTUP_DELAY           | Initial run will start after x seconds (Default set to 0)                                                                                                                                                                                                                                                                                                                                                                                                  | 0             |
| QBT_CONFIG                  | This is used if you want to use a different name for your config.yml. `Example: tv.yml` This variable can also be used to allow the use of multiple config files for a single instance of qbit-manage. For example, listing a wildcard value `Example: QBIT_CONFIG=config_*.yml` and naming your config files accordingly `Example: config_movies.yml` and `config_tv.yml` will instruct qbit-manage to utilize each config file that matches the specified naming convention during every run.                                                                                                                                                                                                                                                                                                                                                                    | config.yml    |
| QBT_LOGFILE                 | This is used if you want to use a different name for your log file. `Example: tv.log`                                                                                                                                                                                                                                                                                                                                                                      | activity.log  |
| QBT_CROSS_SEED              | Use this after running [cross-seed script](https://github.com/mmgoodnow/cross-seed) to add torrents from the cross-seed output folder to qBittorrent                                                                                                                                                                                                                                                                                                       | False         |
| QBT_RECHECK                 | Recheck paused torrents sorted by lowest size. Resume if Completed.                                                                                                                                                                                                                                                                                                                                                                                        | False         |
| QBT_CAT_UPDATE              | Use this if you would like to update your categories or move from one category to another..                                                                                                                                                                                                                                                                                                                                                                | False         |
| QBT_TAG_UPDATE              | Use this if you would like to update your tags. (Only adds tags to untagged torrents)                                                                                                                                                                                                                                                                                                                                                                      | False         |
| QBT_REM_UNREGISTERED        | Use this if you would like to remove unregistered torrents. (It will the delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent without deleting data)                                                                                                                                                                                                                                                           | False         |
| QBT_TAG_TRACKER_ERROR       | Use this to tag any torrents with tracker errors, such as unregistered torrents or unreachable trackers.                                                                                                                                                                                                                                                                                                                                                   | False         |
| QBT_REM_ORPHANED            | Use this if you would like to remove orphaned files from your `root_dir` directory that are not referenced by any torrents. It will scan your `root_dir` directory and compare it with what is in qBittorrent. Any data not referenced in qBittorrent will be moved into `/data/torrents/orphaned_data` folder for you to review/delete.                                                                                                                   | False         |
| QBT_TAG_NOHARDLINKS         | Use this to tag any torrents that do not have any hard links associated with any of the files. This is useful for those that use Sonarr/Radarr that hard links your media files with the torrents for seeding. When files get upgraded they no longer become linked with your media therefore will be tagged with a new tag noHL. You can then safely delete/remove these torrents to free up any extra space that is not being used by your media folder. | False         |
| QBT_SHARE_LIMITS            | Control how torrent share limits are set depending on the priority of your grouping. This can apply a max ratio, seed time limits to your torrents or limit your torrent upload speed as well. Each torrent will be matched with the share limit group with the highest priority that meets the group filter criteria. Each torrent can only be matched with one share limit group.                                                                        | False         |
| QBT_SKIP_CLEANUP            | Use this to skip emptying the Recycle Bin folder (`/root_dir/.RecycleBin`) and Orphaned directory. (`/root_dir/orphaned_data`)                                                                                                                                                                                                                                                                                                                             | False         |
| QBT_SKIP_QB_VERSION_CHECK   | Use this to bypass qBittorrent/libtorrent version compatibility check. You run the risk of undesirable behavior and will receive no support.                                                                                                                                                                                                                                                                                                               | False         |
| QBT_DRY_RUN                 | If you would like to see what is gonna happen but not actually move/delete or tag/categorize anything.                                                                                                                                                                                                                                                                                                                                                     | False         |
| QBT_LOG_LEVEL               | Change the output log level.                                                                                                                                                                                                                                                                                                                                                                                                                               | INFO          |
| QBT_DIVIDER                 | Character that divides the sections (Default: '=')                                                                                                                                                                                                                                                                                                                                                                                                         | =             |
| QBT_WIDTH                   | Screen Width (Default: 100)                                                                                                                                                                                                                                                                                                                                                                                                                                | 100           |
| QBT_DEBUG                   | Enable Debug logs                                                                                                                                                                                                                                                                                                                                                                                                                                          | False           |
| QBT_TRACE                   | Enable Trace logs                                                                                                                                                                                                                                                                                                                                                                                                                                          | False           |

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
    environment:
      - QBT_RUN=false
      - QBT_SCHEDULE=1440
      - QBT_CONFIG=config.yml
      - QBT_LOGFILE=activity.log
      - QBT_CROSS_SEED=false
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
      - QBT_LOG_LEVEL=INFO
      - QBT_DIVIDER==
      - QBT_WIDTH=100
    restart: on-failure:2
```

You will also need to define not just the config volume but the volume to your torrents, this is in order to use the recycling bin, remove orphans and the no hard link options

Here we have `/mnt/user/data/torrents/` mapped to `/data/torrents/` furthermore in the config file associated with it the root_dir is mapped to `/data/torrents/`
We also have `/mnt/user/appdata/qbittorrent/` mapped to `/qbittorrent` and in the config file we associated torrents_dir to `/qbittorrent/data/BT_backup` to use the save_torrents functionality
