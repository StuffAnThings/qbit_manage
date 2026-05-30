# Test fixtures

The JSON files under `qbit_api/` describe responses from the
[qBittorrent Web API v2](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)).
The schema (field names and types) is identical to what a live qBittorrent
returns from the following endpoints:

| File                    | Endpoint                                              |
| ----------------------- | ----------------------------------------------------- |
| `torrents_info.json`    | `GET /api/v2/torrents/info`                           |
| `app_preferences.json`  | `GET /api/v2/app/preferences` (selected keys only)    |
| `torrent_tags.json`     | `GET /api/v2/torrents/tags`                           |
| `torrent_trackers.json` | `GET /api/v2/torrents/trackers?hash=<hash>`           |

The committed files contain **synthetic but schema-correct** data — names,
tracker hosts and save paths are sanitized placeholders. The factory code in
`tests/factories.py` builds `FakeTorrent` objects from these rows.

## Refreshing fixtures from a real qBittorrent

If you'd like to replace the synthetic data with a capture from your own
qBittorrent instance:

```bash
python scripts/capture_qbit_fixtures.py \
    --host http://localhost:8080 \
    --user admin \
    --password adminadmin \
    --output tests/fixtures/qbit_api
```

The script sanitizes hostnames, save paths and torrent names before writing
the files. Re-running it is idempotent for identical input.

## Why fakes instead of `unittest.mock.Mock`?

`Mock`s let any attribute access succeed silently — a regression that adds a
new `torrent.some_field` call wouldn't fail the tests, it would just return a
`Mock`. The explicit `FakeTorrent` here has a defined attribute surface (mirroring
the real `qbittorrentapi.TorrentDictionary`), so unexpected field reads raise
`AttributeError` and the tests catch the API drift.
