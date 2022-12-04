from json import JSONDecodeError

from modules import util
from modules.util import Failed

logger = util.logger
base_url = "https://beyond-hd.me/api/"


class BeyondHD:
    def __init__(self, config, params):
        self.config = config
        self.apikey = params["apikey"]
        logger.secret(self.apikey)
        json = {"search": "test"}
        self.search(json)

    def search(self, json, path="torrents/"):
        url = f"{base_url}{path}{self.apikey}"
        json["action"] = "search"
        logger.trace(url)
        logger.trace(f"JSON: {json}")
        try:
            response = self.config.post(url, json=json, headers={"User-Agent": "Chrome"})
            logger.trace(response)
            response_json = response.json()
        except JSONDecodeError as e:
            if response.status_code >= 400:
                raise Failed(e)
            elif "Expecting value" in e:
                logger.debug(e)
        if response.status_code >= 400:
            logger.debug(f"Response: {response_json}")
            raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
        if not response_json["success"]:
            raise Failed(f"BHD Error: {response_json['status_message']}")
        return response.json()
