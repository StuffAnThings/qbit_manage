import os, sys
from qbittorrentapi import Client, Version, LoginFailed, APIConnectionError, NotFound404Error, Conflict409Error
from modules import util
from modules.util import Failed, list_in_text
from datetime import timedelta
from collections import Counter
from fnmatch import fnmatch
from alive_progress import alive_it, config_handler

logger = util.logger


class Qbt:

    def __init__(self, config, params):
        self.config = config
        config_handler.set_global(bar=None, receipt=False)
        self.host = params["host"]
        self.username = params["username"]
        self.password = params["password"]
        logger.secret(self.username)
        logger.secret(self.password)
        logger.debug(f'Host: {self.host}, Username: {self.username}, Password: {self.password}')
        try:
            self.client = Client(host=self.host, username=self.username, password=self.password, VERIFY_WEBUI_CERTIFICATE=False)
            self.client.auth_log_in()

            SUPPORTED_VERSION = Version.latest_supported_app_version()
            CURRENT_VERSION = self.client.app.version
            logger.debug(f'qBittorrent: {self.client.app.version}')
            logger.debug(f'qBittorrent Web API: {self.client.app.web_api_version}')
            logger.debug(f'qbit_manage support version: {SUPPORTED_VERSION}')
            if not Version.is_app_version_supported(CURRENT_VERSION):
                e = (f"Qbittorrent Error: qbit_manage is only comaptible with {SUPPORTED_VERSION} or lower. You are currently on {CURRENT_VERSION}." + '\n'
                     + f"Please downgrade to your Qbittorrent version to {SUPPORTED_VERSION} to use qbit_manage.")
                self.config.notify(e, "Qbittorrent")
                logger.print_line(e, 'CRITICAL')
                sys.exit(0)
            logger.info("Qbt Connection Successful")
        except LoginFailed:
            e = "Qbittorrent Error: Failed to login. Invalid username/password."
            self.config.notify(e, "Qbittorrent")
            raise Failed(e)
        except APIConnectionError:
            e = "Qbittorrent Error: Unable to connect to the client."
            self.config.notify(e, "Qbittorrent")
            raise Failed(e)
        except Exception:
            e = "Qbittorrent Error: Unable to connect to the client."
            self.config.notify(e, "Qbittorrent")
            raise Failed(e)
        logger.separator("Getting Torrent List", space=False, border=False)
        self.torrent_list = self.get_torrents({'sort': 'added_on'})

        # Will create a 2D Dictionary with the torrent name as the key
        # torrentdict = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'count':1, 'msg':'[]'...},
        #                'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}, 'count':2, 'msg':'[]'...}
        # List of dictionary key definitions
        # Category = Returns category of the torrent (str)
        # save_path = Returns the save path of the torrent (str)
        # count = Returns a count of the total number of torrents with the same name (int)
        # msg = Returns a list of torrent messages by name (list of str)
        # status = Returns the list of status numbers of the torrent by name
        # (0: Tracker is disabled (used for DHT, PeX, and LSD),
        # 1: Tracker has not been contacted yet,
        # 2: Tracker has been contacted and is working,
        # 3: Tracker is updating,
        # 4: Tracker has been contacted, but it is not working (or doesn't send proper replies)
        # is_complete = Returns the state of torrent (Returns True if at least one of the torrent with the State is categorized as Complete.)
        # first_hash = Returns the hash number of the original torrent (Assuming the torrent list is sorted by date added (Asc))
        def get_torrent_info(torrent_list):
            dry_run = self.config.commands['dry_run']
            loglevel = 'DRYRUN' if dry_run else 'INFO'
            torrentdict = {}
            t_obj_unreg = []
            t_obj_valid = []
            t_obj_list = []
            settings = self.config.settings
            logger.separator("Checking Settings", space=False, border=False)
            if settings['force_auto_tmm']:
                logger.print_line('force_auto_tmm set to True. Will force Auto Torrent Management for all torrents.', loglevel)
            logger.separator("Gathering Torrent Information", space=True, border=True)
            for torrent in alive_it(torrent_list):
                is_complete = False
                msg = None
                status = None
                working_tracker = None
                issue = {'potential': False}
                if torrent.auto_tmm is False and settings['force_auto_tmm'] and torrent.category != '' and not dry_run:
                    torrent.set_auto_management(True)
                try:
                    torrent_name = torrent.name
                    torrent_hash = torrent.hash
                    torrent_is_complete = torrent.state_enum.is_complete
                    save_path = torrent.save_path
                    category = torrent.category
                    torrent_trackers = torrent.trackers
                except Exception as e:
                    self.config.notify(e, 'Get Torrent Info', False)
                    logger.warning(e)
                if torrent_name in torrentdict:
                    t_obj_list.append(torrent)
                    t_count = torrentdict[torrent_name]['count'] + 1
                    msg_list = torrentdict[torrent_name]['msg']
                    status_list = torrentdict[torrent_name]['status']
                    is_complete = True if torrentdict[torrent_name]['is_complete'] is True else torrent_is_complete
                    first_hash = torrentdict[torrent_name]['first_hash']
                else:
                    t_obj_list = [torrent]
                    t_count = 1
                    msg_list = []
                    status_list = []
                    is_complete = torrent_is_complete
                    first_hash = torrent_hash
                for x in torrent_trackers:
                    if x.url.startswith('http'):
                        status = x.status
                        msg = x.msg.upper()
                        exception = [
                            "DOWN",
                            "DOWN.",
                            "IT MAY BE DOWN,",
                            "UNREACHABLE",
                            "(UNREACHABLE)",
                            "BAD GATEWAY",
                            "TRACKER UNAVAILABLE"
                        ]
                        if x.status == 2:
                            working_tracker = True
                            break
                        # Add any potential unregistered torrents to a list
                        if x.status == 4 and not list_in_text(msg, exception):
                            issue['potential'] = True
                            issue['msg'] = msg
                            issue['status'] = status
                if working_tracker:
                    status = 2
                    msg = ''
                    t_obj_valid.append(torrent)
                elif issue['potential']:
                    status = issue['status']
                    msg = issue['msg']
                    t_obj_unreg.append(torrent)
                if msg is not None: msg_list.append(msg)
                if status is not None: status_list.append(status)
                torrentattr = {
                    'torrents': t_obj_list, 'Category': category, 'save_path': save_path, 'count': t_count,
                    'msg': msg_list, 'status': status_list, 'is_complete': is_complete, 'first_hash': first_hash
                }
                torrentdict[torrent_name] = torrentattr
            return torrentdict, t_obj_unreg, t_obj_valid
        self.torrentinfo = None
        self.torrentissue = None
        self.torrentvalid = None
        if config.commands['recheck'] or config.commands['cross_seed'] or config.commands['rem_unregistered'] or config.commands['tag_tracker_error'] or config.commands['tag_nohardlinks']:
            # Get an updated torrent dictionary information of the torrents
            self.torrentinfo, self.torrentissue, self.torrentvalid = get_torrent_info(self.torrent_list)

    def get_torrents(self, params):
        return self.client.torrents.info(**params)

    def category(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_cat = 0

        def update_cat(new_cat, cat_change):
            nonlocal dry_run, torrent, num_cat
            tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
            old_cat = torrent.category
            if not dry_run:
                try:
                    torrent.set_category(category=new_cat)
                    if torrent.auto_tmm is False and self.config.settings['force_auto_tmm']:
                        torrent.set_auto_management(True)
                except Conflict409Error:
                    e = logger.print_line(f'Existing category "{new_cat}" not found for save path {torrent.save_path}, category will be created.', loglevel)
                    self.config.notify(e, 'Update Category', False)
                    self.client.torrent_categories.create_category(name=new_cat, save_path=torrent.save_path)
                    torrent.set_category(category=new_cat)
            body = []
            body += logger.print_line(logger.insert_space(f'Torrent Name: {torrent.name}', 3), loglevel)
            if cat_change:
                body += logger.print_line(logger.insert_space(f'Old Category: {old_cat}', 3), loglevel)
                title = "Moving Categories"
            else:
                title = "Updating Categories"
            body += logger.print_line(logger.insert_space(f'New Category: {new_cat}', 3), loglevel)
            body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
            attr = {
                "function": "cat_update",
                "title": title,
                "body": "\n".join(body),
                "torrent_name": torrent.name,
                "torrent_category": new_cat,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"]
            }
            self.config.send_notifications(attr)
            num_cat += 1

        if self.config.commands['cat_update']:
            logger.separator("Updating Categories", space=False, border=False)
            torrent_list = self.get_torrents({'category': '', 'filter': 'completed'})
            for torrent in torrent_list:
                new_cat = self.config.get_category(torrent.save_path)
                update_cat(new_cat, False)

            # Change categories
            if self.config.cat_change:
                for old_cat in self.config.cat_change:
                    torrent_list = self.get_torrents({'category': old_cat, 'filter': 'completed'})
                    for torrent in torrent_list:
                        new_cat = self.config.cat_change[old_cat]
                        update_cat(new_cat, True)

            if num_cat >= 1:
                logger.print_line(f"{'Did not update' if dry_run else 'Updated'} {num_cat} new categories.", loglevel)
            else:
                logger.print_line('No new torrents to categorize.', loglevel)
        return num_cat

    def tags(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_tags = 0
        ignore_tags = self.config.settings['ignoreTags_OnUpdate']
        if self.config.commands['tag_update']:
            logger.separator("Updating Tags", space=False, border=False)
            for torrent in self.torrent_list:
                check_tags = util.get_list(torrent.tags)
                if torrent.tags == '' or (len([x for x in check_tags if x not in ignore_tags]) == 0):
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    if tracker["tag"]:
                        num_tags += len(tracker["tag"])
                        body = []
                        body += logger.print_line(logger.insert_space(f'Torrent Name: {torrent.name}', 3), loglevel)
                        body += logger.print_line(logger.insert_space(f'New Tag{"s" if len(tracker["tag"]) > 1 else ""}: {", ".join(tracker["tag"])}', 8), loglevel)
                        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
                        body.extend(self.set_tags_and_limits(torrent, tracker["max_ratio"], tracker["max_seeding_time"], tracker["limit_upload_speed"], tracker["tag"]))
                        category = self.config.get_category(torrent.save_path) if torrent.category == '' else torrent.category
                        attr = {
                            "function": "tag_update",
                            "title": "Updating Tags",
                            "body": "\n".join(body),
                            "torrent_name": torrent.name,
                            "torrent_category": category,
                            "torrent_tag": ", ".join(tracker["tag"]),
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                            "torrent_max_ratio": tracker["max_ratio"],
                            "torrent_max_seeding_time": tracker["max_seeding_time"],
                            "torrent_limit_upload_speed": tracker["limit_upload_speed"]
                        }
                        self.config.send_notifications(attr)
            if num_tags >= 1:
                logger.print_line(f"{'Did not update' if dry_run else 'Updated'} {num_tags} new tags.", loglevel)
            else:
                logger.print_line('No new torrents to tag.', loglevel)
        return num_tags

    def set_tags_and_limits(self, torrent, max_ratio, max_seeding_time, limit_upload_speed=None, tags=None, restore=False):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        body = []
        # Print Logs
        if limit_upload_speed:
            if limit_upload_speed == -1:                    body += logger.print_line(logger.insert_space('Limit UL Speed: Infinity', 1), loglevel)
            else:                                           body += logger.print_line(logger.insert_space(f'Limit UL Speed: {limit_upload_speed} kB/s', 1), loglevel)
        if max_ratio or max_seeding_time:
            if (max_ratio == -2 or max_seeding_time == -2) and not restore:   body += logger.print_line(logger.insert_space('Share Limit: Use Global Share Limit', 4), loglevel)
            elif (max_ratio == -1 or max_seeding_time == -1) and not restore: body += logger.print_line(logger.insert_space('Share Limit: Set No Share Limit', 4), loglevel)
            else:
                if max_ratio != torrent.max_ratio and (not max_seeding_time or max_seeding_time < 0):
                    body += logger.print_line(logger.insert_space(f'Share Limit: Max Ratio = {max_ratio}', 4), loglevel)
                elif max_seeding_time != torrent.max_seeding_time and (not max_ratio or max_ratio < 0):
                    body += logger.print_line(logger.insert_space(f'Share Limit: Max Seed Time = {max_seeding_time} min', 4), loglevel)
                elif max_ratio != torrent.max_ratio and max_seeding_time != torrent.max_seeding_time:
                    body += logger.print_line(logger.insert_space(f'Share Limit: Max Ratio = {max_ratio}, Max Seed Time = {max_seeding_time} min', 4), loglevel)
        # Update Torrents
        if not dry_run:
            if tags: torrent.add_tags(tags)
            if limit_upload_speed:
                if limit_upload_speed == -1: torrent.set_upload_limit(-1)
                else: torrent.set_upload_limit(limit_upload_speed*1024)
            if (max_ratio or max_seeding_time) and not restore:
                if max_ratio == -2 or max_seeding_time == -2:
                    torrent.set_share_limits(-2, -2)
                    return body
                elif max_ratio == -1 or max_seeding_time == -1:
                    torrent.set_share_limits(-1, -1)
                    return body
            if not max_ratio: max_ratio = torrent.max_ratio
            if not max_seeding_time: max_seeding_time = torrent.max_seeding_time
            torrent.set_share_limits(max_ratio, max_seeding_time)
        return body

    def tag_nohardlinks(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_tags = 0  # counter for the number of torrents that has no hard links
        del_tor = 0  # counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion
        del_tor_cont = 0  # counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion including contents
        num_untag = 0  # counter for number of torrents that previously had no hard links but now have hard links

        if self.config.commands['tag_nohardlinks']:
            logger.separator("Tagging Torrents with No Hardlinks", space=False, border=False)
            nohardlinks = self.config.nohardlinks
            tdel_dict = {}  # dictionary to track the torrent names and content path that meet the deletion criteria
            root_dir = self.config.root_dir
            remote_dir = self.config.remote_dir
            for category in nohardlinks:
                torrent_list = self.get_torrents({'category': category, 'filter': 'completed'})
                if len(torrent_list) == 0:
                    e = 'No torrents found in the category ('+category+') defined under nohardlinks attribute in the config. ' + \
                        'Please check if this matches with any category in qbittorrent and has 1 or more torrents.'
                    # self.config.notify(e, 'Tag No Hard Links', False)
                    logger.warning(e)
                    continue
                for torrent in torrent_list:
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    if any(tag in torrent.tags for tag in nohardlinks[category]['exclude_tags']):
                        # Skip to the next torrent if we find any torrents that are in the exclude tag
                        continue
                    else:
                        # Checks for any hard links and not already tagged
                        if util.nohardlink(torrent['content_path'].replace(root_dir, remote_dir)):
                            # Will only tag new torrents that don't have noHL tag
                            if 'noHL' not in torrent.tags:
                                num_tags += 1
                                body = []
                                body += logger.print_line(logger.insert_space(f'Torrent Name: {torrent.name}', 3), loglevel)
                                body += logger.print_line(logger.insert_space('Added Tag: noHL', 6), loglevel)
                                body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
                                body.extend(self.set_tags_and_limits(torrent, nohardlinks[category]["max_ratio"],
                                            nohardlinks[category]["max_seeding_time"], nohardlinks[category]["limit_upload_speed"], tags='noHL'))
                                attr = {
                                    "function": "tag_nohardlinks",
                                    "title": "Tagging Torrents with No Hardlinks",
                                    "body": "\n".join(body),
                                    "torrent_name": torrent.name,
                                    "torrent_category": torrent.category,
                                    "torrent_tag": 'noHL',
                                    "torrent_tracker": tracker["url"],
                                    "notifiarr_indexer": tracker["notifiarr"],
                                    "torrent_max_ratio": nohardlinks[category]["max_ratio"],
                                    "torrent_max_seeding_time": nohardlinks[category]["max_seeding_time"],
                                    "torrent_limit_upload_speed": nohardlinks[category]["limit_upload_speed"]
                                }
                                self.config.send_notifications(attr)
                            # Cleans up previously tagged noHL torrents
                            else:
                                # Determine min_seeding_time.  noHl > Tracker w/ default 0
                                min_seeding_time = 0
                                tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                                if nohardlinks[category]["min_seeding_time"]:
                                    min_seeding_time = nohardlinks[category]["min_seeding_time"]
                                elif tracker["min_seeding_time"]:
                                    min_seeding_time = tracker["min_seeding_time"]

                                # Deletes torrent with data if cleanup is set to true and meets the ratio/seeding requirements
                                if (nohardlinks[category]['cleanup'] and torrent.state_enum.is_paused and len(nohardlinks[category]) > 0
                                    and torrent.seeding_time > (min_seeding_time*60)):
                                        tdel_dict[torrent.name] = torrent['content_path'].replace(root_dir, root_dir)
                    # Checks to see if previous noHL tagged torrents now have hard links.
                    if (not (util.nohardlink(torrent['content_path'].replace(root_dir, root_dir))) and ('noHL' in torrent.tags)):
                        num_untag += 1
                        body = []
                        body += logger.print_line(f'Previous Tagged noHL Torrent Name: {torrent.name} has hard links found now.', loglevel)
                        body += logger.print_line(logger.insert_space('Removed Tag: noHL', 6), loglevel)
                        body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
                        body += logger.print_line(f"{'Not Reverting' if dry_run else 'Reverting'} share limits.", loglevel)
                        restore_max_ratio = tracker["max_ratio"]
                        restore_max_seeding_time = tracker["max_seeding_time"]
                        restore_limit_upload_speed = tracker["limit_upload_speed"]
                        if restore_max_ratio is None: restore_max_ratio = -2
                        if restore_max_seeding_time is None: restore_max_seeding_time = -2
                        if restore_limit_upload_speed is None: restore_limit_upload_speed = -1
                        if not dry_run:
                            torrent.remove_tags(tags='noHL')
                            body.extend(self.set_tags_and_limits(torrent, restore_max_ratio, restore_max_seeding_time, restore_limit_upload_speed, restore=True))
                            if torrent.state == 'pausedUP': torrent.resume()
                        attr = {
                            "function": "untag_nohardlinks",
                            "title": "Untagging Previous Torrents that now have Hard Links",
                            "body": "\n".join(body),
                            "torrent_name": torrent.name,
                            "torrent_category": torrent.category,
                            "torrent_tag": 'noHL',
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                            "torrent_max_ratio": restore_max_ratio,
                            "torrent_max_seeding_time": restore_max_seeding_time,
                            "torrent_limit_upload_speed": restore_limit_upload_speed
                        }
                        self.config.send_notifications(attr)
                # loop through torrent list again for cleanup purposes
                if (nohardlinks[category]['cleanup']):
                    for torrent in torrent_list:
                        t_name = torrent.name
                        if t_name in tdel_dict.keys() and 'noHL' in torrent.tags:
                            t_count = self.torrentinfo[t_name]['count']
                            t_msg = self.torrentinfo[t_name]['msg']
                            t_status = self.torrentinfo[t_name]['status']
                            # Double check that the content path is the same before we delete anything
                            if torrent['content_path'].replace(root_dir, root_dir) == tdel_dict[t_name]:
                                tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                                body = []
                                body += logger.print_line(logger.insert_space(f'Torrent Name: {t_name}', 3), loglevel)
                                body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
                                body += logger.print_line(logger.insert_space("Cleanup: True [No hard links found and meets Share Limits.]", 8), loglevel)
                                attr = {
                                    "function": "cleanup_tag_nohardlinks",
                                    "title": "Removing NoHL Torrents and meets Share Limits",
                                    "torrent_name": t_name,
                                    "torrent_category": torrent.category,
                                    "cleanup": 'True',
                                    "torrent_tracker": tracker["url"],
                                    "notifiarr_indexer": tracker["notifiarr"],
                                }
                                if (os.path.exists(torrent['content_path'].replace(root_dir, root_dir))):
                                    # Checks if any of the original torrents are working
                                    if t_count > 1 and ('' in t_msg or 2 in t_status):
                                        del_tor += 1
                                        attr["torrents_deleted_and_contents"] = False
                                        if not dry_run: self.tor_delete_recycle(torrent, attr)
                                        body += logger.print_line(logger.insert_space('Deleted .torrent but NOT content files.', 8), loglevel)
                                    else:
                                        del_tor_cont += 1
                                        attr["torrents_deleted_and_contents"] = True
                                        if not dry_run: self.tor_delete_recycle(torrent, attr)
                                        body += logger.print_line(logger.insert_space('Deleted .torrent AND content files.', 8), loglevel)
                                else:
                                    del_tor += 1
                                    attr["torrents_deleted_and_contents"] = False
                                    if not dry_run: self.tor_delete_recycle(torrent, attr)
                                    body += logger.print_line(logger.insert_space('Deleted .torrent but NOT content files.', 8), loglevel)
                                attr["body"] = "\n".join(body)
                                self.config.send_notifications(attr)
                                self.torrentinfo[t_name]['count'] -= 1
            if num_tags >= 1:
                logger.print_line(f"{'Did not Tag/set' if dry_run else 'Tag/set'} share limits for {num_tags} .torrent{'s.' if num_tags > 1 else '.'}", loglevel)
            else:
                logger.print_line('No torrents to tag with no hard links.', loglevel)
            if num_untag >= 1: logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} noHL tags / share limits for {num_untag} .torrent{'s.' if num_untag > 1 else '.'}", loglevel)
            if del_tor >= 1: logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor} .torrent{'s' if del_tor > 1 else ''} but not content files.", loglevel)
            if del_tor_cont >= 1: logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor_cont} .torrent{'s' if del_tor_cont > 1 else ''} AND content files.", loglevel)
        return num_tags, num_untag, del_tor, del_tor_cont

    def rem_unregistered(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        del_tor = 0
        del_tor_cont = 0
        num_tor_error = 0
        num_untag = 0
        tor_error_summary = ''
        tag_error = self.config.settings['tracker_error_tag']
        cfg_rem_unregistered = self.config.commands['rem_unregistered']
        cfg_tag_error = self.config.commands['tag_tracker_error']

        def tag_tracker_error():
            nonlocal dry_run, t_name, msg_up, msg, tracker, t_cat, torrent, tag_error, tor_error_summary, num_tor_error
            tor_error = ''
            tor_error += (logger.insert_space(f'Torrent Name: {t_name}', 3)+'\n')
            tor_error += (logger.insert_space(f'Status: {msg}', 9)+'\n')
            tor_error += (logger.insert_space(f'Tracker: {tracker["url"]}', 8)+'\n')
            tor_error += (logger.insert_space(f"Added Tag: {tag_error}", 6)+'\n')
            tor_error_summary += tor_error
            num_tor_error += 1
            attr = {
                "function": "tag_tracker_error",
                "title": "Tag Tracker Error Torrents",
                "body": tor_error,
                "torrent_name": t_name,
                "torrent_category": t_cat,
                "torrent_tag": tag_error,
                "torrent_status": msg,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            self.config.send_notifications(attr)
            if not dry_run: torrent.add_tags(tags=tag_error)

        def del_unregistered():
            nonlocal dry_run, loglevel, del_tor, del_tor_cont, t_name, msg_up, msg, tracker, t_cat, t_msg, t_status, torrent
            body = []
            body += logger.print_line(logger.insert_space(f'Torrent Name: {t_name}', 3), loglevel)
            body += logger.print_line(logger.insert_space(f'Status: {msg}', 9), loglevel)
            body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
            attr = {
                "function": "rem_unregistered",
                "title": "Removing Unregistered Torrents",
                "torrent_name": t_name,
                "torrent_category": t_cat,
                "torrent_status": msg,
                "torrent_tracker": tracker["url"],
                "notifiarr_indexer": tracker["notifiarr"],
            }
            if t_count > 1:
                # Checks if any of the original torrents are working
                if '' in t_msg or 2 in t_status:
                    attr["torrents_deleted_and_contents"] = False
                    if not dry_run: self.tor_delete_recycle(torrent, attr)
                    body += logger.print_line(logger.insert_space('Deleted .torrent but NOT content files.', 8), loglevel)
                    del_tor += 1
                else:
                    attr["torrents_deleted_and_contents"] = True
                    if not dry_run: self.tor_delete_recycle(torrent, attr)
                    body += logger.print_line(logger.insert_space('Deleted .torrent AND content files.', 8), loglevel)
                    del_tor_cont += 1
            else:
                attr["torrents_deleted_and_contents"] = True
                if not dry_run: self.tor_delete_recycle(torrent, attr)
                body += logger.print_line(logger.insert_space('Deleted .torrent AND content files.', 8), loglevel)
                del_tor_cont += 1
            attr["body"] = "\n".join(body)
            self.config.send_notifications(attr)
            self.torrentinfo[t_name]['count'] -= 1

        if cfg_rem_unregistered or cfg_tag_error:
            if cfg_tag_error: logger.separator("Tagging Torrents with Tracker Errors", space=False, border=False)
            elif cfg_rem_unregistered: logger.separator("Removing Unregistered Torrents", space=False, border=False)
            unreg_msgs = [
                'UNREGISTERED',
                'TORRENT NOT FOUND',
                'TORRENT IS NOT FOUND',
                'NOT REGISTERED',
                'NOT EXIST',
                'UNKNOWN TORRENT',
                'TRUMP',
                'RETITLED',
                'TRUNCATED',
                'TORRENT IS NOT AUTHORIZED FOR USE ON THIS TRACKER'
            ]
            ignore_msgs = [
                'YOU HAVE REACHED THE CLIENT LIMIT FOR THIS TORRENT',
                'MISSING PASSKEY',
                'MISSING INFO_HASH',
                'PASSKEY IS INVALID',
                'INVALID PASSKEY',
                'EXPECTED VALUE (LIST, DICT, INT OR STRING) IN BENCODED STRING',
                'COULD NOT PARSE BENCODED DATA',
                'STREAM TRUNCATED'
            ]
            for torrent in self.torrentvalid:
                check_tags = util.get_list(torrent.tags)
                # Remove any error torrents Tags that are no longer unreachable.
                if tag_error in check_tags:
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    num_untag += 1
                    body = []
                    body += logger.print_line(f'Previous Tagged {tag_error} torrent currently has a working tracker.', loglevel)
                    body += logger.print_line(logger.insert_space(f'Torrent Name: {torrent.name}', 3), loglevel)
                    body += logger.print_line(logger.insert_space(f'Removed Tag: {tag_error}', 4), loglevel)
                    body += logger.print_line(logger.insert_space(f'Tracker: {tracker["url"]}', 8), loglevel)
                    if not dry_run: torrent.remove_tags(tags=tag_error)
                    attr = {
                        "function": "untag_tracker_error",
                        "title": "Untagging Tracker Error Torrent",
                        "body": "\n".join(body),
                        "torrent_name": torrent.name,
                        "torrent_category": torrent.category,
                        "torrent_tag": tag_error,
                        "torrent_tracker": tracker["url"],
                        "notifiarr_indexer": tracker["notifiarr"]
                    }
                    self.config.send_notifications(attr)
            for torrent in self.torrentissue:
                t_name = torrent.name
                t_cat = self.torrentinfo[t_name]['Category']
                t_count = self.torrentinfo[t_name]['count']
                t_msg = self.torrentinfo[t_name]['msg']
                t_status = self.torrentinfo[t_name]['status']
                check_tags = util.get_list(torrent.tags)
                try:
                    for x in torrent.trackers:
                        if x.url.startswith('http'):
                            tracker = self.config.get_tags([x.url])
                            msg_up = x.msg.upper()
                            msg = x.msg
                            # Tag any error torrents
                            if cfg_tag_error:
                                if x.status == 4 and tag_error not in check_tags:
                                    tag_tracker_error()
                            if cfg_rem_unregistered:
                                # Tag any error torrents that are not unregistered
                                if not list_in_text(msg_up, unreg_msgs) and x.status == 4 and tag_error not in check_tags:
                                    # Check for unregistered torrents using BHD API if the tracker is BHD
                                    if 'tracker.beyond-hd.me' in tracker['url'] and self.config.BeyondHD is not None and not list_in_text(msg_up, ignore_msgs):
                                        json = {"info_hash": torrent.hash}
                                        response = self.config.BeyondHD.search(json)
                                        if response['total_results'] == 0:
                                            del_unregistered()
                                            break
                                    tag_tracker_error()
                                if list_in_text(msg_up, unreg_msgs) and not list_in_text(msg_up, ignore_msgs) and x.status == 4:
                                    del_unregistered()
                                    break
                except NotFound404Error:
                    continue
                except Exception as e:
                    logger.stacktrace()
                    self.config.notify(e, 'Remove Unregistered Torrents', False)
                    logger.error(f"Unknown Error: {e}")
            if cfg_rem_unregistered:
                if del_tor >= 1 or del_tor_cont >= 1:
                    if del_tor >= 1: logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor} .torrent{'s' if del_tor > 1 else ''} but not content files.", loglevel)
                    if del_tor_cont >= 1: logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor_cont} .torrent{'s' if del_tor_cont > 1 else ''} AND content files.", loglevel)
                else:
                    logger.print_line('No unregistered torrents found.', loglevel)
            if num_untag >= 1: logger.print_line(f"{'Did not delete' if dry_run else 'Deleted'} {tag_error} tags for {num_untag} .torrent{'s.' if num_untag > 1 else '.'}", loglevel)
            if num_tor_error >= 1:
                logger.separator(f"{num_tor_error} Torrents with tracker errors found", space=False, border=False, loglevel=loglevel)
                logger.print_line(tor_error_summary.rstrip(), loglevel)
        return del_tor, del_tor_cont, num_tor_error, num_untag

    # Function used to move any torrents from the cross seed directory to the correct save directory
    def cross_seed(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        added = 0  # Keep track of total torrents tagged
        tagged = 0  # Track # of torrents tagged that are not cross-seeded
        if self.config.commands['cross_seed']:
            logger.separator("Checking for Cross-Seed Torrents", space=False, border=False)
            # List of categories for all torrents moved
            categories = []

            # Only get torrent files
            cs_files = [f for f in os.listdir(self.config.cross_seed_dir) if f.endswith('torrent')]
            dir_cs = self.config.cross_seed_dir
            dir_cs_out = os.path.join(dir_cs, 'qbit_manage_added')
            os.makedirs(dir_cs_out, exist_ok=True)
            for file in cs_files:
                t_name = file.split(']', 2)[2].split('.torrent')[0]
                t_tracker = file.split(']', 2)[1][1:]
                # Substring Key match in dictionary (used because t_name might not match exactly with torrentdict key)
                # Returned the dictionary of filtered item
                torrentdict_file = dict(filter(lambda item: t_name in item[0], self.torrentinfo.items()))
                if torrentdict_file:
                    # Get the exact torrent match name from torrentdict
                    t_name = next(iter(torrentdict_file))
                    dest = os.path.join(self.torrentinfo[t_name]['save_path'], '')
                    src = os.path.join(dir_cs, file)
                    dir_cs_out = os.path.join(dir_cs, 'qbit_manage_added', file)
                    category = self.config.get_category(dest)
                    # Only add cross-seed torrent if original torrent is complete
                    if self.torrentinfo[t_name]['is_complete']:
                        categories.append(category)
                        body = []
                        body += logger.print_line(f"{'Not Adding' if dry_run else 'Adding'} to qBittorrent:", loglevel)
                        body += logger.print_line(logger.insert_space(f'Torrent Name: {t_name}', 3), loglevel)
                        body += logger.print_line(logger.insert_space(f'Category: {category}', 7), loglevel)
                        body += logger.print_line(logger.insert_space(f'Save_Path: {dest}', 6), loglevel)
                        body += logger.print_line(logger.insert_space(f'Tracker: {t_tracker}', 8), loglevel)
                        attr = {
                            "function": "cross_seed",
                            "title": "Adding New Cross-Seed Torrent",
                            "body": "\n".join(body),
                            "torrent_name": t_name,
                            "torrent_category": category,
                            "torrent_save_path": dest,
                            "torrent_tag": "cross-seed",
                            "torrent_tracker": t_tracker
                        }
                        self.config.send_notifications(attr)
                        added += 1
                        if not dry_run:
                            self.client.torrents.add(torrent_files=src, save_path=dest, category=category, tags='cross-seed', is_paused=True)
                            util.move_files(src, dir_cs_out)
                    else:
                        logger.print_line(f'Found {t_name} in {dir_cs} but original torrent is not complete.', loglevel)
                        logger.print_line('Not adding to qBittorrent', loglevel)
                else:
                    error = f'{t_name} not found in torrents. Cross-seed Torrent not added to qBittorrent.'
                    if dry_run: logger.print_line(error, loglevel)
                    else: logger.print_line(error, 'WARNING')
                    self.config.notify(error, 'cross-seed', False)
            # Tag missing cross-seed torrents tags
            for torrent in self.torrent_list:
                t_name = torrent.name
                t_cat = torrent.category
                if 'cross-seed' not in torrent.tags and self.torrentinfo[t_name]['count'] > 1 and self.torrentinfo[t_name]['first_hash'] != torrent.hash:
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    tagged += 1
                    body = logger.print_line(f"{'Not Adding' if dry_run else 'Adding'} 'cross-seed' tag to {t_name}", loglevel)
                    attr = {
                        "function": "tag_cross_seed",
                        "title": "Tagging Cross-Seed Torrent",
                        "body": body,
                        "torrent_name": t_name,
                        "torrent_category": t_cat,
                        "torrent_tag": "cross-seed",
                        "torrent_tracker": tracker
                    }
                    self.config.send_notifications(attr)
                    if not dry_run: torrent.add_tags(tags='cross-seed')

            numcategory = Counter(categories)
            for c in numcategory:
                if numcategory[c] > 0: logger.print_line(f"{numcategory[c]} {c} cross-seed .torrents {'not added' if dry_run else 'added'}.", loglevel)
            if added > 0:              logger.print_line(f"Total {added} cross-seed .torrents {'not added' if dry_run else 'added'}.", loglevel)
            if tagged > 0:             logger.print_line(f"Total {tagged} cross-seed .torrents {'not tagged' if dry_run else 'tagged'}.", loglevel)
        return added, tagged

    # Function used to recheck paused torrents sorted by size and resume torrents that are completed
    def recheck(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        resumed = 0
        rechecked = 0
        if self.config.commands['recheck']:
            logger.separator("Rechecking Paused Torrents", space=False, border=False)
            # sort by size and paused
            torrent_list = self.get_torrents({'status_filter': 'paused', 'sort': 'size'})
            if torrent_list:
                for torrent in torrent_list:
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    # Resume torrent if completed
                    if torrent.progress == 1:
                        if torrent.max_ratio < 0 and torrent.max_seeding_time < 0:
                            resumed += 1
                            body = logger.print_line(f"{'Not Resuming' if dry_run else 'Resuming'} [{tracker['tag']}] - {torrent.name}", loglevel)
                            attr = {
                                "function": "recheck",
                                "title": "Resuming Torrent",
                                "body": body,
                                "torrent_name": torrent.name,
                                "torrent_category": torrent.category,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                            }
                            self.config.send_notifications(attr)
                            if not dry_run: torrent.resume()
                        else:
                            # Check to see if torrent meets AutoTorrentManagement criteria
                            logger.debug('DEBUG: Torrent to see if torrent meets AutoTorrentManagement Criteria')
                            logger.debug(logger.insert_space(f'- Torrent Name: {torrent.name}', 2))
                            logger.debug(logger.insert_space(f'-- Ratio vs Max Ratio: {torrent.ratio} < {torrent.max_ratio}', 4))
                            logger.debug(logger.insert_space(f'-- Seeding Time vs Max Seed Time: {timedelta(seconds=torrent.seeding_time)} < {timedelta(minutes=torrent.max_seeding_time)}', 4))
                            if (torrent.max_ratio >= 0 and torrent.ratio < torrent.max_ratio and torrent.max_seeding_time < 0) \
                                    or (torrent.max_seeding_time >= 0 and (torrent.seeding_time < (torrent.max_seeding_time * 60)) and torrent.max_ratio < 0) \
                                    or (torrent.max_ratio >= 0 and torrent.max_seeding_time >= 0 and torrent.ratio < torrent.max_ratio and (torrent.seeding_time < (torrent.max_seeding_time * 60))):
                                resumed += 1
                                body = logger.print_line(f"{'Not Resuming' if dry_run else 'Resuming'} [{tracker['tag']}] - {torrent.name}", loglevel)
                                attr = {
                                    "function": "recheck",
                                    "title": "Resuming Torrent",
                                    "body": body,
                                    "torrent_name": torrent.name,
                                    "torrent_category": torrent.category,
                                    "torrent_tracker": tracker["url"],
                                    "notifiarr_indexer": tracker["notifiarr"],
                                }
                                self.config.send_notifications(attr)
                                if not dry_run: torrent.resume()
                    # Recheck
                    elif torrent.progress == 0 and self.torrentinfo[torrent.name]['is_complete'] and not torrent.state_enum.is_checking:
                        rechecked += 1
                        body = logger.print_line(f"{'Not Rechecking' if dry_run else 'Rechecking'} [{tracker['tag']}] - {torrent.name}", loglevel)
                        attr = {
                            "function": "recheck",
                            "title": "Rechecking Torrent",
                            "body": body,
                            "torrent_name": torrent.name,
                            "torrent_category": torrent.category,
                            "torrent_tracker": tracker["url"],
                            "notifiarr_indexer": tracker["notifiarr"],
                        }
                        self.config.send_notifications(attr)
                        if not dry_run: torrent.recheck()
        return resumed, rechecked

    def rem_orphaned(self):
        dry_run = self.config.commands['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        orphaned = 0
        if self.config.commands['rem_orphaned']:
            logger.separator("Checking for Orphaned Files", space=False, border=False)
            torrent_files = []
            root_files = []
            orphaned_files = []
            excluded_orphan_files = []
            orphaned_parent_path = set()
            remote_path = self.config.remote_dir
            root_path = self.config.root_dir
            orphaned_path = self.config.orphaned_dir
            if (remote_path != root_path):
                root_files = [os.path.join(path.replace(remote_path, root_path), name)
                              for path, subdirs, files in alive_it(os.walk(remote_path))
                              for name in files if orphaned_path.replace(remote_path, root_path) not in path]
            else:
                root_files = [os.path.join(path, name) for path, subdirs, files in alive_it(os.walk(root_path))
                              for name in files if orphaned_path.replace(root_path, remote_path) not in path]

            # Get an updated list of torrents
            torrent_list = self.get_torrents({'sort': 'added_on'})
            for torrent in alive_it(torrent_list):
                for file in torrent.files:
                    fullpath = os.path.join(torrent.save_path, file.name)
                    # Replace fullpath with \\ if qbm is runnig in docker (linux) but qbt is on windows
                    fullpath = fullpath.replace(r'/', '\\') if ':\\' in fullpath else fullpath
                    torrent_files.append(fullpath)

            orphaned_files = set(root_files) - set(torrent_files)
            orphaned_files = sorted(orphaned_files)

            if self.config.orphaned['exclude_patterns']:
                exclude_patterns = self.config.orphaned['exclude_patterns']
                excluded_orphan_files = [file for file in orphaned_files for exclude_pattern in exclude_patterns if fnmatch(file, exclude_pattern.replace(remote_path, root_path))]

            orphaned_files = set(orphaned_files) - set(excluded_orphan_files)
            # if self.config.trace_mode:
            #     logger.separator("Torrent Files", space=False, border=False, loglevel='DEBUG')
            #     logger.print_line("\n".join(torrent_files), 'DEBUG')
            #     logger.separator("Root Files", space=False, border=False, loglevel='DEBUG')
            #     logger.print_line("\n".join(root_files), 'DEBUG')
            #     logger.separator("Excluded Orphan Files", space=False, border=False, loglevel='DEBUG')
            #     logger.print_line("\n".join(excluded_orphan_files), 'DEBUG')
            #     logger.separator("Orphaned Files", space=False, border=False, loglevel='DEBUG')
            #     logger.print_line("\n".join(orphaned_files), 'DEBUG')
            #     logger.separator("Deleting Orphaned Files", space=False, border=False, loglevel='DEBUG')

            if orphaned_files:
                os.makedirs(orphaned_path, exist_ok=True)
                body = []
                num_orphaned = len(orphaned_files)
                logger.print_line(f"{num_orphaned} Orphaned files found", loglevel)
                body += logger.print_line("\n".join(orphaned_files), loglevel)
                body += logger.print_line(f"{'Did not move' if dry_run else 'Moved'} {num_orphaned} Orphaned files to {orphaned_path.replace(remote_path,root_path)}", loglevel)

                attr = {
                    "function": "rem_orphaned",
                    "title": f"Removing {num_orphaned} Orphaned Files",
                    "body": "\n".join(body),
                    "orphaned_files": list(orphaned_files),
                    "orphaned_directory": orphaned_path.replace(remote_path, root_path),
                    "total_orphaned_files": num_orphaned,
                }
                self.config.send_notifications(attr)
                # Delete empty directories after moving orphan files
                logger.info('Cleaning up any empty directories...')
                if not dry_run:
                    for file in alive_it(orphaned_files):
                        src = file.replace(root_path, remote_path)
                        dest = os.path.join(orphaned_path, file.replace(root_path, ''))
                        util.move_files(src, dest, True)
                        orphaned_parent_path.add(os.path.dirname(file).replace(root_path, remote_path))
                        for parent_path in orphaned_parent_path:
                            util.remove_empty_directories(parent_path, "**/*")
            else:
                logger.print_line("No Orphaned Files found.", loglevel)
        return orphaned

    def tor_delete_recycle(self, torrent, info):
        if self.config.recyclebin['enabled']:
            tor_files = []
            try:
                info_hash = torrent.hash
                save_path = torrent.save_path.replace(self.config.root_dir, self.config.remote_dir)
                # Define torrent files/folders
                for file in torrent.files:
                    tor_files.append(os.path.join(save_path, file.name))
            except NotFound404Error:
                return

            if self.config.recyclebin['split_by_category']:
                recycle_path = os.path.join(save_path, os.path.basename(self.config.recycle_dir.rstrip(os.sep)))
            else:
                recycle_path = self.config.recycle_dir
            # Create recycle bin if not exists
            torrent_path = os.path.join(recycle_path, 'torrents')
            torrents_json_path = os.path.join(recycle_path, 'torrents_json')

            os.makedirs(recycle_path, exist_ok=True)
            if self.config.recyclebin['save_torrents']:
                if os.path.isdir(torrent_path) is False: os.makedirs(torrent_path)
                if os.path.isdir(torrents_json_path) is False: os.makedirs(torrents_json_path)
                torrent_json_file = os.path.join(torrents_json_path, f"{info['torrent_name']}.json")
                torrent_json = util.load_json(torrent_json_file)
                if not torrent_json:
                    logger.info(f"Saving Torrent JSON file to {torrent_json_file}")
                    torrent_json["torrent_name"] = info["torrent_name"]
                    torrent_json["category"] = info["torrent_category"]
                else:
                    logger.info(f"Adding {info['torrent_tracker']} to existing {os.path.basename(torrent_json_file)}")
                dot_torrent_files = []
                for File in os.listdir(self.config.torrents_dir):
                    if File.startswith(info_hash):
                        dot_torrent_files.append(File)
                        try:
                            util.copy_files(os.path.join(self.config.torrents_dir, File), os.path.join(torrent_path, File))
                        except Exception as e:
                            logger.stacktrace()
                            self.config.notify(e, 'Deleting Torrent', False)
                            logger.warning(f"RecycleBin Warning: {e}")
                if "tracker_torrent_files" in torrent_json:
                    tracker_torrent_files = torrent_json["tracker_torrent_files"]
                else:
                    tracker_torrent_files = {}
                tracker_torrent_files[info["torrent_tracker"]] = dot_torrent_files
                if dot_torrent_files:
                    backup_str = "Backing up "
                    for idx, val in enumerate(dot_torrent_files):
                        if idx == 0: backup_str += val
                        else: backup_str += f" and {val.replace(info_hash,'')}"
                    backup_str += f" to {torrent_path}"
                    logger.info(backup_str)
                torrent_json["tracker_torrent_files"] = tracker_torrent_files
                if "files" not in torrent_json:
                    files_cleaned = [f.replace(self.config.remote_dir, '') for f in tor_files]
                    torrent_json["files"] = files_cleaned
                if "deleted_contents" not in torrent_json:
                    torrent_json["deleted_contents"] = info['torrents_deleted_and_contents']
                else:
                    if torrent_json["deleted_contents"] is False and info['torrents_deleted_and_contents'] is True:
                        torrent_json["deleted_contents"] = info['torrents_deleted_and_contents']
                logger.debug("")
                logger.debug(f"JSON: {torrent_json}")
                util.save_json(torrent_json, torrent_json_file)
            if info['torrents_deleted_and_contents'] is True:
                logger.separator(f"Moving {len(tor_files)} files to RecycleBin", space=False, border=False, loglevel='DEBUG')
                if len(tor_files) == 1: logger.print_line(tor_files[0], 'DEBUG')
                else: logger.print_line("\n".join(tor_files), 'DEBUG')
                logger.debug(f'Moved {len(tor_files)} files to {recycle_path.replace(self.config.remote_dir,self.config.root_dir)}')

                # Move files from torrent contents to Recycle bin
                for file in tor_files:
                    src = file
                    dest = os.path.join(recycle_path, file.replace(self.config.remote_dir, ''))
                    # Move files and change date modified
                    try:
                        toDelete = util.move_files(src, dest, True)
                    except FileNotFoundError:
                        e = logger.print_line(f'RecycleBin Warning - FileNotFound: No such file or directory: {src} ', 'WARNING')
                        self.config.notify(e, 'Deleting Torrent', False)
                # Delete torrent and files
                torrent.delete(delete_files=toDelete)
                # Remove any empty directories
                util.remove_empty_directories(save_path, "**/*")
            else:
                torrent.delete(delete_files=False)
        else:
            if info['torrents_deleted_and_contents'] is True:
                torrent.delete(delete_files=True)
            else:
                torrent.delete(delete_files=False)
