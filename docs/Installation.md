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
- **Linux**: `qbit-manage-linux-amd64`

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
- [Docker Installation](Docker-Installation)
- [Python/Source Installation](Local-Installations)
- [unRAID Installation](Unraid-Installation)
- [NIX Installation](Nix-Installation)

## Desktop App Installation

### Windows
1. Download `qbit-manage-*-desktop-installer-setup.exe` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases)
2. Run the installer and follow the setup wizard
3. Launch qbit_manage from the Start Menu or desktop shortcut
4. The app will automatically create the configuration directory and files

### macOS
1. Download `qbit-manage-*-desktop-installer.dmg` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases)
2. Open the DMG file and drag qbit_manage to your Applications folder
3. Launch qbit_manage from Applications (you may need to allow it in System Preferences > Security & Privacy)
4. The app will automatically create the configuration directory and files

### Linux
1. Download `qbit-manage-*-desktop-installer.deb` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases)
2. Install using your package manager:
   ```bash
   sudo dpkg -i qbit-manage-*-desktop-installer.deb
   sudo apt-get install -f  # Fix any dependency issues
   ```
3. Launch qbit_manage from your applications menu or run `qbit-manage` in terminal
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
2. Make the binary executable:
   ```bash
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
1. Download `qbit-manage-linux-amd64` from the [releases page](https://github.com/StuffAnThings/qbit_manage/releases)
2. Make the binary executable:
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

## Quick Reference: Default Configuration File Locations

### Desktop App & Standalone Binary
- **Windows**: `%APPDATA%\qbit-manage\config.yml`
- **macOS**: `~/Library/Application Support/qbit-manage/config.yml`
- **Linux**: `~/.config/qbit-manage/config.yml`

### Docker Installation
- **Container Path**: `/app/config.yml`
- **Host Mount**: Typically mounted from `/path/to/your/config:/config`

### Custom Location
You can override the default location using the `--config-file` or `-c` command line option:
```bash
qbit-manage --config-file /path/to/your/config.yml
```
