"""Test ShareLimits.delete_share_limits_suffix_tag — migration helper that
cleans up the legacy <group>.share_limit tag format from qbit_manage v4.0.0.
"""

from __future__ import annotations


def test_suffix_tags_deleted(share_limits_factory):
    sl = share_limits_factory()
    sl.client.torrent_tags._tags = [
        "noHL",
        "RadarrComplete.share_limit",
        "manual.share_limit",
        "~share_limit_1.noHL",
        "cross-seed",
    ]
    sl.delete_share_limits_suffix_tag()

    deleted = [call[1] for call in sl.client.torrent_tags.calls if call[0] == "delete_tags"]
    assert "RadarrComplete.share_limit" in deleted
    assert "manual.share_limit" in deleted
    # Non-legacy tags untouched
    assert "noHL" not in deleted
    assert "~share_limit_1.noHL" not in deleted


def test_no_legacy_tags_no_calls(share_limits_factory):
    sl = share_limits_factory()
    sl.client.torrent_tags._tags = ["noHL", "cross-seed", "~share_limit_1.noHL"]
    sl.delete_share_limits_suffix_tag()
    assert sl.client.torrent_tags.calls == []
