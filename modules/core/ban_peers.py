"""Ban Peers Module"""

import re
from modules import util
from modules.qbit_error_handler import handle_qbit_api_errors

logger = util.logger


class BanPeers:
    """Class to handle banning peers from qBittorrent"""
    
    def __init__(self, qbit_manager, peers=None):
        self.qbt = qbit_manager
        self.config = qbit_manager.config
        self.client = qbit_manager.client
        self.stats = 0
        
        if peers:
            self.ban_peers(peers)
    
    def ban_peers(self, peers):
        """
        Ban one or more peers from qBittorrent
        
        Args:
            peers (str): Peer addresses to ban in format 'host:port' or multiple peers separated by '|'
        """
        logger.separator("Banning Peers", space=False, border=False)
        
        if not peers:
            logger.info("No peers specified for banning")
            return
        
        # Validate and clean peer addresses
        peer_list = self._validate_peers(peers)
        
        if not peer_list:
            logger.warning("No valid peers to ban")
            return
        
        logger.info(f"Attempting to ban {len(peer_list)} peer(s): {', '.join(peer_list)}")
        
        if self.config.dry_run:
            logger.info("[DRY-RUN] Would ban the following peers:")
            for peer in peer_list:
                logger.info(f"[DRY-RUN] - {peer}")
            self.stats = len(peer_list)
            return
        
        # Call qBittorrent API to ban peers
        success = self._execute_ban_peers(peer_list)
        
        if success:
            logger.info(f"Successfully banned {len(peer_list)} peer(s)")
            self.stats = len(peer_list)
        else:
            logger.error("Failed to ban peers")
            self.stats = 0
    
    def _validate_peers(self, peers):
        """
        Validate peer addresses and return a list of valid peers
        
        Args:
            peers (str): Peer addresses separated by '|'
            
        Returns:
            list: List of valid peer addresses
        """
        if not isinstance(peers, str):
            logger.error(f"Invalid peer format: expected string, got {type(peers)}")
            return []
        
        # Split peers by pipe separator
        peer_addresses = [peer.strip() for peer in peers.split('|') if peer.strip()]
        valid_peers = []
        
        # Regular expression to validate host:port format
        # Supports IPv4, IPv6, and hostnames
        peer_pattern = re.compile(
            r'^(?:'
            r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}|'  # IPv4
            r'\[[0-9a-fA-F:]+\]|'              # IPv6 in brackets
            r'[a-zA-Z0-9.-]+'                  # Hostname
            r'):[0-9]{1,5}$'                   # Port
        )
        
        for peer in peer_addresses:
            if peer_pattern.match(peer):
                # Additional validation for port range
                try:
                    port = int(peer.split(':')[-1])
                    if 1 <= port <= 65535:
                        valid_peers.append(peer)
                    else:
                        logger.warning(f"Invalid port range for peer: {peer} (port must be 1-65535)")
                except ValueError:
                    logger.warning(f"Invalid port format for peer: {peer}")
            else:
                logger.warning(f"Invalid peer format: {peer} (expected format: host:port)")
        
        return valid_peers
    
    @handle_qbit_api_errors(context="ban_peers", retry_attempts=2)
    def _execute_ban_peers(self, peer_list):
        """
        Execute the actual peer banning via qBittorrent API
        
        Args:
            peer_list (list): List of peer addresses to ban
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Join peers with pipe separator for qBittorrent API
            peers_string = '|'.join(peer_list)
            
            # Call qBittorrent API to ban peers
            self.client.transfer_ban_peers(peers=peers_string)
            
            return True
            
        except Exception as e:
            logger.error(f"Error banning peers: {str(e)}")
            self.config.notify(f"Error banning peers: {str(e)}", "Ban Peers", False)
            return False 