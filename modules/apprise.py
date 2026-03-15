"""Apprise notification class"""

import time

import requests

from modules import util
from modules.util import Failed

logger = util.logger


class Apprise:
    """Apprise notification class"""

    def __init__(self, config, params):
        self.config = config
        self.api_url = params["api_url"]
        logger.secret(self.api_url)
        self.notify_url = ",".join(params["notify_url"])
        response = self.check_api_url()
        time.sleep(1)  # Pause for 1 second before sending the next request
        if response.status_code != 200:
            raise Failed(f"Apprise Error: Unable to connect to Apprise using {self.api_url}")

    def check_api_url(self):
        """Check if the API URL is valid"""
        # Check the response using application.json get header
        status_endpoint = self.api_url + "/status"
        try:
            response = self.config.get(status_endpoint, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise Failed(f"Apprise Error: Unexpected error connecting to {status_endpoint} ({e})")
