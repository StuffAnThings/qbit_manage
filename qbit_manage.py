#!/usr/bin/python3

import sys
import yaml
import argparse
import logging
from logging.handlers import RotatingFileHandler
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

# Logging
log_lev = getattr(logging, args.loglevel.upper())
file_handler = logging.FileHandler(filename=args.logfile)
stdout_handler = logging.StreamHandler(sys.stderr)
rotate_handler = RotatingFileHandler(filename=args.logfile, maxBytes=1024 * 1024 * 2, backupCount=5)
handlers = [file_handler, stdout_handler, rotate_handler]

# noinspection PyArgumentList
logging.basicConfig(level=log_lev, format='%(asctime)s - %(levelname)s: %(message)s', handlers=handlers)
logger = logging.getLogger('qBit Manage')

# Add dry-run to logging.
logging.DRYRUN = 25
logging.addLevelName(logging.DRYRUN, 'DRY-RUN')
setattr(logger, 'dryrun', lambda message, *args: logger._log(logging.DRYRUN, message, args))

# Actual API call to connect to qbt.
client = Client(host=cfg["qbt"]["host"], username=cfg["qbt"]["user"], password=cfg["qbt"]["pass"])

urllib3.disable_warnings()


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


def update_category():
    if args.manage == 'manage' or args.cat_update == 'cat_update':
        num_cat = 0
        torrent_list = client.torrents.info()
        for torrent in torrent_list:
            if torrent.category == '':
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        new_cat = get_category(torrent.save_path)
                        if args.dry_run == 'dry_run':
                            logger.dryrun('\n - Torrent Name: %s \n - New Category: %s \n - Tracker: %s',
                                          torrent.name, new_cat, x.url)
                            num_cat += 1
                        else:
                            logger.info('\n - Torrent Name: %s \n - New Category: %s \n - Tracker: %s',
                                        torrent.name, new_cat, x.url)
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
                        new_tag = get_tags(x.url)
                        if args.dry_run == 'dry_run':
                            logger.dryrun('\n - Torrent Name: %s \n - New Tag: %s \n - Tracker: %s',
                                          torrent.name, new_tag, x.url)
                            num_tags += 1
                        else:
                            logger.info('\n - Torrent Name: %s \n - New Tag: %s \n - Tracker: %s',
                                        torrent.name, new_tag, x.url)
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
        rem_unr = 0
        torrent_list = client.torrents.info()
        for torrent in torrent_list:
            for status in torrent.trackers:
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        if 'Unregistered torrent' in status.msg:
                            if args.dry_run == 'dry_run':
                                logger.dryrun('\n - Torrent Name: %s \n - Status: %s \n - Tracker: %s \n '
                                              '- File NOT Deleted', torrent.name, status.msg, x.url)
                                rem_unr += 1
                            else:
                                logger.info('\n - Torrent Name: %s \n - Status: %s \n - Tracker: %s \n '
                                            '- Deleted', torrent.name, status.msg, x.url)
                                torrent.delete(hash=torrent.hash,
                                               delete_files=True)
                                rem_unr += 1
        if args.dry_run == 'dry_run':
            if rem_unr >= 1:
                logger.dryrun('Did not delete %s torrents.', rem_unr)
            else:
                logger.dryrun('No unregistered torrents found.')
        else:
            if rem_unr >= 1:
                logger.info('Deleted %s torrents.', rem_unr)
            else:
                logger.info('No unregistered torrents found.')


def main():
    update_category()
    update_tags()
    rem_unregistered()


if __name__ == "__main__":
    main()
