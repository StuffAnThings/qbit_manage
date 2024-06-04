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
