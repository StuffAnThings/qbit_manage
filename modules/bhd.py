"""Module for BeyondHD (BHD) tracker."""

from json import JSONDecodeError

from modules import util
from modules.util import Failed

logger = util.logger
BASE_URL = "https://beyond-hd.me/api/"


class BeyondHD:
    """BeyondHD (BHD) tracker class."""

    def __init__(self, config, params):
        self.config = config
        self.apikey = params["apikey"]
        logger.secret(self.apikey)
        json = {"search": "test"}
        self.search(json)

    def search(self, json, path="torrents/"):
        """Search BHD."""
        url = f"{BASE_URL}{path}{self.apikey}"
        json["action"] = "search"
        logger.trace(url)
        logger.trace(f"JSON: {json}")
        try:
            response = self.config.post(url, json=json, headers={"User-Agent": "Chrome"})
            logger.trace(response)
            response_json = response.json()
        except JSONDecodeError as err:
            logger.debug(err)
            return {}
        if response.status_code >= 400:
            logger.debug(f"Response: {response_json}")
            raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
        if "rate limited" in response_json.get("status_message", ""):
            logger.error(f"BHD Error: {response_json.get('status_message')}")
            return {}
        if not response_json.get("success"):
            raise Failed(f"BHD Error: {response_json.get('status_message', 'Issue receiving response from BHD API.')}")
        return response_json
