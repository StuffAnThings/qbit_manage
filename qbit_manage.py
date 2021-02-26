#!/usr/bin/python3

import os
import shutil
import yaml
import argparse
import logging
import logging.handlers
from qbittorrentapi import Client
import urllib3

# import apprise

parser = argparse.ArgumentParser("qBittorrent Manager.",
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

with open(args.config, "r") as cfg_file:
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
host = cfg["qbt"]["host"]
if 'user' in cfg["qbt"]:
    username = cfg["qbt"]["user"]
else:
    username = ''
if 'pass' in cfg["qbt"]:
    password = cfg["qbt"]["pass"]
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
        if i in path:
            category = f
            return category
    else:
        category = ''
        logger.warning('No categories matched. Check your config.yml file. - Setting tag to NULL')
        return category


def get_tags(url):
    tag_path = cfg["tags"]
    for i, f in tag_path.items():
        if i in url:
            tag = f
            return tag
    else:
        tag = ''
        logger.warning('No tags matched. Check your config.yml file. Setting category to NULL')
    return tag


def get_name(t_list):
    dupes = []
    no_dupes = []
    t_name = []
    for torrent in t_list:
        n = torrent.name
        t_name.append(n)
    for s in t_name:
        if t_name.count(s) > 1:
            if s not in dupes:
                dupes.append(s)
        if t_name.count(s) == 1:
            if s not in no_dupes:
                no_dupes.append(s)
    return dupes, no_dupes


# def check_cs_cat():


def cross_seed():
    if args.cross_seed == 'cross_seed':
        num_cs_tv = 0
        num_cs_movie = 0
        num_cs_unknown = 0
        cs_files = os.listdir(cfg["directory"]["cross_seed"])
        dir_cs = cfg["directory"]["cross_seed"]
        dir_tv = cfg["directory"]["tv"]
        dir_movie = cfg["directory"]["movies"]
        dir_unknown = cfg["directory"]["unknown"]
        for file in cs_files:
            if '[episode]' in file or '[pack]' in file:
                src = dir_cs + file
                dest = dir_tv + file
                shutil.move(src, dest)
                logger.info('Moving %s to %s', src, dest)
                num_cs_tv += 1
            elif '[movie]' in file:
                src = dir_cs + file
                dest = dir_movie + file
                shutil.move(src, dest)
                logger.info('Moving %s to %s', src, dest)
                num_cs_movie += 1
            elif '[unknown]' in file:
                src = dir_cs + file
                dest = dir_unknown + file
                shutil.move(src, dest)
                logger.info('Moving %s to %s', src, dest)
                num_cs_unknown += 1
        total = num_cs_tv + num_cs_movie + num_cs_unknown
        logger.info('\n - TV .torrents moved: %s \n - Movie .torrents moved: %s \n - Unknown .torrents moved: %s '
                    '\n -- Total .torrents moved: %s', num_cs_tv, num_cs_movie, num_cs_unknown, total)


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
                            logger.dryrun('\n - Torrent Name: %s \n - New Category: %s \n - Tracker: %s',
                                          torrent.name, new_cat, t_url)
                            num_cat += 1
                        else:
                            logger.info('\n - Torrent Name: %s \n - New Category: %s \n - Tracker: %s',
                                        torrent.name, new_cat, t_url)
                            torrent.set_category(category=new_cat)
                            num_cat += 1
        if args.dry_run == 'dry_run':
            if num_cat >= 1:
                logger.dryrun('Did not update %s new categories.', num_cat)
            else:
                logger.dryrun('No new torrents to categorize.')
        else:
            if num_cat >= 1:
                logger.info('Updated %s new categories.', num_cat)
            else:
                logger.info('No new torrents to categorize.')


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
                            logger.dryrun('\n - Torrent Name: %s \n - New Tag: %s \n - Tracker: %s',
                                          torrent.name, new_tag, t_url)
                            num_tags += 1
                        else:
                            logger.info('\n - Torrent Name: %s \n - New Tag: %s \n - Tracker: %s',
                                        torrent.name, new_tag, t_url)
                            torrent.add_tags(tags=new_tag)
                            num_tags += 1
        if args.dry_run == 'dry_run':
            if num_tags >= 1:
                logger.dryrun('Did not update %s new tags.', num_tags)
            else:
                logger.dryrun('No new torrents to tag.')
        else:
            if num_tags >= 1:
                logger.info('Updated %s new tags.', num_tags)
            else:
                logger.info('No new torrents to tag.')


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
                        if 'Unregistered torrent' in status.msg or 'Torrent is not found' in status.msg:
                            if torrent.name in dupes:
                                if args.dry_run == 'dry_run':
                                    logger.dryrun('\n - Torrent Name: %s \n - Status: %s \n - Tracker: %s \n '
                                                  '- Deleted .torrent but not content files.',
                                                  torrent.name, status.msg, t_url)
                                    rem_unr += 1
                                else:
                                    logger.info('\n - Torrent Name: %s \n - Status: %s \n - Tracker: %s \n '
                                                '- Deleted .torrent but not content files.',
                                                torrent.name, status.msg, t_url)
                                    torrent.delete(hash=torrent.hash, delete_files=False)
                                    rem_unr += 1
                            elif torrent.name in no_dupes:
                                if args.dry_run == 'dry_run':
                                    logger.dryrun('\n - Torrent Name: %s \n - Status: %s \n - Tracker: %s \n '
                                                  '- Deleted .torrent AND content files.',
                                                  torrent.name, status.msg, t_url)
                                    del_tor += 1
                                else:
                                    logger.info('\n - Torrent Name: %s \n - Status: %s \n - Tracker: %s \n '
                                                '- Deleted .torrent AND content files.',
                                                torrent.name, status.msg, t_url)
                                    torrent.delete(hash=torrent.hash, delete_files=True)
                                    del_tor += 1
        if args.dry_run == 'dry_run':
            if rem_unr >= 1 or del_tor >= 1:
                logger.dryrun('Did not delete %s .torrents(s) but not content files.', rem_unr)
                logger.dryrun('Did not delete %s .torrents(s) AND content files.', del_tor)
            else:
                logger.dryrun('No unregistered torrents found.')
        else:
            if rem_unr >= 1 or del_tor >= 1:
                logger.dryrun('Deleted %s .torrents(s) but not content files.', rem_unr)
                logger.dryrun('Deleted %s .torrents(s) AND content files.', del_tor)
            else:
                logger.info('No unregistered torrents found.')


def run():
    cross_seed()
    update_category()
    update_tags()
    rem_unregistered()


if __name__ == "__main__":
    run()
