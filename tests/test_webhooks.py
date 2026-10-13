from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.webhooks import Webhooks

STATS = dict.fromkeys(
    [
        "added",
        "deleted",
        "deleted_contents",
        "resumed",
        "rechecked",
        "categorized",
        "tagged",
        "rem_unreg",
        "tagged_tracker_error",
        "untagged_tracker_error",
        "orphaned",
        "tagged_noHL",
        "untagged_noHL",
        "updated_share_limits",
        "cleaned_share_limits",
        "recycle_emptied",
        "orphaned_emptied",
    ],
    0,
)


def _make(dry_run=False):
    config = SimpleNamespace(args={}, commands={"dry_run": dry_run})
    hooks = Webhooks(config, {"run_start": ["https://x"], "run_end": ["https://x"]})
    hooks._request = MagicMock()
    return hooks


def test_run_start_title_is_not_null():
    hooks = _make()
    hooks.start_time_hooks(datetime.now())
    payload = hooks._request.call_args[0][1]
    assert isinstance(payload["title"], str) and payload["title"]


def test_run_start_dry_run_title():
    hooks = _make(dry_run=True)
    hooks.start_time_hooks(datetime.now())
    assert "Dry-" in hooks._request.call_args[0][1]["title"]


def test_run_end_title_is_not_null():
    hooks = _make()
    now = datetime.now()
    hooks.end_time_hooks(now, now, "0:00:01", None, STATS, "done")
    payload = hooks._request.call_args[0][1]
    assert isinstance(payload["title"], str) and payload["title"]
