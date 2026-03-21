import time
from json import JSONDecodeError

import requests

from modules import util
from modules.util import Failed

logger = util.logger


class Notifiarr:
    """Notifiarr API"""

    BASE_URL = "https://notifiarr.com/api"
    API_VERSION = "v1"

    def __init__(self, config, params):
        """Initialize Notifiarr API"""
        self.config = config
        self.apikey = params["apikey"]
        self.header = {"X-API-Key": self.apikey}
        self.instance = params["instance"]
        self.url = f"{self.BASE_URL}/{self.API_VERSION}/"
        logger.secret(self.apikey)
        try:
            response = self.config.get(f"{self.url}user/qbitManage/", headers=self.header, params={"fetch": "settings"})
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Failed(f"Notifiarr error: Unable to connect to Notifiarr ({e})")
        response_json = None
        try:
            response_json = response.json()
        except JSONDecodeError as e:
            logger.debug(e)
            raise Failed("Notifiarr Error: Invalid response")
        if response.status_code >= 400 or ("result" in response_json and response_json["result"] == "error"):
            logger.debug(f"Response: {response_json}")
            raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
        if not response_json["details"]["response"]:
            raise Failed("Notifiarr Error: Invalid apikey")

    def notification(self, json):
        """Send notification to Notifiarr"""
        params = {"qbit_client": self.config.data["qbt"]["host"], "instance": self.instance}
        try:
            response = self.config.get(f"{self.url}notification/qbitManage/", json=json, headers=self.header, params=params)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Failed(f"Notifiarr error: Unable to send notification ({e})")
        time.sleep(1)  # Pause for 1 second before sending the next request
        return response
