#!/usr/bin/python3

import os
import shutil
import yaml
import argparse
import logging
import logging.handlers
from qbittorrentapi import Client
import urllib3
from collections import Counter
import glob
from pathlib import Path

# import apprise

parser = argparse.ArgumentParser('qBittorrent Manager.',
                                 description='A mix of scripts combined for managing qBittorrent.')
parser.add_argument('-c', '--config-file',
                    dest='config',
                    action='store',
                    default='config.yml',
                    help='This is used if you want to use a different name for your config.yml. Example: tv.yml')
parser.add_argument('-l', '--log-file',
                    dest='logfile',
                    action='store',
                    default='activity.log',
                    help='This is used if you want to use a different name for your log file. Example: tv.log')
parser.add_argument('-m', '--manage',
                    dest='manage',
                    action='store_const',
                    const='manage',
                    help='Use this if you would like to update your tags, categories,'
                         ' remove unregistered torrents, AND recheck/resume paused torrents.')
parser.add_argument('-s', '--cross-seed',
                    dest='cross_seed',
                    action='store_const',
                    const='cross_seed',
                    help='Use this after running cross-seed script to add torrents from the cross-seed output folder to qBittorrent')
parser.add_argument('-re', '--recheck',
                    dest='recheck',
                    action='store_const',
                    const='recheck',
                    help='Recheck paused torrents sorted by lowest size. Resume if Completed.')
parser.add_argument('-g', '--cat-update',
                    dest='cat_update',
                    action='store_const',
                    const='cat_update',
                    help='Use this if you would like to update your categories.')
parser.add_argument('-t', '--tag-update',
                    dest='tag_update',
                    action='store_const',
                    const='tag_update',
                    help='Use this if you would like to update your tags. (Only adds tags to untagged torrents)')
parser.add_argument('-r', '--rem-unregistered',
                    dest='rem_unregistered',
                    action='store_const',
                    const='rem_unregistered',
                    help='Use this if you would like to remove unregistered torrents.')
parser.add_argument('-ro', '--rem-orphaned',
                    dest='rem_orphaned',
                    action='store_const',
                    const='rem_orphaned',
                    help='Use this if you would like to remove orphaned files from your `root_dir` directory that are not referenced by any torrents.'
                    ' It will scan your `root_dir` directory and compare it with what is in Qbitorrent. Any data not referenced in Qbitorrent will be moved into '
                    ' `/data/torrents/orphaned_data` folder for you to review/delete.')
parser.add_argument('-tnhl', '--tag-nohardlinks',
                    dest='tag_nohardlinks',
                    action='store_const',
                    const='tag_nohardlinks',
                    help='Use this to tag any torrents that do not have any hard links associated with any of the files. This is useful for those that use Sonarr/Radarr'
                    'that hard link your media files with the torrents for seeding. When files get upgraded they no longer become linked with your media therefore will be tagged with a new tag noHL'
                    'You can then safely delete/remove these torrents to free up any extra space that is not being used by your media folder.')                    
parser.add_argument('--dry-run',
                    dest='dry_run',
                    action='store_const',
                    const='dry_run',
                    help='If you would like to see what is gonna happen but not actually move/delete or '
                         'tag/categorize anything.')
parser.add_argument('--log',
                    dest='loglevel',
                    action='store',
                    default='INFO',
                    help='Change your log level. ')
args = parser.parse_args()

with open(args.config, 'r') as cfg_file:
    cfg = yaml.load(cfg_file, Loader=yaml.FullLoader)

urllib3.disable_warnings()

file_name_format = args.logfile
msg_format = '%(asctime)s - %(levelname)s: %(message)s'
max_bytes = 1024 * 1024 * 2
backup_count = 5

logger = logging.getLogger('qBit Manage')
logging.DRYRUN = 25
logging.addLevelName(logging.DRYRUN, 'DRY-RUN')
setattr(logger, 'dryrun', lambda dryrun, *args: logger._log(logging.DRYRUN, dryrun, args))
log_lev = getattr(logging, args.loglevel.upper())
logger.setLevel(log_lev)

file_handler = logging.handlers.RotatingFileHandler(filename=file_name_format,
                                                    maxBytes=max_bytes,
                                                    backupCount=backup_count)
file_handler.setLevel(log_lev)
file_formatter = logging.Formatter(msg_format)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(log_lev)
stream_formatter = logging.Formatter(msg_format)
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

# Actual API call to connect to qbt.
host = cfg['qbt']['host']
if 'user' in cfg['qbt']:
    username = cfg['qbt']['user']
else:
    username = ''
if 'pass' in cfg['qbt']:
    password = cfg['qbt']['pass']
else:
    password = ''

client = Client(host=host,
                username=username,
                password=password)


def trunc_val(s, d, n=3):
    return d.join(s.split(d, n)[:n])


def get_category(path):
    if 'cat' in cfg and cfg["cat"] != None:
        cat_path = cfg["cat"]
        for i, f in cat_path.items():
            if f in path:
                category = i
                return category
    else:
        category = ''
        return category
    category = ''
    logger.warning('No categories matched. Check your config.yml file. - Setting category to NULL')
    return category


def get_tags(urls):
    if 'tags' in cfg and cfg["tags"] != None:
        tag_path = cfg['tags']
        for i, f in tag_path.items():
            for url in urls:
                if i in url:
                    tag = f
                    if tag: return tag,trunc_val(url, '/')
    else:
        tag = ('','')
        return tag
    tag = ('','')
    logger.warning('No tags matched. Check your config.yml file. Setting tag to NULL')
    return tag

def remove_empty_directories(pathlib_root_dir):
  # list all directories recursively and sort them by path,
  # longest first
  L = sorted(
      pathlib_root_dir.glob("*/*"),
      key=lambda p: len(str(p)),
      reverse=True,
  )
  for pdir in L:
    try:
        pdir.rmdir()  # remove directory if empty
    except OSError:
      continue  # catch and continue if non-empty       

# Will create a 2D Dictionary with the torrent name as the key
# torrentdict = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV', 'count':1, 'msg':'[]'},
#                'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}, 'count':2, 'msg':'[]'}
def get_torrent_info(t_list):
    torrentdict = {}
    for torrent in t_list:
        save_path = torrent.save_path
        category = get_category(save_path)
        is_complete = False
        if torrent.name in torrentdict:
            t_count = torrentdict[torrent.name]['count'] + 1
            msg_list = torrentdict[torrent.name]['msg']
            status_list = torrentdict[torrent.name]['status']
            is_complete = True if torrentdict[torrent.name]['is_complete'] == True else torrent.state_enum.is_complete
        else:
            t_count = 1
            msg_list = []
            status_list = []
            is_complete = torrent.state_enum.is_complete
        msg,status = [(x.msg,x.status) for x in torrent.trackers if x.url.startswith('http')][0]
        msg_list.append(msg)
        status_list.append(status)
        torrentattr = {'Category': category, 'save_path': save_path, 'count': t_count, 'msg': msg_list, 'status': status_list, 'is_complete': is_complete}
        torrentdict[torrent.name] = torrentattr
    return torrentdict

# Function used to recheck paused torrents sorted by size and resume torrents that are completed 
def recheck():
    if args.cross_seed == 'cross_seed' or args.manage == 'manage' or args.recheck == 'recheck':
        #sort by size and paused
        torrent_sorted_list = client.torrents.info(status_filter='paused',sort='size')
        torrentdict = get_torrent_info(client.torrents.info(sort='added_on',reverse=True))
        for torrent in torrent_sorted_list:
            new_tag,t_url = get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
            if torrent.tags == '' or ('cross-seed' in torrent.tags and len([e for e in torrent.tags.split(",") if not 'noHL' in e]) == 1): torrent.add_tags(tags=new_tag)
            #Resume torrent if completed
            if torrent.progress == 1: 
                if args.dry_run == 'dry_run': 
                    logger.dryrun(f'\n - Not Resuming {new_tag} - {torrent.name}')
                else:
                    logger.info(f'\n - Resuming {new_tag} - {torrent.name}')
                    torrent.resume()
            #Recheck
            elif torrent.progress == 0 and torrentdict[torrent.name]['is_complete']:
                if args.dry_run == 'dry_run':
                    logger.dryrun(f'\n - Not Rechecking {new_tag} - {torrent.name}')
                else:
                    logger.info(f'\n - Rechecking {new_tag} - {torrent.name}')
                    torrent.recheck()

# Function used to move any torrents from the cross seed directory to the correct save directory
def cross_seed():
    if args.cross_seed == 'cross_seed':
        # List of categories for all torrents moved
        categories = []
        # Keep track of total torrents moved
        total = 0
        # Used to output the final list torrents moved to output in the log
        torrents_added = ''
        # Only get torrent files
        cs_files = [f for f in os.listdir(os.path.join(cfg['directory']['cross_seed'], '')) if f.endswith('torrent')]
        dir_cs = os.path.join(cfg['directory']['cross_seed'], '')
        dir_cs_out = os.path.join(dir_cs,'qbit_manage_added')
        os.makedirs(dir_cs_out,exist_ok=True)
        torrent_list = client.torrents.info(sort='added_on',reverse=True)
        torrentdict = get_torrent_info(torrent_list)
        for file in cs_files:
            t_name = file.split(']', 2)[2].split('.torrent')[0]
            # Substring Key match in dictionary (used because t_name might not match exactly with torrentdict key)
            # Returned the dictionary of filtered item
            torrentdict_file = dict(filter(lambda item: t_name in item[0], torrentdict.items()))
            if torrentdict_file:
                # Get the exact torrent match name from torrentdict
                t_name = next(iter(torrentdict_file))
                category = torrentdict[t_name]['Category']
                dest = os.path.join(torrentdict[t_name]['save_path'], '')
                src = os.path.join(dir_cs,file)
                dir_cs_out = os.path.join(dir_cs,'qbit_manage_added',file)
                categories.append(category)
                if args.dry_run == 'dry_run':
                    logger.dryrun(f'Not Adding {t_name} to qBittorrent with: '
                                  f'\n - Category: {category}'
                                  f'\n - Save_Path: {dest}'
                                  f'\n - Paused: True')
                else:
                    if torrentdict[t_name]['is_complete']:
                        client.torrents.add(torrent_files=src,
                                            save_path=dest,
                                            category=category,
                                            is_paused=True)
                        shutil.move(src, dir_cs_out)
                        logger.info(f'Adding {t_name} to qBittorrent with: '
                                    f'\n - Category: {category}'
                                    f'\n - Save_Path: {dest}'
                                    f'\n - Paused: True')
                    else:
                        logger.info(f'Found {t_name} in {dir_cs} but original torrent is not complete. Not adding to qBittorrent')
            else:
                if args.dry_run == 'dry_run':
                    logger.dryrun(f'{t_name} not found in torrents.')
                else:
                    logger.warning(f'{t_name} not found in torrents.')
        numcategory = Counter(categories)
        if args.dry_run == 'dry_run':
            for c in numcategory:
                total += numcategory[c]
                torrents_added += f'\n - {c} .torrents not added: {numcategory[c]}'
            torrents_added += f'\n -- Total .torrents not added: {total}'
            logger.dryrun(torrents_added)
        else:
            for c in numcategory:
                total += numcategory[c]
                torrents_added += f'\n - {c} .torrents added: {numcategory[c]}'
            torrents_added += f'\n -- Total .torrents added: {total}'
            logger.info(torrents_added)


def update_category():
    if args.manage == 'manage' or args.cat_update == 'cat_update':
        num_cat = 0
        torrent_list = client.torrents.info(sort='added_on',reverse=True)
        for torrent in torrent_list:
            if torrent.category == '':
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        t_url = trunc_val(x.url, '/')
                        new_cat = get_category(torrent.save_path)
                        if args.dry_run == 'dry_run':
                            logger.dryrun(f'\n - Torrent Name: {torrent.name}'
                                          f'\n - New Category: {new_cat}'
                                          f'\n - Tracker: {t_url}')
                            num_cat += 1
                        else:
                            logger.info(f'\n - Torrent Name: {torrent.name}'
                                        f'\n - New Category: {new_cat}'
                                        f'\n - Tracker: {t_url}')
                            torrent.set_category(category=new_cat)
                            num_cat += 1
        if args.dry_run == 'dry_run':
            if num_cat >= 1:
                logger.dryrun(f'Did not update {num_cat} new categories.')
            else:
                logger.dryrun(f'No new torrents to categorize.')
        else:
            if num_cat >= 1:
                logger.info(f'Updated {num_cat} new categories.')
            else:
                logger.info(f'No new torrents to categorize.')


def update_tags():
    if args.manage == 'manage' or args.tag_update == 'tag_update':
        num_tags = 0
        torrent_list = client.torrents.info(sort='added_on',reverse=True)
        for torrent in torrent_list:
            if torrent.tags == '' or ('cross-seed' in torrent.tags and len([e for e in torrent.tags.split(",") if not 'noHL' in e]) == 1):
                new_tag,t_url = get_tags([x.url for x in torrent.trackers if x.url.startswith('http')])
                if args.dry_run == 'dry_run':
                    logger.dryrun(f'\n - Torrent Name: {torrent.name}'
                                    f'\n - New Tag: {new_tag}'
                                    f'\n - Tracker: {t_url}')
                    num_tags += 1
                else:
                    logger.info(f'\n - Torrent Name: {torrent.name}'
                                f'\n - New Tag: {new_tag}'
                                f'\n - Tracker: {t_url}')
                    torrent.add_tags(tags=new_tag)
                    num_tags += 1
        if args.dry_run == 'dry_run':
            if num_tags >= 1:
                logger.dryrun(f'Did not update {num_tags} new tags.')
            else:
                logger.dryrun('No new torrents to tag.')
        else:
            if num_tags >= 1:
                logger.info(f'Updated {num_tags} new tags.')
            else:
                logger.info('No new torrents to tag. ')


def rem_unregistered():
    if args.manage == 'manage' or args.rem_unregistered == 'rem_unregistered':
        torrent_list = client.torrents.info(sort='added_on',reverse=True)
        torrentdict = get_torrent_info(torrent_list)
        rem_unr = 0
        del_tor = 0
        pot_unr = ''
        for torrent in torrent_list:
            t_name = torrent.name
            t_count = torrentdict[t_name]['count']
            t_msg = torrentdict[t_name]['msg']
            t_status = torrentdict[t_name]['status']
            for x in torrent.trackers:
                if x.url.startswith('http'):
                    t_url = trunc_val(x.url, '/')
                    n_info = (f'\n - Torrent Name: {t_name} '
                              f'\n - Status: {x.msg} '
                              f'\n - Tracker: {t_url} '
                              f'\n - Deleted .torrent but not content files.')
                    n_d_info = (f'\n - Torrent Name: {t_name} '
                                f'\n - Status: {x.msg} '
                                f'\n - Tracker: {t_url} '
                                f'\n - Deleted .torrent AND content files.')
                    if (x.status == 4):
                        pot_unr += (f'\n - {torrent.name}')
                    if ('Unregistered torrent' in x.msg or \
                        'unregistered torrent' in x.msg or \
                        'Torrent is not found' in x.msg or \
                        'Torrent not registered' in x.msg or \
                        'Torrent not found' in x.msg or \
                        'https://beyond-hd.me/torrents' in x.msg or \
                        'does not exist' in x.msg or \
                        'not registered' in x.msg or \
                        'Unknown torrent' in x.msg or \
                        'Packs are available' in x.msg \
                        ) and x.status == 4:
                        logger.debug(f'Torrent counts: {t_count}')
                        logger.debug(f'msg: {t_msg}')
                        logger.debug(f'status: {t_status}')
                        if t_count > 1:
                            if args.dry_run == 'dry_run':
                                if '' in t_msg: 
                                    logger.dryrun(n_info)
                                    rem_unr += 1
                                else:
                                    logger.dryrun(n_d_info)
                                    del_tor += 1
                            else:
                                # Checks if any of the original torrents are working
                                if '' in t_msg or 2 in t_status: 
                                    logger.info(n_info)
                                    torrent.delete(hash=torrent.hash, delete_files=False)
                                    rem_unr += 1
                                else:
                                    logger.info(n_d_info)
                                    torrent.delete(hash=torrent.hash, delete_files=True)
                                    del_tor += 1                                  
                        else:
                            if args.dry_run == 'dry_run':
                                logger.dryrun(n_d_info)
                                del_tor += 1
                            else:
                                logger.info(n_d_info)
                                torrent.delete(hash=torrent.hash, delete_files=True)
                                del_tor += 1
        if args.dry_run == 'dry_run':
            if rem_unr >= 1 or del_tor >= 1:
                logger.dryrun(f'Did not delete {rem_unr} .torrents(s) or content files.')
                logger.dryrun(f'Did not delete {del_tor} .torrents(s) or content files.')
            else:
                logger.dryrun('No unregistered torrents found.')
        else:
            if rem_unr >= 1 or del_tor >= 1:
                logger.info(f'Deleted {rem_unr} .torrents(s) but not content files.')
                logger.info(f'Deleted {del_tor} .torrents(s) AND content files.')
            else:
                logger.info('No unregistered torrents found.')
        if (len(pot_unr) > 0):
            logger.debug(f'Potential Unregistered torrents: {pot_unr}')

def rem_orphaned():
    if args.rem_orphaned == 'rem_orphaned':
        torrent_list = client.torrents.info()
        torrent_files = []
        root_files = []
        orphaned_files = []

        if 'root_dir' in cfg['directory']:
            root_path = os.path.join(cfg['directory']['root_dir'], '')
        else:
            logger.error('root_dir not defined in config.')
            return

        if ('remote_dir' in cfg['directory'] and cfg['directory']['remote_dir'] != ''):
            remote_path = os.path.join(cfg['directory']['remote_dir'], '')
            root_files = [os.path.join(path.replace(remote_path,root_path), name) for path, subdirs, files in os.walk(remote_path) for name in files if os.path.join(remote_path,'orphaned_data') not in path]
        else:
            remote_path = root_path
            root_files = [os.path.join(path, name) for path, subdirs, files in os.walk(root_path) for name in files if os.path.join(root_path,'orphaned_data') not in path]

        for torrent in torrent_list:
            for file in torrent.files:
                torrent_files.append(os.path.join(torrent.save_path,file.name))
            
        orphaned_files = set(root_files) - set(torrent_files)
        orphaned_files = sorted(orphaned_files)
        logger.debug('----------torrent files-----------')
        logger.debug("\n".join(torrent_files))
        logger.debug('----------root_files-----------')
        logger.debug("\n".join(root_files))
        logger.debug('----------orphaned_files-----------')
        logger.debug("\n".join(orphaned_files))
        logger.debug('----------Deleting orphan files-----------')
        if (orphaned_files):
            if args.dry_run == 'dry_run':
                dir_out = os.path.join(remote_path,'orphaned_data')
                logger.dryrun(f'\n----------{len(orphaned_files)} Orphan files found-----------'
                                f'\n - '+'\n - '.join(orphaned_files)+
                                f'\n - Did not move {len(orphaned_files)} Orphaned files to {dir_out.replace(remote_path,root_path)}')
            else:
                dir_out = os.path.join(remote_path,'orphaned_data')
                os.makedirs(dir_out,exist_ok=True)

                for file in orphaned_files:
                    src = file.replace(root_path,remote_path)
                    dest = os.path.join(dir_out,file.replace(root_path,''))
                    src_path = trunc_val(src, '/',len(remote_path.split('/')))
                    dest_path = os.path.dirname(dest)
                    if os.path.isdir(dest_path) == False:
                        os.makedirs(dest_path)
                    shutil.move(src, dest)
                logger.info(f'\n----------{len(orphaned_files)} Orphan files found-----------'
                                f'\n - '+'\n - '.join(orphaned_files)+
                                f'\n - Moved {len(orphaned_files)} Orphaned files to {dir_out.replace(remote_path,root_path)}')
                #Delete empty directories after moving orphan files
                remove_empty_directories(Path(remote_path))
        else:
            if args.dry_run == 'dry_run':
                logger.dryrun('No Orphaned Files found.')
            else:
                logger.info('No Orphaned Files found.')

def tag_nohardlinks():
    if args.tag_nohardlinks == 'tag_nohardlinks':
        nohardlinks = cfg['nohardlinks']

        if 'root_dir' in cfg['directory']:
            root_path = os.path.join(cfg['directory']['root_dir'], '')
        else:
            logger.error('root_dir not defined in config.')
            return
        if ('remote_dir' in cfg['directory'] and cfg['directory']['remote_dir'] != ''):
            remote_path = os.path.join(cfg['directory']['remote_dir'], '')
        else:
            remote_path = root_path

        for category in nohardlinks:
            t_count = 0 #counter for the number of torrents that has no hard links
            t_del = 0 #counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion
            t_del_cs = 0 #counter for the number of torrents that has no hard links and meets the criteria for ratio limit/seed limit for deletion including cross-seeds
            tdel_tags = 0 #counter for number of torrents that previously had no hard links but now have hard links
            n_info = ''
            tdel_dict = {} #dictionary to track the torrent names and content path that meet the deletion criteria
            t_excl_tags = []#list of tags to exclude based on config.yml
            torrent_list = client.torrents.info(category=category,filter='completed')
            
            #Convert string to list if only one tag defined.
            if ('exclude_tags' in nohardlinks[category]):
                if isinstance(nohardlinks[category]['exclude_tags'],str):
                    t_excl_tags.append(nohardlinks[category]['exclude_tags'])
                else:
                    t_excl_tags = nohardlinks[category]['exclude_tags']

            if len(torrent_list) == 0:
                logger.error('No torrents found in the category ('+category+') defined in config.yml inside the nohardlinks section. Please check if this matches with any category in qbittorrent and has 1 or more torrents.')
                continue
            for torrent in torrent_list:
                if args.dry_run != 'dry_run':
                    torrent.resume()    
                if('exclude_tags' in nohardlinks[category] and (any(tag in torrent.tags for tag in t_excl_tags))):
                    #Skip to the next torrent if we find any torrents that are in the exclude tag
                    continue
                else:
                    #Checks for any hard links and not already tagged
                    if (nohardlink(torrent['content_path'].replace(root_path,remote_path))):
                        #Will only tag new torrents that don't have noHL tag
                        if('noHL' not in torrent.tags):
                            t_count += 1
                            n_info += (f'\n - Torrent Name: {torrent.name} has no hard links found.')
                            n_info += (' Adding tags noHL.')
                            if(nohardlinks[category] != None):
                                #set the max seeding time for the torrent
                                if ('max_seeding_time' in nohardlinks[category]):
                                    seeding_time_limit = nohardlinks[category]['max_seeding_time']
                                    n_info += (' \n    Setting max seed time to ' + str(seeding_time_limit) + '.')
                                else:
                                    seeding_time_limit = -2
                                #set the max ratio for the torrent
                                if ('max_ratio' in nohardlinks[category]):
                                    ratio_limit = nohardlinks[category]['max_ratio']
                                    n_info += (' \n    Setting max ratio to ' + str(ratio_limit)+ '.')
                                else:
                                    ratio_limit = -2
                            else:
                                seeding_time_limit = -2
                                ratio_limit = -2
                            if args.dry_run != 'dry_run':
                                #set the tag for no hard links
                                torrent.add_tags(tags='noHL')
                                client.torrents_set_share_limits(ratio_limit,seeding_time_limit,torrent.hash)

                        #Cleans up previously tagged noHL torrents
                        else:
                            if(nohardlinks[category] != None):
                                # Deletes torrent with data if cleanup is set to true and meets the ratio/seeding requirements
                                if ('cleanup' in nohardlinks[category] and nohardlinks[category]['cleanup'] and torrent.state_enum.is_paused and len(nohardlinks[category])>0):
                                    t_del += 1
                                    n_info += (f'\n - Torrent Name: {torrent.name} has no hard links found and meets ratio/seeding requirements.')
                                    tdel_dict[torrent.name] = torrent['content_path'].replace(root_path,remote_path)
                                    if args.dry_run == 'dry_run':
                                        n_info += (' \n    Cleanup flag set to true. NOT Deleting torrent + contents.')
                                    else:
                                        n_info += (' \n    Cleanup flag set to true. Deleting torrent + contents.')
                
                #Checks to see if previous noHL tagged torrents now have hard links.
                if (not (nohardlink(torrent['content_path'].replace(root_path,remote_path))) and ('noHL' in torrent.tags)):
                    n_info += (f'\n - Previous Tagged noHL Torrent Name: {torrent.name} has hard links found now.')
                    n_info += (' Removing tags noHL.')
                    n_info += (' Removing ratio and seeding time limits.')
                    tdel_tags += 1
                    if args.dry_run != 'dry_run':
                        #Remove tags and share limits
                        torrent.remove_tags(tags='noHL')
                        client.torrents_set_share_limits(-2,-2,torrent.hash)
                        
            if(nohardlinks[category] != None):
                #loop through torrent list again for cleanup purposes
                if ('cleanup' in nohardlinks[category] and nohardlinks[category]['cleanup']):
                    for torrent in torrent_list:
                        if torrent.name in tdel_dict.keys() and 'noHL' in torrent.tags:
                            #Double check that the content path is the same before we delete anything
                            if torrent['content_path'].replace(root_path,remote_path) == tdel_dict[torrent.name]:
                                t_del_cs += 1
                                if args.dry_run != 'dry_run':
                                    if (os.path.exists(torrent['content_path'].replace(root_path,remote_path))):
                                        torrent.delete(hash=torrent.hash, delete_files=True)
                                    else:
                                        torrent.delete(hash=torrent.hash, delete_files=False)

        if args.dry_run == 'dry_run':
            if t_count >= 1 or len(n_info) > 1:
                logger.dryrun(n_info)
                logger.dryrun(f'Did not tag/set ratio limit/seeding time for  {t_count} .torrents(s)')
                if t_del >= 1:
                    logger.dryrun(f'Did not delete {t_del} .torrents(s) or content files.')
                    logger.dryrun(f'Did not delete {t_del_cs} .torrents(s) (including cross-seed) or content files.')
                if tdel_tags >= 1:
                    logger.dryrun(f'Did not delete noHL tags/ remove ratio limit/seeding time for  {tdel_tags} .torrents(s)')
            else:
                logger.dryrun('No torrents to tag with no hard links.')
        else:
            if t_count >= 1 or len(n_info) > 1:
                logger.info(n_info)
                logger.info(f'tag/set ratio limit/seeding time for  {t_count} .torrents(s)')
                if t_del >= 1:
                    logger.info(f'Deleted {t_del} .torrents(s) AND content files.')
                    logger.info(f'Deleted {t_del_cs} .torrents(s) (includes cross-seed torrents) AND content files.')
                if tdel_tags >= 1:
                    logger.info(f'Deleted noHL tags/ remove ratio limit/seeding time for  {tdel_tags} .torrents(s)')
            else:
                logger.info('No torrents to tag with no hard links.')


#will check if there are any hard links if it passes a file or folder
def nohardlink(file):
    check = True
    if (os.path.isfile(file)):
        if (os.stat(file).st_nlink > 1):
            check = False
    else:
        for path, subdirs, files in os.walk(file):
            for x in files:
                if (os.stat(os.path.join(path,x)).st_nlink > 1):
                    check = False
    return check

def run():
    update_category()
    update_tags()
    rem_unregistered()
    cross_seed()
    recheck()
    rem_orphaned()
    tag_nohardlinks()

if __name__ == '__main__':
    run()
