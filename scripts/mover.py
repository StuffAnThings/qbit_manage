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
parser.add_argument("--days_from", help="Set Number of Days to stop torrents between two offsets", type=int, default=0)
parser.add_argument("--days_to", help="Set Number of Days to stop torrents between two offsets", type=int, default=2)
# --DEFINE VARIABLES--#

# --START SCRIPT--#
try:
    from qbittorrentapi import APIConnectionError
    from qbittorrentapi import Client
    from qbittorrentapi import LoginFailed
except ModuleNotFoundError:
    print('Requirements Error: qbittorrent-api not installed. Please install using the command "pip install qbittorrent-api"')
    sys.exit(1)


def filter_torrents(torrent_list, timeoffset_from, timeoffset_to):
    result = []
    for torrent in torrent_list:
        if torrent.added_on >= timeoffset_to and torrent.added_on <= timeoffset_from:
            result.append(torrent)
        elif torrent.added_on < timeoffset_to:
            break
    return result


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

    torrents = filter_torrents(torrent_list, timeoffset_from.timestamp(), timeoffset_to.timestamp())

    # Pause Torrents
    print(f"Pausing [{len(torrents)}] torrents from {args.days_from} - {args.days_to} days ago")
    stop_start_torrents(torrents, True)
    time.sleep(10)
    # Start mover
    print("Starting Mover")
    # Or using mover tunning
    # os.system('/usr/local/sbin/mover start')
    os.system("/usr/local/sbin/mover.old start")
    # Start Torrents
    print(f"Resuming [{len(torrents)}] paused torrents from {args.days_from} - {args.days_to} days ago")
    stop_start_torrents(torrents, False)
