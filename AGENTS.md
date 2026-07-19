# qBit Manage — AI Agent Instructions

**qBit Manage** is a Python automation tool for qBittorrent. It handles
tagging, share-limit enforcement, category changes, hardlink-aware no-HL
detection, orphan/unregistered removal, and exposes both a web UI and a REST
API. Standalone helper scripts live in `scripts/`.

This is the canonical instructions file for AI coding assistants (Claude,
GitHub Copilot, and others) working in this repository, following the
[AGENTS.md](https://agents.md/) open standard.

---

## Branch Model

| Branch | Purpose |
|--------|---------|
| `develop` | Active development — all PRs target this branch |
| `master` | Stable releases only — never PR directly to master |

- **Always branch from `develop`. Never open a PR to `master`** (except
  hotfixes with a `hotfix/` prefix and explicit maintainer approval — see
  `DEVELOPER.md`).
- Keep changes focused on one issue or behavior per PR.
- Read `docs/Contributing.md` for the contributor workflow and `DEVELOPER.md`
  before changing release automation.

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

Equivalent raw commands (useful when `make` isn't available):

```bash
ruff check .
ruff format --check .
pytest tests/
pre-commit run --all-files
```

---

## Test Commands

```bash
pytest tests/              # full suite (~168 tests)
pytest tests/ --no-cov     # quick run, skip coverage
pytest tests/test_foo.py   # single file
```

- Run the narrowest relevant tests first, then the related suite.
- Add regression tests for bug fixes and tests for new behavior.
- Tests use `tests/factories.py` bypass-constructors — never instantiate core
  classes directly in tests when a factory exists. Key factories:
  `make_share_limits()`, `make_category()`, `make_tag_nohardlinks()`.
- Keep tests deterministic and independent of a live qBittorrent instance
  unless the test is explicitly an integration test.

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

## Implementation Standards

- Support Python 3.10 and newer.
- Follow existing module patterns and prefer the smallest change that fixes
  the behavior.
- Validate input at API, CLI, configuration, and filesystem boundaries.
- Handle errors explicitly. Preserve the original failure context in logs and
  return clear user-facing API errors.
- Avoid mutating caller-owned objects. Return new values or copies when state
  must change.
- Keep functions focused, avoid deep nesting, and use descriptive names.
- Comments explain non-obvious constraints or rationale, not what the code
  already states.

---

## Code Style

- **Ruff** for lint + format; config in `ruff.toml` (line-length=130).
- Single-line imports (isort rules enforced).
- Run `make pre-commit` before pushing — CI will reject non-compliant code.

---

## Secrets Hygiene

- `config/config.yml` is gitignored — never commit a real config.
- Never hardcode credentials, tracker passkeys, announce URLs, API keys, or
  other secrets.
- The `check_no_tracker_secrets` pre-commit hook blocks commits that include
  tracker credentials or announce URLs with embedded tokens.
- Never bypass with `--no-verify` without maintainer approval.
- Preserve secret redaction in every logging format and avoid changes that
  corrupt line-delimited JSON output.

---

## Web UI

- Preserve the existing vanilla HTML, CSS, and JavaScript architecture unless
  a change explicitly requires a new dependency.
- Maintain responsive behavior and verify layouts at the breakpoints
  documented in `web-ui/css/responsive.css`.
- Treat long torrent names, paths, tracker URLs, and log lines as expected
  input. They must not create horizontal page overflow.
- Preserve accessibility semantics, keyboard behavior, labels, focus states,
  and reduced-motion feature queries.

---

## API, Configuration, and Logging

- Keep FastAPI routes authenticated and rate-limited according to existing
  endpoint patterns.
- Resolve filesystem paths and verify containment before reading or writing
  user-selected files.
- Register configuration keys through the existing `check_for_attribute`
  patterns in `modules/config.py`.
- Keep text-mode logging behavior compatible unless the requested change
  explicitly updates it.

---

## GitHub Actions and Releases

- This is a public repository. Use GitHub-hosted runners and never execute
  public pull request code on private or self-hosted infrastructure.
- Pin third-party actions to full commit SHAs and retain the version comment.
- Use least-privilege job permissions.
- Do not suppress GitHub CLI or API errors when checking whether a release,
  tag, or artifact exists. Handle an explicit not-found response separately
  from authentication, rate-limit, or transient failures.
- Preserve the release flow documented in `DEVELOPER.md`: release PR draft,
  merge to `master`, version tag, production publication, then
  synchronization back to `develop`.
- Keep stable tags under `v*`; rolling develop tags must not trigger
  stable-release workflows.

---

## Review Priorities

When reviewing changes, prioritize:

1. Data loss, unintended torrent deletion, and filesystem containment.
2. Authentication, secret exposure, unsafe API input, and permission
   expansion.
3. Release, versioning, and branch-flow regressions.
4. Behavior changes without regression tests.
5. Web UI overflow, accessibility, and desktop/mobile regressions.

Report concrete findings with the affected file and line. Do not invent
failures when the change is correct.

---

## Docs / Wiki

- `docs/` and the [GitHub Wiki](https://github.com/StuffAnThings/qbit_manage/wiki) are kept in sync **bidirectionally** by `.github/workflows/docs.yml`:
  - Push to `develop` touching `docs/**` → CI syncs `docs/` → wiki.
  - Wiki edit via the GitHub UI → `gollum` event → CI syncs wiki → `docs/` on `develop`.
- Either side is a valid place to edit; the sync is not instant (each
  direction is a CI run), but neither side overwrites the other.
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
