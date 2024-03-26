#!/usr/bin/env python3
# This standalone script is used to pause torrents older than last x days,
# run mover (in Unraid) and start torrents again once completed
import argparse
import os
import sys
import time
from datetime import datetime
from datetime import timedelta

parser = argparse.ArgumentParser(prog="Qbit Mover", description="Stop torrents and kick off Unraid mover process")
parser.add_argument("--host", help="qbittorrent host including port", required=True)
parser.add_argument("-u", "--user", help="qbittorrent user", default="admin")
parser.add_argument("-p", "--password", help="qbittorrent password", default="adminadmin")
parser.add_argument(
    "--cache-mount",
    "--cache_mount",
    help="Cache mount point in Unraid. This is used to additionally filter for only torrents that exists on the cache mount."
    "Use this option ONLY if you follow TRaSH Guides folder structure.",
    required=True,
)
parser.add_argument(
    "--days-from", "--days_from", help="Set Number of Days to stop torrents between two offsets", type=int, default=0
)
parser.add_argument("--days-to", "--days_to", help="Set Number of Days to stop torrents between two offsets", type=int, default=2)
parser.add_argument("--debug", help="Enable debug logger for mover", default=False)
# --DEFINE VARIABLES--#

# --START SCRIPT--#
try:
    from qbittorrentapi import APIConnectionError
    from qbittorrentapi import Client
    from qbittorrentapi import LoginFailed
except ModuleNotFoundError:
    print('Requirements Error: qbittorrent-api not installed. Please install using the command "pip install qbittorrent-api"')
    sys.exit(1)


def filter_torrents(torrent_list, timeoffset_from, timeoffset_to, cache_mount):
    result = []
    for torrent in torrent_list:
        if torrent.added_on >= timeoffset_to and torrent.added_on <= timeoffset_from:
            if not cache_mount or os.path.exists(cache_path(cache_mount, torrent.content_path)):
                result.append(torrent)
        elif torrent.added_on < timeoffset_to:
            break
    return result


def cache_path(cache_mount, content_path):
    return os.path.join(cache_mount, content_path.lstrip("/"))


def find_hardlinks(file_path, cache_mount):
    inode = os.stat(file_path).st_ino
    hardlinks = set()
    for dirpath, _, filenames in os.walk(cache_mount):
        for filename in filenames:
            candidate_path = os.path.join(dirpath, filename)
            if os.stat(candidate_path).st_ino == inode:
                hardlinks.add(candidate_path)
    return hardlinks


def stop_start_torrents(torrent_list, pause=True):
    for torrent in torrent_list:
        if pause:
            print(f"Pausing: {torrent.name} [{torrent.added_on}]")
            torrent.pause()
        else:
            print(f"Resuming: {torrent.name} [{torrent.added_on}]")
            torrent.resume()


if __name__ == "__main__":
    current = datetime.now()
    args = parser.parse_args()

    if args.days_from > args.days_to:
        raise ("Config Error: days_from must be set lower than days_to")

    try:
        client = Client(host=args.host, username=args.user, password=args.password)
    except LoginFailed:
        raise ("Qbittorrent Error: Failed to login. Invalid username/password.")
    except APIConnectionError:
        raise ("Qbittorrent Error: Unable to connect to the client.")
    except Exception:
        raise ("Qbittorrent Error: Unable to connect to the client.")

    timeoffset_from = current - timedelta(days=args.days_from)
    timeoffset_to = current - timedelta(days=args.days_to)
    torrent_list = client.torrents.info(sort="added_on", reverse=True)

    for torrent in filter_torrents(torrent_list, timeoffset_from.timestamp(), timeoffset_to.timestamp(), args.cache_mount):
        file_paths = set()

        print(f"Pausing: {torrent.name} [{torrent.added_on}]")
        torrent.pause()

        content_path = cache_path(args.cache_mount, torrent.content_path)

        if os.path.isdir(content_path):
            # If file_path is a directory, include all files within it
            for root, dirs, files in os.walk(content_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_paths.add(os.path.join(root, file))
                    file_paths.update(find_hardlinks(file_path, args.cache_mount))
                for dir in dirs:
                    directory_path = os.path.join(root, dir)
                    file_paths.add(directory_path)
            file_paths.add(content_path)
        else:
            file_paths.add(content_path)
            file_paths.update(find_hardlinks(content_path, args.cache_mount))

        time.sleep(5)
        print(f"Moving files for {torrent.name}.")
        
        files_string = "\n".join(file_paths)
        os.system(f"echo '{files_string}' | /usr/local/sbin/move")

        print(f"Resuming: {torrent.name} [{torrent.added_on}]")
        torrent.resume()
