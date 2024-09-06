#!/usr/bin/python3
import argparse
import os
import shutil
import sys

import yaml


def move_files(src, dest, debug=True):
    """Move files from source to destination"""
    dest_path = os.path.dirname(dest)
    if debug:
        print(f"From: {src} To: {dest}")
    else:
        if not os.path.isdir(dest_path):
            os.makedirs(dest_path, exist_ok=True)
        try:
            shutil.move(src, dest)
        except PermissionError as perm:
            print(perm)
        except FileNotFoundError as file:
            print(f"{file} : source: {src} -> destination: {dest}")
        except Exception as ex:
            print(ex)


def joiner(base, add):
    """Join two paths together, just makes for less characters"""
    return os.path.join(base, add)


def ls(path):
    """Kind of like bash ls, less characters"""
    return os.listdir(path)


def load_config(config_path):
    """Load configuration from qbit manage's YAML config"""
    with open(config_path) as file:
        return yaml.safe_load(file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="QBM_Recovery",
        description="Move files in the RecycleBin back into place",
        epilog="Don't forget to restart qbittorrent...",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yml",
        help="path to qbit_manages configuration file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Print debug statements instead of taking action",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        help="Base directory of the RecycleBin",
    )
    parser.add_argument(
        "--btbackup-dir",
        type=str,
        help="Destination directory for BT_backup",
    )
    args = parser.parse_args()

    # Load configuration from YAML
    config = load_config(args.config)

    # Retrieve directories from the config with defaults if not present
    base_dir = args.base_dir or config.get("directory", {}).get("recycle_bin")
    btbackup_dir = args.btbackup_dir or config.get("directory", {}).get("torrents_dir")

    debug = args.debug

    try:
        for dir in ls(base_dir):  # torrents tv movies torrents_json links
            dir_path = joiner(base_dir, dir)
            if dir == "torrents_json":  # skip
                continue
            elif dir == "torrents":  # move as is
                for subdir in ls(dir_path):
                    subdir_path = joiner(dir_path, subdir)
                    move_files(subdir_path, btbackup_dir, debug)
            elif dir == "links":  # will have a subfolder
                for subdir in ls(dir_path):
                    subdir_path = joiner(dir_path, subdir)
                    for tdir in ls(subdir_path):  # the action torrent files
                        tdir_path = joiner(subdir_path, tdir)
                        move_files(tdir_path, tdir_path.replace(base_dir, ""), debug)
            else:  # movies tv
                for subdir in ls(dir_path):
                    # might be a file, might be a folder
                    subdir_path = joiner(dir_path, subdir)
                    move_files(subdir_path, subdir_path.replace(base_dir, ""), debug)
        print("\n\nRemember to restart Qbittorrent: docker compose restart qbittorrent")
    except KeyboardInterrupt:
        sys.exit(1)
