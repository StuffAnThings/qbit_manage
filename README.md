# <img src="https://github.com/StuffAnThings/qbit_manage/blob/master/icons/qbm_logo.png?raw=true" width="75"> qBit Manage

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/StuffAnThings/qbit_manage?style=plastic)](https://github.com/StuffAnThings/qbit_manage/releases)
[![GitHub commits since latest release (by SemVer)](https://img.shields.io/github/commits-since/StuffAnThings/qbit_manage/latest/develop?label=Commits%20in%20Develop&style=plastic)](https://github.com/StuffAnThings/qbit_manage/tree/develop)
[![Docker Image Version (latest semver)](https://img.shields.io/docker/v/bobokun/qbit_manage?label=docker&sort=semver&style=plastic)](https://hub.docker.com/r/bobokun/qbit_manage)
[![PyPi (latest semver)](https://img.shields.io/pypi/v/qbit-manage?label=PyPI&sort=semver&style=plastic)](https://pypi.org/project/qbit-manage)
[![Github Workflow Status](https://img.shields.io/github/actions/workflow/status/StuffAnThings/qbit_manage/version.yml?style=plastic)](https://github.com/StuffAnThings/qbit_manage/actions/workflows/version.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/StuffAnThings/qbit_manage/master.svg)](https://results.pre-commit.ci/latest/github/StuffAnThings/qbit_manage/master)
[![Ghcr packages](https://img.shields.io/badge/ghcr.io-packages?style=plastic&label=packages)](https://ghcr.io/StuffAnThings/qbit_manage)
[![Docker Pulls](https://img.shields.io/docker/pulls/bobokun/qbit_manage?style=plastic)](https://hub.docker.com/r/bobokun/qbit_manage)
[![Sponsor or Donate](https://img.shields.io/badge/-Sponsor_or_Donate-blueviolet?style=plastic)](https://github.com/sponsors/bobokun)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

This is a program used to manage your qBittorrent instance such as:

* Tag torrents based on tracker URLs
* Apply category based on `save_path` to uncategorized torrents in category's `save_path`
* Change categories based on current category (`cat_change`)
* Remove unregistered torrents (delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent)
* Recheck paused torrents sorted by lowest size and resume if completed
* Remove orphaned files from your root directory that are not referenced by qBittorrent
* Tag any torrents that have no hard links outside the root folder (for multi-file torrents the largest file is used)
* Apply share limits based on groups filtered by tags/categories and allows optional cleanup to delete these torrents and contents based on maximum ratio and/or time seeded. Additionally allows for a minimum seed time to ensure tracker rules are respected and minimum number of seeders to keep torrents alive.
* RecycleBin function to move files into a RecycleBin folder instead of deleting the data directly when deleting a torrent
* Built-in scheduler to run the script every x minutes. (Can use `--run` command to run without the scheduler)
* Webhook notifications with [Notifiarr](https://notifiarr.com/) and [Apprise API](https://github.com/caronc/apprise-api) integration

## Supported Qbittorrent Versions

We rely on [qbittorrent-api](https://pypi.org/project/qbittorrent-api/) to interact with Qbittorrent.

Generally expect new releases of Qbittorrent to not immediately be supported. Support CANNOT be added until qbittorrent-api adds support for the version. Any material changed and impact must then be assessed prior to Qbit Manage supporting it.

### Master

![master - qBittorrent version](https://img.shields.io/badge/dynamic/json?label=master%20-%20qBittorrent&query=master.qbit&url=https%3A%2F%2Fraw.githubusercontent.com%2FStuffAnThings%2Fqbit_manage%2Fdevelop%2FSUPPORTED_VERSIONS.json&color=brightgreen)

![master - qbittorrent-api version](https://img.shields.io/badge/dynamic/json?label=master%20-%20qbittorrent-api&query=master.qbitapi&url=https%3A%2F%2Fraw.githubusercontent.com%2FStuffAnThings%2Fqbit_manage%2Fdevelop%2FSUPPORTED_VERSIONS.json&color=blue)

### Develop

![develop - qBittorrent version](https://img.shields.io/badge/dynamic/json?label=develop%20-%20qBittorrent&query=develop.qbit&url=https%3A%2F%2Fraw.githubusercontent.com%2FStuffAnThings%2Fqbit_manage%2Fdevelop%2FSUPPORTED_VERSIONS.json&color=brightgreen)

![develop - qbittorrent-api version](https://img.shields.io/badge/dynamic/json?label=develop%20-%20qbittorrent-api&query=develop.qbitapi&url=https%3A%2F%2Fraw.githubusercontent.com%2FStuffAnThings%2Fqbit_manage%2Fdevelop%2FSUPPORTED_VERSIONS.json&color=blue)

## Getting Started

Check out the [wiki](https://github.com/StuffAnThings/qbit_manage/wiki) for installation help

1. Install qbit_manage either by installing Python 3.9.0+ on the localhost and following the [Local Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Local-Installations) Guide or by installing Docker and following the [Docker Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Docker-Installation) Guide or the [unRAID Installation](https://github.com/StuffAnThings/qbit_manage/wiki/Unraid-Installation) Guide.
1. Once installed, you have to [set up your Configuration](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup) by create a [Configuration File](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample) filled with all your values to connect to your qBittorrent instance.
1. Please refer to the list of [Commands](https://github.com/StuffAnThings/qbit_manage/wiki/Commands) that can be used with this tool.

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
