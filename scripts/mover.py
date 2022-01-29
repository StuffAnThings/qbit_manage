#!/usr/bin/env python3
# This standalone script is used to pause torrents older than last x days, run mover (in Unraid) and start torrents again once completed
import os, sys, time
from datetime import datetime, timedelta


# --DEFINE VARIABLES--#
# Set Number of Days to stop torrents for the move
days = 2
qbt_host = 'qbittorrent:8080'
qbt_user = None
qbt_pass = None
# --DEFINE VARIABLES--#

# --START SCRIPT--#
try:
    from qbittorrentapi import Client, LoginFailed, APIConnectionError
except ModuleNotFoundError:
    print("Requirements Error: qbittorrentapi not installed. Please install with pip")
    sys.exit(0)

current = datetime.now()
timeoffset = (current - timedelta(days=days)).timestamp()


def stop_start_torrents(torrent_list, pause=True):
    for torrent in torrent_list:
        if (torrent.added_on >= timeoffset):
            if pause:
                torrent.pause()
            else:
                torrent.resume()
        else:
            break


if __name__ == '__main__':
    try:
        client = Client(host=qbt_host, username=qbt_user, password=qbt_pass)
    except LoginFailed:
        raise("Qbittorrent Error: Failed to login. Invalid username/password.")
    except APIConnectionError:
        raise("Qbittorrent Error: Unable to connect to the client.")
    except Exception:
        raise("Qbittorrent Error: Unable to connect to the client.")
    torrent_list = client.torrents.info(sort='added_on', reverse=True)

    # Pause Torrents
    print(f"Pausing torrents from the last {days} Days")
    stop_start_torrents(torrent_list, True)
    time.sleep(10)
    # Start mover
    print("Starting Mover")
    os.system('/usr/local/sbin/mover.old start')
    # Start Torrents
    print(f"Resuming paused torrents from the last {days} Days")
    stop_start_torrents(torrent_list, False)
