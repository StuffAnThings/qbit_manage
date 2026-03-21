# Contributing & Building

Pull requests are welcome! Please submit them to the [develop branch](https://github.com/StuffAnThings/qbit_manage/tree/develop).

## Prerequisites

- **Python 3.10+**
- **Git**
- **[uv](https://docs.astral.sh/uv/)** (Python package manager)
- **[Rust](https://rustup.rs/)** (only for desktop app builds)

## Development Setup

```bash
# Clone the repository
git clone https://github.com/StuffAnThings/qbit_manage.git
cd qbit_manage
git checkout develop

# Create virtual environment and install all dependencies (including dev tools)
make venv

# Activate the virtual environment
source .venv/bin/activate

# Install pre-commit hooks
make install-hooks
```

The `make venv` target handles everything: installs uv if needed, creates a `.venv`, installs the project in editable mode, and adds dev dependencies (pre-commit, ruff).

## Common Make Targets

| Target | Description |
|--------|-------------|
| `make venv` | Create virtual environment and install all dependencies |
| `make install-hooks` | Install pre-commit hooks into your local repo |
| `make test` | Run the test suite |
| `make lint` | Run ruff linter with auto-fix |
| `make format` | Run ruff code formatter |
| `make pre-commit` | Run all pre-commit hooks on all files |
| `make build` | Build Python package for distribution |
| `make install` | Install qbit-manage as a `uv tool` (system-wide CLI) |
| `make clean` | Remove all generated files (venv, dist, build, cache) |
| `make help` | Show all available targets (including release/publishing targets) |

## Code Style

The project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting:

- **Line length**: 130 characters
- **Import style**: Single-line imports (enforced by isort rules)
- **Pre-commit hooks** run automatically on commit and enforce:
  - Trailing whitespace removal
  - End-of-file fixer
  - JSON/YAML validation
  - Ruff linting and formatting
  - Automatic develop version bumping

## Building

### Standalone Binary (PyInstaller)

The standalone binary bundles Python, all dependencies, the web UI, and docs into a single executable.

```bash
# Activate the virtual environment
source .venv/bin/activate

# Install PyInstaller
pip install pyinstaller

# Build the binary
pyinstaller --noconfirm --clean --onefile \
    --name qbit-manage \
    --add-data "web-ui:web-ui" \
    --add-data "config/config.yml.sample:config" \
    --add-data "icons/qbm_logo.png:." \
    --add-data "VERSION:." \
    --add-data "docs:docs" \
    qbit_manage.py

# Binary will be in dist/qbit-manage
./dist/qbit-manage --help
```

> **Note:** PyInstaller produces a binary for the architecture of the machine you build on. To get an ARM64 binary, build on an ARM64 machine.

> **Note:** On Windows, replace `:` with `;` in the `--add-data` arguments (e.g., `--add-data "web-ui;web-ui"`).

### Desktop App (Tauri)

The desktop app wraps the standalone binary in a [Tauri v2](https://v2.tauri.app/) shell with a native window, system tray, and the web UI as the frontend.

#### Install Tauri Build Dependencies

**Linux (Debian/Ubuntu):**
```bash
sudo make tauri-deps
```

This installs the required system packages (`build-essential`, `libgtk-3-dev`, `libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`, `patchelf`, and more). Requires root for `apt-get`.

**macOS:** Xcode Command Line Tools are sufficient.

**Windows:** Install [NSIS](https://nsis.sourceforge.io/) (e.g., `choco install nsis`).

#### Build Steps

1. **Build the standalone binary first** (see above) and copy it into the Tauri sidecar directory with the platform-specific name:
   ```bash
   mkdir -p desktop/tauri/src-tauri/bin

   # Copy only YOUR platform's binary (pick one):
   cp dist/qbit-manage desktop/tauri/src-tauri/bin/qbit-manage-linux-amd64   # x86_64 Linux
   # cp dist/qbit-manage desktop/tauri/src-tauri/bin/qbit-manage-linux-arm64   # ARM64 Linux
   # cp dist/qbit-manage desktop/tauri/src-tauri/bin/qbit-manage-macos-arm64   # Apple Silicon
   # cp dist/qbit-manage desktop/tauri/src-tauri/bin/qbit-manage-macos-x86_64  # Intel Mac

   chmod +x desktop/tauri/src-tauri/bin/qbit-manage-*
   ```

2. **Install the Tauri CLI and build:**
   ```bash
   cd desktop/tauri/src-tauri
   cargo install tauri-cli --version ^2 --locked
   cargo tauri build --bundles deb   # Linux: produces .deb in target/release/bundle/deb/
   cargo tauri build --bundles dmg   # macOS: produces .dmg
   cargo tauri build --bundles nsis  # Windows: produces installer .exe
   ```

The build script (`build.rs`) automatically reads the `VERSION` file and updates `Cargo.toml` and `tauri.conf.json` to keep versions in sync.

### Docker Image

```bash
docker build -t qbit-manage .
```

The Dockerfile is a multi-stage Alpine build. For multi-architecture builds (amd64, arm64, arm/v7), the CI uses Docker Buildx with QEMU.

## Project Structure

```
qbit_manage/
├── qbit_manage.py          # Main entry point
├── modules/                # Core application modules
├── web-ui/                 # Web UI frontend (HTML/CSS/JS)
│   ├── index.html
│   ├── js/
│   └── css/
├── desktop/tauri/          # Tauri desktop app shell
│   └── src-tauri/
│       ├── src/            # Rust source
│       ├── bin/            # Sidecar binaries (gitignored, populated at build time)
│       ├── Cargo.toml
│       ├── build.rs        # Version sync script
│       └── tauri.conf.json # Tauri configuration
├── config/                 # Sample configuration files
├── docs/                   # Wiki documentation (synced to GitHub wiki)
├── icons/                  # Application icons
├── scripts/                # Standalone helper scripts
├── Makefile                # Development automation
├── Dockerfile              # Docker build
├── pyproject.toml          # Python project configuration
└── VERSION                 # Single source of truth for version
```

## Submitting Changes

1. Fork the repository and create a branch from `develop`
2. Make your changes and ensure `make pre-commit` passes
3. Test your changes locally
4. Submit a pull request to the `develop` branch
5. Describe what your PR does and why

## Support

- **Questions**: Join the [Notifiarr Discord](https://discord.com/invite/AURf8Yz) and post in the `qbit-manage` channel
- **Bugs/Enhancements**: Open an [Issue](https://github.com/StuffAnThings/qbit_manage/issues/new)
- **Config Questions**: Start a [Discussion](https://github.com/StuffAnThings/qbit_manage/discussions/new)
