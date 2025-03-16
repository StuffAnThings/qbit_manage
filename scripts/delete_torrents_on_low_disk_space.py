"""This script deletes torrents once your drive space drops below a certain threshold.
You can set a min torrent age and share ratio for a torrent to be deleted.
You can also allow incomplete torrents to be deleted.
Torrents will be deleted starting with the ones with the most seeds, only torrents with a single hardlink will be deleted.
Only torrents on configured drive path will be deleted. To monitor multiple drives, use multiple copies of this script.
"""

import os
import shutil
import time

import qbittorrentapi

"""===Config==="""
# qBittorrent WebUi Login
qbt_login = {"host": "localhost", "port": 8080, "username": "???", "password": "???"}
# Path of drive to monitor. Only torrents with paths that start with this may be deleted.
PATH = "M:"
MIN_FREE_SPACE = 10  # In GB. Min free space on drive.
MIN_FREE_USAGE = 0  # In decimal percentage, 0 to 1. Min % free space on drive.
# In decimal percentage, 0 to inf. Min seeding ratio of torrent to delete.
MIN_TORRENT_SHARE_RATIO = 0
# In days, min age of torrent to delete. Uses seeding time.
MIN_TORRENT_AGE = 30
ALLOW_INCOMPLETE_TORRENT_DELETIONS = (
    # Also delete torrents that haven't finished downloading. MIN_TORRENT_AGE now based on time active.
    False
)
PREFER_PRIVATE_TORRENTS = (
    # Will delete public torrents before private ones regardless of seed difference. See is_torrent_public().
    True
)
"""===End Config==="""

# Services
qbt_client: qbittorrentapi.Client = None


def quit_program(code=0):
    """Quits program with info"""
    print("Exiting...")
    import sys

    sys.exit(code)


def setup_services(qbt=False):
    """Setup required services"""
    global qbt_client

    if qbt:
        qbt_client = qbittorrentapi.Client(
            host=qbt_login["host"], port=qbt_login["port"], username=qbt_login["username"], password=qbt_login["password"]
        )
        try:
            qbt_client.auth_log_in()
            print("Successfully connected to qBittorrent!")
        except:
            print("Error: Could not log into qBittorrent. Please verify login details are correct and Web Ui is available.")
            quit_program(1)


def bytes_to_gb(data):
    """Converts bytes to GB."""
    return data / 1024**3


def seconds_to_days(seconds):
    """Converts seconds to days."""
    return seconds / 60 / 60 / 24


def get_disk_usage():
    """Gets the free space and free usage of disk."""
    stat = shutil.disk_usage(PATH)
    free_space = bytes_to_gb(stat.free)
    free_usage = stat.free / stat.total
    return free_space, free_usage


def is_storage_full():
    """Checks if free space are below user threshold."""
    free_space, free_usage = get_disk_usage()
    if free_space < MIN_FREE_SPACE or free_usage < MIN_FREE_USAGE:
        return True
    return False


def print_free_space():
    """Prints free space and user threshold."""
    free_space, free_usage = get_disk_usage()
    print(f"Free space: {free_space:.2f} GB ({free_usage:.2%}) - Thresholds: {MIN_FREE_SPACE:.2f} GB ({MIN_FREE_USAGE:.2%}) ")


def is_torrent_public(torrent_hash, setup=True):
    """Checks if torrent is public or private by word 'private' in tracker messages."""
    setup_services(qbt=setup)
    torrent_trackers = qbt_client.torrents_trackers(torrent_hash)
    for tracker in torrent_trackers:
        if "private" in tracker["msg"].lower():
            return False
    return True


def has_single_hard_link(path):
    """Check if file has a single hard link. False if any file in directory has multiple."""
    # Check all files if path is directory
    if os.path.isfile(path):
        if os.stat(path).st_nlink > 1:
            return False
    else:
        for dirpath, _, filenames in os.walk(path):
            for file in filenames:
                file_path = os.path.join(dirpath, file)
                if os.stat(file_path).st_nlink > 1:
                    return False
    return True


def torrent_on_monitored_drive(torrent):
    """Check if torrent path is within monitored drive"""
    return torrent["content_path"].startswith(PATH)


def torrent_age_satisfied(torrent):
    """Gets the age of the torrent based on config"""
    if ALLOW_INCOMPLETE_TORRENT_DELETIONS:
        return seconds_to_days(torrent["time_active"]) >= MIN_TORRENT_AGE
    else:
        return seconds_to_days(torrent["seeding_time"]) >= MIN_TORRENT_AGE


def main():
    # If free space above requirements, terminate
    print_free_space()
    if is_storage_full():
        print("Drive space low, will be deleting torrents...")
    else:
        print("Free space already above threshold, no torrents were deleted!")
        quit_program(0)

    setup_services(qbt=True)

    # Get all torrents older than threshold
    print("Getting all torrents above age and seeding threshold...")
    torrent_hashes_raw = []
    torrent_privacy_raw = []
    torrent_num_seeds_raw = []
    for torrent in qbt_client.torrents_info():
        torrent_share_ratio = qbt_client.torrents_properties(torrent["hash"])["share_ratio"]
        if (
            torrent_on_monitored_drive(torrent)
            and torrent_age_satisfied(torrent)
            and torrent_share_ratio >= MIN_TORRENT_SHARE_RATIO
        ):
            torrent_hashes_raw.append(torrent["hash"])
            torrent_privacy_raw.append(is_torrent_public(torrent["hash"], setup=False) if PREFER_PRIVATE_TORRENTS else True)
            torrent_num_seeds_raw.append(torrent["num_complete"])

    # Sort so most available torrent is last.
    torrent_hashes = []
    for *_, torrent_hash in sorted(zip(torrent_privacy_raw, torrent_num_seeds_raw, torrent_hashes_raw)):
        torrent_hashes.append(torrent_hash)

    # Delete torrents until storage is above threshold
    deleted_torrents = []
    if torrent_hashes:
        print("Deleting torrents with a single hard link...")
        while is_storage_full() and torrent_hashes:
            torrent_hash = torrent_hashes.pop()
            torrent_info = qbt_client.torrents_info(torrent_hashes=torrent_hash)[0]
            torrent_name = torrent_info["name"]
            torrent_path = torrent_info["content_path"]
            # Only delete torrents with a single hard link as ones with multiple won't free any space
            if has_single_hard_link(torrent_path):
                qbt_client.torrents_delete(torrent_hashes=torrent_hash, delete_files=True)
                deleted_torrents.append(torrent_name)
                print(f"--- {torrent_name}")
                # Sleep a bit after each deletion to make sure disk usage is updated.
                time.sleep(1)

    # Print results
    print_free_space()
    if not is_storage_full():
        print(f"Free space now above threshold, {len(deleted_torrents)} torrents were deleted!")
    else:  # No more torrents to delete but still low on space
        print(
            f"WARNING... Free space still below threshold after deleting all {len(deleted_torrents)} eligible torrents! Either:"
        )
        print(
            f"--- Torrent ages are below threshold of '{MIN_TORRENT_AGE} days'\n"
            f"--- Torrent seed ratios are below threshold of '{MIN_TORRENT_SHARE_RATIO}'\n"
            "--- Torrents have multiple hard links\n"
            "--- No torrents exists!"
        )

    quit_program(0)


if __name__ == "__main__":
    main()
