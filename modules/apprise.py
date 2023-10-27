"""Apprise notification class"""
import time

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
        response = self.config.get(self.api_url)
        time.sleep(1)  # Pause for 1 second before sending the next request
        if response.status_code != 200:
            raise Failed(f"Apprise Error: Unable to connect to Apprise using {self.api_url}")
