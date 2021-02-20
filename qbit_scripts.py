#!/usr/bin/python3

from qbittorrentapi import Client
import yaml
import argparse

parser = argparse.ArgumentParser("qBittorrent scripts.",
                                 description='A mix of scripts combined for managing qBittorrent.')
parser.add_argument('-c', '--config-file',
                    dest='config',
                    action='store',
                    default='config.yml',
                    help='This is used if you want to use different names for your config.yml. Example: tv.yml')
parser.add_argument('--cat-update',
                    dest='command',
                    action='store_const',
                    const='cat-update',
                    help='Use this if you would like to update your categories.')
parser.add_argument('--tag-update',
                    dest='command',
                    action='store_const',
                    const='tag-update',
                    help='Use this if you would like to update your tags.')
args = parser.parse_args()

with open(args.config, "r") as cfg_file:
    cfg = yaml.load(cfg_file, Loader=yaml.FullLoader)

# Actual API call to connect to qbt.
client = Client(host=cfg["qbt"]["host"], username=cfg["qbt"]["user"], password=cfg["qbt"]["pass"])
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


# Main command that does the work.
def update_category():
    num_cat = 0
    for torrent in torrent_list:
        if torrent.category == '':
            new_cat = get_category(torrent.save_path)
            print('Torrent Name: ' + torrent.name)
            print('  - New Category: ' + new_cat)
            torrent.set_category(category=new_cat)
            num_cat += 1
    if num_cat >= 1:
        print('Updated ', num_cat, ' new categories')
    else:
        print('No new torrents to categorize.')


def get_tags(url):
    tag_path = cfg["tags"]
    for t, n in tag_path.items():
        if t in url:
            tag = n
            return tag
    else:
        tag = ''
        return tag


def update_tags():
    num_tags = 0
    for torrent in torrent_list:
        if torrent.tags == '':
            for x in torrent.trackers:
                if x.url.startswith('http'):
                    new_tag = get_tags(x.url)
                    print('Torrent Name: ' + torrent.name)
                    print('  - New Tag: ' + new_tag)
                    torrent.add_tags(tags=new_tag)
                    num_tags += 1
    if num_tags >= 1:
        print('Updated ', num_tags, ' new tags')
    else:
        print('No new torrents to tag.')


def main():
    if args.command == 'cat-update':
        update_category()
    elif args.command == 'tag-update':
        update_tags()


if __name__ == "__main__":
    main()
