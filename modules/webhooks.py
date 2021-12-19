import logging
from json import JSONDecodeError

from modules.util import Failed

logger = logging.getLogger("qBit Manage")

class Webhooks:
    def __init__(self, config, system_webhooks, notifiarr=None, apprise=None):
        self.config = config
        self.error_webhooks = system_webhooks["error"] if "error" in system_webhooks else []
        self.run_start_webhooks = system_webhooks["run_start"] if "run_start" in system_webhooks else []
        self.run_end_webhooks = system_webhooks["run_end"] if "run_end" in system_webhooks else []
        if "function" in system_webhooks and system_webhooks["function"] is not None:
            try:
                self.function_webhooks = system_webhooks["function"][0]
            except IndexError:
                self.function_webhooks = []
        else:
            self.function_webhooks = []
        self.notifiarr = notifiarr
        self.apprise = apprise

    def _request(self, webhooks, json):
        if self.config.trace_mode:
            logger.debug("")
            logger.debug(f"JSON: {json}")
        for webhook in list(set(webhooks)):
            if self.config.trace_mode:
                logger.debug(f"Webhook: {webhook}")
            if webhook == "notifiarr":
                url, params = self.notifiarr.get_url("notification/qbitManage/")
                for x in range(6):
                    response = self.config.get(url, json=json, params=params)
                    if response.status_code < 500:
                        break
            elif webhook == "apprise":
                if self.apprise is None:
                    raise Failed(f"Webhook attribute set to apprise but apprise attribute is not configured.")
                json['urls'] = self.apprise.notify_url
                response = self.config.post(f"{self.apprise.api_url}/notify", json=json)
            else:
                response = self.config.post(webhook, json=json)
            
            skip = False
            try:
                response_json = response.json()
                if self.config.trace_mode:
                    logger.debug(f"Response: {response_json}")
                if "result" in response_json and response_json["result"] == "error" and "details" in response_json and "response" in response_json["details"]:
                    if ('trigger is not enabled' in response_json['details']['response']):
                        logger.debug(f"Notifiarr Warning: {response_json['details']['response']}")
                        skip = True
                    else:
                        raise Failed(f"Notifiarr Error: {response_json['details']['response']}")
                if (response.status_code >= 400 or ("result" in response_json and response_json["result"] == "error")) and skip == False:
                    raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
            except JSONDecodeError:
                if response.status_code >= 400:
                    raise Failed(f"({response.status_code} [{response.reason}])")

    def start_time_hooks(self, start_time):
        if self.run_start_webhooks:
            dry_run = self.config.args['dry_run']
            if dry_run:
                start_type = "Dry-"
            else:
                start_type = ""
            self._request(self.run_start_webhooks, {
                "function":"run_start",
                "title": None,
                "body":f"Starting {start_type}Run",
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "dry_run": self.config.args['dry_run']
            })

    def end_time_hooks(self, start_time, end_time, run_time, stats, body):
        dry_run = self.config.args['dry_run']
        if dry_run:
            start_type = "Dry-"
        else:
            start_type = ""
        if self.run_end_webhooks:
            self._request(self.run_end_webhooks, {
                "function":"run_end",
                "title": None,
                "body": body,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "run_time": run_time,
                "torrents_added": stats["added"],
                "torrents_deleted": stats["deleted"],
                "torrents_deleted_and_contents": stats["deleted_contents"],
                "torrents_resumed": stats["resumed"],
                "torrents_rechecked": stats["rechecked"],
                "torrents_categorized": stats["categorized"],
                "torrents_tagged": stats["tagged"],
                "remove_unregistered": stats["rem_unreg"],
                "orphaned_files_found": stats["orphaned"],
                "torrents_tagged_no_hardlinks": stats["taggednoHL"],
                "torrents_untagged_no_hardlinks": stats["untagged"],
                "files_deleted_from_recyclebin": stats["recycle_emptied"]
            })

    def error_hooks(self, text, function_error=None, critical=True):
        if self.error_webhooks:
            type = "failure" if critical == True else "warning"
            json = {"function":"run_error","title":f"{function_error} Error","body": str(text), "critical": critical, "type": type}
            if function_error:
                json["function_error"] = function_error
            self._request(self.error_webhooks, json)

    def function_hooks(self, webhook, json):
        if self.function_webhooks:
            self._request(webhook, json)