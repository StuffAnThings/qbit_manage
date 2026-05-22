"""Unit tests for modules.util.redact_passkey.

Standalone: imports only modules.util (no qBittorrent client / config fixtures).

Test-passkey values are deterministic hashes of well-known plaintexts so the
fixtures match the SHAPE of real tracker passkeys (32-hex / 128-hex /
32-char base32) without being any actual private-tracker passkey:

    BHD-shape       = md5("testkey12345")          = 1190b6b1524e05197e1a678e7f365e8a
    Blutopia-shape  = md5("blutest12345")          = e4a393c3de26fc9af474c2566728e597
    HDBits-shape    = sha512("testkey12345")       = 067aae2a...485c99bb (128 hex)
    BTN-shape       = base32(sha1("btntest12345"), lowercase) = xhtbsxkgcwpoj62rh6st4i4ribozodwu

Anyone can verify with:
    python3 -c 'import hashlib; print(hashlib.md5(b"testkey12345").hexdigest())'
"""

from __future__ import annotations

from modules.util import redact_passkey

# Shape-realistic deterministic test fixtures (hashes of known plaintexts above).
BHD_PK = "1190b6b1524e05197e1a678e7f365e8a"
BLU_PK = "e4a393c3de26fc9af474c2566728e597"
HDB_PK = (
    "067aae2a64e0c7ce1f389c68908b1313bdbea0aed70b5e3b64db4a98b1782584"
    "8b90657b5c1430cd8f81ec87c1f64941534a65a94d4e5df4ea6cbc4d485c99bb"
)
BTN_PK = "xhtbsxkgcwpoj62rh6st4i4ribozodwu"

# ---- private-tracker shapes that MUST be redacted ----


def test_bhd_path_passkey_redacted():
    url = f"https://tracker.beyond-hd.me:2053/announce/{BHD_PK}"
    out = redact_passkey(url)
    assert BHD_PK not in out
    assert out == "https://tracker.beyond-hd.me:2053/announce[REDACTED]"


def test_blutopia_path_passkey_redacted():
    url = f"https://blutopia.cc/announce/{BLU_PK}"
    out = redact_passkey(url)
    assert BLU_PK not in out
    assert out == "https://blutopia.cc/announce[REDACTED]"


def test_hdbits_query_passkey_redacted():
    url = f"https://tracker.hdbits.org/announce.php?passkey={HDB_PK}"
    out = redact_passkey(url)
    assert HDB_PK not in out
    assert out == "https://tracker.hdbits.org/announce[REDACTED]"


def test_btn_path_prefix_passkey_redacted():
    url = f"http://landof.tv/{BTN_PK}/announce"
    out = redact_passkey(url)
    assert BTN_PK not in out
    assert out == "http://landof.tv/announce[REDACTED]"


def test_passkey_in_path_with_trailing_slash():
    url = f"https://example.org/announce/{BHD_PK}/"
    out = redact_passkey(url)
    assert BHD_PK not in out


# ---- shapes that MUST pass through ----


def test_dht_sentinel_unchanged():
    assert redact_passkey("** [DHT] **") == "** [DHT] **"


def test_pex_sentinel_unchanged():
    assert redact_passkey("** [PeX] **") == "** [PeX] **"


def test_lsd_sentinel_unchanged():
    assert redact_passkey("** [LSD] **") == "** [LSD] **"


def test_public_tracker_clean_announce_unchanged():
    url = "udp://tracker.openbittorrent.com:80/announce"
    assert redact_passkey(url) == url


def test_https_clean_announce_unchanged():
    url = "https://tracker.example/announce"
    assert redact_passkey(url) == url


def test_empty_string_unchanged():
    assert redact_passkey("") == ""


def test_none_unchanged():
    assert redact_passkey(None) is None


# ---- malformed inputs collapse to a benign placeholder ----


def test_relative_passkey_path_redacted():
    """qBit cross-seed corrupt entries can report `/announce/<pk>` with no scheme."""
    out = redact_passkey(f"/announce/{BHD_PK}")
    assert BHD_PK not in out


def test_headless_query_only_redacted():
    """Some corrupt entries are just `passkey=<pk>` with no scheme/path."""
    out = redact_passkey(f"passkey={BHD_PK}")
    assert BHD_PK not in out
