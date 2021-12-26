import logging, os
from qbittorrentapi import Client, LoginFailed, APIConnectionError
from modules import util
from modules.util import Failed, print_line, print_multiline, separator
from datetime import timedelta
from collections import Counter
from fnmatch import fnmatch
from alive_progress import alive_it, config_handler

logger = logging.getLogger("qBit Manage")

class Qbt:
    def __init__(self, config, params):
        self.config = config
        config_handler.set_global(bar=None, receipt_text=False)
        self.host = params["host"]
        self.username = params["username"]
        self.password = params["password"]
        logger.debug(f'Host: {self.host}, Username: {self.username}, Password: {self.password if self.password is None else "[REDACTED]"}')
        try:
            self.client = Client(host=self.host, username=self.username, password=self.password)
            self.client.auth_log_in()
            logger.info(f"Qbt Connection Successful")
        except LoginFailed:
            raise Failed("Qbittorrent Error: Failed to login. Invalid username/password.")
        except APIConnectionError:
            raise Failed("Qbittorrent Error: Unable to connect to the client.")
        except Exception:
            raise Failed("Qbittorrent Error: Unable to connect to the client.")
        separator(f"Getting Torrent List", space=False, border=False)
        self.torrent_list = self.get_torrents({'sort':'added_on'})

        # Will create a 2D Dictionary with the torrent name as the key
        # torrentdict = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'count':1, 'msg':'[]'...},
        #                'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}, 'count':2, 'msg':'[]'...}
        # List of dictionary key definitions
        # Category = Returns category of the torrent (str)
        # save_path = Returns the save path of the torrent (str)
        # count = Returns a count of the total number of torrents with the same name (int)
        # msg = Returns a list of torrent messages by name (list of str)
        # status = Returns the list of status numbers of the torrent by name (0: Tracker is disabled (used for DHT, PeX, and LSD), 1: Tracker has not been contacted yet, 2:Tracker has been contacted and is working, 3:Tracker is updating, 4:Tracker has been contacted, but it is not working (or doesn't send proper replies)
        # is_complete = Returns the state of torrent (Returns True if at least one of the torrent with the State is categorized as Complete.)
        # first_hash = Returns the hash number of the original torrent (Assuming the torrent list is sorted by date added (Asc))
        def get_torrent_info(torrent_list):
            torrentdict = {}
            t_obj_unreg = []
            t_obj_valid = []
            for torrent in alive_it(torrent_list):
                is_complete = False
                msg = None
                status = None
                try:
                    torrent_name = torrent.name
                    torrent_hash = torrent.hash
                    torrent_is_complete = torrent.state_enum.is_complete
                    save_path = torrent.save_path
                    category = torrent.category
                    torrent_trackers = torrent.trackers
                except Exception as e:
                    self.config.notify(e,'Get Torrent Info',False)
                    logger.warning(e)
                if torrent_name in torrentdict:
                    t_obj_list.append(torrent)
                    t_count = torrentdict[torrent_name]['count'] + 1
                    msg_list = torrentdict[torrent_name]['msg']
                    status_list = torrentdict[torrent_name]['status']
                    is_complete = True if torrentdict[torrent_name]['is_complete'] == True else torrent_is_complete
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
                        exception = ["DOWN","UNREACHABLE","BAD GATEWAY"]
                        #Add any potential unregistered torrents to a list
                        if x.status == 4 and all(x not in msg for x in exception):
                            t_obj_unreg.append(torrent)
                        if x.status == 2:
                            t_obj_valid.append(torrent)
                if msg is not None: msg_list.append(msg)
                if status is not None: status_list.append(status)
                torrentattr = {'torrents': t_obj_list, 'Category': category, 'save_path': save_path, 'count': t_count, 'msg': msg_list, 'status': status_list, 'is_complete': is_complete, 'first_hash':first_hash}
                torrentdict[torrent_name] = torrentattr
            return torrentdict,t_obj_unreg,t_obj_valid
        self.torrentinfo = None
        self.torrentissue = None
        self.torrentvalid = None
        if config.args['recheck'] or config.args['cross_seed'] or config.args['rem_unregistered']:
            #Get an updated torrent dictionary information of the torrents
            self.torrentinfo,self.torrentissue,self.torrentvalid = get_torrent_info(self.torrent_list)

    def get_torrents(self,params):
        return self.client.torrents.info(**params)

    def category(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_cat = 0
        if self.config.args['cat_update']:
            separator(f"Updating Categories", space=False, border=False)
            for torrent in self.torrent_list:
                if torrent.category == '':
                    new_cat = self.config.get_category(torrent.save_path)
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    if not dry_run: torrent.set_category(category=new_cat)
                    body = []
                    body += print_line(util.insert_space(f'Torrent Name: {torrent.name}',3),loglevel)
                    body += print_line(util.insert_space(f'New Category: {new_cat}',3),loglevel)
                    body += print_line(util.insert_space(f'Tracker: {tracker["url"]}',8),loglevel)
                    attr = {
                        "function":"cat_update",
                        "title":"Updating Categories",
                        "body": "\n".join(body),
                        "torrent_name":torrent.name,
                        "torrent_new_cat": new_cat,
                        "torrent_tracker": tracker["url"],
                        "notifiarr_indexer": tracker["notifiarr"]
                        }
                    self.config.send_notifications(attr)
                    num_cat += 1
            if num_cat >= 1:
                print_line(f"{'Did not update' if dry_run else 'Updated'} {num_cat} new categories.",loglevel)
            else:
                print_line(f'No new torrents to categorize.',loglevel)
        return num_cat

    def tags(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_tags = 0
        ignore_tags = ['noHL','issue','cross-seed']
        if self.config.args['tag_update']:
            separator(f"Updating Tags", space=False, border=False)
            for torrent in self.torrent_list:
                check_tags = util.get_list(torrent.tags)
                if torrent.tags == '' or (len([x for x in check_tags if x not in ignore_tags]) == 0):
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    if tracker["tag"]:
                        num_tags += 1
                        body = []
                        body += print_line(util.insert_space(f'Torrent Name: {torrent.name}',3),loglevel)
                        body += print_line(util.insert_space(f'New Tag: {tracker["tag"]}',8),loglevel)
                        body += print_line(util.insert_space(f'Tracker: {tracker["url"]}',8),loglevel)
                        body.extend(self.set_tags_and_limits(torrent, tracker["max_ratio"], tracker["max_seeding_time"],tracker["limit_upload_speed"],tracker["tag"]))
                        attr = {
                        "function":"tag_update",
                        "title":"Updating Tags",
                        "body": "\n".join(body),
                        "torrent_name":torrent.name,
                        "torrent_category":torrent.category,
                        "torrent_tag": tracker["tag"],
                        "torrent_tracker": tracker["url"],
                        "notifiarr_indexer": tracker["notifiarr"],
                        "torrent_max_ratio": tracker["max_ratio"],
                        "torrent_max_seeding_time": tracker["max_seeding_time"],
                        "torrent_limit_upload_speed": tracker["limit_upload_speed"]
                        }
                        self.config.send_notifications(attr)
            if num_tags >= 1:
                print_line(f"{'Did not update' if dry_run else 'Updated'} {num_tags} new tags.",loglevel)
            else:
                print_line(f'No new torrents to tag.',loglevel)
        return num_tags

    def set_tags_and_limits(self,torrent,max_ratio,max_seeding_time,limit_upload_speed=None,tags=None,restore=False):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        body = []
        #Print Logs
        if limit_upload_speed:
            if limit_upload_speed == -1:                    body += print_line(util.insert_space(f'Limit UL Speed: Infinity',1),loglevel)
            else:                                           body += print_line(util.insert_space(f'Limit UL Speed: {limit_upload_speed} kB/s',1),loglevel)
        if max_ratio or max_seeding_time:
            if (max_ratio == -2 or max_seeding_time == -2) and not restore:   body += print_line(util.insert_space(f'Share Limit: Use Global Share Limit',4),loglevel)
            elif (max_ratio == -1 or max_seeding_time == -1) and not restore: body += print_line(util.insert_space(f'Share Limit: Set No Share Limit',4),loglevel)
            else:
                if max_ratio != torrent.max_ratio and (not max_seeding_time or max_seeding_time < 0):
                    body += print_line(util.insert_space(f'Share Limit: Max Ratio = {max_ratio}',4),loglevel)
                elif max_seeding_time != torrent.max_seeding_time and (not max_ratio or max_ratio < 0):
                    body += print_line(util.insert_space(f'Share Limit: Max Seed Time = {max_seeding_time} min',4),loglevel)
                elif max_ratio != torrent.max_ratio and max_seeding_time != torrent.max_seeding_time: 
                    body += print_line(util.insert_space(f'Share Limit: Max Ratio = {max_ratio}, Max Seed Time = {max_seeding_time} min',4),loglevel)
        #Update Torrents
        if not dry_run:
            if tags: torrent.add_tags(tags)
            if limit_upload_speed: 
                if limit_upload_speed == -1: torrent.set_upload_limit(-1)
                else: torrent.set_upload_limit(limit_upload_speed*1024)
            if (max_ratio or max_seeding_time) and not restore:
                if max_ratio == -2 or max_seeding_time == -2:
                    torrent.set_share_limits(-2,-2)
                    return body
                elif max_ratio == -1 or max_seeding_time == -1:
                    torrent.set_share_limits(-1,-1)
                    return body
            if not max_ratio: max_ratio = torrent.max_ratio
            if not max_seeding_time: max_seeding_time = torrent.max_seeding_time
            torrent.set_share_limits(max_ratio,max_seeding_time)
        return body

    def tag_nohardlinks(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        num_tags = 0 #counter for the number of torrents that has no hard links
        del_tor = 0 #counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion
        del_tor_cont = 0 #counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion including contents
        num_untag = 0 #counter for number of torrents that previously had no hard links but now have hard links

        if self.config.args['tag_nohardlinks']:
            util.separator(f"Tagging Torrents with No Hardlinks", space=False, border=False)
            nohardlinks = self.config.nohardlinks
            tdel_dict = {} #dictionary to track the torrent names and content path that meet the deletion criteria
            root_dir = self.config.root_dir
            remote_dir = self.config.remote_dir
            for category in nohardlinks:
                torrent_list = self.get_torrents({'category':category,'filter':'completed'})
                if len(torrent_list) == 0:
                    e = f'No torrents found in the category ('+category+') defined under nohardlinks attribute in the config. Please check if this matches with any category in qbittorrent and has 1 or more torrents.'
                    self.config.notify(e,'Tag No Hard Links',False)
                    logger.error(e)
                    continue
                for torrent in alive_it(torrent_list):
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    if any(tag in torrent.tags for tag in nohardlinks[category]['exclude_tags']):
                        #Skip to the next torrent if we find any torrents that are in the exclude tag
                        continue
                    else:
                        #Checks for any hard links and not already tagged
                        if util.nohardlink(torrent['content_path'].replace(root_dir,remote_dir)):
                            #Will only tag new torrents that don't have noHL tag
                            if 'noHL' not in torrent.tags :
                                num_tags += 1
                                body = []
                                body += print_line(util.insert_space(f'Torrent Name: {torrent.name}',3),loglevel)
                                body += print_line(util.insert_space(f'Added Tag: noHL',6),loglevel)
                                body += print_line(util.insert_space(f'Tracker: {tracker["url"]}',8),loglevel)
                                body.extend(self.set_tags_and_limits(torrent, nohardlinks[category]["max_ratio"], nohardlinks[category]["max_seeding_time"],nohardlinks[category]["limit_upload_speed"],tags='noHL'))
                                attr = {
                                "function":"tag_nohardlinks",
                                "title":"Tagging Torrents with No Hardlinks",
                                "body": "\n".join(body),
                                "torrent_name":torrent.name,
                                "torrent_category":torrent.category,
                                "torrent_add_tag": 'noHL',
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                "torrent_max_ratio": nohardlinks[category]["max_ratio"],
                                "torrent_max_seeding_time": nohardlinks[category]["max_seeding_time"],
                                "torrent_limit_upload_speed": nohardlinks[category]["limit_upload_speed"]
                                }
                                self.config.send_notifications(attr)
                            #Cleans up previously tagged noHL torrents
                            else:
                                # Deletes torrent with data if cleanup is set to true and meets the ratio/seeding requirements
                                if (nohardlinks[category]['cleanup'] and torrent.state_enum.is_paused and len(nohardlinks[category])>0):
                                    tdel_dict[torrent.name] = torrent['content_path'].replace(root_dir,root_dir)
                    #Checks to see if previous noHL tagged torrents now have hard links.
                    if (not (util.nohardlink(torrent['content_path'].replace(root_dir,root_dir))) and ('noHL' in torrent.tags)):
                        num_untag += 1
                        body = []
                        body += print_line(f'Previous Tagged noHL Torrent Name: {torrent.name} has hard links found now.',loglevel)
                        body += print_line(util.insert_space(f'Removed Tag: noHL',6),loglevel)
                        body += print_line(util.insert_space(f'Tracker: {tracker["url"]}',8),loglevel)
                        body += print_line(f"{'Not Reverting' if dry_run else 'Reverting'} share limits.",loglevel)
                        if not dry_run: 
                            torrent.remove_tags(tags='noHL')
                            restore_max_ratio = tracker["max_ratio"]
                            restore_max_seeding_time = tracker["max_seeding_time"]
                            restore_limit_upload_speed = tracker["limit_upload_speed"]
                            if restore_max_ratio is None: restore_max_ratio = -2
                            if restore_max_seeding_time is None: restore_max_seeding_time = -2
                            if restore_limit_upload_speed is None: restore_limit_upload_speed = -1
                            body.extend(self.set_tags_and_limits(torrent, restore_max_ratio, restore_max_seeding_time,restore_limit_upload_speed,restore=True))  
                            if torrent.state == 'pausedUP': torrent.resume()
                        attr = {
                                "function":"untag_nohardlinks",
                                "title":"Untagging Previous Torrents that now have Hard Links",
                                "body": "\n".join(body),
                                "torrent_name":torrent.name,
                                "torrent_category":torrent.category,
                                "torrent_remove_tag": 'noHL',
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                "torrent_max_ratio": restore_max_ratio,
                                "torrent_max_seeding_time": restore_max_seeding_time,
                                "torrent_limit_upload_speed": restore_limit_upload_speed
                                }
                        self.config.send_notifications(attr)
                #loop through torrent list again for cleanup purposes
                if (nohardlinks[category]['cleanup']):
                    for torrent in torrent_list:
                        if torrent.name in tdel_dict.keys() and 'noHL' in torrent.tags:
                            #Double check that the content path is the same before we delete anything
                            if torrent['content_path'].replace(root_dir,root_dir) == tdel_dict[torrent.name]:
                                tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                                body = []
                                body += print_line(util.insert_space(f'Torrent Name: {torrent.name}',3),loglevel)
                                body += print_line(util.insert_space(f'Tracker: {tracker["url"]}',8),loglevel)
                                body += print_line(util.insert_space(f"Cleanup: True [No hard links found and meets Share Limits.]",8),loglevel)
                                attr = {
                                "function":"cleanup_tag_nohardlinks",
                                "title":"Removing NoHL Torrents and meets Share Limits",
                                "torrent_name":torrent.name,
                                "torrent_category":torrent.category,
                                "cleanup": 'True',
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                }
                                if (os.path.exists(torrent['content_path'].replace(root_dir,root_dir))):
                                    if not dry_run: self.tor_delete_recycle(torrent)
                                    del_tor_cont += 1
                                    attr["torrents_deleted_and_contents"] = True
                                    body += print_line(util.insert_space(f'Deleted .torrent AND content files.',8),loglevel)
                                else:
                                    if not dry_run: torrent.delete(hash=torrent.hash, delete_files=False)
                                    del_tor += 1
                                    attr["torrents_deleted_and_contents"] = False
                                    body += print_line(util.insert_space(f'Deleted .torrent but NOT content files.',8),loglevel)
                                attr["body"] = "\n".join(body)
                                self.config.send_notifications(attr)
            if num_tags >= 1: 
                print_line(f"{'Did not Tag/set' if dry_run else 'Tag/set'} share limits for {num_tags} .torrent{'s.' if num_tags > 1 else '.'}",loglevel)
            else:
                print_line(f'No torrents to tag with no hard links.',loglevel)
            if num_untag >=1: print_line(f"{'Did not delete' if dry_run else 'Deleted'} noHL tags / share limits for {num_untag} .torrent{'s.' if num_tags > 1 else '.'}",loglevel)
            if del_tor >=1: print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor} .torrent{'s' if num_tags > 1 else ''} but not content files.",loglevel) 
            if del_tor_cont >=1: print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor} .torrent{'s' if num_tags > 1 else ''} AND content files.",loglevel) 
        return num_tags,num_untag,del_tor,del_tor_cont

    def rem_unregistered(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        del_tor = 0
        del_tor_cont = 0
        pot_unreg = 0
        pot_unr_summary = ''
        if self.config.args['rem_unregistered']:
            separator(f"Removing Unregistered Torrents", space=False, border=False)
            unreg_msgs = [
            'UNREGISTERED',
            'TORRENT NOT FOUND',
            'TORRENT IS NOT FOUND',
            'NOT REGISTERED',
            'HTTPS://BEYOND-HD.ME/TORRENTS',
            'NOT EXIST',
            'UNKNOWN TORRENT',
            'REDOWNLOAD',
            'PACKS',
            'REPACKED',
            'PACK',
            'TRUMP',
            'RETITLED',
            'PRE-RETAIL',
            'FULL SEASON',
            'MASS REMOVAL'
            ]
            for torrent in self.torrentvalid:
                check_tags = util.get_list(torrent.tags)
                #Remove any potential unregistered torrents Tags that are no longer unreachable.
                if 'issue' in check_tags:
                    if not dry_run: torrent.remove_tags(tags='issue')
            for torrent in self.torrentissue:
                t_name = torrent.name
                t_cat = self.torrentinfo[t_name]['Category']
                t_count = self.torrentinfo[t_name]['count']
                t_msg = self.torrentinfo[t_name]['msg']
                t_status = self.torrentinfo[t_name]['status']
                check_tags = util.get_list(torrent.tags)
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        tracker = self.config.get_tags([x.url])
                        msg_up = x.msg.upper()
                        #Tag any potential unregistered torrents
                        if not any(m in msg_up for m in unreg_msgs) and x.status == 4 and 'issue' not in check_tags:
                            pot_unr = ''
                            pot_unr += (util.insert_space(f'Torrent Name: {t_name}',3)+'\n')
                            pot_unr += (util.insert_space(f'Status: {msg_up}',9)+'\n')
                            pot_unr += (util.insert_space(f'Tracker: {tracker["url"]}',8)+'\n')
                            pot_unr += (util.insert_space(f"Added Tag: 'issue'",6)+'\n')
                            pot_unr_summary += pot_unr
                            pot_unreg += 1
                            attr = {
                                "function":"potential_rem_unregistered",
                                "title":"Potential Unregistered Torrents",
                                "body": pot_unr,
                                "torrent_name":t_name,
                                "torrent_category":t_cat,
                                "torrent_add_tag": "issue",
                                "torrent_status": msg_up,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                }
                            self.config.send_notifications(attr)
                            if not dry_run: torrent.add_tags(tags='issue')
                        if any(m in msg_up for m in unreg_msgs) and x.status == 4:
                            body = []
                            body += print_line(util.insert_space(f'Torrent Name: {t_name}',3),loglevel)
                            body += print_line(util.insert_space(f'Status: {msg_up}',9),loglevel)
                            body += print_line(util.insert_space(f'Tracker: {tracker["url"]}',8),loglevel)
                            attr = {
                                "function":"rem_unregistered",
                                "title":"Removing Unregistered Torrents",
                                "torrent_name":t_name,
                                "torrent_category":t_cat,
                                "torrent_status": msg_up,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                }
                            if t_count > 1:
                                # Checks if any of the original torrents are working
                                if '' in t_msg or 2 in t_status:
                                    if not dry_run: torrent.delete(hash=torrent.hash, delete_files=False)
                                    attr["torrents_deleted_and_contents"] = False
                                    body += print_line(util.insert_space(f'Deleted .torrent but NOT content files.',8),loglevel)
                                    del_tor += 1
                                else:
                                    if not dry_run: self.tor_delete_recycle(torrent)
                                    attr["torrents_deleted_and_contents"] = True
                                    body += print_line(util.insert_space(f'Deleted .torrent AND content files.',8),loglevel)
                                    del_tor_cont += 1
                            else:
                                if not dry_run: self.tor_delete_recycle(torrent)
                                attr["torrents_deleted_and_contents"] = True
                                body += print_line(util.insert_space(f'Deleted .torrent AND content files.',8),loglevel)
                                del_tor_cont += 1
                            attr["body"] = "\n".join(body)
                            self.config.send_notifications(attr)
            if del_tor >=1 or del_tor_cont >=1:
                if del_tor >= 1: print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor} .torrent{'s' if del_tor > 1 else ''} but not content files.",loglevel)
                if del_tor_cont >= 1: print_line(f"{'Did not delete' if dry_run else 'Deleted'} {del_tor_cont} .torrent{'s' if del_tor_cont > 1 else ''} AND content files.",loglevel)
            else:
                print_line('No unregistered torrents found.',loglevel)

            if (pot_unreg > 0):
                separator(f"{pot_unreg} Potential Unregistered torrents found", space=False, border=False,loglevel=loglevel)
                print_multiline(pot_unr_summary.rstrip(),loglevel)
        return del_tor,del_tor_cont, pot_unreg

    # Function used to move any torrents from the cross seed directory to the correct save directory
    def cross_seed(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        added = 0 # Keep track of total torrents tagged
        tagged = 0 #Track # of torrents tagged that are not cross-seeded
        if self.config.args['cross_seed']:
            separator(f"Checking for Cross-Seed Torrents", space=False, border=False)
            # List of categories for all torrents moved
            categories = []

            # Only get torrent files
            cs_files = [f for f in os.listdir(self.config.cross_seed_dir) if f.endswith('torrent')]
            dir_cs = self.config.cross_seed_dir
            dir_cs_out = os.path.join(dir_cs,'qbit_manage_added')
            os.makedirs(dir_cs_out,exist_ok=True)
            for file in cs_files:
                t_name = file.split(']', 2)[2].split('.torrent')[0]
                # Substring Key match in dictionary (used because t_name might not match exactly with torrentdict key)
                # Returned the dictionary of filtered item
                torrentdict_file = dict(filter(lambda item: t_name in item[0], self.torrentinfo.items()))
                if torrentdict_file:
                    # Get the exact torrent match name from torrentdict
                    t_name = next(iter(torrentdict_file))
                    dest = os.path.join(self.torrentinfo[t_name]['save_path'], '')
                    src = os.path.join(dir_cs,file)
                    dir_cs_out = os.path.join(dir_cs,'qbit_manage_added',file)
                    category = self.config.get_category(dest)
                    #Only add cross-seed torrent if original torrent is complete
                    if self.torrentinfo[t_name]['is_complete']:
                        categories.append(category)
                        body = []
                        body += print_line(f"{'Not Adding' if dry_run else 'Adding'} to qBittorrent:",loglevel)
                        body += print_line(util.insert_space(f'Torrent Name: {t_name}',3),loglevel)
                        body += print_line(util.insert_space(f'Category: {category}',7),loglevel)
                        body += print_line(util.insert_space(f'Save_Path: {dest}',6),loglevel)
                        attr = {
                                "function":"cross_seed",
                                "title":"Adding New Cross-Seed Torrent",
                                "body": "\n".join(body),
                                "torrent_name":t_name,
                                "torrent_category": category,
                                "torrent_save_path": dest,
                                "torrent_add_tag": "cross-seed"
                                }
                        self.config.send_notifications(attr)
                        added += 1
                        if not dry_run:
                            self.client.torrents.add(torrent_files=src, save_path=dest, category=category, tags='cross-seed', is_paused=True)
                            util.move_files(src,dir_cs_out)
                    else:
                        print_line(f'Found {t_name} in {dir_cs} but original torrent is not complete.',loglevel)
                        print_line(f'Not adding to qBittorrent',loglevel)
                else:
                    error = f'{t_name} not found in torrents. Cross-seed Torrent not added to qBittorrent.'
                    if dry_run: print_line(error,loglevel)
                    else: print_line(error,'WARNING')
                    self.config.notify(error,'cross-seed',False)
            #Tag missing cross-seed torrents tags
            for torrent in self.torrent_list:
                t_name = torrent.name
                t_cat = torrent.category
                if 'cross-seed' not in torrent.tags and self.torrentinfo[t_name]['count'] > 1 and self.torrentinfo[t_name]['first_hash'] != torrent.hash:
                    tagged += 1
                    body = print_line(f"{'Not Adding' if dry_run else 'Adding'} 'cross-seed' tag to {t_name}",loglevel)
                    attr = {
                        "function":"tag_cross_seed",
                        "title":"Tagging Cross-Seed Torrent",
                        "body":body,
                        "torrent_name":t_name,
                        "torrent_category": t_cat,
                        "torrent_add_tag": "cross-seed"
                        }
                    self.config.send_notifications(attr)
                    if not dry_run: torrent.add_tags(tags='cross-seed')
                        
            numcategory = Counter(categories)
            for c in numcategory:
                if numcategory[c] > 0: print_line(f"{numcategory[c]} {c} cross-seed .torrents {'not added' if dry_run else 'added'}.",loglevel)
            if added > 0:              print_line(f"Total {added} cross-seed .torrents {'not added' if dry_run else 'added'}.",loglevel)
            if tagged > 0:             print_line(f"Total {tagged} cross-seed .torrents {'not tagged' if dry_run else 'tagged'}.",loglevel)
        return added,tagged

    # Function used to recheck paused torrents sorted by size and resume torrents that are completed 
    def recheck(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        resumed = 0
        rechecked = 0
        if self.config.args['recheck']:
            separator(f"Rechecking Paused Torrents", space=False, border=False)
            #sort by size and paused
            torrent_list = self.get_torrents({'status_filter':'paused','sort':'size'})
            if torrent_list:
                for torrent in torrent_list:
                    tracker = self.config.get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                    #Resume torrent if completed
                    if torrent.progress == 1:
                        if torrent.max_ratio < 0 and torrent.max_seeding_time < 0:
                            resumed += 1
                            body = print_line(f"{'Not Resuming' if dry_run else 'Resuming'} [{tracker['tag']}] - {torrent.name}",loglevel)
                            attr = {
                                "function":"recheck",
                                "title":"Resuming Torrent",
                                "body": body,
                                "torrent_name":torrent.name,
                                "torrent_category":torrent.category,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                }
                            self.config.send_notifications(attr)
                            if not dry_run: torrent.resume()
                        else:
                            #Check to see if torrent meets AutoTorrentManagement criteria
                            logger.debug(f'DEBUG: Torrent to see if torrent meets AutoTorrentManagement Criteria')
                            logger.debug(util.insert_space(f'- Torrent Name: {torrent.name}',2))
                            logger.debug(util.insert_space(f'-- Ratio vs Max Ratio: {torrent.ratio} < {torrent.max_ratio}',4))
                            logger.debug(util.insert_space(f'-- Seeding Time vs Max Seed Time: {timedelta(seconds=torrent.seeding_time)} < {timedelta(minutes=torrent.max_seeding_time)}',4))
                            if (torrent.max_ratio >= 0 and torrent.ratio < torrent.max_ratio and torrent.max_seeding_time < 0) \
                            or (torrent.max_seeding_time >= 0 and (torrent.seeding_time < (torrent.max_seeding_time * 60)) and torrent.max_ratio < 0) \
                            or (torrent.max_ratio >= 0 and torrent.max_seeding_time >= 0 and torrent.ratio < torrent.max_ratio and (torrent.seeding_time < (torrent.max_seeding_time * 60))):
                                resumed += 1
                                body = print_line(f"{'Not Resuming' if dry_run else 'Resuming'} [{tracker['tag']}] - {torrent.name}",loglevel)
                                attr = {
                                "function":"recheck",
                                "title":"Resuming Torrent",
                                "body": body,
                                "torrent_name":torrent.name,
                                "torrent_category":torrent.category,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                }
                                self.config.send_notifications(attr)
                                if not dry_run: torrent.resume()
                    #Recheck
                    elif torrent.progress == 0 and self.torrentinfo[torrent.name]['is_complete'] and not torrent.state_enum.is_checking:
                        rechecked += 1
                        body = print_line(f"{'Not Rechecking' if dry_run else 'Rechecking'} [{tracker['tag']}] - {torrent.name}",loglevel)
                        attr = {
                                "function":"recheck",
                                "title":"Rechecking Torrent",
                                "body": body,
                                "torrent_name":torrent.name,
                                "torrent_category":torrent.category,
                                "torrent_tracker": tracker["url"],
                                "notifiarr_indexer": tracker["notifiarr"],
                                }
                        self.config.send_notifications(attr)
                        if not dry_run: torrent.recheck()
        return resumed,rechecked

    def rem_orphaned(self):
        dry_run = self.config.args['dry_run']
        loglevel = 'DRYRUN' if dry_run else 'INFO'
        orphaned = 0
        if self.config.args['rem_orphaned']:
            separator(f"Checking for Orphaned Files", space=False, border=False)
            torrent_files = []
            root_files = []
            orphaned_files = []
            excluded_orphan_files = []
            orphaned_parent_path = set()
            remote_path = self.config.remote_dir
            root_path = self.config.root_dir
            if (remote_path != root_path):
                root_files = [os.path.join(path.replace(remote_path,root_path), name) for path, subdirs, files in alive_it(os.walk(remote_path)) for name in files if os.path.join(remote_path,'orphaned_data') not in path and os.path.join(remote_path,'.RecycleBin') not in path]
            else:
                root_files = [os.path.join(path, name) for path, subdirs, files in alive_it(os.walk(root_path)) for name in files if os.path.join(root_path,'orphaned_data') not in path and os.path.join(root_path,'.RecycleBin') not in path]

            #Get an updated list of torrents
            torrent_list = self.get_torrents({'sort':'added_on'})
            for torrent in alive_it(torrent_list):
                for file in torrent.files:
                    torrent_files.append(os.path.join(torrent.save_path,file.name))

            orphaned_files = set(root_files) - set(torrent_files)
            orphaned_files = sorted(orphaned_files)

            if self.config.orphaned['exclude_patterns']:
                exclude_patterns = self.config.orphaned['exclude_patterns']
                excluded_orphan_files = [file for file in orphaned_files for exclude_pattern in exclude_patterns if fnmatch(file, exclude_pattern.replace(remote_path,root_path))]

            orphaned_files = set(orphaned_files) - set(excluded_orphan_files)
            if self.config.trace_mode:
                separator(f"Torrent Files", space=False, border=False, loglevel='DEBUG')
                print_multiline("\n".join(torrent_files),'DEBUG')
                separator(f"Root Files", space=False, border=False,loglevel='DEBUG')
                print_multiline("\n".join(root_files),'DEBUG')
                separator(f"Excluded Orphan Files", space=False, border=False,loglevel='DEBUG')
                print_multiline("\n".join(excluded_orphan_files),'DEBUG')
                separator(f"Orphaned Files", space=False, border=False,loglevel='DEBUG')
                print_multiline("\n".join(orphaned_files),'DEBUG')
                separator(f"Deleting Orphaned Files", space=False, border=False,loglevel='DEBUG')

            if orphaned_files:
                dir_out = os.path.join(remote_path,'orphaned_data')
                os.makedirs(dir_out,exist_ok=True)
                body = []
                num_orphaned = len(orphaned_files)
                print_line(f"{num_orphaned} Orphaned files found",loglevel)
                body += print_multiline("\n".join(orphaned_files),loglevel)
                body += print_line(f"{'Did not move' if dry_run else 'Moved'} {num_orphaned} Orphaned files to {dir_out.replace(remote_path,root_path)}",loglevel)
                
                attr = {
                "function":"rem_orphaned",
                "title":f"Removing {num_orphaned} Orphaned Files",
                "body": "\n".join(body),
                "orphaned_files": list(orphaned_files),
                "orphaned_directory": dir_out.replace(remote_path,root_path),
                "total_orphaned_files": num_orphaned,
                }
                self.config.send_notifications(attr)
                #Delete empty directories after moving orphan files
                logger.info(f'Cleaning up any empty directories...')
                if not dry_run:
                    for file in alive_it(orphaned_files):
                        src = file.replace(root_path,remote_path)
                        dest = os.path.join(dir_out,file.replace(root_path,''))
                        util.move_files(src,dest)
                        orphaned_parent_path.add(os.path.dirname(file).replace(root_path,remote_path))
                        for parent_path in orphaned_parent_path:
                            util.remove_empty_directories(parent_path,"**/*")
            else:
                print_line(f"No Orphaned Files found.",loglevel)
        return orphaned


    def tor_delete_recycle(self,torrent):
        if self.config.recyclebin['enabled']:
            tor_files = []
            #Define torrent files/folders
            for file in torrent.files:
                tor_files.append(os.path.join(torrent.save_path,file.name))

            #Create recycle bin if not exists
            recycle_path = os.path.join(self.config.remote_dir,'.RecycleBin')
            os.makedirs(recycle_path,exist_ok=True)

            separator(f"Moving {len(tor_files)} files to RecycleBin", space=False, border=False,loglevel='DEBUG')
            if len(tor_files) == 1: print_line(tor_files[0],'DEBUG')
            else: print_multiline("\n".join(tor_files),'DEBUG')
            logger.debug(f'Moved {len(tor_files)} files to {recycle_path.replace(self.config.remote_dir,self.config.root_dir)}')

            #Move files from torrent contents to Recycle bin
            for file in tor_files:
                src = file.replace(self.config.root_dir,self.config.remote_dir)
                dest = os.path.join(recycle_path,file.replace(self.config.root_dir,''))
                #move files and change date modified
                try:
                    util.move_files(src,dest,True)
                except FileNotFoundError:
                    print_line(f'RecycleBin Warning - FileNotFound: No such file or directory: {src} ','WARNING')
            #Delete torrent and files
            torrent.delete(hash=torrent.hash, delete_files=False)
            #Remove any empty directories
            util.remove_empty_directories(torrent.save_path.replace(self.config.root_dir,self.config.remote_dir),"**/*")
        else:
            torrent.delete(hash=torrent.hash, delete_files=True)
