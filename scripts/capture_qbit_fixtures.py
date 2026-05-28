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

# Match a torrent basename and split it into <title>.<rest> where <rest> begins
# at the first scene-naming marker (season, year, resolution, source, codec…).
# We keep <rest> intact (preserves format/group info for realistic tests) and
# replace <title> with a generic placeholder.
_TITLE_MARKER_PATTERN = re.compile(
    r"^(?P<title>[A-Za-z0-9._-]+?)"
    r"(?P<rest>"
    r"\.(?:S\d{1,4}(?:E\d{1,4})?|\d{4}|\d{3,4}[pi]|"
    r"TVRip|BRRip|WEBRip|HDTV|BluRay|WEB[.-]?DL|"
    r"REPACK|PROPER|INTERNAL|DV|HDR|HEVC|AVC|x26[45]|h26[45])"
    r".*"
    r")$",
    re.IGNORECASE,
)


def _sanitize_torrent_basename(basename: str) -> str:
    """Replace the title slug of a torrent path basename with a generic
    placeholder while keeping scene markers (season, quality, codec) and the
    trailing release group. Examples:

        Looney.Tunes.S1942.TVRip-NOGRP  ->  Tv.Series.S1942.TVRip-NOGRP
        Some.Movie.2024.1080p.WEB-DL-X  ->  Tv.Series.2024.1080p.WEB-DL-X

    Returns the input unchanged if no scene marker is detected (likely already
    sanitized or non-release-named directory).
    """
    m = _TITLE_MARKER_PATTERN.match(basename)
    if not m:
        return basename
    return f"Tv.Series{m.group('rest')}"


def _sanitize_root_path(root_path: str) -> str:
    """Sanitize the LAST path segment of root_path with _sanitize_torrent_basename.
    Earlier segments (category dir, tracker subdir) are preserved since they
    convey structure and don't leak title PII."""
    if not root_path:
        return root_path
    # Detect both POSIX `/` and Windows `\\` separators; fixtures captured
    # on Windows would otherwise bypass sanitization (Copilot review #1207).
    if "/" in root_path:
        sep = "/"
    elif "\\" in root_path:
        sep = "\\"
    else:
        return root_path
    prefix, _, basename = root_path.rpartition(sep)
    return f"{prefix}{sep}{_sanitize_torrent_basename(basename)}"


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
    """Strip everything after the sanitized host. Path, query, and headless
    fragments all leak passkeys (BHD format: /announce/<pk>; HDBits:
    ?passkey=<pk>; BTN: /<pk>/announce; cross-seed corrupt entries store
    just the path or query alone). Anything that isn't a clean ``[DHT]``-
    style sentinel collapses to ``<scheme>://<sanitized-host>/announce`` or
    ``/announce`` so zero secret material survives."""
    if not url:
        return url
    if url.startswith("**"):  # [DHT]/[PeX]/[LSD]
        return url
    # Headless / corrupt shapes seen in cross-seed entries:
    # "/announce/<pk>", "/<pk>/announce", "passkey=<pk>", "passkey%3D<pk>"
    if url.startswith("/") or url.startswith(("passkey=", "passkey%3D")):
        return "/announce"
    if not url.startswith(("http", "udp", "ws")):
        # Unknown shape — collapse to a benign placeholder
        return "/announce"
    parsed = urlparse(url)
    host = tracker_map.get(parsed.netloc, "tracker.example")
    return f"{parsed.scheme}://{host}/announce"


def _sanitize_tags(tags: list[str]) -> list[str]:
    """Drop tag names that look like they embed secrets (e.g. ``passkey=<pk>``
    tags added by autobrr/qBit filters). Length-32-or-128 hex strings, base32
    passkeys, and ``passkey=`` prefixes all qualify."""
    out = []
    for tag in tags:
        if any(p.search(tag) for p in _SECRET_PATTERNS):
            continue
        out.append(tag)
    return out


def _sanitize_torrents_info(rows: list[dict], sample_size: int = 5) -> list[dict]:
    """Truncate to a representative sample and scrub identifying fields."""
    tracker_map = _build_tracker_map(rows)
    sanitized: list[dict] = []
    for idx, row in enumerate(rows[:sample_size]):
        row = dict(row)
        row["name"] = f"Torrent.NAME.{idx + 1}"
        category = row.get("category") or "uncategorized"
        row["save_path"] = f"/data/torrents/{category}/"
        row["content_path"] = f"/data/torrents/{category}/Torrent.NAME.{idx + 1}"
        # download_path can leak indexer setup ("/mnt/.../Blutopia (API)") — scrub
        if "download_path" in row and row["download_path"]:
            row["download_path"] = f"/data/torrents/{category}/"
        # root_path's last segment is the original release name and leaks the
        # title even though save_path / content_path / name are sanitized above.
        if row.get("root_path"):
            row["root_path"] = _sanitize_root_path(row["root_path"])
        if "tracker" in row:
            row["tracker"] = _sanitize_tracker_url(row["tracker"], tracker_map)
        # magnet_uri's tr= parameter is the full announce URL with passkey —
        # blank it; tests don't need a real magnet
        if "magnet_uri" in row and row["magnet_uri"]:
            row["magnet_uri"] = ""
        # comment leaks tracker membership via site detail URL — blank it
        if "comment" in row and row["comment"]:
            row["comment"] = ""
        # infohash_v1/v2 are public but pair to real torrents — replace
        for k in ("infohash_v1", "infohash_v2"):
            if row.get(k):
                row[k] = f"{idx + 1:040x}"
        # Hash is structural — replace with deterministic placeholder
        row["hash"] = f"{idx + 1:040x}"
        # tags field is a comma-separated string — strip any secret-shaped entries
        if row.get("tags"):
            kept = [t.strip() for t in row["tags"].split(",") if t.strip() and not any(p.search(t) for p in _SECRET_PATTERNS)]
            row["tags"] = ", ".join(kept)
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


# Secret-shape patterns to refuse to write. 32-hex and 128-hex catch BHD,
# Blutopia, HDBits passkey formats; 32-char base32 (lowercase a-z + 2-7) catches
# BTN-style. Tracker placeholder hostnames (tracker1.example) and the
# 40-hex torrent infohash placeholders are explicitly allowed.
_SECRET_PATTERNS = [
    re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])"),
    re.compile(r"(?<![0-9a-f])[0-9a-f]{128}(?![0-9a-f])"),
    re.compile(r"(?<![a-z0-9])[a-z2-7]{32}(?![a-z2-7])"),
    re.compile(r"passkey=", re.IGNORECASE),
    re.compile(r"/announce/[A-Za-z0-9]{8,}"),  # path-based passkey
]


def _assert_clean(path: Path) -> None:
    """Refuse to leave a fixture file on disk if it looks like it still
    contains a tracker passkey. Hard-fails the script."""
    content = path.read_text()
    # Allow the 40-hex torrent infohash placeholders we wrote on purpose
    # (hash, infohash_v1, infohash_v2 — all 40 hex per BitTorrent spec).
    stripped = re.sub(r'"(?:hash|infohash_v1|infohash_v2)":\s*"[0-9a-f]{40}"', "", content)
    for pat in _SECRET_PATTERNS:
        m = pat.search(stripped)
        if m:
            sys.stderr.write(
                f"REFUSING TO WRITE {path}: matches secret-shape pattern {pat.pattern!r} at offset {m.start()}: {m.group()!r}\n"
            )
            path.unlink()
            sys.exit(2)


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

    # ---- torrent_tags (drops any tag that embeds a secret-shaped string) ----
    _dump(out_dir / "torrent_tags.json", _sanitize_tags(list(client.torrent_tags.tags)))

    # ---- one torrent's trackers ----
    first_hash = raw_rows[0]["hash"]
    trackers = [dict(t) for t in client.torrents_trackers(torrent_hash=first_hash)]
    _dump(out_dir / "torrent_trackers.json", _sanitize_trackers(trackers, tracker_map))

    # ---- secret-shape audit (refuses to leave passkey-like content on disk) ----
    for fname in ("torrents_info.json", "app_preferences.json", "torrent_tags.json", "torrent_trackers.json"):
        _assert_clean(out_dir / fname)
    print("All fixtures pass secret-shape audit.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
