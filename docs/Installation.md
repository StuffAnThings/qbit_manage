# Installation Options

qbit_manage offers multiple installation methods to suit different use cases:

## Installation Methods

### 1. Desktop App (Recommended for most users)
- **Windows**: Download and run the `.exe` installer
- **macOS**: Download and install the `.dmg` package
- **Linux**: Download and install the `.deb` package

The desktop app provides a graphical interface and automatically handles configuration file setup.

### 2. Standalone Binary (Command-line)
- **Windows**: `qbit-manage-windows-amd64.exe`
- **macOS**: `qbit-manage-macos-arm64` (Apple Silicon) or `qbit-manage-macos-x86_64` (Intel)
- **Linux**: `qbit-manage-linux-amd64` (x86_64) or `qbit-manage-linux-arm64` (ARM64/Raspberry Pi)

Perfect for server environments, automation, or users who prefer command-line tools.

### 3. Docker Container
- Multi-architecture support (amd64, arm64, arm/v7)
- Ideal for containerized environments and NAS systems

### 4. Python Installation
- Install from source or PyPI
- For developers or users who want to modify the code

## Detailed Installation Guides

- [Desktop App Installation](#desktop-app-installation)
- [Standalone Binary Installation](#standalone-binary-installation)
- [Python/Source Installation](#pythonsource-installation)
- [Docker Installation](Docker-Installation)
- [unRAID Installation](Unraid-Installation)

## Desktop App Installation

### Windows
1. Download `qBit.Manage_<version>_x64-desktop-installer-setup.exe` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases)
2. Run the installer and follow the setup wizard
3. Launch qBit Manage from the Start Menu or desktop shortcut
4. The app will automatically create the configuration directory and files

### macOS
1. Download the appropriate `.dmg` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases):
   - `qBit.Manage_<version>_aarch64-desktop-installer.dmg` for Apple Silicon (M1+)
   - `qBit.Manage_<version>_x64-desktop-installer.dmg` for Intel Macs
2. Open the DMG file and drag qBit Manage to your Applications folder
3. The app is not code-signed. To open it, remove the quarantine attribute:
   ```bash
   xattr -cr /Applications/qBit\ Manage.app
   ```
4. Launch qBit Manage from Applications
5. The app will automatically create the configuration directory and files

### Linux
1. Download the appropriate `.deb` installer from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases):
   - `qBit.Manage_<version>_amd64-desktop-installer.deb` for x86_64 systems
   - `qBit.Manage_<version>_arm64-desktop-installer.deb` for ARM64 systems (Raspberry Pi, etc.)
2. Install using your package manager:
   ```bash
   sudo dpkg -i qBit.Manage_*-desktop-installer.deb
   sudo apt-get install -f  # Fix any dependency issues
   ```
3. Launch qBit Manage from your applications menu or run `qbit-manage` in terminal
4. The app will automatically create the configuration directory and files

## Standalone Binary Installation

### Windows
1. Download `qbit-manage-windows-amd64.exe` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases)
2. Place the executable in a directory of your choice (e.g., `C:\Program Files\qbit-manage\`)
3. Add the directory to your PATH environment variable (optional)
4. Run from Command Prompt or PowerShell:
   ```cmd
   qbit-manage-windows-amd64.exe --help
   ```

### macOS
1. Download the appropriate binary from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases):
   - `qbit-manage-macos-arm64` for Apple Silicon Macs (M1, M2, M3, etc.)
   - `qbit-manage-macos-x86_64` for Intel Macs
2. Remove the quarantine attribute and make executable:
   ```bash
   xattr -cr qbit-manage-macos-*
   chmod +x qbit-manage-macos-*
   ```
3. Move to a directory in your PATH (optional):
   ```bash
   sudo mv qbit-manage-macos-* /usr/local/bin/qbit-manage
   ```
4. Run the binary:
   ```bash
   ./qbit-manage-macos-* --help
   ```

### Linux
1. Download the appropriate binary from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases):
   - `qbit-manage-linux-amd64` for x86_64 systems
   - `qbit-manage-linux-arm64` for ARM64 systems (Raspberry Pi, etc.)
2. Make the binary executable (substitute `arm64` for ARM64 systems):
   ```bash
   chmod +x qbit-manage-linux-amd64
   ```
3. Move to a directory in your PATH (optional):
   ```bash
   sudo mv qbit-manage-linux-amd64 /usr/local/bin/qbit-manage
   ```
4. Run the binary:
   ```bash
   ./qbit-manage-linux-amd64 --help
   ```

## Python/Source Installation

For developers or users who want to modify the code, you can install from source or PyPI.

### Prerequisites
- Python 3.9 or higher
- Git (for source installation)

### Method 1: Install from PyPI

```bash
# Install uv first
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install qbit-manage
uv tool install qbit-manage
```

### Method 2: Install from Source

```bash
# Clone the repository
git clone https://github.com/StuffAnThings/qbit_manage.git
cd qbit_manage

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the package
uv tool install .
```

### Running qbit-manage

After installation, you can run qbit-manage from anywhere:

```bash
# Show help and available options
qbit-manage --help

# Run once (without scheduler)
qbit-manage --run

# Run with web UI (default on desktop)
qbit-manage --web-server

# Run without web UI (force disable)
qbit-manage --web-server=False
```

### Usage

After installation, you can run qbit_manage using:

```bash
qbit-manage --help
```

> [!TIP]
> For Python installations, it's recommended to use a virtual environment to avoid conflicts with other packages.

### Development Installation

For development work or to contribute to the project:

```bash
# Clone the repository
git clone https://github.com/StuffAnThings/qbit_manage.git
cd qbit_manage

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows

# Install in development mode
uv pip install -e .
```

### Updating

**Tool installation:**
```bash
uv tool upgrade qbit-manage
```

**Development installation:**
```bash
cd qbit_manage
git pull
uv pip install -e . --upgrade
```

## Quick Reference: Default Configuration File Locations

### Desktop App & Standalone Binary
- **Windows**: `%APPDATA%\qbit-manage\config.yml`
- **macOS**: `~/Library/Application Support/qbit-manage/config.yml`
- **Linux**: `~/.config/qbit-manage/config.yml`

### Docker Installation
- **Container Path**: `/app/config.yml`
- **Host Mount**: Typically mounted from `/path/to/your/config:/config`

### Custom Location
You can override the default location using the `--config-dir` or `-cd` command line option:
```bash
qbit-manage --config-dir /path/to/your/config/directory
```
