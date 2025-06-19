import argparse
import json
import os
import shutil
import sys

from qbittorrentapi import APIConnectionError
from qbittorrentapi import Client
from qbittorrentapi import LoginFailed

# Configuration Constants
QBIT_HOST = "http://qbittorrent:8080"  # Replace with your qBittorrent host
QBIT_USERNAME = ""  # Replace with your qBittorrent username
QBIT_PASSWORD = ""  # Replace with your qBittorrent password
RECYCLE_BIN_DIR = "/qbm/torrents/.RecycleBin"
ROOT_DIR = "/qbm/torrents/"


def main():
    parser = argparse.ArgumentParser(description="Restore torrents from Recyclebin.")
    parser.add_argument("--name", help="Filter by torrent name (partial match).")
    parser.add_argument("--category", help="Filter by torrent category.")
    parser.add_argument("--tracker", help="Filter by tracker URL (partial match).")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without moving files or injecting torrents.")
    args = parser.parse_args()

    torrents_metadata = load_torrents_metadata()
    filtered_torrents = filter_torrents(torrents_metadata, args.name, args.category, args.tracker)

    if not filtered_torrents:
        print("No torrents found matching the criteria.")
        return

    print(f"Found {len(filtered_torrents)} torrent(s) to restore.")
    for torrent in filtered_torrents:
        print(
            f"- {torrent['torrent_name']} "
            f"(Category: {torrent['category']}, "
            f"Trackers: {', '.join(torrent['tracker_torrent_files'].keys()) if torrent['tracker_torrent_files'] else 'N/A'})"
        )

    confirm = input("Proceed with restoration? (yes/no): ").lower()
    if confirm not in ["yes", "y"]:
        print("Restoration cancelled.")
        return

    restore_torrents(filtered_torrents, args.dry_run)


def load_torrents_metadata():
    metadata_path = os.path.join(RECYCLE_BIN_DIR, "torrents_json")
    torrents_data = []
    if not os.path.exists(metadata_path):
        print(f"Error: Metadata directory not found at {metadata_path}")
        return torrents_data

    for filename in os.listdir(metadata_path):
        if filename.endswith(".json"):
            filepath = os.path.join(metadata_path, filename)
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    torrents_data.append(data)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from {filepath}: {e}")
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
    return torrents_data


def filter_torrents(torrents_data, name_filter, category_filter, tracker_filter):
    filtered = []
    for torrent in torrents_data:
        match = True
        if name_filter and name_filter.lower() not in torrent.get("torrent_name", "").lower():
            match = False
        if category_filter and category_filter.lower() != torrent.get("category", "").lower():
            match = False
        if tracker_filter:
            found_tracker = False
            for tracker_url in torrent.get("tracker_torrent_files", {}).keys():
                if tracker_filter.lower() in tracker_url.lower():
                    found_tracker = True
                    break
            if not found_tracker:
                match = False
        if match:
            filtered.append(torrent)
    return filtered


def restore_torrents(torrents_to_restore, dry_run=False):
    print("\nStarting torrent restoration...")

    client = None
    # Authenticate with qBittorrent
    try:
        client = Client(
            host=QBIT_HOST,
            username=QBIT_USERNAME,
            password=QBIT_PASSWORD,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={"timeout": (45, 60)},
        )
        client.auth_log_in()
        print("Successfully logged in to qBittorrent.")
    except LoginFailed:
        print("Failed to login to qBittorrent: Invalid username/password.")
        sys.exit(1)
    except APIConnectionError as e:
        print(f"Failed to connect to qBittorrent: {e}. Please check host and ensure qBittorrent is running.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during qBittorrent login: {e}")
        sys.exit(1)

    qb_version = None
    if client:  # Only try to get version if client was initialized
        qb_version = client.app.version
        if not qb_version:
            print("Could not determine qBittorrent version. Cannot proceed with torrent injection.")
            return
        print(f"qBittorrent Version: {qb_version}")

    for torrent in torrents_to_restore:
        torrent_name = torrent.get("torrent_name", "Unknown")
        print(f"\nRestoring: {torrent_name}")

        # 1. Move files back to ROOT_DIR
        if torrent.get("deleted_contents", False):
            print(f"  Restoring contents for {torrent_name}...")
            for file_path_relative in torrent.get("files", []):
                src_file_path = os.path.join(RECYCLE_BIN_DIR, file_path_relative)
                dest_file_path = os.path.join(ROOT_DIR, file_path_relative)
                dest_dir = os.path.dirname(dest_file_path)

                if os.path.exists(src_file_path):
                    os.makedirs(dest_dir, exist_ok=True)
                    if not dry_run:
                        try:
                            shutil.move(src_file_path, dest_file_path)
                            print(f"  Moved file: {file_path_relative}")
                        except Exception as e:
                            print(f"  Error moving {file_path_relative}: {e}")
                    else:
                        print(f"  [DRY RUN] Would move file: {src_file_path} to {dest_file_path}")
                else:
                    print(f"  Warning: Source file not found for {file_path_relative}. Skipping move.")
        else:
            print(f"  Contents were not marked as deleted. Skipping file movement for {torrent_name}.")

        # 2. Inject torrent back into qBittorrent
        torrent_hash = None
        torrent_file_path = None

        tracker_info = next(iter(torrent.get("tracker_torrent_files", {}).values()), None)
        if tracker_info:
            for f_name in tracker_info:
                if f_name.endswith(".torrent"):
                    import re

                    # Try to extract hash from filename like "2ac1dc887ca635df34ea5168348074317edb2e59.torrent"
                    if len(f_name) == 40 + len(".torrent"):
                        torrent_hash = f_name.replace(".torrent", "")
                        break
                    # Try to extract hash from filename like "Torrent.Name [hash].torrent"
                    match = re.search(r"\[([0-9a-fA-F]{40})\]\.torrent$", f_name)
                    if match:
                        torrent_hash = match.group(1)
                        break

        if not torrent_hash:
            print(f"  Could not determine torrent hash for {torrent_name}. Skipping injection.")
            continue

        # Convert qBittorrent version string to a comparable format (e.g., tuple of integers)
        if qb_version:
            qb_version_tuple = tuple(map(int, qb_version.lstrip("v").split(".")))
        min_version_for_export = (4, 5, 0)

        if qb_version_tuple >= min_version_for_export:
            # Use torrents_export folder
            torrent_file_name = f"{torrent_hash}.torrent"
            torrent_file_path = os.path.join(RECYCLE_BIN_DIR, "torrents_export", torrent_file_name)
            if not os.path.exists(torrent_file_path):
                print(f"  Error: Exported torrent file not found at {torrent_file_path}. Skipping injection.")
                continue

            if not dry_run:
                try:
                    with open(torrent_file_path, "rb") as f:
                        torrent_content = f.read()
                    client.torrents_add(torrent_files=torrent_content, save_path=ROOT_DIR, category=torrent.get("category"))
                    print(f"  Injected torrent {torrent_name} using torrents_export.")
                except Exception as e:
                    print(f"  Error injecting torrent {torrent_name}: {e}")
            else:
                print(f"  [DRY RUN] Would inject torrent {torrent_name} using torrents_export from {torrent_file_path}.")

        else:
            # Use torrents folder for older versions
            torrent_file_name = f"{torrent_hash}.torrent"
            torrent_file_path = os.path.join(RECYCLE_BIN_DIR, "torrents", torrent_file_name)

            if not os.path.exists(torrent_file_path):
                print(f"  Error: Torrent file not found at {torrent_file_path}. Skipping injection.")
                continue

            if not dry_run:
                try:
                    with open(torrent_file_path, "rb") as f:
                        torrent_content = f.read()
                    # For older versions, qbittorrent-api's torrents_add should still work.
                    # The fastresume file is typically managed by qBittorrent itself when adding.
                    # If the fastresume file needs to be explicitly moved, it would go to qBittorrent's
                    # configuration directory, which is outside the scope of this script's current
                    # knowledge of ROOT_DIR and RECYCLE_BIN_DIR.
                    client.torrents_add(torrent_files=torrent_content, save_path=ROOT_DIR, category=torrent.get("category"))
                    print(f"  Injected torrent {torrent_name} using torrents folder (older version method).")
                except Exception as e:
                    print(f"  Error injecting torrent {torrent_name}: {e}")
            else:
                print(
                    f"  [DRY RUN] Would inject torrent {torrent_name} using torrents "
                    f"folder from {torrent_file_path} (older version method)."
                )


if __name__ == "__main__":
    main()
