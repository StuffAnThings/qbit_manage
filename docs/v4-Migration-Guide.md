# Qbit-Manage Migration

Currently the qbit-manage (qbm) config file manages torrents in two ways: via tracker and via hardlinks. The section of the config where you specify your trackers is also where you can specify share limits (duration and ratio) on a per-tracker basis. The section of the config where you address no hardlinks (noHL) is where you specify share limits for files that are not hardlinked.

Starting with develop version 4.0.0 torrents are no longer configured solely by tracker or noHL status. You now create groups of torrents based on tags and you can set specific share limits for each group. This means max_seeding_time, min_seeding_time and max_ratio are no longer used in the tracker or noHL section of the config, they are used for each group of torrents.

## Old config

```yml
cat:
  movies: “/data/torrents/movies”
  tv: “/data/torrents/tv”
tracker:
  Tracker-a:
    tag: a
    max_seeding_time: 100
    max_ratio: 5
  Tracker-b:
    tag: b
    max_seeding_time: 100
    max_ratio: 5
  Tracker-c:
    tag: c
    max_seeding_time: 50
    max_ratio: 3
nohardlinks:
  movies:
    cleanup: true
    max_seeding_time: 75
    max_ratio: 2
  tv:
    cleanup: true
    max_seeding_time: 25
    max_ratio: 1
```

### New config

```yml
cat:
  movies: “/data/torrents/movies”
  tv: “/data/torrents/tv”
tracker:
  Tracker-a:
    tag: a
  Tracker-b:
    tag: b
    Tracker-c:
    tag: c
nohardlinks:
- movies
- tv
share_limits:
  group1.noHL:
    priority: 1
    include_any_tags:
    - a
    - b
    include_all_tags:
    - noHL
    categories:
    - movies
    max_ratio: 2
    max_seeding_time: 75
    cleanup: true
  group1:
    priority: 2
    include_any_tags:
    - a
    - b
    categories:
    - movies
    max_ratio: 5
    max_seeding_time: 100
  group2.noHL:
    priority: 3
    include_any_tags:
    - c
    include_all_tags:
    - noHL
    categories:
    - tv
    max_ratio: 1
    max_seeding_time: 25
  group2:
    priority: 4
    include_any_tags:
    - c
    categories:
    - tv
    max_ratio:
    max_seeding_time:
```

The new config will operate as follows:
Torrents from tracker a and tracker b that are tagged as noHL and in the movie category will have a share limit of 75 minutes and a ratio of 2. These same torrents, when not tagged as noHL, will then have a share limit of 100 minutes and a ratio of 5.

Torrents from tracker c that are tagged as noHL and in the tv category will have a share limit of 50 minutes and a ratio of 3. These same torrents, when not tagged as noHL, will have no share limit applied and will seed indefinitely.

There is now much greater flexibility to apply different share limits to torrents based on how you group them and which tags and categories are assigned to each group. When assigning priority it is best to determine what limits/restrictions you want based on your preferences and assign the more restrictive limits as higher priority groups since share limits will not transfer when a torrent is moved from one group to another. In the examples above, the settings are more restrictive for noHL torrents so those are listed as higher priority within the group.

## Post-v4.0 Notable Additions

The following settings were added after the v4.0 release. No migration is required — they are all optional with safe defaults. See [Config-Setup](Config-Setup.md) for full details.

- **`upload_speed_on_limit_reached`** (int, default `0`) — throttle per-torrent upload speed (KiB/s) when share limits are reached and `cleanup` is `false`. `0` = disabled, `-1` = unlimited.
- **`min_torrent_size`** / **`max_torrent_size`** (str) — filter torrents included in a share-limits group by size (e.g. `200MB`, `40GB`). Leave unset to disable.
- **`reset_upload_speed_on_unmet_minimums`** (bool, default `true`) — when minimum seeding conditions are not yet met, reset upload speed limits to unlimited. Set to `false` to preserve existing limits.
- **`rem_unregistered_grace_minutes`** (int, default `10`) — protect newly added torrents from `rem_unregistered` removal for this many minutes after they are added.
- **`rem_unregistered_max_torrents`** (int, default `10`) — maximum number of torrents to remove per tracker per run when using `rem_unregistered`. Set to `0` to disable the cap.
- **`rem_unregistered_filter_completed`** (bool, default `false`) — restrict `rem_unregistered` to completed torrents only.
- **`stalled_tag`** (str, default `stalledDL`) — customizable tag name applied to stalled torrents when `tag_stalled_torrents: true`.
- **Web API & Web UI** — a full REST API and web interface are now available. See [Web API](Web-API.md) and [Web UI](Web-UI.md).
