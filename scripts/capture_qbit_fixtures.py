#!/usr/bin/env python3
"""Capture real qBittorrent Web API responses into tests/fixtures/qbit_api/.

Run this against a live qBittorrent that has some torrents in it to (re)build
the schema-correct JSON fixtures that the test suite uses. The script
sanitizes hostnames, save paths and torrent names before writing the files.

Usage:
    python scripts/capture_qbit_fixtures.py \
        --host http://localhost:8080 \
        --user admin \
        --password adminadmin

By default it writes to ``tests/fixtures/qbit_api/`` relative to the repo root.
Pass ``--output <dir>`` to override.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from qbittorrentapi import Client
except ImportError:
    sys.stderr.write("qbittorrent-api is not installed. Run: pip install qbittorrent-api\n")
    sys.exit(1)


_TRACKER_HOST_PATTERN = re.compile(r"://[^/]+")


def _build_tracker_map(rows: list[dict]) -> dict[str, str]:
    """Collect every distinct tracker host across all torrents and assign each
    a sanitized placeholder like ``tracker1.example``."""
    hosts: list[str] = []
    for row in rows:
        tracker = row.get("tracker") or ""
        if not tracker:
            continue
        parsed = urlparse(tracker)
        host = parsed.netloc
        if host and host not in hosts:
            hosts.append(host)
    return {host: f"tracker{i + 1}.example" for i, host in enumerate(hosts)}


def _sanitize_tracker_url(url: str, tracker_map: dict[str, str]) -> str:
    if not url or not url.startswith(("http", "udp", "ws")):
        return url  # leave [DHT]/[PeX]/[LSD] sentinels alone
    parsed = urlparse(url)
    if parsed.netloc in tracker_map:
        return url.replace(parsed.netloc, tracker_map[parsed.netloc])
    return url


def _sanitize_torrents_info(rows: list[dict], sample_size: int = 5) -> list[dict]:
    """Truncate to a representative sample and scrub identifying fields."""
    tracker_map = _build_tracker_map(rows)
    sanitized: list[dict] = []
    for idx, row in enumerate(rows[:sample_size]):
        row = dict(row)
        row["name"] = f"Torrent.NAME.{idx + 1}"
        # Replace save_path and content_path with a stable placeholder
        category = row.get("category") or "uncategorized"
        row["save_path"] = f"/data/torrents/{category}/"
        row["content_path"] = f"/data/torrents/{category}/Torrent.NAME.{idx + 1}"
        if "tracker" in row:
            row["tracker"] = _sanitize_tracker_url(row["tracker"], tracker_map)
        # Hash is structural — replace with deterministic placeholder
        row["hash"] = f"{idx + 1:040x}"
        sanitized.append(row)
    return sanitized


def _sanitize_trackers(trackers: list[dict], tracker_map: dict[str, str]) -> list[dict]:
    out = []
    for tracker in trackers:
        tracker = dict(tracker)
        if "url" in tracker:
            tracker["url"] = _sanitize_tracker_url(tracker["url"], tracker_map)
        out.append(tracker)
    return out


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"Wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="qBittorrent WebUI URL (e.g. http://localhost:8080)")
    parser.add_argument("--user", required=True, help="WebUI username")
    parser.add_argument("--password", required=True, help="WebUI password")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "qbit_api"),
        help="Output directory (default: tests/fixtures/qbit_api)",
    )
    parser.add_argument("--sample-size", type=int, default=5, help="Max torrents to include (default: 5)")
    args = parser.parse_args()

    out_dir = Path(args.output)

    client = Client(host=args.host, username=args.user, password=args.password, VERIFY_WEBUI_CERTIFICATE=False)
    client.auth_log_in()

    # ---- torrents/info ----
    raw_rows = [dict(t) for t in client.torrents.info()]
    if not raw_rows:
        sys.stderr.write("No torrents found in qBittorrent — cannot capture fixtures.\n")
        return 1
    tracker_map = _build_tracker_map(raw_rows)
    _dump(out_dir / "torrents_info.json", _sanitize_torrents_info(raw_rows, args.sample_size))

    # ---- app/preferences (selected keys) ----
    prefs = client.app.preferences
    _dump(
        out_dir / "app_preferences.json",
        {
            "max_ratio_enabled": prefs["max_ratio_enabled"],
            "max_ratio": prefs["max_ratio"],
            "max_seeding_time_enabled": prefs["max_seeding_time_enabled"],
            "max_seeding_time": prefs["max_seeding_time"],
        },
    )

    # ---- torrent_tags ----
    _dump(out_dir / "torrent_tags.json", list(client.torrent_tags.tags))

    # ---- one torrent's trackers ----
    first_hash = raw_rows[0]["hash"]
    trackers = [dict(t) for t in client.torrents_trackers(torrent_hash=first_hash)]
    _dump(out_dir / "torrent_trackers.json", _sanitize_trackers(trackers, tracker_map))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
