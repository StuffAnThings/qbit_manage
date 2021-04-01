# qBit Management
This is a program used to manage your qBitorrent instance such as:
* Tag torrents based on tracker URL (only tag torrents that have no tags)
* Update categories based on save directory
* Remove unregistered torrents (delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent)
* Automatically add [cross-seed](https://github.com/mmgoodnow/cross-seed) torrents in paused state (used in conjunction with the [cross-seed](https://github.com/mmgoodnow/cross-seed) script)
* Recheck paused torrents sorted by lowest size. Resume if completed.

## Installation

####Unraid Installation:
* [Guide to setup on Unraid](https://github.com/StuffAnThings/qbit_manage/wiki/qBit-Manager-on-unRAID)
####Local Installation:
* Requires `python 3`. Dependencies must be installed by running:
```
pip install -r requirements.txt
```
If there are issues installing dependencies try:
```
pip install -r requirements.txt --ignore-installed
```

## Usage
To run the script in an interactive terminal run:
* copy the `config.yml.sample` file to `config.yml`
* add your qBittorrent host, user and pass. If you are not using a username and password you can remove the `user` and `pass` lines. 
* add your `cross_seed` and `root_dir`. If you are using a docker container you must fill out `remote_dir` as well.
* Add your categories and save path to match with what is being used in your qBitorrent instance. I suggest using the full path when defining `save_path`
* Add the `tag` definition based on tracker URL
* To run the script in an interactive terminal with a list of possible commands run:
```
python qbit_manage.py -h
```

## Commands
|      Name     | Shell Command | Description | Default Value | 
| :-----------  | :------------ | :------------  | :------------ |
| Config  | `-c CONFIG` or `--config-file CONFIG`  | This is used if you want to use a different name for your config.yml. `Example: tv.yml`  | config.yml |
| Log File| `-l LOGFILE,` or `--log-file LOGFILE,` | This is used if you want to use a different name for your log file. `Example: tv.log` | activity.log |
| Manage| `-m` or `--manage` | Use this if you would like to update your tags, categories, remove unregistered torrents, AND recheck/resume paused torrents.  |  |
| Cross-Seed| `-s` or `--cross-seed` | Use this after running [cross-seed script](https://github.com/mmgoodnow/cross-seed) to add torrents from the cross-seed output folder to qBittorrent  |  |
| Recheck| `-re` or `--recheck` | Recheck paused torrents sorted by lowest size. Resume if Completed.  |  |
| Update Category| `-g` or `--cat-update` |  Use this if you would like to update your categories.  |  |
| Add Tags| `-t` or `--tag-update` |  Use this if you would like to update your tags. (Only adds tags to untagged torrents) |  |
| Remove Unregistered Torrents| `-r` or `--rem-unregistered` |  Use this if you would like to remove unregistered torrents. (It will the delete data & torrent if it is not being cross-seeded, otherwise it will just remove the torrent without deleting data) |  |
| Remove Orphaned Data| `-ro` or `--rem-orphaned` | Use this if you would like to remove orphaned files from your `root_dir` directory that are not referenced by any torrents. It will scan your `root_dir` directory and compare it with what is in Qbitorrent. Any data not referenced in Qbitorrent will be moved into `/data/torrents/orphaned_data` folder for you to review/delete. |  |
| Dry-Run | `--dry-run` |   If you would like to see what is gonna happen but not actually move/delete or tag/categorize anything. |  |
| Log Level | `--log LOGLEVEL` |   Change the ouput log level. | INFO |

### Config
To choose the location of the YAML config file
```
python qbit_manage.py --config-file <path_to_config>
```
### Log
To choose the location of the Log File
```
python qbit_manage.py --log-file <path_to_log>
```