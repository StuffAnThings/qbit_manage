from modules import util

from modules.util import Failed
from json import JSONDecodeError

logger = util.logger

base_url = "https://notifiarr.com/api/v1/"
dev_url = "https://dev.notifiarr.com/api/v1/"


class Notifiarr:
    def __init__(self, config, params):
        self.config = config
        self.apikey = params["apikey"]
        self.develop = params["develop"]
        self.test = params["test"]
        self.instance = params["instance"]
        url, _ = self.get_url("user/validate/")
        response = self.config.get(url)
        response_json = None
        try:
            response_json = response.json()
        except JSONDecodeError as e:
            if response.status_code >= 400:
                if response.status_code == 525:
                    raise Failed("Notifiarr Error (Response: 525): SSL handshake between Cloudflare and the origin web server failed.")
                else:
                    raise Failed(e)
        if response_json is None:
            raise Failed("Notifiarr Error: Unable to connect to Notifiarr. It may be down?")
        if response.status_code >= 400 or ("result" in response_json and response_json["result"] == "error"):
            logger.debug(f"Response: {response_json}")
            raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
        if not params["test"] and not response_json["details"]["response"]:
            raise Failed("Notifiarr Error: Invalid apikey")

    def get_url(self, path):
        url = f"{dev_url if self.develop else base_url}{'notification/test' if self.test else f'{path}{self.apikey}'}"
        if self.config.trace_mode:
            logger.debug(url.replace(self.apikey, "APIKEY"))
        if self.test:
            params = {"event": f"qbitManage-{self.apikey[:5]}", "qbit_client": self.config.data["qbt"]["host"], "instance": self.instance}
        else:
            params = {"qbit_client": self.config.data["qbt"]["host"], "instance": self.instance}
        return url, params
