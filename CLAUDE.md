# qBit Manage — Claude Code Project Instructions

**qBit Manage** is a Python automation tool for qBittorrent. It handles
tagging, share-limit enforcement, category changes, hardlink-aware no-HL
detection, orphan/unregistered removal, and exposes both a web UI and a REST
API. Standalone helper scripts live in `scripts/`.

---

## Branch Model

| Branch | Purpose |
|--------|---------|
| `develop` | Active development — all PRs target this branch |
| `master` | Stable releases only — never PR directly to master |

**Always branch from `develop`. Never open a PR to `master`** (except hotfixes
with `hotfix/` prefix and explicit maintainer approval — see `DEVELOPER.md`).

---

## Dev Environment

```bash
# Recommended: uv (faster)
make venv            # creates .venv, installs project + dev deps
source .venv/bin/activate
make install-hooks   # installs pre-commit hooks

# Alternative: pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Key targets:

```bash
make lint        # ruff check --fix
make format      # ruff format
make test        # pytest tests/
make pre-commit  # run all hooks on all files
```

---

## Test Commands

```bash
pytest tests/              # full suite (~168 tests, once PR #1198 merges)
pytest tests/ --no-cov     # quick run, skip coverage
pytest tests/test_foo.py   # single file
```

Tests use `tests/factories.py` bypass-constructors — never instantiate core
classes directly in tests. Key factories: `make_share_limits()`,
`make_category()`, `make_tag_nohardlinks()`.

---

## File Layout

```
qbit_manage.py           # CLI entry point; all argparse definitions here
modules/
  config.py              # Config loading; all valid keys defined via check_for_attribute()
  qbittorrent.py         # qBittorrent API wrapper
  util.py                # Shared helpers (logging, formatting, file utils)
  webhooks.py            # Notification webhook support
  web_api.py             # FastAPI REST server
  web_ui.py              # Web UI static server
  core/
    tags.py              # Torrent tagging logic
    share_limits.py      # Upload ratio / seeding time enforcement
    category.py          # Category assignment automation
    tag_nohardlinks.py   # Hardlink-aware no-HL tagging
    recheck.py           # Force-recheck stalled torrents
    remove_orphaned.py   # Remove torrents without matching files
    remove_unregistered.py  # Remove torrents flagged by tracker as unregistered
scripts/
  pre-commit/
    increase_version.sh        # Auto-bumps developN counter on commit
    update_develop_version.sh  # Called by increase_version.sh
tests/
  factories.py           # Bypass-constructors for unit tests
docs/                    # Wiki source (synced to GitHub Wiki via docs.yml)
```

To find which config keys are valid, search `config.py` for
`check_for_attribute` calls — each call registers a valid key with its type,
default, and whether it is required.

---

## Conventional Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <description>
```

Types in use: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ci`, `perf`.

PR titles must also follow the same format — CI uses the title to categorize
the commit in auto-generated release notes.

---

## Code Style

- **Ruff** for lint + format; config in `ruff.toml` (line-length=130).
- Single-line imports (isort rules enforced).
- Run `make pre-commit` before pushing — CI will reject non-compliant code.

---

## Secrets Hygiene

- `config/config.yml` is gitignored — never commit a real config.
- The `check_no_tracker_secrets` pre-commit hook (landing with PR #1198)
  blocks commits that include tracker credentials or announce URLs with
  embedded tokens.
- Never bypass with `--no-verify` without maintainer approval.

---

## Docs / Wiki

- `docs/` is the source for the [GitHub Wiki](https://github.com/StuffAnThings/qbit_manage/wiki).
- The `docs.yml` CI workflow syncs `docs/` to the wiki on every push to `develop`.
- Edit docs in `docs/` — never edit the wiki directly.
- `docs/Contributing.md` is the contributor guide.
- `DEVELOPER.md` documents the release flow and CI gates.

---

## Key References

- **Config keys:** `modules/config.py` — `check_for_attribute()` calls
- **CLI args:** `qbit_manage.py` — argparse section at the bottom
- **Release flow:** `DEVELOPER.md`
- **Contributing guide:** `docs/Contributing.md`
- **Pre-commit hooks:** `.pre-commit-config.yaml` + `scripts/pre-commit/`
- **CI workflows:** `.github/workflows/`
