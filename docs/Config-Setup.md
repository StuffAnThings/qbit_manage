# Overview

The script utilizes a YAML config file to load information to connect to the various APIs you can connect with. Alternatively, you can configure qBit Manage using the [Web UI](Web-UI), which requires the [Web API](Web-API) to be enabled.

## Default Configuration File Locations

The script looks for the configuration file in different locations depending on your platform:

### Local Installation (Platform-specific)

- **Windows**: `%APPDATA%\qbit-manage\config.yml` (typically `C:\Users\<username>\AppData\Roaming\qbit-manage\config.yml`)
- **macOS**: `~/Library/Application Support/qbit-manage/config.yml`
- **Linux/Unix**: `~/.config/qbit-manage/config.yml` (or `$XDG_CONFIG_HOME/qbit-manage/config.yml` if XDG_CONFIG_HOME is set)

### Docker Installation

- `/config/config.yml` (inside the container)

You can override the default location by using the `--config-dir` or `-cd` command line option to specify a custom directory.

A template Configuration File can be found in the repo [config/config.yml.sample](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample).

You can reference environment variables inside your `config.yml` by `!ENV VAR_NAME`

> [!CAUTION]
> As this software is constantly evolving and this wiki might not be up to date the sample shown here might not be current. Please refer to the repo for the most current version.

# Config File

## [Config Sample File](https://github.com/StuffAnThings/qbit_manage/blob/master/config/config.yml.sample)

# **List of variables**

## **commands:**

---

This section will override any [commands](Commands) that are defined via environment variable or command line and use the ones defined in this yaml file instead. Useful if you want to run qbm with multiple configurations files that execute different commands for each qbt instance.

| Variable  | Definition                                            | Required            |
| :-------- | :---------------------------------------------------- | :------------------ |
| `command` | The [command](Commands) that you want qbm to execute. | <center>❌</center> |

## **qbt:**

---

This section defines your qBittorrent instance.

| Variable | Definition                          | Required            |
| :------- | :---------------------------------- | :------------------ |
| `host`   | IP address of your qB installation. | <center>✅</center> |
| `user`   | The user name of your qB's webUI.   | <center>❌</center> |
| `pass`   | Thee password of your qB's webUI.   | <center>❌</center> |

## **settings:**

---

This section defines any settings defined in the configuration.

| Variable                            | Definition                                                                                                                                                                                                                                                                                                                                      | Default Values            | Required            |
| :---------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------ | :------------------ |
| `force_auto_tmm`                    | Will force qBittorrent to enable Automatic Torrent Management for each torrent.                                                                                                                                                                                                                                                                 | False                     | <center>❌</center> |
| `force_auto_tmm_ignore_tags`        | Torrents with these tags will be ignored when force_auto_tmm is enabled.                                                                                                                                                                                                                                                                        |                           | <center>❌</center> |
| `tracker_error_tag`                 | Define the tag of any torrents that do not have a working tracker. (Used in `--tag-tracker-error`)                                                                                                                                                                                                                                              | issue                     | <center>❌</center> |
| `nohardlinks_tag`                   | Define the tag of any torrents that don't have hardlinks (Used in `--tag-nohardlinks`)                                                                                                                                                                                                                                                          | noHL                      | <center>❌</center> |
| `private_tag`                       | Define the tag of any torrents that are private.                                                                                                                                                                                                                                                                                                | None                      | <center>❌</center> |
| `share_limits_tag`                  | Will add this tag when applying share limits to provide an easy way to filter torrents by share limit group/priority for each torrent. For example, if you have a share-limit group `cross-seed` with a priority of 2 and the default share_limits_tag `~share_limits` would add the tag `~share_limit_2.cross-seed` (Used in `--share-limits`) | ~share_limit              | <center>❌</center> |
| `share_limits_min_seeding_time_tag` | Will add this tag when applying share limits to torrents that have not yet reached the minimum seeding time (Used in `--share-limits`)                                                                                                                                                                                                          | MinSeedTimeNotReached     | <center>❌</center> |
| `share_limits_min_num_seeds_tag`    | Will add this tag when applying share limits to torrents that have not yet reached the minimum number of seeds (Used in `--share-limits`)                                                                                                                                                                                                       | MinSeedsNotMet            | <center>❌</center> |
| `share_limits_last_active_tag`      | Will add this tag when applying share limits to torrents that have not yet reached the last active limit (Used in `--share-limits`)                                                                                                                                                                                                             | LastActiveLimitNotReached | <center>❌</center> |
| `cat_filter_completed`              | When running `--cat-update` function, it will filter for completed torrents only.                                                                                                                                                                                                                                                               | True                      | <center>❌</center> |
| `share_limits_filter_completed`     | When running `--share-limits` function, it will filter for completed torrents only.                                                                                                                                                                                                                                                             | True                      | <center>❌</center> |
| `tag_nohardlinks_filter_completed`  | When running `--tag-nohardlinks` function, , it will filter for completed torrents only.                                                                                                                                                                                                                                                        | True                      | <center>❌</center> |
| `cat_update_all`                    | When running `--cat-update` function, it will check and update all torrents categories, otherwise it will only update uncategorized torrents.                                                                                                                                                                                                   | True                      | <center>❌</center> |
| `disable_qbt_default_share_limits`  | When running `--share-limits` function, it allows QBM to handle share limits by disabling qBittorrents default Share limits.                                                                                                                                                                                                                    | True                      | <center>❌</center> |
| `tag_stalled_torrents`              | Tags any downloading torrents that are stalled with the user defined `stalledDL` tag when running the tag_update command                                                                                                                                                                                                                        | True                      | <center>❌</center> |
| `rem_unregistered_ignore_list`      | Ignores a list of words found in the status of the tracker when running rem_unregistered command and will not remove the torrent if matched                                                                                                                                                                                                     |                           | <center>❌</center> |
| `rem_unregistered_grace_minutes`    | Minimum age in minutes to protect newly added torrents from removal when a tracker reports unregistered. Set to 0 to disable.                                                                                                                                                                                                                   | 10                        | <center>❌</center> |
| `rem_unregistered_max_torrents`     | Maximum number of torrents to remove per tracker per run. Set to 0 to disable.                                                                                                                                                                                                                                                                  | 10                        | <center>❌</center> |

## **directory:**

---

This section defines the directories that qbit_manage will be looking into for various parts of the script.

| Variable       | Definition                                                                                                                                                                                                                                                                                                          | Required                                                      |
| :------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------ |
| `root_dir`     | Root downloads directory used to check for orphaned files, noHL, and remove unregistered. This directory is where you place all your downloads. This will need to be how qB views the directory where it places the downloads. This is required if you're using qbit_managee and/or qBittorrent within a container. | QBT_REM_ORPHANED / QBT_TAG_NOHARDLINKS / QBT_REM_UNREGISTERED |
| `remote_dir`   | Path of docker host mapping of root_dir, this must be set if you're running qbit_manage locally (not required if running qbit_manage in a container) and qBittorrent/cross_seed is in a docker. Essentially this is where your downloads are being kept on the host.                                                | <center>❌</center>                                           |
| `recycle_bin`  | Path of the RecycleBin folder. Default location is set to `remote_dir/.RecycleBin`. All files in this folder will be cleaned up based on your recycle bin settings.                                                                                                                                                 | <center>❌</center>                                           |
| `torrents_dir` | Path of the your qbittorrent torrents directory. Required for `save_torrents` attribute in recyclebin `/qbittorrent/data/BT_backup`.                                                                                                                                                                                | <center>❌</center>                                           |
| `orphaned_dir` | Path of the Orphaned Directory folder. Default location is set to `remote_dir/orphaned_data`. All files in this folder will be cleaned up based on your orphaned data settings. Only orphaned data shall exist in this path as all contents are considered disposable.                                              | <center>❌</center>                                           |

## **cat:**

---

This section defines the categories that you are currently using and the save path's that are associated with them.

The `cat` command will use the cats defined to Category function takes the save path of the torrent and assigns the category to it based on that save path

> [!WARNING] > **ALL save paths** of all torrents must be defined here. If the save path is in your qBit, then it **MUST** be defined here, if not the script will throw errors.
> If you want to leave a save_path as uncategorized you can use the key 'Uncategorized' as the name of the category.
> You may map a folder and its subdirectories to a single folder by appending `*` to the path e.g. `<path>/<to>/category/*`

| Configuration | Definition                | Required            |
| :------------ | :------------------------ | :------------------ |
| `key`         | Name of the category      | <center>✅</center> |
| `value`       | Save Path of the category | <center>✅</center> |

The syntax for all the categories are as follows

```yaml
category: <path>/<to>/category
```

## **cat_change:**

---

This moves all the torrents from one category to another category if the torrents are marked as complete.

> [!CAUTION]
> If the paths are different and Default Torrent Management Mode is set to Automatic the files could be moved !!!

| Configuration | Definition                    | Required            |
| :------------ | :---------------------------- | :------------------ |
| `key`         | Name of the original category | <center>✅</center> |
| `value`       | Name of the new category      | <center>✅</center> |

The syntax for the categories are as follows

```yaml
old_category_name: new_category_name
```

## **tracker:**

---

This section defines the tags used based upon the tracker's URL.

| Configuration | Definition                                                                                 | Required            |
| :------------ | :----------------------------------------------------------------------------------------- | :------------------ |
| `key`         | Tracker URL Keyword. You can define multiple tracker urls by splitting with `\|` delimiter | <center>✅</center> |

| Variable    | Definition                                                                                                          | Default Values | Required            |
| :---------- | :------------------------------------------------------------------------------------------------------------------ | :------------- | :------------------ |
| `tag`       | The tracker tag or additional list of tags defined                                                                  | Tracker URL    | <center>✅</center> |
| `cat`       | Set the category based on tracker URL. This category option takes priority over the category defined in [cat](#cat) | None           | <center>❌</center> |
| `notifiarr` | Set this to the notifiarr react name. This is used to add indexer reactions to the notifications sent by Notifiarr  | None           | <center>❌</center> |

If you are unsure what key word to use. Simply select a torrent within qB and down at the bottom you should see a tab that says `Trackers` within the list that is populated there are ea list of trackers that are associated with this torrent, select a keyword from there and add it to the config file. Make sure this keyword is unique enough that the script will not get confused with any other tracker.

> [!TIP]
> The `other` key is a special keyword and if defined will tag any other trackers that don't match the above trackers into this tag.

> [!NOTE]
> If `other` is not used then trackers will be auto added.

## **nohardlinks:**

---

Hardlinking data allows you to have your data in both the torrent directory and your media directory at the same time without using double the amount of data.

If you're needing information regarding hardlinks here are some excellent resources.

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/AMcHsQJ7My0/0.jpg)](https://www.youtube.com/watch?v=AMcHsQJ7My0)

- [Trash-Guides: Hardlinks and Instant Moves (Atomic-Moves)](https://trash-guides.info/Hardlinks/Hardlinks-and-Instant-Moves/)
- [Wikipedia: Hardlinks](https://en.wikipedia.org/wiki/Hard_link)

> [!NOTE]
> Mandatory to fill out [directory parameter](#directory) above to use this function (root_dir/remote_dir)
> Beyond this you'll need to use one of the [categories](#cat) above as the key.

This functionality will tag any torrent's whose file (or largest file if multi-file) does not have any hardlinks outside the qbm root_dir.
Note that `ignore_root_dir` (Default: True) will ignore any hardlinks detected in the same root_dir.

| Configuration | Definition                                                | Required            |
| :------------ | :-------------------------------------------------------- | :------------------ |
| `key`         | Category name to check for nohardlinked torrents in qbit. | <center>✅</center> |

| Variable          | Definition                                                                                                                                                                            | Default Values | Required            |
| :---------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------- | :------------------ |
| `exclude_tags`    | List of tags to exclude from the check. Torrents with any of these tags will not be processed. This is useful to exclude certain trackers from being scanned for hardlinking purposes | None           | <center>❌</center> |
| `ignore_root_dir` | Ignore any hardlinks detected in the same [root_dir](#directory)                                                                                                                      | True           | <center>❌</center> |

## **share_limits:**

Control how torrent share limits are set depending on the priority of your grouping. This can apply a max ratio, seed time limits to your torrents or limit your torrent upload speed as well. Each torrent will be matched with the share limit group with the highest priority that meets the group filter criteria. Each torrent can only be matched with one share limit group.

| Configuration | Definition                                                                                                    | Required            |
| :------------ | :------------------------------------------------------------------------------------------------------------ | :------------------ |
| `key`         | This variable is mandatory and is a text defining the name of your grouping. This can be any string you want. | <center>✅</center> |

| Variable                               | Definition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Default Values       | Type      | Required            |
| :------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------- | :-------- | :------------------ |
| `priority`                             | This is the priority of your grouping. The lower the number the higher the priority. This determines the order in which share limits are applied based on the filters set in this group                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | largest priority + 1 | int/float | <center>✅</center> |
| `include_all_tags`                     | Filter the group based on one or more tags. Multiple include_all_tags are checked with an **AND** condition. All tags defined here must be present in the torrent for it to be included in this group                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | None                 | list      | <center>❌</center> |
| `include_any_tags`                     | Filter the group based on one or more tags. Multiple include_any_tags are checked with an **OR** condition. Any tags defined here must be present in the torrent for it to be included in this group                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | None                 | list      | <center>❌</center> |
| `exclude_all_tags`                     | Filter the group based on one or more tags. Multiple exclude_all_tags are checked with an **AND** condition. All tags defined here must be present in the torrent for it to be excluded in this group                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | None                 | list      | <center>❌</center> |
| `exclude_any_tags`                     | Filter the group based on one or more tags. Multiple exclude_any_tags are checked with an **OR** condition. Any tags defined here must be present in the torrent for it to be excluded in this group                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | None                 | list      | <center>❌</center> |
| `categories`                           | Filter by including one or more categories. Multiple categories are checked with an **OR** condition. Since one torrent can only be associated with a single category, multiple categories are checked with an **OR** condition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | None                 | list      | <center>❌</center> |
| `min_torrent_size`                     | Only include torrents at least this size in the group. Accepts human‑readable sizes like `200MB`, `40GB`, `1024MiB`. Leave unset/blank to disable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | None                 | str       | <center>❌</center> |
| `max_torrent_size`                     | Only include torrents no larger than this size in the group. Accepts human‑readable sizes like `200MB`, `40GB`, `1024MiB`. Leave unset/blank to disable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | None                 | str       | <center>❌</center> |
| `cleanup`                              | **WARNING!!** Setting this as true will remove and delete contents of any torrents that satisfies the share limits **(max time OR max ratio)** It will also delete the torrent's data if and only if no other torrents are using the same folder/files.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | False                | bool      | <center>❌</center> |
| `max_ratio`                            | Will set the torrent Maximum share ratio until torrent is stopped from seeding/uploading and may be cleaned up / removed if the minimums have been met. (`-2` : Global Limit , `-1` : No Limit)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | -1                   | float     | <center>❌</center> |
| `max_seeding_time`                     | Will set the torrent Maximum seeding time until torrent is stopped from seeding/uploading and may be cleaned up / removed if the minimums have been met. (`-2` : Global Limit , `-1` : No Limit) (Max value of 1 year (525600 minutes)) See Some examples of [valid time expressions](https://github.com/onegreyonewhite/pytimeparse2?tab=readme-ov-file#pytimeparse2-time-expression-parser) 32m, 2h32m, 3d2h32m, 1w3d2h32m                                                                                                                                                                                                                                                                                                  | -1                   | str       | <center>❌</center> |
| `max_last_active`                      | Will delete the torrent if cleanup variable is set and if torrent has been inactive longer than x minutes. See Some examples of [valid time expressions](https://github.com/onegreyonewhite/pytimeparse2?tab=readme-ov-file#pytimeparse2-time-expression-parser) 32m, 2h32m, 3d2h32m, 1w3d2h32m                                                                                                                                                                                                                                                                                                                                                                                                                               | -1                   | str       | <center>❌</center> |
| `min_seeding_time`                     | Will prevent torrent deletion by the cleanup variable if the torrent has reached the `max_ratio` limit you have set. If the torrent has not yet reached this minimum seeding time, it will change the share limits back to no limits and resume the torrent to continue seeding. See Some examples of [valid time expressions](https://github.com/onegreyonewhite/pytimeparse2?tab=readme-ov-file#pytimeparse2-time-expression-parser) 32m, 2h32m, 3d2h32m, 1w3d2h32m. **MANDATORY: Must use also `max_ratio` with a value greater than `0` (default: `-1`) for this to work.** If you use both `min_seed_time` and `max_seed_time`, then you must set the value of `max_seed_time` to a number greater than `min_seed_time`. | 0                    | str       | <center>❌</center> |
| `min_last_active`                      | Will prevent torrent deletion by cleanup variable if torrent has been active within the last x minutes. If the torrent has been active within the last x minutes, it will change the share limits back to no limits and resume the torrent to continue seeding. See Some examples of [valid time expressions](https://github.com/onegreyonewhite/pytimeparse2?tab=readme-ov-file#pytimeparse2-time-expression-parser) 32m, 2h32m, 3d2h32m, 1w3d2h32m                                                                                                                                                                                                                                                                          | 0                    | str       | <center>❌</center> |
| `limit_upload_speed`                   | Will limit the upload speed KiB/s (KiloBytes/second) (`-1` : No Limit)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | -1                   | int       | <center>❌</center> |
| `upload_speed_on_limit_reached`        | When cleanup is `false` and a torrent reaches its share limits, throttle per‑torrent upload to this value (KiB/s). Use `-1` for unlimited. QBM will also clear the share limits to prevent qBittorrent from pausing, allowing continued seeding at the throttled rate.                                                                                                                                                                                                                                                                                                                                                                                                                                                        | -1                   | int       | <center>❌</center> |
| `enable_group_upload_speed`            | Upload speed limits are applied at the group level. This will take `limit_upload_speed` defined and divide it equally among the number of torrents in the group.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | False                | bool      | <center>❌</center> |
| `reset_upload_speed_on_unmet_minimums` | Controls whether upload speed limits are reset when minimum conditions are not met. When `true` (default), upload speed limits will be reset to unlimited if minimum seeding time, number of seeds, or last active time conditions are not satisfied. When `false`, existing upload speed limits will be preserved for bandwidth management purposes.                                                                                                                                                                                                                                                                                                                                                                         | True                 | bool      | <center>❌</center> |
| `resume_torrent_after_change`          | Will resume your torrent after changing share limits.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | True                 | bool      | <center>❌</center> |
| `add_group_to_tag`                     | This adds your grouping as a tag with a prefix defined in settings (share_limits_tag). Example: A grouping named noHL with a priority of 1 will have a tag set to `~share_limit_1.noHL` (if using the default prefix).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | True                 | bool      | <center>❌</center> |
| `min_num_seeds`                        | Will prevent torrent deletion by cleanup variable if the number of seeds is less than the value set here (depending on the tracker, you may or may not be included). If the torrent has less number of seeds than the min_num_seeds, the share limits will be changed back to no limits and resume the torrent to continue seeding.                                                                                                                                                                                                                                                                                                                                                                                           | 0                    | int       | <center>❌</center> |
| `custom_tag`                           | Apply a custom tag name for this particular group. **WARNING (This tag MUST be unique as it will be used to determine share limits. Please ensure it does not overlap with any other tags in qBittorrent)**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | None                 | str       | <center>❌</center> |

## **recyclebin:**

---

Recycle Bin method of deletion will move files into the recycle bin (Located in /root_dir/.RecycleBin) instead of directly deleting them in qbit.

This is very useful if you're hesitant about using this script to delete information off your system hingswithout first checking it. Plus with the ability of this script to remove trumped/unregistered torrents there is a very small chance that something may happen to cause the script to go to town on your library. With the recycling bin in place your data is secure (unless the bin is emptied before this issue is caught). All you'd need to do to recover would be to place the data back into the correct directory, redownload the torrent file from the tracker and recheck the torrent with the tracker from the UI.

| Variable             | Definition                                                                                                                                                                                 | Default Values | Required            |
| :------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------- | :------------------ |
| `enable`             | `true` or `false`                                                                                                                                                                          | `true`         | <center>✅</center> |
| `empty_after_x_days` | Will delete Recycle Bin contents if the files have been in the Recycle Bin for more than x days. (Uses date modified to track the time)                                                    | None           | <center>❌</center> |
| `save_torrents`      | This will save a copy of your .torrent and .fastresume file in the recycle bin before deleting it from qbittorrent. This requires the [torrents_dir](#directory) to be defined             | False          | <center>❌</center> |
| `split_by_category`  | This will split the recycle bin folder by the save path defined in the [cat](#cat) attribute and add the base folder name of the recycle bin that was defined in [recycle_bin](#directory) | False          | <center>❌</center> |

> [!TIP]
> Note: The more time you place for the `empty_after_x_days:` variable the better, allowing you more time to catch any mistakes by the script. If the variable is set to `0` it will delete contents immediately after every script run. If the variable is not set it will never delete the contents of the Recycle Bin.

## **orphaned:**

---

This section allows for the exclusion of certain files from being considered "Orphaned"

This is handy when you have automatically generated files that certain OSs decide to make. `.DS_Store` Is a primary example, for those who use MacOS.

| Variable                       | Definition                                                                                                                                                                                                                      | Default Values | Required            |
| :----------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------- | :------------------ |
| `empty_after_x_days`           | Will delete Orphaned data contents if the files have been in the Orphaned data for more than x days. (Uses date modified to track the time)                                                                                     | None           | <center>❌</center> |
| `exclude_patterns`             | List of [patterns](https://commandbox.ortusbooks.com/usage/parameters/globbing-patterns) to exclude certain files from orphaned                                                                                                 | None           | <center>❌</center> |
| `max_orphaned_files_to_delete` | This will help reduce the number of accidental large amount orphaned deletions in a single run. Set your desired threshold for the maximum number of orphaned files qbm will delete in a single run. (-1 to disable safeguards) | 50             | <center>❌</center> |
| `min_file_age_minutes`         | Minimum age in minutes for files to be considered orphaned. Files newer than this will be protected from deletion to prevent removal of actively uploading files. Set to 0 to disable age protection.                           | 0              | <center>❌</center> |

> [!TIP]
> The more time you place for the `empty_after_x_days:` variable the better, allowing you more time to catch any mistakes by the script. If the variable is set to `0` it will delete contents immediately after every script run. If the variable is not set it will never delete the contents of the Orphaned Data.

## **apprise:**

---

[Apprise](https://github.com/caronc/apprise) integration is used in conjunction with webhooks to allow notifications via apprise-api.

| Variable     | Definition                                                          | Default Values | Required            |
| :----------- | :------------------------------------------------------------------ | :------------- | :------------------ |
| `api_url`    | Apprise API Endpoint URL                                            | N/A            | <center>✅</center> |
| `notify_url` | [Notification Services URL](https://github.com/caronc/apprise/wiki) | N/A            | <center>✅</center> |

## **notifiarr:**

---

[Notifiarr](https://notifiarr.com/) integration is used in conjunction with webhooks to allow discord notifications via Notifiarr.

| Variable   | Definition                                                                                              | Default Values | Required            |
| :--------- | :------------------------------------------------------------------------------------------------------ | :------------- | :------------------ |
| `apikey`   | Notifiarr API Key                                                                                       | N/A            | <center>✅</center> |
| `instance` | Optional unique value used to identify your instance. (could be your username on notifiarr for example) | N/A            | <center>❌</center> |

## **webhooks:**

---

Provide webhook notifications based on event triggers

| Variable                                                        | Notification Sent                                                    | Default Values | Required            |
| :-------------------------------------------------------------- | :------------------------------------------------------------------- | :------------- | :------------------ |
| [error](#error-notifications)                                   | When errors occur during the run                                     | N/A            | <center>❌</center> |
| [run_start](#run-start-notifications)                           | At the beginning of every run                                        | N/A            | <center>❌</center> |
| [run_end](#run-end-notifications)                               | At the end of every run                                              | N/A            | <center>❌</center> |
| [recheck](#recheck-notifications)                               | During the recheck function                                          | N/A            | <center>❌</center> |
| [cat_update](#category-update-notifications)                    | During the category update function                                  | N/A            | <center>❌</center> |
| [tag_update](#tag-update-notifications)                         | During the tag update function                                       | N/A            | <center>❌</center> |
| [rem_unregistered](#remove-unregistered-torrents-notifications) | During the removing unregistered torrents function                   | N/A            | <center>❌</center> |
| [tag_tracker_error](#tag-tracker-error-notifications)           | During the removing unregistered torrents/tag tracker error function | N/A            | <center>❌</center> |
| [rem_orphaned](#remove-orphaned-files-notifications)            | During the removing orphaned function                                | N/A            | <center>❌</center> |
| [tag_nohardlinks](#tag-no-hardlinks-notifications)              | During the tag no hardlinks function                                 | N/A            | <center>❌</center> |
| [share_limits](#share-limits-notifications)                     | During the share limits function                                     | N/A            | <center>❌</center> |
| [cleanup_dirs](#cleanup-directories-notifications)              | When files are deleted from certain directories                      | N/A            | <center>❌</center> |

### **Error Notifications**

Payload will be sent on any errors

```yaml
{ "function": "run_error", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Error Message of the Payload
    "critical"
  : bool, ? // Critical Error
    "type"
  : str                  // severity of error }
```

### **Run Start Notifications**

Payload will be sent at the start of the run

```yaml
{ "function": "run_start", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "start_time"
  : str, ? // Time Run is started Format "YYYY-mm-dd HH:MM:SS"
    "dry_run"
  : bool, ? // Dry-Run
    "web_api_used"
  : bool, ? // Indicates whether the run was initiated via the Web API (true) or not (false).
    "commands"
  : list, ? // List of commands that that will be ran
    "execution_options"
  : list    // List of eecution options selected }
```

### **Run End Notifications**

Payload will be sent at the end of the run

```yaml
{
  "function": "run_end",                      // Webhook Trigger keyword
  "title": str,                               // Title of the Payload
  "body": str,                                // Message of the Payload
  "start_time": str,                          // Time Run started Format "YYYY-mm-dd HH:MM:SS"
  "end_time": str,                            // Time Run ended Format "YYYY-mm-dd HH:MM:SS"
  "next_run": str,                            // Time Next Run Format "YYYY-mm-dd HH:MM:SS"
  "run_time": str,                            // Total Run Time "H:MM:SS"
  "torrents_added": int,                      // Total Torrents Added
  "torrents_deleted": int,                    // Total Torrents Deleted
  "torrents_deleted_and_contents_count": int, // Total Torrents + Contents Deleted
  "torrents_resumed": int,                    // Total Torrents Resumed
  "torrents_rechecked": int,                  // Total Torrents Rechecked
  "torrents_categorized": int,                // Total Torrents Categorized
  "torrents_tagged": int,                     // Total Torrents Tagged
  "remove_unregistered": int,                 // Total Unregistered Torrents Removed
  "torrents_tagged_tracker_error": int,       // Total Tracker Error Torrents Tagged
  "torrents_untagged_tracker_error": int,     // Total Tracker Error Torrents untagged
  "orphaned_files_found": int,                // Total Orphaned Files Found
  "torrents_tagged_no_hardlinks": int,        // Total noHL Torrents Tagged
  "torrents_untagged_no_hardlinks": int,      // Total noHL Torrents untagged
  "torrents_updated_share_limits": int        // Total Share Limits updated
  "torrents_cleaned_share_limits": int        // Total Share Limit Torrents Cleaned (Deleted + Contents Deleted)
  "files_deleted_from_recyclebin": int,       // Total Files Deleted from Recycle Bin
  "files_deleted_from_orphaned": int          // Total Files Deleted from Orphaned Data
}
```

### **Recheck Notifications**

Payload will be sent when rechecking/resuming a torrent that is paused

```yaml
{ "function": "recheck", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_tag"
  : str, ? // Torrent Tags
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

### **Category Update Notifications**

Payload will be sent when updating torrents with missing category

```yaml
{ "function": "cat_update", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // New Torrent Category
    "torrent_tag"
  : str, ? // Torrent Tags
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

### **Tag Update Notifications**

Payload will be sent when updating torrents with missing tag

```yaml
{ "function": "tag_update", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_tag"
  : str, ? // New Torrent Tag
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

### **Remove Unregistered Torrents Notifications**

Payload will be sent when Unregistered Torrents are found

```yaml
{ "function": "rem_unregistered", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_status"
  : str, ? // Torrent Tracker Status message
    "torrent_tag"
  : str, ? // Torrent Tags
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, ? // Notifiarr React name/id for indexer
    "torrents_deleted_and_contents"
  : bool, // Deleted Torrents and contents or Deleted just the torrent }
```

### **Tag Tracker Error Notifications**

Payload will be sent when trackers with errors are tagged/untagged

```yaml
{ "function": "tag_tracker_error", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_tag"
  : "issue", ? // Tag Added
    "torrent_status"
  : str, ? // Torrent Tracker Status message
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

```yaml
{ "function": "untag_tracker_error", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_tag"
  : str, ? // Tag Added
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

### **Remove Orphaned Files Notifications**

Payload will be sent when Orphaned Files are found and moved into the orphaned folder

```yaml
{ "function": "rem_orphaned", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "orphaned_files"
  : list, ? // List of orphaned files
    "orphaned_directory"
  : str, ? // Folder path where orphaned files will be moved to
    "total_orphaned_files"
  : int, // Total number of orphaned files found }
```

### **Tag No Hardlinks Notifications**

Payload will be sent when no hard links are found for any files in a particular torrent

```yaml
{ "function": "tag_nohardlinks", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_tag"
  : "noHL", ? // Add `noHL` to Torrent Tags
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

Payload will be sent when hard links are found for any torrents that were previously tagged with `noHL`

```yaml
{ "function": "untag_nohardlinks", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "torrent_tag"
  : "noHL", ? // Remove `noHL` from Torrent Tags
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, // Notifiarr React name/id for indexer }
```

### **Share Limits Notifications**

Payload will be sent when Share Limits are updated for a specific group

```yaml
{ "function": "share_limits", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "grouping"
  : str, ? // Share Limit group name
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_tag"
  : str, ? // Torrent Tags
    "torrent_max_ratio"
  : float, ? // Set the Max Ratio Share Limit
    "torrent_max_seeding_time"
  : int, ? // Set the Max Seeding Time (minutes) Share Limit
    "torrent_min_seeding_time"
  : int, ? // Set the Min Seeding Time (minutes) Share Limit
    "torrent_limit_upload_speed"
  : int         // Set the the torrent upload speed limit (kB/s) }
```

Payload will be sent when `cleanup` flag is set to true and torrent meets share limit criteria.

```yaml
{ "function": "cleanup_share_limits", ? // Webhook Trigger keyword
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "grouping"
  : str, ? // Share Limit group name
    "torrents"
  : [str], ? // List of Torrent Names
    "torrent_category"
  : str, ? // Torrent Category
    "cleanup"
  : True, ? // Cleanup flag
    "torrent_tracker"
  : str, ? // Torrent Tracker URL
    "notifiarr_indexer"
  : str, ? // Notifiarr React name/id for indexer
    "torrents_deleted_and_contents"
  : bool, // Deleted Torrents and contents or Deleted just the torrent }
```

### **Cleanup directories Notifications**

Payload will be sent when files are deleted/cleaned up from the various folders

```yaml
{ "function": "cleanup_dirs", ? // Webhook Trigger keyword
    "location"
  : str, ? // Location of the folder that is being cleaned
    "title"
  : str, ? // Title of the Payload
    "body"
  : str, ? // Message of the Payload
    "files"
  : list, ? // List of files that were deleted from the location
    "empty_after_x_days"
  : int, ? // Number of days that the files will be kept in the location
    "size_in_bytes"
  : int, // Total number of bytes deleted from the location }
```
