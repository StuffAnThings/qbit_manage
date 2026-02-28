# qbit_manage

Python tool for managing qBittorrent. Automates tagging, categorization, orphan cleanup, and more.

## Project
- Python 3.10+, setuptools + pyproject.toml
- Ruff: line-length=130 (see ruff.toml)
- Entry point: `qbit_manage.py`
- Config: `config/config.yml` (gitignored)
- Logs: `config/logs/`

## Structure
- `modules/` — core logic (qbittorrent.py, config.py, webhooks.py, util.py)
- `modules/core/` — per-feature modules (tags, share_limits, category)
- `scripts/` — standalone utilities
- `build/` — generated, never edit

## Dev
- `pip install -e ".[dev]"` to install with dev deps
- `ruff check --fix .` — lint and auto-fix
- `ruff format .` — format
- PRs target the `develop` branch
