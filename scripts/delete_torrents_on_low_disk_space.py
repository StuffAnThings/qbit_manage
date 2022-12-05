"""This script deletes torrents once your drive space drops below a certain threshold.
You can set a min torrent age and share ratio for a torrent to be deleted. You can also allow incomplete torrents to be deleted.
Torrents will be deleted starting with the ones with the most seeds then size, only torrents with a single hardlink will be deleted.
Only torrents on configured drive path will be deleted. To monitor multiple drives, use multiple copies of this script.
"""
import os
import shutil
import sys
import time

import qbittorrentapi


"""===Config==="""
# qBittorrent WebUi Login
qbt_login = {"host": "localhost", "port": 8080, "username": "???", "password": "???"}
PATH = "M:"  # Path of drive to monitor. Only torrents with paths that start with this may be deleted.
MIN_FREE_SPACE = 10  # In GB. Min free space on drive.
MIN_FREE_USAGE = 0  # In decimal percentage, 0 to 1. Min % free space on drive.
MIN_TORRENT_SHARE_RATIO = 0  # In decimal percentage, 0 to inf. Min seeding ratio of torrent to delete.
MIN_TORRENT_AGE = 30  # In days, min age of torrent to delete. Uses seeding time.
# In GB. If total size of torrents containing this tracker is above this limit, delete those torrents first. 0 to disable.
MAX_SIZE_PER_TRACKER = 0
# A python dict where key is the tracker url and value is the max tracker size in GB. This overides MAX_SIZE_PER_TRACKER for that tracker url.
SPECIFIC_TRACKER_SIZES = {}
ALLOW_INCOMPLETE_TORRENT_DELETIONS = (
    False  # Also delete torrents that haven't finished downloading. MIN_TORRENT_AGE now based on time active.
)
# Will delete public torrents before private ones regardless of seed difference or tracker sizes. See is_torrent_public().
PREFER_PRIVATE_TORRENTS = True
# Additional trackers urls to consider private. Save a comma separated strings. Don't include the port to match all ports.
PRIVATE_TRACKERS = ["http://example.com"]
DRY_RUN = True  # If True will only show what torrents will be deleted.
"""===End Config==="""

# Misc
qbt_client: qbittorrentapi.Client = None
TORRENTS = {}  # Information about all the torrents from api calls. Each hash will contain the api call results for that hash.
tracker_sizes = {}


def quit_program(code=0):
    """Quits program with info"""
    print("Exiting...")
    sys.exit(code)


def setup_services():
    """Setup required services"""
    global qbt_client
    if not qbt_client:
        qbt_client = qbittorrentapi.Client(host=qbt_login["host"], port=qbt_login["port"])
        try:
            qbt_client.auth_log_in()
            print("Succesfully connected to qBittorrent!")
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
    """Gets the free space, free usage, and total of disk in GB."""
    stat = shutil.disk_usage(PATH)
    free_space = bytes_to_gb(stat.free)
    free_usage = stat.free / stat.total
    return [free_space, free_usage, bytes_to_gb(stat.total)]


def is_storage_full(disk_usage=None):
    """Checks if free space are below user threshold. Optional disk_usage parameter to use non-realtime usage."""
    if disk_usage:
        free_space, free_usage, _ = disk_usage
    else:
        free_space, free_usage, _ = get_disk_usage()
    if free_space < MIN_FREE_SPACE or free_usage < MIN_FREE_USAGE:
        return True
    return False


def update_projected_storage(projected_usage, torrent_size_gb):
    """Updates the projected usage by adding torrent size."""
    projected_usage[0] += torrent_size_gb
    projected_usage[2] += torrent_size_gb
    projected_usage[1] = projected_usage[0] / projected_usage[2]


def print_free_space():
    """Prints free space and user threshold."""
    free_space, free_usage, total = get_disk_usage()
    print(
        f"Free space: {free_space:,.2f} GB ({free_usage:.2%}) - Thresholds: {MIN_FREE_SPACE:,.2f} GB ({MIN_FREE_USAGE:.2%}) - Total: {total:,.2f} GB"
    )


def is_torrent_public(torrent_hash):
    """Checks if torrent is public or private by word 'private' in tracker messages."""
    for tracker in TORRENTS[torrent_hash]["torrents_trackers"]:
        if "private" in tracker["msg"].lower():
            return False
        for tracker_url in PRIVATE_TRACKERS:
            if tracker_url in tracker["url"]:
                return False
    return True


def update_tracker_sizes(torrent_hash):
    """Updates global tracker sizes dict with current torrent size"""
    setup_services()
    torrent_size_gb = bytes_to_gb(TORRENTS[torrent_hash]["torrents_info"]["size"])
    for tracker in TORRENTS[torrent_hash]["torrents_trackers"]:
        tracker_url = tracker["url"]
        if "://" not in tracker_url:  # Ignore PeX, LSD, DHT
            continue
        if tracker_url in tracker_sizes:
            tracker_sizes[tracker_url] += torrent_size_gb
        else:
            tracker_sizes[tracker_url] = torrent_size_gb


def trackers_above_limit(torrent_hash):
    """Checks if all torrent trackers are above size limit."""
    for tracker in TORRENTS[torrent_hash]["torrents_trackers"]:
        tracker_url = tracker["url"]
        if "://" not in tracker_url:  # Ignore PeX, LSD, DHT
            continue
        if tracker_url in SPECIFIC_TRACKER_SIZES:
            if tracker_sizes.get(tracker_url, 0) > SPECIFIC_TRACKER_SIZES[tracker_url]:
                return True
        elif MAX_SIZE_PER_TRACKER and tracker_sizes.get(tracker_url, 0) > MAX_SIZE_PER_TRACKER:
            return True
    return False


def torrent_has_single_hard_link(torrent_hash):
    """Check if file has a single hard link. False if any file in directory has multiple."""
    path = TORRENTS[torrent_hash]["torrents_info"]["content_path"]
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


def torrent_on_monitored_drive(torrent_hash):
    """Check if torrent path is within monitored drive"""
    return TORRENTS[torrent_hash]["torrents_info"]["content_path"].startswith(PATH)


def torrent_age_satisfied(torrent_hash):
    """Gets the age of the torrent based on config"""
    if ALLOW_INCOMPLETE_TORRENT_DELETIONS:
        return seconds_to_days(TORRENTS[torrent_hash]["torrents_info"]["time_active"]) >= MIN_TORRENT_AGE
    else:
        return seconds_to_days(TORRENTS[torrent_hash]["torrents_info"]["seeding_time"]) >= MIN_TORRENT_AGE


def main():
    # If free space above requirements, terminate
    print_free_space()
    if is_storage_full():
        if not DRY_RUN:
            print("Drive space low, will be deleting torrents...")
        else:
            print("DRY RUN: Drive space low but no torrents will be deleted...")
    else:
        print("Free space already above threshold, no torrents were deleted!")
        quit_program(0)
    setup_services()

    # Get all torrents older than threshold
    print("Getting all torrents...")
    temp_torrents_info = qbt_client.torrents_info()
    total_torrents = 0
    for torrent_info in temp_torrents_info:
        TORRENTS[torrent_info["hash"]] = {}
        TORRENTS[torrent_info["hash"]]["torrents_info"] = torrent_info
        TORRENTS[torrent_info["hash"]]["torrents_properties"] = qbt_client.torrents_properties(torrent_info["hash"])
        TORRENTS[torrent_info["hash"]]["torrents_trackers"] = qbt_client.torrents_trackers(torrent_info["hash"])
        update_tracker_sizes(torrent_info["hash"])
        total_torrents += 1

    print("Getting elligible torrents...")
    torrent_elligible_hashes_raw = []
    torrent_privacy_raw = []
    torrent_tracker_sizes_raw = []
    torrent_num_seeds_raw = []
    torrent_sizes_raw = []
    for torrent_hash in TORRENTS:
        torrent_share_ratio = TORRENTS[torrent_hash]["torrents_properties"]["share_ratio"]
        if (
            torrent_on_monitored_drive(torrent_hash)
            and torrent_age_satisfied(torrent_hash)
            and torrent_share_ratio >= MIN_TORRENT_SHARE_RATIO
            and torrent_has_single_hard_link(torrent_hash)
        ):
            torrent_elligible_hashes_raw.append(torrent_hash)
            torrent_privacy_raw.append(is_torrent_public(torrent_hash) if PREFER_PRIVATE_TORRENTS else True)
            torrent_tracker_sizes_raw.append(trackers_above_limit(torrent_hash))
            torrent_num_seeds_raw.append(TORRENTS[torrent_hash]["torrents_info"]["num_complete"])
            torrent_sizes_raw.append(TORRENTS[torrent_hash]["torrents_info"]["size"])
    # Sort so most available torrent is last.
    elligible_torrent_hashes = []
    sort_order = zip(
        torrent_privacy_raw, torrent_tracker_sizes_raw, torrent_num_seeds_raw, torrent_sizes_raw, torrent_elligible_hashes_raw
    )
    for *_, torrent_hash in sorted(sort_order):
        elligible_torrent_hashes.append(torrent_hash)
    num_elligible_torrents = len(elligible_torrent_hashes)

    print("Getting torrents to delete...")
    torrent_hashes_to_delete = []
    if elligible_torrent_hashes:
        projected_storage = get_disk_usage()
        while is_storage_full(projected_storage) and elligible_torrent_hashes:
            torrent_hash = elligible_torrent_hashes.pop()
            torrent_hashes_to_delete.append(torrent_hash)
            torrent_info = TORRENTS[torrent_hash]["torrents_info"]
            torrent_size_gb = bytes_to_gb(torrent_info["size"])
            update_projected_storage(projected_storage, torrent_size_gb)
            print(f"--- {torrent_info['name']}: {torrent_size_gb:,.2f} GB")
    num_torrents_to_delete = len(torrent_hashes_to_delete)
    if not DRY_RUN:
        print(f"Deleting {num_torrents_to_delete:,}/{num_elligible_torrents:,} elligible torrents! (Total: {total_torrents:,})")
        qbt_client.torrents_delete(torrent_hashes=torrent_hashes_to_delete, delete_files=True)
        time.sleep(1)  # Need to wait a bit for disk usage to update
    else:
        print(
            f"DRY RUN: {num_torrents_to_delete:,}/{num_elligible_torrents:,} elligible torrents would be deleted! (Total: {total_torrents:,})"
        )

    # Print results
    if not DRY_RUN:
        print_free_space()
        if not is_storage_full():
            print(f"Free space now above threshold!")
        else:  # No more torrents to delete but still low on space
            print(
                f"WARNING... Free space still below threshold after deleting all {num_torrents_to_delete:,} eligible torrents! Either:"
            )
            print(
                f"--- Torrent ages are below threshold of '{MIN_TORRENT_AGE:,} days'\n"
                f"--- Torrent seed ratios are below threshold of '{MIN_TORRENT_SHARE_RATIO:,}'\n"
                f"--- Torrents have multiple hard links\n"
                f"--- No torrents exists!"
            )

    quit_program(0)


if __name__ == "__main__":
    main()
