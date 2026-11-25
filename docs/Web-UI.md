# qBit Manage Web UI

> [!IMPORTANT]
> Below is a summary of the WebUI. For details on the specific features and settings please see the rest of the wiki and sample config file to understand the functionality and description of each setting. The WebUI is effectively a GUI config file editor. You cannot edit environmental or container variables via the WebUI.

## Overview
The Web UI edits your YAML config files in a browser and runs commands on demand.

## Key Features
The qBit Manage Web UI offers a range of features designed to simplify your configuration and management tasks:
- **Visual Configuration Editor**: Easily edit your YAML configuration files through intuitive forms, eliminating the need for manual text editing.
- **Command Execution**: Run qBit Manage commands on demand directly from the Web UI, without waiting for scheduled runs.
- **Undo/Redo History**: Track and revert changes with a comprehensive history, ensuring you can always go back to a previous state.
- **Theme Support**: Switch between light and dark modes, with automatic detection of your system's preferred theme.
- **Responsive Design**: Access and manage your qBit Manage instance seamlessly from both desktop and mobile devices.
- **YAML Preview**: See a real-time preview of the YAML configuration as you make changes, ensuring accuracy before saving.

## Turn it on and log in

The web server is off by default. Turn it on with `--web-server` or `QBT_WEB_SERVER=true` (the desktop app does this for you). A login is always required.

1. Set `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD` before the first start, or read the generated password from `qbm_initial_password.txt` in your config folder.
2. Open the Web UI and sign in. Change the password under Security. Example of a valid password: `Wh1te-Rabbit!`.
3. For single sign-on, use the `oidc` mode.

## Upgrading to 5.0

- Docker and Unraid: add `QBT_WEB_USERNAME` and `QBT_WEB_PASSWORD`. Keep `QBT_WEB_SERVER=true`.
- Python, binary, headless, or seedbox: add `--web-server` if you use the Web UI. The default bind is now `127.0.0.1`.
- Desktop app: no change. Sign in with the generated password.

See [Security](Security#upgrading-to-50) for every install type.

## Port, host, and base URL

The web server uses port 8181 and binds to `127.0.0.1` by default (`0.0.0.0` in Docker). Change them with `--port`, `--host`, and `--base-url` or `QBT_PORT`, `QBT_HOST`, and `QBT_BASE_URL`. See [Installation](Installation#changing-the-web-server-port).

## Configuration Sections
The Web UI organizes all configuration options into logical sections for easy navigation and management:
1. **Commands**: Define and manage the various script execution workflows.
2. **qBittorrent Connection**: Set up and configure access to your qBittorrent instance.
3. **Settings**: Adjust general application preferences and behavior.
4. **Directory Paths**: Specify important file system locations used by qBit Manage.
5. **Categories**: Manage your torrent categories and their associated save paths.
6. **Category Changes**: Configure rules for bulk modification of torrent categories.
7. **Tracker Configuration**: Define settings and tags based on torrent tracker URLs.
8. **No Hard Links**: Handle torrents that do not have hard links, often used for media management.
9. **Share Limits**: Apply rules for torrent ratio and seeding time based on custom criteria.
10. **Recycle Bin**: Configure how deleted torrents and their data are managed.
11. **Orphaned Files**: Set up cleanup rules for files not associated with any torrents.
12. **Notifications**: Configure various alert and notification settings.
13. **Logs**: View application logs for monitoring and troubleshooting.

## Usage
To get started with the qBit Manage Web UI:
1. Ensure the qBit Manage backend is running and accessible. In Docker, set `QBT_WEB_SERVER=true`, `QBT_WEB_USERNAME`, and `QBT_WEB_PASSWORD`, and publish the port.
2. Access the Web UI through your web browser at the configured address (e.g., `http://localhost:8181` or `http://your-docker-host-ip:8181`).
3. Select your desired configuration file from the dropdown menu.
4. Navigate through the different configuration sections using the sidebar.
5. Use the preview button to review the generated YAML before saving.
6. Save your changes when you are satisfied with the configuration.
7. To run commands immediately, open the "Run Commands" modal (using the button in the toolbar or the `Ctrl+R` keyboard shortcut), select the commands you wish to run, and click "Run".

### Keyboard Shortcuts
For quicker navigation and actions, the Web UI supports the following keyboard shortcuts:
- `Ctrl+S`: Save the current configuration.
- `Ctrl+R`: Open the "Run Commands" modal to execute qBit Manage operations immediately.
- `Ctrl+Z`: Undo the last change.
- `Ctrl+Y`: Redo the last undone change.
- `Ctrl+/`: Toggle the "Help" modal.
- `Ctrl+P` or `Cmd+P`: Toggle the YAML preview.
- `Escape`: Close any open modals or panels.
