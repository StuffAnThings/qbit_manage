# qBit Management

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/StuffAnThings/qbit_manage?style=plastic)](https://github.com/StuffAnThings/qbit_manage/releases)
[![GitHub commits since latest release (by SemVer)](https://img.shields.io/github/commits-since/StuffAnThings/qbit_manage/latest/develop?label=Commits%20in%20Develop&style=plastic)](https://github.com/StuffAnThings/qbit_manage/tree/develop)
[![Docker Image Version (latest semver)](https://img.shields.io/docker/v/bobokun/qbit_manage?label=docker&sort=semver&style=plastic)](https://hub.docker.com/r/bobokun/qbit_manage)
![Github Workflow Status](https://img.shields.io/github/workflow/status/StuffAnThings/qbit_manage/Docker%20Latest%20Release?style=plastic)
[![Docker Pulls](https://img.shields.io/docker/pulls/bobokun/qbit_manage?style=plastic)](https://hub.docker.com/r/bobokun/qbit_manage)
[![Sponsor or Donate](https://img.shields.io/badge/-Sponsor_or_Donate-blueviolet?style=plastic)](https://github.com/sponsors/bobokun)

This is a program used to manage your qBittorrent instance such as:

* Tag torrents based on tracker URL and set seed goals/limit upload speed by tag (only tag torrents that have no tags)
* Update categories based on save directory
* Remove unregistered torrents (delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent)
* Automatically add [cross-seed](https://github.com/mmgoodnow/cross-seed) torrents in paused state (used in conjunction with the [cross-seed](https://github.com/mmgoodnow/cross-seed) script) <-- cross-seed now allows for torrent injections directly to qBit.
* Recheck paused torrents sorted by lowest size and resume if completed
* Remove orphaned files from your root directory that are not referenced by qBittorrent
* Tag any torrents that have no hard links and allows optional cleanup to delete these torrents and contents based on maximum ratio and/or time seeded
* RecycleBin function to move files into a RecycleBin folder instead of deleting the data directly when deleting a torrent
* Built-in scheduler to run the script every x minutes. (Can use `--run` command to run without the scheduler)
## Installation

Check out the [wiki](https://github.com/StuffAnThings/qbit_manage/wiki) for installation help

## Usage

To run the script in an interactive terminal run:

* copy the `config.yml.sample` file to `config.yml`
* add your qBittorrent host, user and pass. If you are not using a username and password you can remove the `user` and `pass` lines.
* add your `cross_seed` and `root_dir`. If you're running cross-seed in a docker container you must fill out `remote_dir` as well.
* Add your categories and save path to match with what is being used in your qBittorrent instance. I suggest using the full path when defining `save_path`
* Add the `tag` definition based on tracker URL (optional add seed goals/limit upload speed by tag)
* Modify the  `nohardlinks` by specifying your completed movies/series category to match with qBittorrent. Please ensure the `root_dir` and/or  `remote_dir` is added in the `directory` section
* `root_dir` needs to be defined in order to use the RecycleBin function. If optional `empty_after_x_days` is not defined then it will never empty the RecycleBin. Setting it to 0 will empty the RecycleBin immediately.
* Modify the `orphaned` section to define file patterns not to consider as orphans. Use this to exclude your incomplete torrents directory, or to ignore auto-generated files such as Thumbs.db.
* To run the script in an interactive terminal with a list of possible commands run:

```bash
python qbit_manage.py -h
```

## Commands

| Shell Command |Docker Environment Variable |Description | Default Value |
| :------------ | :------------  | :------------ | :------------ |
| `-r` or`--run` | QBT_RUN |Run without the scheduler. Script will exit after completion. | False |
| `-sch` or `--schedule` | QBT_SCHEDULE  | Schedule to run every x minutes. (Default set to 30)  | 30 |
| `-c CONFIG` or `--config-file CONFIG` | QBT_CONFIG  | This is used if you want to use a different name for your config.yml. `Example: tv.yml`  | config.yml |
| `-lf LOGFILE,` or `--log-file LOGFILE,` | QBT_LOGFILE | This is used if you want to use a different name for your log file. `Example: tv.log` | activity.log |
| `-cs` or `--cross-seed` | QBT_CROSS_SEED | Use this after running [cross-seed script](https://github.com/mmgoodnow/cross-seed) to add torrents from the cross-seed output folder to qBittorrent  | False |
| `-re` or `--recheck` | QBT_RECHECK | Recheck paused torrents sorted by lowest size. Resume if Completed.  | False |
| `-cu` or `--cat-update` | QBT_CAT_UPDATE |  Use this if you would like to update your categories.  | False |
| `-tu` or `--tag-update` | QBT_TAG_UPDATE |  Use this if you would like to update your tags and/or set seed goals/limit upload speed by tag. (Only adds tags to untagged torrents) | False |
| `-ru` or `--rem-unregistered` | QBT_REM_UNREGISTERED |  Use this if you would like to remove unregistered torrents. (It will the delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent without deleting data) | False |
| `-ro` or `--rem-orphaned` | QBT_REM_ORPHANED | Use this if you would like to remove orphaned files from your `root_dir` directory that are not referenced by any torrents. It will scan your `root_dir` directory and compare it with what is in qBittorrent. Any data not referenced in qBittorrent will be moved into `/data/torrents/orphaned_data` folder for you to review/delete. | False |
| `-tnhl` or `--tag-nohardlinks` | QBT_TAG_NOHARDLINKS | Use this to tag any torrents that do not have any hard links associated with any of the files. This is useful for those that use Sonarr/Radarr that hard links your media files with the torrents for seeding. When files get upgraded they no longer become linked with your media therefore will be tagged with a new tag noHL. You can then safely delete/remove these torrents to free up any extra space that is not being used by your media folder. | False |
| `-sr` or `--skip-recycle` | QBT_SKIP_RECYCLE | Use this to skip emptying the Reycle Bin folder (`/root_dir/.RecycleBin`). | False |
| `-dr` or `--dry-run` | QBT_DRY_RUN |   If you would like to see what is gonna happen but not actually move/delete or tag/categorize anything. | False |
| `-ll` or `--log-level LOGLEVEL` | QBT_LOG_LEVEL |   Change the ouput log level. | INFO |
| `-d` or `--divider` | QBT_DIVIDER |   Character that divides the sections (Default: '=') | = |
| `-w` or `--width` | QBT_WIDTH |   Screen Width (Default: 100) | 100 |
### Config

To choose the location of the YAML config file

```bash
python qbit_manage.py --config-file <path_to_config>
```

### Log

To choose the location of the Log File

```bash
python qbit_manage.py --log-file <path_to_log>
```
