import hashlib

import bencodepy

from modules import util
from modules.util import Failed

logger = util.logger


class TorrentHashGenerator:
    def __init__(self, torrent_file_path):
        self.torrent_file_path = torrent_file_path

    def generate_torrent_hash(self):
        try:
            with open(self.torrent_file_path, "rb") as torrent_file:
                torrent_data = torrent_file.read()
            try:
                torrent_info = bencodepy.decode(torrent_data)
                info_data = bencodepy.encode(torrent_info[b"info"])
                info_hash = hashlib.sha1(info_data).hexdigest()
                logger.trace(f"info_hash: {info_hash}")
                return info_hash
            except KeyError:
                logger.error("Invalid .torrent file format. 'info' key not found.")
        except FileNotFoundError:
            logger.error(f"Torrent file '{self.torrent_file_path}' not found.")
        except Failed as err:
            logger.error(f"TorrentHashGenerator Error: {err}")
