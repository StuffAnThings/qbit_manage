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
                    help='Use this if you would like to update your tags AND'
                         ' categories AND remove unregistered torrents.')
parser.add_argument('-s', '--cross-seed',
                    dest='cross_seed',
                    action='store_const',
                    const='cross_seed',
                    help='Use this after running cross-seed script to organize your torrents into specified '
                         'watch folders.')
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
                    help='Use this if you would like to update your tags.')
parser.add_argument('-r', '--rem-unregistered',
                    dest='rem_unregistered',
                    action='store_const',
                    const='rem_unregistered',
                    help='Use this if you would like to remove unregistered torrents.')
parser.add_argument('--dry-run',
                    dest='dry_run',
                    action='store_const',
                    const='dry_run',
                    help='If you would like to see what is gonna happen but not actually delete or '
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
    cat_path = cfg["cat"]
    for i, f in cat_path.items():
        if f in path:
            category = i
            return category
    else:
        category = ''
        logger.warning('No categories matched. Check your config.yml file. - Setting tag to NULL')
        return category


def get_tags(url):
    tag_path = cfg['tags']
    for i, f in tag_path.items():
        if i in url:
            tag = f
            return tag
    else:
        tag = ''
        logger.warning('No tags matched. Check your config.yml file. Setting tag to NULL')
    return tag


def get_name(t_list):
    dupes = []
    no_dupes = []
    t_name = [torrent.name for torrent in t_list]
    dupes = [s for s in t_name if t_name.count(s) > 1 if s not in dupes]
    no_dupes = [s for s in t_name if t_name.count(s) == 1 if s not in no_dupes]
    return dupes, no_dupes


# Will create a 2D Dictionary with the torrent name as the key
# torrentdict = {'TorrentName1' : {'Category':'TV', 'save_path':'/data/torrents/TV'},
#                'TorrentName2' : {'Category':'Movies', 'save_path':'/data/torrents/Movies'}}
def get_torrent_info(t_list):
    torrentdict = {}
    for torrent in t_list:
        save_path = torrent.save_path
        category = get_category(save_path)
        torrentattr = {'Category': category, 'save_path': save_path}
        torrentdict[torrent.name] = torrentattr
    return torrentdict

# Function used to recheck paused torrents sorted by size and resume torrents that are completed 
def recheck():
    if args.cross_seed == 'cross_seed' or args.manage == 'manage' or args.recheck == 'recheck':
        #sort by size and paused
        torrent_sorted_list = client.torrents.info(status_filter='paused',sort='size')
        for torrent in torrent_sorted_list:
            #Tag the torrents
            new_tag = [get_tags(x.url) for x in torrent.trackers if x.url.startswith('http')]
            torrent.add_tags(tags=new_tag)
            #print(f'{torrent.hash[-6:]}: {torrent.name} ({torrent.state}) {torrent.progress}')
            #Resume torrent if completed
            if torrent.progress == 1: 
                if args.dry_run == 'dry_run': 
                    logger.dryrun(f'\n - Not Resuming {new_tag} - {torrent.name}')
                else:
                    logger.info(f'\n - Resuming {new_tag} - {torrent.name}')
                    torrent.resume()
            #Recheck
            elif torrent.progress == 0:
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
        torrent_list = client.torrents.info()
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
                    logger.dryrun(f'Adding {t_name} to qBittorrent with: '
                                  f'\n - Category: {category}'
                                  f'\n - Save_Path: {dest}'
                                  f'\n - Paused: True')
                else:
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
                if args.dry_run == 'dry_run':
                    logger.dryrun(f'{t_name} not found in torrents.')
                else:
                    logger.warning(f'{t_name} not found in torrents.')
        recheck()
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
        torrent_list = client.torrents.info()
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
        torrent_list = client.torrents.info()
        for torrent in torrent_list:
            if torrent.tags == '':
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        t_url = trunc_val(x.url, '/')
                        new_tag = get_tags(x.url)
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
        torrent_list = client.torrents.info()
        dupes, no_dupes = get_name(torrent_list)
        rem_unr = 0
        del_tor = 0
        for torrent in torrent_list:
            for status in torrent.trackers:
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        t_url = trunc_val(x.url, '/')
                        n_info = (f'\n - Torrent Name: {torrent.name} '
                                  f'\n - Status: {status.msg} '
                                  f'\n - Tracker: {t_url} '
                                  f'\n - Deleted .torrent but not content files.')
                        n_d_info = (f'\n - Torrent Name: {torrent.name} '
                                    f'\n - Status: {status.msg} '
                                    f'\n - Tracker: {t_url} '
                                    f'\n - Deleted .torrent AND content files.')
                        if 'Unregistered torrent' in status.msg or 'Torrent is not found' in status.msg:
                            if torrent.name in dupes:
                                if args.dry_run == 'dry_run':
                                    logger.dryrun(n_info)
                                    rem_unr += 1
                                else:
                                    logger.info(n_info)
                                    torrent.delete(hash=torrent.hash, delete_files=False)
                                    rem_unr += 1
                            elif torrent.name in no_dupes:
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


def run():
    update_category()
    update_tags()
    rem_unregistered()
    cross_seed()
    recheck()

if __name__ == '__main__':
    run()