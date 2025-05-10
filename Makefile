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
	@echo "Installing project dependencies..."
	@$(UV_PATH) pip install -e .
	@echo "Installing development dependencies..."
	@$(UV_PATH) pip install pre-commit ruff
	@echo "Virtual environment created and dependencies installed."
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
	@echo "Cleanup complete."

.PHONY: lint
lint: venv
	@echo "Running linter..."
	@. $(VENV_ACTIVATE) && $(VENV_RUFF) check --fix .

.PHONY: format
format: venv
	@echo "Running formatter..."
	@. $(VENV_ACTIVATE) && $(VENV_RUFF) format .
