# Define the path to uv
UV_PATH := $(shell which uv 2>/dev/null || echo "")
UV_LOCAL_PATH := $(HOME)/.local/bin/uv
UV_CARGO_PATH := $(HOME)/.cargo/bin/uv

# Check if uv is installed, if not set UV_INSTALL to 1
ifeq ($(UV_PATH),)
    ifeq ($(wildcard $(UV_LOCAL_PATH)),)
        ifeq ($(wildcard $(UV_CARGO_PATH)),)
            UV_INSTALL := 1
        else
            UV_PATH := $(UV_CARGO_PATH)
        endif
    else
        UV_PATH := $(UV_LOCAL_PATH)
    endif
endif

# Define the virtual environment path
VENV := .venv
VENV_ACTIVATE := $(VENV)/bin/activate
VENV_PYTHON := $(VENV)/bin/python
VENV_UV := $(VENV)/bin/uv
VENV_PIP := $(VENV)/bin/pip
VENV_PRE_COMMIT := $(VENV)/bin/pre-commit
VENV_RUFF := $(VENV)/bin/ruff

.PHONY: all
all: venv

.PHONY: install-uv
install-uv:
ifdef UV_INSTALL
	@echo "Installing uv..."
	@curl -LsSf https://astral.sh/uv/install.sh | sh
	@echo "uv installed to $(HOME)/.local/bin/uv"
	$(eval UV_PATH := $(HOME)/.local/bin/uv)
endif

.PHONY: venv
venv: install-uv
	@echo "Creating virtual environment..."
	@$(UV_PATH) venv $(VENV)
	@echo "Installing project dependencies from pyproject.toml..."
	@$(UV_PATH) pip install --python $(VENV_PYTHON) -e . --config-settings editable_mode=compat
	@echo "Removing conflicting console script to avoid PATH conflicts..."
	@rm -f $(VENV)/bin/qbit-manage 2>/dev/null || true
	@echo "Installing development dependencies..."
	@$(UV_PATH) pip install --python $(VENV_PYTHON) pre-commit ruff
	@echo "Virtual environment created and dependencies installed."
	@echo "✓ Virtual environment ready for development"
	@echo "To activate the virtual environment, run: source $(VENV_ACTIVATE)"

.PHONY: sync
sync: venv
	@echo "Syncing dependencies from pyproject.toml..."
	@$(UV_PATH) pip sync pyproject.toml

.PHONY: test
test: venv
	@echo "Running tests..."
	@. $(VENV_ACTIVATE) && $(VENV_PYTHON) -m pytest

.PHONY: pre-commit
pre-commit: venv
	@echo "Running pre-commit hooks..."
	@. $(VENV_ACTIVATE) && $(VENV_PRE_COMMIT) run --all-files

.PHONY: install-hooks
install-hooks: venv
	@echo "Installing pre-commit hooks..."
	@. $(VENV_ACTIVATE) && $(VENV_PRE_COMMIT) install -f --install-hooks

.PHONY: clean
clean:
	@echo "Cleaning up..."
	@find -name '*.pyc' -delete
	@find -name '__pycache__' -delete
	@rm -rf $(VENV)
	@rm -rf .pytest_cache
	@rm -rf .ruff_cache
	@rm -rf dist/
	@rm -rf build/
	@rm -rf *.egg-info/
	@rm -rf web-ui/dist/
	@rm -rf web-ui/build/
	@rm -rf web-ui/node_modules/
	@rm -rf desktop/tauri/src-tauri/target/
	@rm -rf desktop/tauri/src-tauri/gen/
	@rm -rf desktop/tauri/node_modules/
	@echo "Cleanup complete."

.PHONY: lint
lint: venv
	@echo "Running linter..."
	@. $(VENV_ACTIVATE) && $(VENV_RUFF) check --fix .

.PHONY: format
format: venv
	@echo "Running formatter..."
	@. $(VENV_ACTIVATE) && $(VENV_RUFF) format .

.PHONY: build
build: venv
	@echo "Building package..."
	@$(UV_PATH) pip install --python $(VENV_PYTHON) build twine
	@. $(VENV_ACTIVATE) && $(VENV_PYTHON) -m build
	@echo "Package built successfully. Files in dist/"

.PHONY: check-dist
check-dist: build
	@echo "Checking distribution files..."
	@. $(VENV_ACTIVATE) && $(VENV_PYTHON) -m twine check dist/*

.PHONY: setup-pypi
setup-pypi:
	@echo "Setting up PyPI configuration..."
	@if [ -f ~/.pypirc ] && grep -q "password = pypi-" ~/.pypirc 2>/dev/null; then \
		echo "✓ ~/.pypirc already exists with API tokens configured"; \
	else \
		$(MAKE) setup-pypi-interactive; \
	fi

.PHONY: setup-pypi-interactive
setup-pypi-interactive:
	@echo ""
	@echo "This will set up your PyPI credentials for automatic uploads."
	@echo "You'll need API tokens from:"
	@echo "  - Test PyPI: https://test.pypi.org/manage/account/token/"
	@echo "  - Live PyPI: https://pypi.org/manage/account/token/"
	@echo ""
	@echo "Creating accounts (if needed):"
	@echo "  - Test PyPI: https://test.pypi.org/account/register/"
	@echo "  - Live PyPI: https://pypi.org/account/register/"
	@echo ""
	@printf "Press Enter to continue or Ctrl+C to cancel..."
	@read dummy
	@echo ""
	@printf "Please enter your Test PyPI API token (starts with 'pypi-'): "
	@read testpypi_token; \
	echo ""; \
	printf "Please enter your PyPI API token (starts with 'pypi-'): "; \
	read pypi_token; \
	echo ""; \
	if [ -z "$$testpypi_token" ] || [ -z "$$pypi_token" ]; then \
		echo "❌ Both tokens are required. Setup cancelled."; \
		exit 1; \
	fi; \
	if ! echo "$$testpypi_token" | grep -q "^pypi-" || ! echo "$$pypi_token" | grep -q "^pypi-"; then \
		echo "❌ Invalid token format. Tokens should start with 'pypi-'"; \
		exit 1; \
	fi; \
	echo "Creating ~/.pypirc configuration file..."; \
	echo "[distutils]" > ~/.pypirc; \
	echo "index-servers =" >> ~/.pypirc; \
	echo "    pypi" >> ~/.pypirc; \
	echo "    testpypi" >> ~/.pypirc; \
	echo "" >> ~/.pypirc; \
	echo "[pypi]" >> ~/.pypirc; \
	echo "repository = https://upload.pypi.org/legacy/" >> ~/.pypirc; \
	echo "username = __token__" >> ~/.pypirc; \
	echo "password = $$pypi_token" >> ~/.pypirc; \
	echo "" >> ~/.pypirc; \
	echo "[testpypi]" >> ~/.pypirc; \
	echo "repository = https://test.pypi.org/legacy/" >> ~/.pypirc; \
	echo "username = __token__" >> ~/.pypirc; \
	echo "password = $$testpypi_token" >> ~/.pypirc; \
	chmod 600 ~/.pypirc; \
	echo "✓ PyPI configuration saved to ~/.pypirc"; \
	echo "✓ You can now use 'make upload-test' and 'make upload-pypi' without entering tokens"

.PHONY: upload-test
upload-test: check-dist
	@echo "Uploading to Test PyPI..."
	@if [ -z "$$TWINE_PASSWORD_TESTPYPI" ] && ! grep -q "password = pypi-" ~/.pypirc 2>/dev/null; then \
		echo ""; \
		echo "No API token found. Please either:"; \
		echo "1. Set environment variable: export TWINE_PASSWORD_TESTPYPI=your-test-pypi-token"; \
		echo "2. Run 'make setup-pypi' and edit ~/.pypirc with your tokens"; \
		echo "3. Get token from: https://test.pypi.org/manage/account/token/"; \
		exit 1; \
	fi
	@if [ -n "$$TWINE_PASSWORD_TESTPYPI" ]; then \
		echo "Using environment variable for authentication"; \
		. $(VENV_ACTIVATE) && TWINE_USERNAME=__token__ TWINE_PASSWORD=$$TWINE_PASSWORD_TESTPYPI $(VENV_PYTHON) -m twine upload --repository testpypi --verbose --skip-existing dist/*; \
	else \
		echo "Using ~/.pypirc for authentication"; \
		. $(VENV_ACTIVATE) && $(VENV_PYTHON) -m twine upload --repository testpypi --verbose --skip-existing dist/*; \
	fi
	@echo "Upload to Test PyPI complete!"
	@echo "Test installation with: pip install --index-url https://test.pypi.org/simple/ qbit-manage"

.PHONY: upload-pypi
upload-pypi: check-dist
	@echo "Uploading to PyPI..."
	@echo "WARNING: This will upload to the LIVE PyPI repository!"
	@if [ -z "$$TWINE_PASSWORD_PYPI" ] && ! grep -q "password = pypi-" ~/.pypirc 2>/dev/null; then \
		echo ""; \
		echo "No API token found. Please either:"; \
		echo "1. Set environment variable: export TWINE_PASSWORD_PYPI=your-pypi-token"; \
		echo "2. Run 'make setup-pypi' and edit ~/.pypirc with your tokens"; \
		echo "3. Get token from: https://pypi.org/manage/account/token/"; \
		exit 1; \
	fi
	@read -p "Are you sure you want to continue? (y/N): " confirm && [ "$$confirm" = "y" ]
	@if [ -n "$$TWINE_PASSWORD_PYPI" ]; then \
		echo "Using environment variable for authentication"; \
		. $(VENV_ACTIVATE) && TWINE_USERNAME=__token__ TWINE_PASSWORD=$$TWINE_PASSWORD_PYPI $(VENV_PYTHON) -m twine upload --verbose --skip-existing dist/*; \
	else \
		echo "Using ~/.pypirc for authentication"; \
		. $(VENV_ACTIVATE) && $(VENV_PYTHON) -m twine upload --verbose --skip-existing dist/*; \
	fi
	@echo "Upload to PyPI complete!"
	@echo "Package is now available at: https://pypi.org/project/qbit-manage/"

.PHONY: bump-version
bump-version:
	@echo "Current version: $$(cat VERSION)"
	@echo "Bumping patch version for testing..."
	@current_version=$$(cat VERSION | cut -d'-' -f1); \
	IFS='.' read -r major minor patch <<< "$$current_version"; \
	new_patch=$$((patch + 1)); \
	new_version="$$major.$$minor.$$new_patch"; \
	echo "$$new_version-dev" > VERSION; \
	echo "✓ Version bumped to: $$(cat VERSION)"
	@echo "Now you can run: make build && make upload-test"

.PHONY: debug-upload
debug-upload: check-dist
	@echo "Debugging upload configuration..."
	@echo "Current version: $$(cat VERSION 2>/dev/null || echo 'VERSION file not found')"
	@echo ""
	@echo "Checking ~/.pypirc configuration:"
	@if [ -f ~/.pypirc ]; then \
		echo "✓ ~/.pypirc exists"; \
		echo "Repositories configured:"; \
		grep -E "^\[.*\]" ~/.pypirc || echo "No repositories found"; \
		echo ""; \
		echo "Test PyPI config:"; \
		sed -n '/\[testpypi\]/,/^\[/p' ~/.pypirc | head -n -1 || echo "No testpypi section found"; \
	else \
		echo "❌ ~/.pypirc not found"; \
	fi
	@echo ""
	@echo "Environment variables:"
	@echo "TWINE_USERNAME: $${TWINE_USERNAME:-not set}"
	@echo "TWINE_PASSWORD_TESTPYPI: $${TWINE_PASSWORD_TESTPYPI:+set (hidden)}"
	@echo "TWINE_PASSWORD_PYPI: $${TWINE_PASSWORD_PYPI:+set (hidden)}"
	@echo ""
	@echo "Package information:"
	@ls -la dist/ 2>/dev/null || echo "No dist/ directory found"
	@echo ""
	@echo "Common issues and solutions:"
	@echo "  - File already exists: Run 'make bump-version' to create a new version"
	@echo "  - Invalid token: Run 'make setup-pypi' to reconfigure"
	@echo "  - Package name taken: Change name in pyproject.toml"

# UV Tool Installation targets
.PHONY: install
install:
	@echo "Installing qbit-manage using uv tool..."
	@echo "Cleaning cache and build artifacts to ensure fresh install..."
	@rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@$(UV_PATH) cache clean >/dev/null 2>&1 || true
	@$(UV_PATH) tool install . --force
	@echo "✓ Installation complete!"
	@echo "Test with: qbit-manage --version"

.PHONY: uninstall
uninstall:
	@echo "Uninstalling qbit-manage..."
	@$(UV_PATH) tool uninstall qbit-manage || echo "qbit-manage was not installed"
	@echo "✓ Uninstall complete!"

.PHONY: reinstall
reinstall: uninstall install
	@echo "✓ Reinstall complete!"

.PHONY: tauri-deps
tauri-deps:
	@echo "Installing Tauri Linux build dependencies (apt)..."
	@export DEBIAN_FRONTEND=noninteractive; \
	apt-get update; \
	WEBKIT_PKG=libwebkit2gtk-4.1-dev; \
	if ! apt-cache show $${WEBKIT_PKG} >/dev/null 2>&1; then WEBKIT_PKG=libwebkit2gtk-4.0-dev; fi; \
	apt-get install -y \
	  build-essential \
	  curl \
	  pkg-config \
	  patchelf \
	  libgtk-3-dev \
	  $${WEBKIT_PKG} \
	  libayatana-appindicator3-dev \
	  librsvg2-dev \
	  libglib2.0-dev \
	  libpango1.0-dev \
	  libcairo2-dev \
	  libgdk-pixbuf-2.0-dev \
	  libatk1.0-dev \
	  xdg-desktop-portal \
	  xdg-desktop-portal-gtk; \
	true

.PHONY: prep-release
prep-release:
	@echo "Preparing release..."
	@# Step 1: Update uv lock and sync dependencies
	@echo "Updating uv lock and syncing dependencies..."
	@uv lock --upgrade
	@uv sync
	@echo "✓ Dependencies updated"
	@# Step 2: Strip '-develop*' suffix from VERSION
	@current_version=$$(cat VERSION); \
	clean_version=$$(echo $$current_version | sed 's/-develop.*$$//'); \
	echo "$$clean_version" > VERSION; \
	echo "✓ VERSION updated to $$clean_version"
	@# Step 3: Check Tauri Rust project builds
	@echo "Ensuring desktop build dependencies are installed (apt)..."
	@$(MAKE) tauri-deps
	@echo "Running cargo check in desktop/tauri/src-tauri..."
	@cd desktop/tauri/src-tauri && cargo check
	@# Step 4: Prepare CHANGELOG skeleton and bump Full Changelog link
	@new_version=$$(cat VERSION); \
	major=$$(echo "$$new_version" | cut -d. -f1); \
	minor=$$(echo "$$new_version" | cut -d. -f2); \
	patch=$$(echo "$$new_version" | cut -d. -f3); \
	prev_patch=$$((patch - 1)); \
	prev_version="$$major.$$minor.$$prev_patch"; \
	git fetch origin master:master; \
	updated_deps=$$(git diff master..HEAD -- pyproject.toml | grep '^+' | grep '==' | sed 's/^+//' | sed 's/^ *//' | sed 's/,$$//' | sed 's/^/- /'); \
	echo "# Requirements Updated" > CHANGELOG; \
	if [ -n "$$updated_deps" ]; then \
		echo "$$updated_deps" >> CHANGELOG; \
	fi; \
	echo "" >> CHANGELOG; \
	echo "# New Features" >> CHANGELOG; \
	echo "" >> CHANGELOG; \
	echo "" >> CHANGELOG; \
	echo "# Improvements" >> CHANGELOG; \
	echo "" >> CHANGELOG; \
	echo "" >> CHANGELOG; \
	echo "# Bug Fixes" >> CHANGELOG; \
	echo "" >> CHANGELOG; \
	echo "" >> CHANGELOG; \
	echo "**Full Changelog**: https://github.com/StuffAnThings/qbit_manage/compare/v$$prev_version...v$$new_version" >> CHANGELOG; \
	echo "✓ CHANGELOG prepared for release $$new_version"
	@echo ""
	@echo "REMINDER: Update the CHANGELOG contents with actual improvements and bug fixes before making the release."

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  install       - Install qbit-manage using uv tool (overwrites existing)"
	@echo "  uninstall     - Uninstall qbit-manage from uv tools"
	@echo "  reinstall     - Uninstall then install (clean reinstall)"
	@echo "  venv          - Create virtual environment and install dependencies"
	@echo "  sync          - Sync dependencies from pyproject.toml"
	@echo "  test          - Run tests"
	@echo "  lint          - Run linter with fixes"
	@echo "  format        - Run code formatter"
	@echo "  pre-commit    - Run pre-commit hooks"
	@echo "  build         - Build package for distribution"
	@echo "  check-dist    - Check distribution files"
	@echo "  setup-pypi    - Set up PyPI configuration (~/.pypirc)"
	@echo "  bump-version  - Bump patch version for testing uploads"
	@echo "  prep-release - Strip '-develop*' from VERSION, cargo check, and template CHANGELOG"
	@echo "  debug-upload  - Debug PyPI upload configuration"
	@echo "  upload-test   - Upload to Test PyPI (uses env vars or ~/.pypirc)"
	@echo "  upload-pypi   - Upload to PyPI (LIVE) (uses env vars or ~/.pypirc)"
	@echo "  clean         - Clean up all generated files (venv, dist, build, cache)"
	@echo "  help          - Show this help message"
