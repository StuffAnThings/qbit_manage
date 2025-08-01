# Standalone Scripts

This section provides documentation for standalone Python scripts located in the `scripts/` directory. These scripts offer additional functionalities that can be run independently of the main `qbit_manage.py` application.

## Scripts Overview

### [`delete_torrents_on_low_disk_space.py`](scripts/delete_torrents_on_low_disk_space.py)
This script automatically deletes torrents when your drive space falls below a specified threshold. It allows you to set minimum torrent age and share ratio for deletion, and optionally delete incomplete torrents. Torrents with the most seeds are prioritized for deletion, and only those with a single hardlink are removed to ensure space is freed. It monitors a configured drive path, and multiple copies of the script can be used for multiple drives.

**Usage:**
```bash
python scripts/delete_torrents_on_low_disk_space.py
```

**Configuration:**
Edit the variables directly within the script:
- `qbt_login`: qBittorrent WebUI login details (`host`, `port`, `username`, `password`).
- `PATH`: Path of the drive to monitor (e.g., `"M:"` or `"/mnt/user/data"`). Only torrents with paths starting with this will be considered for deletion.
- `MIN_FREE_SPACE`: Minimum free space in GB.
- `MIN_FREE_USAGE`: Minimum free space in decimal percentage (0 to 1).
- `MIN_TORRENT_SHARE_RATIO`: Minimum seeding ratio of a torrent to be eligible for deletion (0 to infinity).
- `MIN_TORRENT_AGE`: Minimum age of a torrent in days (based on seeding time) to be eligible for deletion.
- `ALLOW_INCOMPLETE_TORRENT_DELETIONS`: Set to `True` to also delete torrents that haven't finished downloading. `MIN_TORRENT_AGE` will then be based on `time_active`.
- `PREFER_PRIVATE_TORRENTS`: Set to `True` to delete public torrents before private ones, regardless of seed difference.

### [`edit_passkey.py`](scripts/edit_passkey.py)
This script is used to update passkeys for torrents from a specific tracker in qBittorrent. It iterates through your torrents, finds those matching a defined tracker and old passkey, and replaces the old passkey with a new one in the tracker URL.

**Usage:**
```bash
python scripts/edit_passkey.py
```

**Configuration:**
Edit the variables directly within the script:
- `qbt_host`: qBittorrent host including port (e.g., `"qbittorrent:8080"`).
- `qbt_user`: qBittorrent WebUI username.
- `qbt_pass`: qBittorrent WebUI password.
- `TRACKER`: A keyword or part of the tracker URL to identify torrents (e.g., `"blutopia"` or `"your-tracker.com"`).
- `OLD_PASSKEY`: The old passkey string to be replaced.
- `NEW_PASSKEY`: The new passkey string to replace the old one.

### [`edit_tracker.py`](scripts/edit_tracker.py)
This script is used to change tracker URLs for torrents in qBittorrent. It finds torrents associated with an old tracker URL and updates them to a new tracker URL.

**Usage:**
```bash
python scripts/edit_tracker.py
```

**Configuration:**
Edit the variables directly within the script:
- `qbt_host`: qBittorrent host including port (e.g., `"qbittorrent:8080"`).
- `qbt_user`: qBittorrent WebUI username.
- `qbt_pass`: qBittorrent WebUI password.
- `OLD_TRACKER`: The full URL of the tracker you want to replace (e.g., `"https://blutopia.xyz"`).
- `NEW_TRACKER`: The full URL of the new tracker to replace it with (e.g., `"https://blutopia.cc"`).

### [`mover.py`](scripts/mover.py)
This script is designed to pause torrents older than a specified age range, trigger the Unraid mover process (to move files from cache to array disks), and then resume the paused torrents once the mover completes. It can filter torrents by their status and optionally by cache mount point.

**Usage:**
```bash
python scripts/mover.py --host <qb_host:port> [--user <username>] [--password <password>] [--cache-mount <path>] [--days-from <days>] [--days-to <days>] [--mover-old] [--status-filter <status>]
```

**Arguments:**
- `--host`: **(Required)** qBittorrent host including port (e.g., `"qbittorrent:8080"`).
- `-u`, `--user`: qBittorrent WebUI username (default: `admin`).
- `-p`, `--password`: qBittorrent WebUI password (default: `adminadmin`).
- `--cache-mount`: Cache mount point in Unraid (e.g., `"/mnt/cache"`). Use this to filter torrents only on the cache mount, especially if following TRaSH Guides folder structure.
- `--days-from`: Number of days from the current date to start pausing torrents (inclusive, default: `0`).
- `--days-to`: Number of days from the current date to stop pausing torrents (inclusive, default: `2`). `days-from` must be less than or equal to `days-to`.
- `--mover-old`: Use `mover.old` instead of `mover`. Useful if you're using the Mover Tuning Plugin.
- `--status-filter`: Define a status to limit which torrents to pause. Useful if you want to leave certain torrents unpaused. Choices include: `all`, `downloading`, `seeding`, `completed`, `paused`, `stopped`, `active`, `inactive`, `resumed`, `running`, `stalled`, `stalled_uploading`, `stalled_downloading`, `checking`, `moving`, `errored`. (default: `completed`).

### [`remove_cross-seed_tag.py`](scripts/remove_cross-seed_tag.py)
This script removes a specific tag (defaulting to 'cross-seed') from all torrents in your qBittorrent client. You can configure the qBittorrent connection details and the tag to be removed.

**Usage:**
```bash
python scripts/remove_cross-seed_tag.py
```

**Configuration:**
Edit the variables directly within the script:
- `QBIT_HOST`: qBittorrent host including port (e.g., `"http://localhost:8080"`). Can be overridden by `QBT_HOST` environment variable.
- `QBIT_USERNAME`: qBittorrent WebUI username (default: `admin`). Can be overridden by `QBT_USERNAME` environment variable.
- `QBIT_PASSWORD`: qBittorrent WebUI password (default: `YOURPASSWORD`). Can be overridden by `QBT_PASSWORD` environment variable.
- `CROSS_SEED_TAG`: The tag to be removed from torrents (default: `"cross-seed"`).

### [`restore_torrents.py`](scripts/restore_torrents.py)
This script restores torrents and their associated files from a Recycle Bin directory back into qBittorrent and their original download locations. It provides an interactive interface to select torrents by name, category, tracker, or all. Restored torrents are added in a paused state for manual rechecking.

**Usage:**
```bash
python scripts/restore_torrents.py [--dry-run]
```

**Arguments:**
- `--dry-run`: Perform a dry run without actually moving files or injecting torrents into qBittorrent.

**Configuration:**
Edit the variables directly within the script:
- `QBIT_HOST`: Hostname or IP address of the qBittorrent WebUI (e.g., `"http://qbittorrent:8080"`).
- `QBIT_USERNAME`: Username for the qBittorrent WebUI.
- `QBIT_PASSWORD`: Password for the qBittorrent WebUI.
- `RECYCLE_BIN_DIR`: The directory where torrents and their metadata are moved before deletion (e.g., `"/data/torrents/.RecycleBin"`).
- `ROOT_DIR`: The root directory where your downloads are stored (e.g., `"/data/torrents/"`).
- `LOG_LEVEL`: Set the logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).

### [`update-readme-version.py`](scripts/update-readme-version.py)
This script updates the `SUPPORTED_VERSIONS.json` file with the latest supported qBittorrent version and the current `qbittorrent-api` version. It is typically run as part of a CI/CD pipeline or pre-commit hook to keep version information up-to-date.

**Usage:**
```bash
python scripts/update-readme-version.py <branch_name>
```

**Arguments:**
- `<branch_name>`: **(Required)** The name of the current Git branch (e.g., `main`, `develop`). This is used as a key in the `SUPPORTED_VERSIONS.json` file.

**Configuration:**
- `versions_file_path`: Path to the `SUPPORTED_VERSIONS.json` file (default: `"SUPPORTED_VERSIONS.json"`).
- The script automatically extracts the `qbittorrent-api` version from `pyproject.toml`.

### [`ban_peers.py`](scripts/ban_peers.py)
This script bans one or more peers from qBittorrent using the provided peer addresses in 'host:port' format or multiple separated by '|'.

**Usage:**
```bash
python scripts/ban_peers.py --peers "127.0.0.1:8080|example.com:80" [options]
```

**Arguments:**
- `--host`: qBittorrent host (default: "localhost").
- `--port`: qBittorrent port (default: 8080).
- `--user`: Username.
- `--pass`: Password.
- `--peers`: Peers to ban, separated by '|' (required).
- `--dry-run`: Dry run mode without banning.
