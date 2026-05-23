#!/usr/bin/env python3
"""Re-sanitize an existing tests/fixtures/qbit_api/torrents_info.json file.

Use this when a fixture was captured by an older version of
``capture_qbit_fixtures.py`` that left a leaky field (e.g. ``root_path``
once contained real release names while ``name`` / ``content_path`` were
already scrubbed). Reuses the sanitization helpers from
``capture_qbit_fixtures.py`` so the behavior matches a fresh capture.

Usage:
    python scripts/sanitize_qbit_fixture.py [PATH]

PATH defaults to ``tests/fixtures/qbit_api/torrents_info.json``. The file is
rewritten in place. The script refuses to write if the result still looks
like it contains a tracker passkey (uses the same secret-shape audit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from capture_qbit_fixtures import _assert_clean
from capture_qbit_fixtures import _build_tracker_map
from capture_qbit_fixtures import _sanitize_root_path
from capture_qbit_fixtures import _sanitize_tracker_url


def _sanitize_in_place(rows: list[dict]) -> list[dict]:
    """Apply the subset of capture-side sanitization that is safe to re-run
    on an already-captured fixture (idempotent for already-clean rows)."""
    tracker_map = _build_tracker_map(rows)
    out = []
    for row in rows:
        row = dict(row)
        if row.get("root_path"):
            row["root_path"] = _sanitize_root_path(row["root_path"])
        if row.get("tracker"):
            row["tracker"] = _sanitize_tracker_url(row["tracker"], tracker_map)
        if "magnet_uri" in row and row["magnet_uri"]:
            row["magnet_uri"] = ""
        if "comment" in row and row["comment"]:
            row["comment"] = ""
        out.append(row)
    return out


def main() -> int:
    default_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "qbit_api" / "torrents_info.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=default_path,
        help="Fixture file to scrub in place (default: tests/fixtures/qbit_api/torrents_info.json)",
    )
    args = parser.parse_args()

    if not args.path.exists():
        sys.stderr.write(f"File not found: {args.path}\n")
        return 1

    rows = json.loads(args.path.read_text())
    if not isinstance(rows, list):
        sys.stderr.write(f"Expected a JSON list at {args.path}, got {type(rows).__name__}\n")
        return 2

    scrubbed = _sanitize_in_place(rows)
    args.path.write_text(json.dumps(scrubbed, indent=2, sort_keys=True) + "\n")
    print(f"Rewrote {args.path} ({len(scrubbed)} rows)")

    _assert_clean(args.path)
    print("Fixture passes secret-shape audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
