#!/usr/bin/python3
# This script was written by zakkarry ( https://github.com/zakkarry )
# Simply follow the basic configuration options below to remove all 'cross-seed'
# tags from all torrents from qBittorrent client matching the options below.
#
# If you do not know how to use environmental variables, or do not need to, simply
# configure the second part of the OBIT_* variables, where the actual URL and strings are.
#
# If you need to, you can use this script to remove any tag as well, simply modify CROSS_SEED_TAG
# from 'cross-seed' to whichever tag you wish to remove.
#

import os

# USES ENVIRONMENTAL VARIABLES, IF NONE ARE PRESENT WILL FALLBACK TO THE SECOND STRING
QBIT_HOST = os.getenv("QBT_HOST", "http://localhost:8080")
QBIT_USERNAME = os.getenv("QBT_USERNAME", "admin")
QBIT_PASSWORD = os.getenv("QBT_PASSWORD", "YOURPASSWORD")

CRED = "\033[91m"
CGREEN = "\33[32m"
CEND = "\033[0m"

CROSS_SEED_TAG = "cross-seed"


def split(separator, data):
    if data is None:
        return None
    else:
        return [item.strip() for item in str(data).split(separator)]


try:
    from qbittorrentapi import APIConnectionError
    from qbittorrentapi import Client
    from qbittorrentapi import LoginFailed
except ModuleNotFoundError:
    print('Error: qbittorrent-api not installed. Please install using the command "pip install qbittorrent-api"')
    exit(1)

try:
    qbt_client = Client(host=QBIT_HOST, username=QBIT_USERNAME, password=QBIT_PASSWORD)
except LoginFailed:
    raise "Qbittorrent Error: Failed to login. Invalid username/password."
except APIConnectionError:
    raise "Qbittorrent Error: Unable to connect to the client."
except Exception:
    raise "Qbittorrent Error: Unable to connect to the client."
print("qBittorrent:", qbt_client.app_version())
print("qBittorrent Web API:", qbt_client.app_web_api_version())
print()

torrents_list = qbt_client.torrents.info(sort="added_on", reverse=True)

print("Total torrents:", len(torrents_list))
print()

for torrent in torrents_list:
    torrent_tags = split(",", torrent.tags)

    if CROSS_SEED_TAG in torrent_tags:
        print(CGREEN, "remove cross-seed tag:", torrent.name, CEND)
        torrent.remove_tags(tags=CROSS_SEED_TAG)
