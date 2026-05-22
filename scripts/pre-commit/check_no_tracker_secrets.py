#!/usr/bin/env python3
"""Pre-commit guard: refuse staged content that looks like a tracker passkey.

Matches the patterns the fixture sanitizer enforces, so the same shapes
that capture_qbit_fixtures.py's _assert_clean() rejects are also blocked
at commit time. This is a defense-in-depth check; the fixture script is
the primary line of defense for fixture files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Same patterns enforced by scripts/capture_qbit_fixtures.py._assert_clean
PATTERNS = [
    re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])"),
    re.compile(r"(?<![0-9a-f])[0-9a-f]{128}(?![0-9a-f])"),
    re.compile(r"(?<![a-z0-9])[a-z2-7]{32}(?![a-z2-7])"),
    re.compile(r"passkey=[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(r"/announce/[A-Za-z0-9]{8,}"),
]

# Allow these explicitly-structured 32/40-char placeholders (test fixtures).
ALLOWLIST_LINE_PATTERNS = [
    # Deterministic infohash placeholders ("0000...0001" through "...0099")
    re.compile(r'"(?:hash|infohash_v1|infohash_v2)":\s*"[0-9a-f]{40}"'),
    # MD5("0") and a few other well-known sentinel hashes that appear in
    # bencoded cross_seed_entry markers
    re.compile(r"cfcd208495d565ef66e7dff9f98764da"),
]

# File globs that are inherently allowed to contain hex hashes / passkey-like
# strings (no real secrets here — synthetic fixtures or pattern definitions).
ALLOWLISTED_PATHS = [
    re.compile(r"^scripts/pre-commit/check_no_tracker_secrets\.py$"),
    re.compile(r"^scripts/capture_qbit_fixtures\.py$"),
    # Unit tests for redact_passkey() necessarily contain synthetic passkey-
    # shaped inputs (32-hex, 32-char base32) as positive test cases.
    re.compile(r"^tests/test_redact_passkey\.py$"),
]


def is_allowlisted_path(path: str) -> bool:
    return any(p.match(path) for p in ALLOWLISTED_PATHS)


def line_is_allowed(line: str) -> bool:
    return any(p.search(line) for p in ALLOWLIST_LINE_PATTERNS)


def check(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_number, pattern, matched_text) tuples."""
    hits: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return hits
    for n, line in enumerate(text.splitlines(), start=1):
        if line_is_allowed(line):
            continue
        for pat in PATTERNS:
            m = pat.search(line)
            if m:
                hits.append((n, pat.pattern, m.group()))
                break
    return hits


def main(argv: list[str]) -> int:
    if not argv:
        return 0
    exit_code = 0
    for arg in argv:
        path = Path(arg)
        if not path.is_file() or is_allowlisted_path(arg):
            continue
        for line_no, pattern, matched in check(path):
            sys.stderr.write(f"{arg}:{line_no}: matches tracker-secret pattern {pattern!r}: {matched[:40]}...\n")
            exit_code = 1
    if exit_code:
        sys.stderr.write(
            "\nRefusing commit: staged content matches a tracker-passkey "
            "shape (32-hex / 128-hex / 32-char base32 / passkey= / "
            "/announce/<token>). If this is a false positive, add the path "
            "to ALLOWLISTED_PATHS in scripts/pre-commit/check_no_tracker_secrets.py.\n"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
