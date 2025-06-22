# restore_torrents.py
# Version: 1.0.0
#
# This script restores torrents and their files from a Recycle Bin directory
# to qBittorrent and their original locations.
#
# Usage:
# python scripts/restore_torrents.py [--dry-run]
#
# Features:
# - Interactive selection by torrent name, category, tracker, or all.
# - Dry run mode for testing without actual changes.
# - Injected torrents are added in a paused state to allow users to manually recheck or re-verify.
# - Requires qbittorrentapi (`pip install qbittorrentapi`).
#
# Please fill in the configuration details below in the Configuration Constants section.

import argparse
import json
import logging
import os
import re
import shutil
import sys

from qbittorrentapi import APIConnectionError
from qbittorrentapi import Client
from qbittorrentapi import LoginFailed

### Configuration Constants ###
QBIT_HOST = "http://qbittorrent:8080"  # Hostname or IP address of the qBittorrent WebUI.
QBIT_USERNAME = ""  # Username for the qBittorrent WebUI.
QBIT_PASSWORD = ""  # Password for the qBittorrent WebUI.
RECYCLE_BIN_DIR = "/data/torrents/.RecycleBin"  # Directory where torrents are moved before deletion.
ROOT_DIR = "/data/torrents/"  # Root directory where your downloads are stored.
LOG_LEVEL = "INFO"  # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
### End of Configuration Constants ###


def main():
    parser = argparse.ArgumentParser(description="Restore torrents from Recyclebin.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without moving files or injecting torrents.")
    args = parser.parse_args()

    # Check if ROOT_DIR exists and is a directory
    if not os.path.isdir(ROOT_DIR):
        logging.error(f"Error: ROOT_DIR '{ROOT_DIR}' does not exist or is not a directory. Please check your configuration.")
        sys.exit(1)

    # Check if RECYCLE_BIN_DIR exists and is a directory
    if not os.path.isdir(RECYCLE_BIN_DIR):
        logging.error(
            f"Error: RECYCLE_BIN_DIR '{RECYCLE_BIN_DIR}' does not exist or is not a directory. Please check your configuration."
        )
        sys.exit(1)

    # Configure logging
    log_level = getattr(logging, LOG_LEVEL.upper())
    script_dir = os.path.dirname(__file__)
    log_file_path = os.path.join(script_dir, "restore_torrents.log")
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    console_formatter = logging.Formatter("%(message)s")

    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)  # Ensure file handler respects the overall log level

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)  # Ensure console handler respects the overall log level

    logging.basicConfig(level=log_level, handlers=[file_handler, console_handler])

    if args.dry_run:
        logging.info("*** DRY RUN MODE ACTIVE *** No files will be moved and no torrents will be injected.")
    torrents_metadata = load_torrents_metadata()
    filter_type, filter_value = get_user_restore_choice(torrents_metadata)

    name_filter = None
    category_filter = None
    tracker_filter = None

    if filter_type == "name":
        name_filter = filter_value
        filtered_torrents = filter_torrents(torrents_metadata, name_filter, None, None)
    elif filter_type == "category":
        category_filter = filter_value
        filtered_torrents = filter_torrents(torrents_metadata, None, category_filter, None)
    elif filter_type == "tracker":
        tracker_filter = filter_value
        filtered_torrents = filter_torrents(torrents_metadata, None, None, tracker_filter)
    elif filter_type == "all":
        filtered_torrents = torrents_metadata
    else:
        logging.error("Invalid filter choice. Exiting.")
        return

    if not filtered_torrents:
        logging.info("No torrents found matching the criteria.")
        return

    # Prepare a flattened list of individual torrents to restore
    torrents_to_process = []
    qb_version = None
    try:
        client = Client(
            host=QBIT_HOST,
            username=QBIT_USERNAME,
            password=QBIT_PASSWORD,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={"timeout": (45, 60)},
        )
        client.auth_log_in()
        qb_version = client.app.version
        if qb_version:
            qb_version_tuple = tuple(map(int, qb_version.lstrip("v").split(".")))
        else:
            qb_version_tuple = None  # Cannot determine version, default to newer logic
    except (LoginFailed, APIConnectionError, Exception) as e:
        logging.warning(f"Could not connect to qBittorrent to determine version: {e}. Defaulting to newer torrent file format.")
        qb_version_tuple = None  # Default to newer logic if connection fails

    for torrent_entry in filtered_torrents:
        individual_torrents = get_torrent_file_for_version(torrent_entry.get("tracker_torrent_files", {}), qb_version_tuple)
        for tracker_url, torrent_hash, torrent_file_name in individual_torrents:  # Unpack tracker_url
            torrents_to_process.append(
                {
                    "torrent_name": torrent_entry.get("torrent_name"),
                    "category": torrent_entry.get("category"),
                    "tracker": tracker_url,  # Add tracker information here
                    "files": torrent_entry.get("files", []),
                    "deleted_contents": torrent_entry.get("deleted_contents", False),
                    "torrent_hash": torrent_hash,
                    "torrent_file_name": torrent_file_name,
                }
            )

    if not torrents_to_process:
        logging.info("No individual torrent files found to restore based on your selection and qBittorrent version.")
        return

    logging.info(f"Found {len(torrents_to_process)} individual torrents to restore.")
    for torrent in torrents_to_process:
        logging.info(
            f"- {torrent['torrent_name']} "
            f"(Category: {torrent['category']}, "
            f"Tracker: {torrent['tracker']}, "
            f"File: {torrent['torrent_file_name']})"
        )

    if args.dry_run:
        logging.info("\n*** DRY RUN MODE ACTIVE *** No files will be moved and no torrents will be injected.")
    confirm = input("Proceed with restoration? (yes/no): ").lower()
    if confirm not in ["yes", "y"]:
        logging.info("Restoration cancelled.")
        return

    restore_torrents(torrents_to_process, args.dry_run)


def load_torrents_metadata():
    metadata_path = os.path.join(RECYCLE_BIN_DIR, "torrents_json")
    torrents_data = []
    if not os.path.exists(metadata_path):
        logging.error(f"Metadata directory not found at {metadata_path}")
        sys.exit(1)
        return torrents_data

    for filename in os.listdir(metadata_path):
        if filename.endswith(".json"):
            filepath = os.path.join(metadata_path, filename)
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    torrents_data.append(data)
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON from {filepath}: {e}")
            except Exception as e:
                logging.error(f"Error reading {filepath}: {e}")
    return torrents_data


def get_user_restore_choice(torrents_metadata):
    while True:
        logging.info("\nHow would you like to restore torrents?")
        logging.info("1) Torrent Name")
        logging.info("2) Category")
        logging.info("3) Tracker")
        logging.info("4) All (torrents + files)")
        choice = input("Enter your choice (1-4, or Enter for default '1'): ")
        if not choice:
            choice = "1"  # Default to Torrent Name

        if choice == "0":  # '0' is not a valid option for the main menu
            logging.warning("Invalid choice. '0' is not an option here. Please enter a number between 1 and 4.")
            continue
        elif choice == "1":
            while True:
                keywords = input("Enter keywords for torrent name (partial match): ").lower().split(",")
                keywords = [k.strip() for k in keywords if k.strip()]

                if not keywords:
                    logging.warning("Please enter at least one keyword.")
                    continue

                matching_torrents = []
                for torrent in torrents_metadata:
                    torrent_name = torrent.get("torrent_name", "").lower()
                    if all(keyword in torrent_name for keyword in keywords):
                        matching_torrents.append(torrent)

                if not matching_torrents:
                    logging.warning("No torrents found matching your keywords. Please try again.")
                    continue

                if len(matching_torrents) > 15:
                    logging.info(f"Found {len(matching_torrents)} torrents. Please be more specific with your keywords.")
                    for i, torrent in enumerate(matching_torrents[:15]):  # Display first 15
                        logging.info(f"{i + 1}) {torrent['torrent_name']}")
                    continue  # Loop back to ask for more specific keywords

                logging.info("\nMatching Torrents:")
                for i, torrent in enumerate(matching_torrents):
                    logging.info(f"{i + 1}) {torrent['torrent_name']}")

                while True:
                    try:
                        torrent_choice = input(
                            f"Select a torrent by number (1-{len(matching_torrents)}), "
                            f"Enter for default '1', or '0' to re-enter keywords): "
                        )
                        if not torrent_choice:
                            torrent_choice = "1"  # Default to the first matching torrent
                        if torrent_choice == "0":
                            break  # Break inner loop to re-enter keywords

                        torrent_choice = int(torrent_choice)
                        if 1 <= torrent_choice <= len(matching_torrents):
                            logging.info(
                                f"User selected to restore by name: {matching_torrents[torrent_choice - 1]['torrent_name']}"
                            )
                            return "name", matching_torrents[torrent_choice - 1]["torrent_name"]
                        else:
                            logging.warning("Invalid choice. Please enter a number within the range or '0'.")
                    except ValueError:
                        logging.warning("Invalid input. Please enter a number or '0'.")
        elif choice == "2":
            categories = set()
            for torrent in torrents_metadata:
                category = torrent.get("category")
                if category:
                    categories.add(category)

            if not categories:
                logging.warning("No categories found in recycle bin metadata.")
                continue

            logging.info("\nAvailable Categories:")
            sorted_categories = sorted(list(categories))
            for i, cat in enumerate(sorted_categories):
                logging.info(f"{i + 1}) {cat}")

            while True:
                category_choice_str = input(
                    f"Select a category (1-{len(sorted_categories)}, Enter for default '1', or '0' to go back): "
                )
                if not category_choice_str:
                    category_choice_str = "1"  # Default to the first category

                if category_choice_str == "0":
                    logging.info("User chose to go back from category selection.")
                    break  # Go back to main menu choice

                try:
                    category_choice = int(category_choice_str)
                    if 1 <= category_choice <= len(sorted_categories):
                        logging.info(f"User selected to restore by category: {sorted_categories[category_choice - 1]}")
                        return "category", sorted_categories[category_choice - 1]
                    else:
                        logging.warning("Invalid choice. Please enter a number within the range or '0'.")
                except ValueError:
                    logging.warning("Invalid input. Please enter a number or '0'.")
        elif choice == "3":
            trackers = set()
            for torrent in torrents_metadata:
                for tracker_url in torrent.get("tracker_torrent_files", {}).keys():
                    trackers.add(tracker_url)

            if not trackers:
                logging.warning("No trackers found in recycle bin metadata.")
                continue

            logging.info("\nAvailable Trackers:")
            sorted_trackers = sorted(list(trackers))
            for i, tracker in enumerate(sorted_trackers):
                logging.info(f"{i + 1}) {tracker}")

            while True:
                tracker_choice_str = input(
                    f"Select a tracker (1-{len(sorted_trackers)}, Enter for default '1', or '0' to go back): "
                )
                if not tracker_choice_str:
                    tracker_choice_str = "1"  # Default to the first tracker

                if tracker_choice_str == "0":
                    logging.info("User chose to go back from tracker selection.")
                    break  # Go back to main menu choice

                try:
                    tracker_choice = int(tracker_choice_str)
                    if 1 <= tracker_choice <= len(sorted_trackers):
                        logging.info(f"User selected to restore by tracker: {sorted_trackers[tracker_choice - 1]}")
                        return "tracker", sorted_trackers[tracker_choice - 1]
                    else:
                        logging.warning("Invalid choice. Please enter a number within the range or '0'.")
                except ValueError:
                    logging.warning("Invalid input. Please enter a number or '0'.")
        elif choice == "4":
            logging.info("User selected to restore all torrents.")
            return "all", None
        else:
            logging.warning("Invalid choice. Please enter a number between 1 and 4.")


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


def get_torrent_file_for_version(tracker_torrent_files, qb_version_tuple):
    min_version_for_export = (4, 5, 0)

    torrents_to_return = []  # This will store all (tracker_url, hash, filename) tuples

    for tracker_url, files_list in tracker_torrent_files.items():
        current_full_hash = None
        current_newer_version_torrent_filename = None
        current_older_version_torrent_filename = None

        for f_name in files_list:
            # Attempt to extract full hash from filename like "2ac1dc887ca635df34ea5168348074317edb2e59.torrent"
            if len(f_name) == 40 + len(".torrent") and f_name.endswith(".torrent"):
                potential_full_hash = f_name.replace(".torrent", "")
                if re.match(r"^[0-9a-fA-F]{40}$", potential_full_hash):
                    current_full_hash = potential_full_hash
                    current_older_version_torrent_filename = f_name
            # Attempt to extract 8-digit hash from filename like "Torrent.Name [hash].torrent"
            elif re.search(r"\[([0-9a-fA-F]{8})\]\.torrent$", f_name):
                match = re.search(r"\[([0-9a-fA-F]{8})\]\.torrent$", f_name)
                if match:
                    # Store this as a potential newer version filename.
                    # We'll confirm it matches the full hash later.
                    current_newer_version_torrent_filename = f_name

        if not current_full_hash:
            # If we couldn't find a full hash filename for this tracker's files, skip this entry.
            continue

        # Now that we have the full hash for this tracker's entry,
        # we can refine the newer_version_torrent_filename if it was found.
        if current_newer_version_torrent_filename:
            # Re-check the newer_version_torrent_filename against the current_full_hash
            # to ensure the 8-digit hash matches the last 8 digits of the full hash.
            match = re.search(r"\[([0-9a-fA-F]{8})\]\.torrent$", current_newer_version_torrent_filename)
            if not (match and match.group(1).lower() == current_full_hash[-8:].lower()):
                current_newer_version_torrent_filename = None  # Invalidate if it doesn't match

        # Determine which torrent file to add to the list based on qBittorrent version
        if qb_version_tuple and qb_version_tuple >= min_version_for_export:
            if current_newer_version_torrent_filename:
                torrents_to_return.append((tracker_url, current_full_hash, current_newer_version_torrent_filename))
            elif current_older_version_torrent_filename:  # Fallback if newer format not found but older is
                torrents_to_return.append((tracker_url, current_full_hash, current_older_version_torrent_filename))
        else:  # Default to older version logic if qb_version_tuple is None or older
            if current_older_version_torrent_filename:
                torrents_to_return.append((tracker_url, current_full_hash, current_older_version_torrent_filename))
            elif current_newer_version_torrent_filename:  # Fallback if older format not found but newer is
                torrents_to_return.append((tracker_url, current_full_hash, current_newer_version_torrent_filename))

    return torrents_to_return  # Return the list of all found torrents


def restore_torrents(torrents_to_restore, dry_run=False):
    logging.info("\nStarting torrent restoration...")

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
        logging.info("Successfully logged in to qBittorrent.")
    except LoginFailed:
        logging.error("Failed to login to qBittorrent: Invalid username/password.")
        sys.exit(1)
    except APIConnectionError as e:
        logging.error(f"Failed to connect to qBittorrent: {e}. Please check host and ensure qBittorrent is running.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred during qBittorrent login: {e}")
        sys.exit(1)

    for torrent_info in torrents_to_restore:
        torrent_name = torrent_info.get("torrent_name", "Unknown")
        torrent_hash = torrent_info.get("torrent_hash")
        torrent_file_name = torrent_info.get("torrent_file_name")
        category = torrent_info.get("category")
        logging.debug(f"\nProcessing: {torrent_name} (Hash: {torrent_hash})")

    # Collect all unique files to move
    all_files_to_move = set()
    for torrent_info in torrents_to_restore:
        if torrent_info.get("deleted_contents", False):
            for file_path_relative in torrent_info.get("files", []):
                all_files_to_move.add(file_path_relative)

    failed_file_operations = []

    # Perform all file movements once
    if all_files_to_move:
        logging.info("\nMoving deleted contents back to their original locations...")
        for file_path_relative in all_files_to_move:
            src_file_path = os.path.join(RECYCLE_BIN_DIR, file_path_relative)
            dest_file_path = os.path.join(ROOT_DIR, file_path_relative)
            dest_dir = os.path.dirname(dest_file_path)

            if os.path.exists(src_file_path):
                os.makedirs(dest_dir, exist_ok=True)
                if not dry_run:
                    try:
                        shutil.move(src_file_path, dest_file_path)
                        logging.info(f"  Moved file: {file_path_relative}")
                    except Exception as move_e:
                        logging.error(f"  Error moving {file_path_relative}: {move_e}. Attempting to copy instead.")
                        try:
                            shutil.copy2(src_file_path, dest_file_path)
                            logging.info(f"  Copied file as fallback: {file_path_relative}")
                        except Exception as copy_e:
                            logging.error(f"  Error copying {file_path_relative} as fallback: {copy_e}")
                            failed_file_operations.append(file_path_relative)
                    else:
                        logging.info(f"  [DRY RUN] Would move file: {src_file_path} to {dest_file_path}")
                else:
                    logging.warning(f"  Source file not found for {file_path_relative}. Skipping move.")
                    failed_file_operations.append(file_path_relative)  # Also add to failed if source not found
    else:
        logging.info("\nNo contents marked as deleted for selected torrents. Skipping file movement.")

    if failed_file_operations:
        logging.error("\n--- Failed File Operations Summary ---")
        for failed_file in failed_file_operations:
            logging.error(f"  - {failed_file}")
        logging.error("------------------------------------")
        proceed_anyway = input(
            "Some file operations failed. Do you want to proceed with torrent injection anyway? (yes/no): "
        ).lower()
        if proceed_anyway not in ["yes", "y"]:
            logging.info("Torrent injection cancelled due to failed file operations.")
            sys.exit(0)

    logging.info("\nStarting torrent injection. All injected torrents will be added in a paused state.")
    for torrent_info in torrents_to_restore:
        torrent_name = torrent_info.get("torrent_name", "Unknown")
        torrent_hash = torrent_info.get("torrent_hash")
        torrent_file_name = torrent_info.get("torrent_file_name")
        category = torrent_info.get("category")

        if not torrent_hash or not torrent_file_name:
            logging.warning(f"  Missing torrent hash or file name for {torrent_name}. Skipping injection.")
            continue

        # Determine the correct path for the torrent file based on its name
        # Assuming torrent_file_name already contains the correct format (hash-only or name [hash])
        # and is located in either torrents_export or torrents folder.
        # The get_torrent_file_for_version already handles which file name to pick.
        # Now we just need to find it in the correct recycle bin subfolder.

        # Prioritize torrents_export for newer versions, then fallback to torrents
        torrent_file_full_path = os.path.join(RECYCLE_BIN_DIR, "torrents_export", torrent_file_name)
        if not os.path.exists(torrent_file_full_path):
            torrent_file_full_path = os.path.join(RECYCLE_BIN_DIR, "torrents", torrent_file_name)

        if not os.path.exists(torrent_file_full_path):
            logging.error(f"  Torrent file not found at {torrent_file_full_path}. Skipping injection.")
            continue

        if not dry_run:
            try:
                with open(torrent_file_full_path, "rb") as f:
                    torrent_content = f.read()
                client.torrents_add(torrent_files=torrent_content, category=category, is_skip_checking=True, is_paused=True)
                logging.info(f"  Injected torrent {torrent_file_name} Name: {torrent_name} (Hash: {torrent_hash})")
            except Exception as e:
                logging.error(f"  Error injecting torrent {torrent_name}: {e}")
        else:
            logging.info(f"  [DRY RUN] Would inject torrent {torrent_file_name} Name: {torrent_name} (Hash: {torrent_hash})")


if __name__ == "__main__":
    main()
