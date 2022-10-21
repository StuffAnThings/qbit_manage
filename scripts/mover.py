#!/usr/bin/env python3
# This standalone script is used to pause torrents older than last x days, run mover (in Unraid) and start torrents again once completed
import os, sys, time
from datetime import datetime, timedelta


# --DEFINE VARIABLES--#
# Set Number of Days to stop torrents between two offsets
# days_from set to 0 will pause any torrents from todays date
# days_to will be the upper limit of how far you want to pause torrents to
days_from = 0
days_to = 2
qbt_host = 'qbittorrent:8080'
qbt_user = None
qbt_pass = None
# --DEFINE VARIABLES--#

# --START SCRIPT--#
try:
    from qbittorrentapi import Client, LoginFailed, APIConnectionError
except ModuleNotFoundError:
    print("Requirements Error: qbittorrent-api not installed. Please install using the command \"pip install qbittorrent-api\"")
    sys.exit(0)

current = datetime.now()
timeoffset_from = (current - timedelta(days=days_from)).timestamp()
timeoffset_to = (current - timedelta(days=days_to)).timestamp()

if days_from > days_to:
    raise("Config Error: days_from must be set lower than days_to")

def stop_start_torrents(torrent_list, pause=True):
    for torrent in torrent_list:
        if torrent.added_on >= timeoffset_to and torrent.added_on <= timeoffset_from:
            if pause:
                torrent.pause()
            else:
                torrent.resume()
        else:
            if torrent.added_on >= timeoffset_to:
                continue
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
    print(f"Pausing torrents from {days_from} - {days_to} days ago")
    stop_start_torrents(torrent_list, True)
    time.sleep(10)
    # Start mover
    print("Starting Mover")
    os.system('/usr/local/sbin/mover.old start')
    # Start Torrents
    print(f"Resuming paused torrents from {days_from} - {days_to} days ago")
    stop_start_torrents(torrent_list, False)
