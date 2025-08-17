# Python/Source Installation

This guide covers installing qbit_manage from source code or PyPI for development purposes or when you need the latest features.

**Note**: For most users, we recommend using the [Desktop App or Standalone Binary](Installation) instead, as they're easier to install and use.

## Prerequisites

* Python 3.9.0 or higher
* pip (Python package installer)
* Git (for source installation)

## Installation Methods

### Method 1: Install from PyPI (Recommended)

```bash
pip install qbit-manage
```

### Method 2: Install from Source

Navigate to the directory where you'd like to clone the repository:

```bash
# Clone the repository
git clone https://github.com/StuffAnThings/qbit_manage
cd qbit_manage

# Install the package
pip install .
```

If you encounter dependency issues, try:

```bash
pip install . --ignore-installed
```

### Method 3: Development Installation

For development or to get the latest unreleased features:

```bash
# Clone the repository
git clone https://github.com/StuffAnThings/qbit_manage
cd qbit_manage

# Install in development mode
pip install -e .
```

## Configuration File Setup

After installation, qbit_manage will look for configuration files in platform-specific locations:

- **Windows**: `%APPDATA%\qbit-manage\config.yml`
- **macOS**: `~/Library/Application Support/qbit-manage/config.yml`
- **Linux/Unix**: `~/.config/qbit-manage/config.yml`

### Setting up the Configuration

1. Create the configuration directory:
   ```bash
   # Windows (PowerShell)
   New-Item -ItemType Directory -Force -Path "$env:APPDATA\qbit-manage"

   # macOS/Linux
   mkdir -p ~/.config/qbit-manage  # Linux
   mkdir -p ~/Library/Application\ Support/qbit-manage  # macOS
   ```

2. Copy the sample configuration:
   ```bash
   # From the cloned repository
   cp config/config.yml.sample ~/.config/qbit-manage/config.yml  # Linux
   cp config/config.yml.sample ~/Library/Application\ Support/qbit-manage/config.yml  # macOS
   copy config\config.yml.sample "%APPDATA%\qbit-manage\config.yml"  # Windows
   ```

3. Edit the configuration file as outlined in the [Config-Setup](Config-Setup) guide.

**Alternative**: You can place the config file anywhere and specify its location using the `--config-file` option.

## Usage

### Running the Script

### Basic Usage

Run the script with `-h` to see all available commands:

```bash
qbit-manage -h
# or if installed from source
python qbit_manage.py -h
```

### Common Usage Examples

**Run with default configuration:**
```bash
qbit-manage
```

**Run specific commands:**
```bash
qbit-manage --cat-update --tag-update
```

**Run with Web API and Web UI:**
```bash
qbit-manage --web-server
```
You can then access the Web UI in your browser at `http://localhost:8080`.

**Use custom configuration file:**
```bash
qbit-manage --config-file /path/to/your/config.yml
```

**Run in dry-run mode (preview changes without applying them):**
```bash
qbit-manage --dry-run --cat-update --tag-update
```

**Run on a schedule:**
```bash
qbit-manage --schedule 1440  # Run every 24 hours (1440 minutes)
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--config-file`, `-c` | Specify custom config file location |
| `--log-file`, `-lf` | Specify custom log file location |
| `--web-server`, `-ws` | Start the web server for API and UI |
| `--port`, `-p` | Web server port (default: 8080) |
| `--dry-run`, `-dr` | Preview changes without applying them |
| `--schedule`, `-sch` | Run on a schedule (minutes) |
| `--run`, `-r` | Run once and exit (no scheduler) |

For a complete list of commands and options, see the [Commands](Commands) documentation.

### Virtual Environment (Recommended)

For Python installations, it's recommended to use a virtual environment:

```bash
# Create virtual environment
python -m venv qbit-manage-env

# Activate virtual environment
# Linux/macOS:
source qbit-manage-env/bin/activate
# Windows:
qbit-manage-env\Scripts\activate

# Install qbit-manage
pip install qbit-manage

# Run qbit-manage
qbit-manage --help
```

### Updating

**PyPI installation:**
```bash
pip install --upgrade qbit-manage
```

**Source installation:**
```bash
cd qbit_manage
git pull
pip install . --upgrade
```
