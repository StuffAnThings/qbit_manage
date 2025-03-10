#!/usr/bin/env python3
# This standalone script is used to edit tracker urls from one tracker to another.
# Needs to have qbittorrent-api installed
# pip3 install qbittorrent-api
import sys

# --DEFINE VARIABLES--#
qbt_host = "qbittorrent:8080"
qbt_user = None
qbt_pass = None
OLD_TRACKER = "https://blutopia.xyz"  # This is the tracker you want to replace
# This is the tracker you want to replace it with
NEW_TRACKER = "https://blutopia.cc"
# --DEFINE VARIABLES--#
# --START SCRIPT--#

try:
    from qbittorrentapi import APIConnectionError
    from qbittorrentapi import Client
    from qbittorrentapi import LoginFailed
except ModuleNotFoundError:
    print('Requirements Error: qbittorrent-api not installed. Please install using the command "pip install qbittorrent-api"')
    sys.exit(1)


if __name__ == "__main__":
    try:
        client = Client(host=qbt_host, username=qbt_user, password=qbt_pass)
    except LoginFailed:
        raise ("Qbittorrent Error: Failed to login. Invalid username/password.")
    except APIConnectionError:
        raise ("Qbittorrent Error: Unable to connect to the client.")
    except Exception:
        raise ("Qbittorrent Error: Unable to connect to the client.")
    torrent_list = client.torrents.info(sort="added_on", reverse=True)

    for torrent in torrent_list:
        for x in torrent.trackers:
            if OLD_TRACKER in x.url:
                newurl = x.url.replace(OLD_TRACKER, NEW_TRACKER)
                print(f"torrent name: {torrent.name}, original url: {x.url}, modified url: {newurl}\n")
                torrent.remove_trackers(urls=x.url)
                torrent.add_trackers(urls=newurl)
