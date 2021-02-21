#!/usr/bin/python3

from qbittorrentapi import Client
import yaml
import argparse
import logging
import sys
# import apprise

parser = argparse.ArgumentParser("qBittorrent Manager.",
                                 description='A mix of scripts combined for managing qBittorrent.')
parser.add_argument('-c', '--config-file',
                    dest='config',
                    action='store',
                    default='config.yml',
                    help='This is used if you want to use different names for your config.yml. Example: tv.yml')
parser.add_argument('-l', '--log-file',
                    dest='logfile',
                    action='store',
                    default='activity.log',
                    help='This is used if you want to use different names for your config.yml. Example: tv.yml')
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
stdout_handler = logging.StreamHandler(sys.stdout)
handlers = [file_handler, stdout_handler]

# noinspection PyArgumentList
logging.basicConfig(level=log_lev,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=handlers)
logger = logging.getLogger('qBit Manage')


# Actual API call to connect to qbt.
client = Client(host=cfg["qbt"]["host"],
                username=cfg["qbt"]["user"],
                password=cfg["qbt"]["pass"])
torrent_list = client.torrents.info()


def get_category(path):
    cat_path = cfg["cat"]
    for p, c in cat_path.items():
        if p in path:
            category = c
            return category
    else:
        category = ''
        return category


def get_tags(url):
    tag_path = cfg["tags"]
    for t, n in tag_path.items():
        if t in url:
            tag = n
            return tag
    else:
        tag = ''
        return tag


def update_category():
    if args.manage == 'manage' or args.cat_update == 'cat_update':
        num_cat = 0
        for torrent in torrent_list:
            if torrent.category == '':
                new_cat = get_category(torrent.save_path)
                if args.dry_run == 'dry_run':
                    logger.info('DRY-RUN:   Torrent Name: %s', torrent.name)
                    logger.info('DRY-RUN:     - New Category: %s', new_cat)
                    num_cat += 1
                else:
                    logger.info('Torrent Name: %s', torrent.name)
                    logger.info('  - New Category: %s', new_cat)
                    torrent.set_category(category=new_cat)
                    num_cat += 1
        if args.dry_run == 'dry_run':
            if num_cat >= 1:
                logger.info('DRY-RUN:   Did not update %s new categories.', num_cat)
            else:
                logger.info('DRY-RUN:   No new torrents to categorize.')
        else:
            if num_cat >= 1:
                logger.info('Updated %s new categories.', num_cat)
            else:
                logger.info('No new torrents to categorize.')


def update_tags():
    if args.manage == 'manage' or args.tag_update == 'tag_update':
        num_tags = 0
        for torrent in torrent_list:
            if torrent.tags == '':
                for x in torrent.trackers:
                    if x.url.startswith('http'):
                        new_tag = get_tags(x.url)
                        if args.dry_run == 'dry_run':
                            logger.info('DRY-RUN:   Torrent Name: %s', torrent.name)
                            logger.info('DRY-RUN:     - New Tag: %s', new_tag)
                            num_tags += 1
                        else:
                            logger.info('Torrent Name: %s', torrent.name)
                            logger.info('  - New Tag: %s', new_tag)
                            torrent.add_tags(tags=new_tag)
                            num_tags += 1
        if args.dry_run == 'dry_run':
            if num_tags >= 1:
                logger.info('DRY-RUN:   Did not update %s new tags.', num_tags)
            else:
                logger.info('DRY-RUN:   No new torrents to tag.')
        else:
            if num_tags >= 1:
                logger.info('Updated %s new tags.', num_tags)
            else:
                logger.info('No new torrents to tag.')


def rem_unregistered():
    if args.manage == 'manage' or args.rem_unregistered == 'rem_unregistered':
        rem_unr = 0
        for torrent in torrent_list:
            for status in torrent.trackers:
                if 'Unregistered torrent' in status.msg:
                    if args.dry_run == 'dry_run':
                        logger.info('DRY-RUN:    %s -> %s', torrent.name, status.msg)
                        logger.info('DRY-RUN:      - NOT Deleted')
                        rem_unr += 1
                    else:
                        logger.info('%s -> %s', torrent.name, status.msg)
                        logger.info('  - Deleted')
                        torrent.delete(hash=torrent.hash,
                                       delete_files=True)
                        rem_unr += 1
        if args.dry_run == 'dry_run':
            if rem_unr >= 1:
                logger.info('DRY-RUN:   Did not delete %s torrents.', rem_unr)
            else:
                logger.info('DRY-RUN:   No unregistered torrents found.')
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
