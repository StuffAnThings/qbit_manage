# Qbit-Manage Migration

> Last validated against qbit_manage v4.7.1.

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

---

### `upload_speed_on_limit_reached`

**What it does:** Throttles each torrent's upload speed (KiB/s) when its share limits are reached and `cleanup` is `false`, allowing the torrent to keep seeding at a reduced rate instead of being left at full speed indefinitely.

**Old behavior:** Before this key, torrents that hit their ratio/time limit with `cleanup: false` continued seeding at whatever upload speed was already set — there was no way to automatically reduce speed on limit-reached via config.

**Migration step:** Add to the relevant `share_limits` group under `share_limits/<group>`:

```yaml
share_limits:
  my_group:
    priority: 1
    max_ratio: 2.0
    cleanup: false
    upload_speed_on_limit_reached: 50   # throttle to 50 KiB/s once limit hit; 0 = disabled, -1 = unlimited
```

**When to use it:** When you want limit-reached torrents to keep seeding but at a reduced upload rate to free bandwidth for active downloads.

---

### `min_torrent_size` / `max_torrent_size`

**What they do:** Filter which torrents are eligible for a share-limits group based on total torrent size. Only torrents within the specified size range are processed by that group.

**Old behavior:** Before these keys, all torrents matching a group's tags/categories were processed regardless of size — there was no per-group size gate in the config.

**Migration step:** Add to any `share_limits` group where you want size-based filtering:

```yaml
share_limits:
  large_files:
    priority: 1
    include_any_tags:
      - linux-iso
    min_torrent_size: 1GB     # human-readable: MB, GB, TB
    max_torrent_size: 100GB
    max_ratio: 1.0
    cleanup: true
```

Both keys are optional and independent — set only the bound(s) you need. Omitting a key disables that bound.

**When to use it:** When different size tiers of torrents should have different seeding policies (e.g., large files get a lower ratio target).

---

### `reset_upload_speed_on_unmet_minimums`

**What it does:** When a torrent has not yet met its minimum seeding conditions (`min_seeding_time`, `min_num_seeds`, etc.), this key controls whether qbit_manage resets its upload speed limit to unlimited (`-1`) on each run.

**Old behavior:** Before this key, upload speed was always reset to unlimited while minimum conditions were unmet — there was no way to preserve a custom speed limit during the minimum seeding window.

**Migration step:** Add to any `share_limits` group where you use `limit_upload_speed` alongside minimum seeding conditions:

```yaml
share_limits:
  my_group:
    priority: 1
    min_seeding_time: 1440    # 24 hours minimum
    limit_upload_speed: 100   # KiB/s cap while seeding
    reset_upload_speed_on_unmet_minimums: false   # default: true
```

**When to use it:** Set to `false` when you want a hard upload-speed cap that applies even before the torrent has met its minimum seeding requirements.

---

### `rem_unregistered_grace_minutes`

**What it does:** Protects newly added torrents from being removed by `rem_unregistered` for the specified number of minutes after they were added to qBittorrent, preventing false-positive removal of torrents that haven't yet had a chance to register with their tracker.

**Old behavior:** Before this key, `rem_unregistered` could remove a torrent immediately after it was added if the tracker hadn't responded yet — there was no built-in grace period.

**Migration step:** Add to the `settings` block at the top level of your config:

```yaml
settings:
  rem_unregistered_grace_minutes: 30   # default: 10; set to 0 to disable grace period
```

**When to use it:** Increase from the default `10` if your trackers are slow to acknowledge new registrations, or if you frequently add torrents and see premature removals.

---

### `rem_unregistered_max_torrents`

**What it does:** Caps the maximum number of torrents removed per tracker per run when `rem_unregistered` is active, preventing a misconfigured tracker from causing mass-deletions in a single cycle.

**Old behavior:** Before this key, `rem_unregistered` could remove an unlimited number of torrents from a tracker in one run — a stuck or temporarily unreachable tracker could trigger large-scale accidental removal.

**Migration step:** Add to the `settings` block:

```yaml
settings:
  rem_unregistered_max_torrents: 5   # default: 10; set to 0 to disable the cap entirely
```

**When to use it:** Lower from the default `10` on large libraries where accidental mass-removal would be costly, or raise/disable it on small libraries where speed of cleanup matters more.

---

### Other Post-v4.0 Additions

- **`rem_unregistered_filter_completed`** (bool, default `false`) — restrict `rem_unregistered` to completed torrents only. Add to `settings:` block.
- **`stalled_tag`** (str, default `stalledDL`) — customizable tag name applied to stalled torrents when `tag_stalled_torrents: true`. Add to `settings:` block.
- **Web API & Web UI** — a full REST API and web interface are now available. See [Web API](Web-API.md) and [Web UI](Web-UI.md).
