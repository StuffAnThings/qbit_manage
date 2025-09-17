"""Class to handle webhooks."""

import time
from json import JSONDecodeError

from requests.exceptions import JSONDecodeError as requestsJSONDecodeError

from modules import util
from modules.util import Failed

logger = util.logger

GROUP_NOTIFICATION_LIMIT = 10


class Webhooks:
    """Class to handle webhooks."""

    def __init__(self, config, system_webhooks, notifiarr=None, apprise=None, web_api_used=False):
        """Initialize the class."""
        self.config = config
        self.error_webhooks = system_webhooks["error"] if "error" in system_webhooks else []
        self.run_start_webhooks = system_webhooks["run_start"] if "run_start" in system_webhooks else []
        self.run_end_webhooks = system_webhooks["run_end"] if "run_end" in system_webhooks else []
        if "function" in system_webhooks and system_webhooks["function"] is not None:
            try:
                self.function_webhooks = system_webhooks["function"][0]
            except (IndexError, KeyError):
                self.function_webhooks = []
        else:
            self.function_webhooks = []
        self.notifiarr = notifiarr
        self.apprise = apprise
        self.web_api_used = web_api_used

    def request_and_check(self, webhook, json):
        """
        Send a webhook request and check for errors.
        retry up to 6 times if the response is a 500+ error.
        """
        retry_count = 0
        retry_attempts = 6
        request_delay = 2
        for retry_count in range(retry_attempts):
            if webhook == "notifiarr":
                response = self.notifiarr.notification(json=json)
            else:
                webhook_post = webhook
                if webhook == "apprise":
                    json["urls"] = self.apprise.notify_url
                    webhook_post = f"{self.apprise.api_url}/notify"
                response = self.config.post(webhook_post, json=json)
            if response.status_code < 500:
                return response
            logger.debug(f"({response.status_code} [{response.reason}]) Retrying in {request_delay} seconds.")
            time.sleep(request_delay)
            logger.debug(f"(Retry {retry_count + 1} of {retry_attempts}.")
            retry_count += 1
        logger.warning(f"({response.status_code} [{response.reason}]) after {retry_attempts} attempts.")

    def _request(self, webhooks, json):
        """
        Send a webhook request via request_and_check.
        Check for errors and log them.
        """
        logger.trace("")
        logger.trace(f"JSON: {json}")
        for webhook in list(set(webhooks)):
            response = None
            logger.trace(f"Webhook: {webhook}")
            if webhook is None:
                break
            elif (webhook == "notifiarr" and self.notifiarr is None) or (webhook == "apprise" and self.apprise is None):
                logger.warning(f"Webhook attribute set to {webhook} but {webhook} attribute is not configured.")
                break
            response = self.request_and_check(webhook, json)
            if response:
                skip = False
                try:
                    response_json = response.json()
                    logger.trace(f"Response: {response_json}")
                    if (
                        "result" in response_json
                        and response_json["result"] == "error"
                        and "details" in response_json
                        and "response" in response_json["details"]
                    ):
                        if "trigger is not enabled" in response_json["details"]["response"]:
                            logger.info(f"Notifiarr Warning: {response_json['details']['response']}")
                            skip = True
                        else:
                            raise Failed(f"Notifiarr Error: {response_json['details']['response']}")
                    if (
                        response.status_code >= 400 or ("result" in response_json and response_json["result"] == "error")
                    ) and skip is False:
                        raise Failed(f"({response.status_code} [{response.reason}]) {response_json}")
                except (JSONDecodeError, requestsJSONDecodeError) as exc:
                    if response.status_code >= 400:
                        raise Failed(f"({response.status_code} [{response.reason}])") from exc

    def start_time_hooks(self, start_time):
        """Send a webhook to notify that the run has started."""
        # Skip sending start notifications during config validation
        if self.run_start_webhooks and not self.config.args.get("validation_mode", False):
            dry_run = self.config.commands["dry_run"]
            if dry_run:
                start_type = "Dry-"
            else:
                start_type = ""

            # Get enabled commands
            enabled_commands = [
                cmd
                for cmd in [
                    "recheck",
                    "cat_update",
                    "tag_update",
                    "rem_unregistered",
                    "tag_tracker_error",
                    "rem_orphaned",
                    "tag_nohardlinks",
                    "share_limits",
                ]
                if self.config.commands.get(cmd, False)
            ]

            # Get execution options
            execution_options = [
                opt for opt in ["skip_cleanup", "dry_run", "skip_qb_version_check"] if self.config.commands.get(opt, False)
            ]

            self._request(
                self.run_start_webhooks,
                {
                    "function": "run_start",
                    "title": None,
                    "body": f"Starting {'WebAPI ' if self.web_api_used else ''}{start_type}Run",
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "dry_run": self.config.commands["dry_run"],
                    "web_api_used": self.web_api_used,
                    "commands": enabled_commands,
                    "execution_options": execution_options,
                },
            )

    def end_time_hooks(self, start_time, end_time, run_time, next_run, stats, body):
        """Send a webhook to notify that the run has ended."""
        if self.run_end_webhooks:
            self._request(
                self.run_end_webhooks,
                {
                    "function": "run_end",
                    "title": None,
                    "body": body,
                    "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run is not None else next_run,
                    "run_time": run_time,
                    "torrents_added": stats["added"],
                    "torrents_deleted": stats["deleted"],
                    "torrents_deleted_and_contents_count": stats["deleted_contents"],
                    "torrents_resumed": stats["resumed"],
                    "torrents_rechecked": stats["rechecked"],
                    "torrents_categorized": stats["categorized"],
                    "torrents_tagged": stats["tagged"],
                    "remove_unregistered": stats["rem_unreg"],
                    "torrents_tagged_tracker_error": stats["tagged_tracker_error"],
                    "torrents_untagged_tracker_error": stats["untagged_tracker_error"],
                    "orphaned_files_found": stats["orphaned"],
                    "torrents_tagged_no_hardlinks": stats["tagged_noHL"],
                    "torrents_untagged_no_hardlinks": stats["untagged_noHL"],
                    "torrents_updated_share_limits": stats["updated_share_limits"],
                    "torrents_cleaned_share_limits": stats["cleaned_share_limits"],
                    "files_deleted_from_recyclebin": stats["recycle_emptied"],
                    "files_deleted_from_orphaned": stats["orphaned_emptied"],
                },
            )

    def error_hooks(self, text, function_error=None, critical=True):
        """Send a webhook to notify that an error has occurred."""
        if self.error_webhooks:
            err_type = "failure" if critical is True else "warning"
            json = {
                "function": "run_error",
                "title": f"{function_error} Error",
                "body": str(text),
                "critical": critical,
                "type": err_type,
            }
            if function_error:
                json["function_error"] = function_error
            self._request(self.error_webhooks, json)

    def function_hooks(self, webhook, json):
        """Send a webhook to notify that a function has completed."""
        if self.function_webhooks:
            self._request(webhook, json)

    def notify(self, torrents_updated=[], payload={}, group_by=""):
        if len(torrents_updated) > GROUP_NOTIFICATION_LIMIT:
            logger.trace(
                f"Number of torrents updated > {GROUP_NOTIFICATION_LIMIT}, grouping notifications"
                f"{f' by {group_by}' if group_by else ''}",
            )
            if group_by == "category":
                group_attr = group_notifications_by_key(payload, "torrent_category")
            elif group_by == "tag":
                group_attr = group_notifications_by_key(payload, "torrent_tag")
            elif group_by == "tracker":
                group_attr = group_notifications_by_key(payload, "torrent_tracker")
            elif group_by == "status":
                group_attr = group_notifications_by_key(payload, "torrent_status")

            # group notifications by grouping attribute
            for group in group_attr:
                num_torrents_updated = len(group_attr[group]["torrents"])
                only_one_torrent_updated = num_torrents_updated == 1

                attr = {
                    "function": group_attr[group]["function"],
                    "title": f"{group_attr[group]['title']} for {group}",
                    "body": (
                        group_attr[group]["body"]
                        if only_one_torrent_updated
                        else (
                            f"Updated {num_torrents_updated} "
                            f"{'torrent' if only_one_torrent_updated else 'torrents'} with {group_by} '{group}'"
                        )
                    ),
                    "torrents": group_attr[group]["torrents"],
                }
                if group_by == "category":
                    attr["torrent_category"] = group
                    attr["torrent_tag"] = group_attr[group].get("torrent_tag") if only_one_torrent_updated else None
                    attr["torrent_tracker"] = group_attr[group].get("torrent_tracker") if only_one_torrent_updated else None
                    attr["notifiarr_indexer"] = group_attr[group].get("notifiarr_indexer") if only_one_torrent_updated else None
                elif group_by == "tag":
                    attr["torrent_tag"] = group
                    attr["torrent_category"] = group_attr[group].get("torrent_category") if only_one_torrent_updated else None
                    attr["torrent_tracker"] = group_attr[group].get("torrent_tracker")
                    attr["notifiarr_indexer"] = group_attr[group].get("notifiarr_indexer")
                elif group_by == "tracker":
                    attr["torrent_tracker"] = group
                    attr["torrent_category"] = group_attr[group].get("torrent_category") if only_one_torrent_updated else None
                    attr["torrent_tag"] = group_attr[group].get("torrent_tag") if only_one_torrent_updated else None
                    attr["notifiarr_indexer"] = group_attr[group].get("notifiarr_indexer")
                elif group_by == "status":
                    attr["torrent_status"] = group
                    attr["torrent_category"] = group_attr[group].get("torrent_category")
                    attr["torrent_tag"] = group_attr[group].get("torrent_tag")
                    attr["torrent_tracker"] = group_attr[group].get("torrent_tracker")
                    attr["notifiarr_indexer"] = group_attr[group].get("notifiarr_indexer")

                self.config.send_notifications(attr)
        else:
            for attr in payload:
                self.config.send_notifications(attr)


def group_notifications_by_key(payload, key):
    """Group notifications by key"""
    group_attr = {}
    for attr in payload:
        group = attr[key]
        if group not in group_attr:
            group_attr[group] = attr
        else:
            group_attr[group]["torrents"].append(attr.get("torrents", [None])[0])
    return group_attr
