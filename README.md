# <img src="qbm_logo.png" width="75"> qBit Management

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
* Automatically add [cross-seed](https://github.com/mmgoodnow/cross-seed) torrents in paused state. **\*Note: cross-seed now allows for torrent injections directly to qBit, making this feature obsolete.\***
* Recheck paused torrents sorted by lowest size and resume if completed
* Remove orphaned files from your root directory that are not referenced by qBittorrent
* Tag any torrents that have no hard links and allows optional cleanup to delete these torrents and contents based on maximum ratio and/or time seeded
* RecycleBin function to move files into a RecycleBin folder instead of deleting the data directly when deleting a torrent
* Built-in scheduler to run the script every x minutes. (Can use `--run` command to run without the scheduler)
## Getting Started

Check out the [wiki](https://github.com/StuffAnThings/qbit_manage/wiki) for installation help
1. Install qbit_mange either by installing Python3 on the localhost and following the [Local Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Local-Installations) Guide or by installing Docker and following the [Docker Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Docker-Installation) Guide or the [unRAID Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Unraid-Installation) Guide.<br>
2. Once installed, you have to [set up your Configuration](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup) by create a [Configuration File](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample) filled with all your values to connect to your qBittorrent instance. 

## Usage
To run the script in an interactive terminal with a list of possible commands run:

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
## Support
* If you're getting an Error or have an Enhancement post in the [Issues](https://github.com/StuffAnThings/qbit_manage/issues/new).
* If you have a configuration question post in the [Discussions](https://github.com/StuffAnThings/qbit_manage/discussions/new).
* Pull Request are welcome but please submit them to the [develop branch](https://github.com/StuffAnThings/qbit_manage/tree/develop).