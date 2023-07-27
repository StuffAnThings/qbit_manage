# <img src="qbm_logo.png" width="75"> qBit Manage

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/StuffAnThings/qbit_manage?style=plastic)](https://github.com/StuffAnThings/qbit_manage/releases)
[![GitHub commits since latest release (by SemVer)](https://img.shields.io/github/commits-since/StuffAnThings/qbit_manage/latest/develop?label=Commits%20in%20Develop&style=plastic)](https://github.com/StuffAnThings/qbit_manage/tree/develop)
[![Docker Image Version (latest semver)](https://img.shields.io/docker/v/bobokun/qbit_manage?label=docker&sort=semver&style=plastic)](https://hub.docker.com/r/bobokun/qbit_manage)
![Github Workflow Status](https://img.shields.io/github/actions/workflow/status/StuffAnThings/qbit_manage/latest.yml?style=plastic)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/StuffAnThings/qbit_manage/master.svg)](https://results.pre-commit.ci/latest/github/StuffAnThings/qbit_manage/master)
[![Docker Pulls](https://img.shields.io/docker/pulls/bobokun/qbit_manage?style=plastic)](https://hub.docker.com/r/bobokun/qbit_manage)
[![Sponsor or Donate](https://img.shields.io/badge/-Sponsor_or_Donate-blueviolet?style=plastic)](https://github.com/sponsors/bobokun)

This is a program used to manage your qBittorrent instance such as:

* Tag torrents based on tracker URLs
* Update categories based on save directory
* Remove unregistered torrents (delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent)
* Automatically add [cross-seed](https://github.com/mmgoodnow/cross-seed) torrents in paused state. **\*Note: cross-seed now allows for torrent injections directly to qBit, making this feature obsolete.\***
* Recheck paused torrents sorted by lowest size and resume if completed
* Remove orphaned files from your root directory that are not referenced by qBittorrent
* Tag any torrents that have no hard links outisde the root folder
* Apply share limits based on groups filtered by tags/categories and allows optional cleanup to delete these torrents and contents based on maximum ratio and/or time seeded
* RecycleBin function to move files into a RecycleBin folder instead of deleting the data directly when deleting a torrent
* Built-in scheduler to run the script every x minutes. (Can use `--run` command to run without the scheduler)
* Webhook notifications with [Notifiarr](https://notifiarr.com/) and [Apprise API](https://github.com/caronc/apprise-api) integration
## Getting Started

Check out the [wiki](https://github.com/StuffAnThings/qbit_manage/wiki) for installation help
1. Install qbit_manage either by installing Python 3.8.1+ on the localhost and following the [Local Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Local-Installations) Guide or by installing Docker and following the [Docker Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Docker-Installation) Guide or the [unRAID Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Unraid-Installation) Guide.<br>
2. Once installed, you have to [set up your Configuration](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup) by create a [Configuration File](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample) filled with all your values to connect to your qBittorrent instance.
3. Please refer to the list of [Commands](https://github.com/StuffAnThings/qbit_manage/wiki/Commands) that can be used with this tool.
## Usage
To run the script in an interactive terminal with a list of possible commands run:
```bash
python qbit_manage.py -h
```
## Support
* If you have any questions or require support please join the [Notifiarr Discord](https://discord.com/invite/AURf8Yz) and post your question under the `qbit-manage` channel.
* If you're getting an Error or have an Enhancement post in the [Issues](https://github.com/StuffAnThings/qbit_manage/issues/new).
* If you have a configuration question post in the [Discussions](https://github.com/StuffAnThings/qbit_manage/discussions/new).
* Pull Request are welcome but please submit them to the [develop branch](https://github.com/StuffAnThings/qbit_manage/tree/develop).
