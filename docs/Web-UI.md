# qBit Manage Web UI (Develop)

## Overview
The qBit Manage Web UI provides a modern interface for configuring and managing qBit Manage. It offers real-time editing of YAML configuration files through an intuitive visual interface, eliminating the need for manual file editing.

## Key Features
The qBit Manage Web UI offers a range of features designed to simplify your configuration and management tasks:
- **Visual Configuration Editor**: Easily edit your YAML configuration files through intuitive forms, eliminating the need for manual text editing.
- **Command Execution**: Run qBit Manage commands on demand directly from the Web UI, without waiting for scheduled runs.
- **Undo/Redo History**: Track and revert changes with a comprehensive history, ensuring you can always go back to a previous state.
- **Theme Support**: Switch between light and dark modes, with automatic detection of your system's preferred theme.
- **Responsive Design**: Access and manage your qBit Manage instance seamlessly from both desktop and mobile devices.
- **YAML Preview**: See a real-time preview of the YAML configuration as you make changes, ensuring accuracy before saving.

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
1. Ensure the qBit Manage backend is running and accessible. If running in Docker, ensure the web server is enabled and the port is mapped (e.g., `QBT_WEB_SERVER=true` and `ports: - "8080:8080"`).
2. Access the Web UI through your web browser at the configured address (e.g., `http://localhost:8080` or `http://your-docker-host-ip:8080`).
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
