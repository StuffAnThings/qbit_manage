# Contributing to qBit Manage

Pull requests are welcome! Please target the **`develop`** branch — PRs to `master` will not be accepted.

---

## Quick Start

### 1. Fork and Clone

```bash
# Fork via GitHub, then:
git clone https://github.com/<your-username>/qbit_manage.git
cd qbit_manage
git checkout develop
```

### 2. Create a Branch

Branch from `develop`. Use a descriptive name:

```bash
git checkout -b fix/share-limits-edge-case
git checkout -b feat/new-tagging-option
```

### 3. Set Up Your Dev Environment

**Option A — uv (recommended, faster):**

```bash
# Install uv if not already present
curl -Lsf https://astral.sh/uv/install.sh | sh

make venv            # creates .venv, installs project + dev deps
source .venv/bin/activate
make install-hooks   # install pre-commit hooks
```

**Option B — pip + venv:**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

> uv is also kept current via Dependabot (uv ecosystem), so lock-file updates happen automatically.

---

## Common Make Targets

| Target | Description |
|--------|-------------|
| `make venv` | Create virtual environment and install all dependencies |
| `make install-hooks` | Install pre-commit hooks into your local repo |
| `make test` | Run the full test suite |
| `make lint` | Run ruff linter with auto-fix |
| `make format` | Run ruff code formatter |
| `make pre-commit` | Run all pre-commit hooks on all files |
| `make clean` | Remove generated files (venv, dist, build, cache) |
| `make help` | List all available targets |

---

## Code Style

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

- **Line length:** 130 characters (see `ruff.toml`)
- **Import style:** Single-line imports (isort rules enforced)

Run before committing:

```bash
ruff check --fix .
ruff format .
```

---

## Pre-Commit Hooks

Hooks run automatically on `git commit`. They enforce:

| Hook | What it does |
|------|-------------|
| `trailing-whitespace` | Strips trailing spaces |
| `end-of-file-fixer` | Ensures files end with a newline |
| `check-json` / `check-yaml` | Validates JSON and YAML syntax |
| `yamllint` + `yamlfix` | Strict YAML style lint and auto-fix |
| `ruff-check` | Lints Python with auto-fix |
| `ruff-format` | Formats Python |
| `increase-version` | Bumps the `developN` counter in `VERSION` on develop branches |
| `check_no_tracker_secrets` | (Once PR #1198 merges) Prevents accidental commit of tracker credentials from config files |

Run all hooks manually at any time:

```bash
make pre-commit
# or directly:
pre-commit run --all-files
```

---

## Tests

> Tests land with PR #1198. Until that PR merges, the test suite is not present on `develop`.

Once available:

```bash
pytest tests/              # full suite (~168 tests)
pytest tests/ --no-cov     # quick run, skip coverage report
```

**Test scaffolding pattern** (`tests/factories.py`):

The factories module provides bypass-constructors that create objects without
needing a live qBittorrent connection. Key helpers:

- `make_share_limits()` — returns a configured `ShareLimits` instance
- `make_category()` — returns a `Category` instance
- `make_tag_nohardlinks()` — returns a `TagNoHardLinks` instance

Use these in your own test fixtures rather than instantiating core classes
directly. Each factory accepts keyword arguments to override defaults, keeping
tests readable and isolated.

---

## Commit Messages

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

Scopes are optional but encouraged (e.g., `share_limits`, `tags`, `config`).

**Types used in this repo** (verified against git history):

| Type | When to use |
|------|-------------|
| `feat` | New feature or behavior |
| `fix` | Bug fix |
| `refactor` | Code restructuring, no behavior change |
| `chore` | Dependency bumps, tooling, housekeeping |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `ci` | CI/CD workflow changes |
| `perf` | Performance improvements |

Examples from the log:
```
feat(tags): add support for tagging private torrents
fix(share_limits): set limits when throttle skipped
refactor(share_limits): simplify logic and reduce code duplication
chore(deps): bump ruff from 0.14.5 to 0.14.6
```

---

## Submitting a PR

1. Ensure `make pre-commit` passes with no errors.
2. Run `pytest tests/` (once available) and confirm no regressions.
3. Push your branch and open a PR against **`develop`** — not `master`.
4. Describe what your PR does and link any related issues.
5. A maintainer will review; CI must be green before merge.

For the release process (merging `develop → master`, tagging, PyPI publish),
see [`DEVELOPER.md`](../DEVELOPER.md).

---

## Project Structure

```
qbit_manage/
├── qbit_manage.py          # Main entry point and CLI argument parsing
├── modules/                # Core application logic
│   ├── config.py           # Config loading; check_for_attribute() calls define all valid keys
│   ├── qbittorrent.py      # qBittorrent API wrapper
│   ├── util.py             # Shared helpers and utilities
│   ├── webhooks.py         # Webhook notification support
│   ├── web_api.py          # REST API server
│   ├── web_ui.py           # Web UI server
│   └── core/               # Per-feature modules
│       ├── tags.py
│       ├── share_limits.py
│       ├── category.py
│       ├── tag_nohardlinks.py
│       ├── recheck.py
│       ├── remove_orphaned.py
│       └── remove_unregistered.py
├── tests/                  # Test suite (landing with PR #1198)
│   └── factories.py        # Bypass-constructors for unit testing
├── scripts/                # Standalone helper scripts
│   └── pre-commit/         # Pre-commit hook scripts
├── web-ui/                 # Web UI frontend (HTML/CSS/JS)
├── desktop/tauri/          # Tauri desktop app shell
├── docs/                   # Wiki documentation (synced to GitHub Wiki)
├── config/                 # Sample configuration files
├── icons/                  # Application icons
├── Makefile                # Development automation
├── Dockerfile              # Docker build
├── pyproject.toml          # Python project configuration
├── ruff.toml               # Ruff linter/formatter config
└── VERSION                 # Single source of truth for version
```

---

## Support

- **Questions:** Join the [Notifiarr Discord](https://discord.com/invite/AURf8Yz) → `#qbit-manage` channel
- **Bugs / Enhancements:** Open an [Issue](https://github.com/StuffAnThings/qbit_manage/issues/new)
- **Config Questions:** Start a [Discussion](https://github.com/StuffAnThings/qbit_manage/discussions/new)
