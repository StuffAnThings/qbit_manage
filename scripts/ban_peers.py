import argparse
import logging
import re
import sys

from qbittorrentapi import Client
from qbittorrentapi.exceptions import APIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def validate_peers(peers_str):
    if not isinstance(peers_str, str):
        raise ValueError("Peers must be a string")
    peer_addresses = [peer.strip() for peer in peers_str.split("|") if peer.strip()]
    valid_peers = []
    peer_pattern = re.compile(
        r"^(?:"
        r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}|"  # IPv4
        r"\[[0-9a-fA-F:]+\]|"  # IPv6
        r"[a-zA-Z0-9.-]+"  # Hostname
        r"):[0-9]{1,5}$"
    )
    for peer in peer_addresses:
        if peer_pattern.match(peer):
            try:
                port = int(peer.split(":")[-1])
                if 1 <= port <= 65535:
                    valid_peers.append(peer)
                else:
                    logger.warning(f"Invalid port range for peer: {peer}")
            except ValueError:
                logger.warning(f"Invalid port for peer: {peer}")
        else:
            logger.warning(f"Invalid peer format: {peer}")
    return valid_peers


def ban_peers(client, peer_list, dry_run):
    if not peer_list:
        logger.info("No valid peers to ban")
        return 0
    logger.info(f"Attempting to ban {len(peer_list)} peer(s): {', '.join(peer_list)}")
    if dry_run:
        for peer in peer_list:
            logger.info(f"[DRY-RUN] - {peer}")
        return len(peer_list)
    try:
        peers_string = "|".join(peer_list)
        client.transfer.ban_peers(peers=peers_string)
        logger.info(f"Successfully banned {len(peer_list)} peer(s)")
        return len(peer_list)
    except APIError as e:
        logger.error(f"Error banning peers: {str(e)}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Ban peers in qBittorrent.")
    parser.add_argument("--host", default="localhost", help="qBittorrent host")
    parser.add_argument("--port", type=int, default=8080, help="qBittorrent port")
    parser.add_argument("--user", help="Username")
    parser.add_argument("--pass", dest="password", help="Password")
    parser.add_argument("--peers", required=True, help="Peers to ban, separated by |")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    args = parser.parse_args()
    try:
        client = Client(
            host=args.host,
            port=args.port,
            username=args.user,
            password=args.password,
        )
        client.auth_log_in()
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        sys.exit(1)
    valid_peers = validate_peers(args.peers)
    stats = ban_peers(client, valid_peers, args.dry_run)
    logger.info(f"Banned {stats} peers")


if __name__ == "__main__":
    main()
