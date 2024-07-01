""" Utility functions for qBit Manage. """

import json
import logging
import os
import shutil
import signal
import time
from pathlib import Path

import requests
import ruamel.yaml
from pytimeparse2 import parse

logger = logging.getLogger("qBit Manage")


def get_list(data, lower=False, split=True, int_list=False):
    """Return a list from a string or list."""
    if data is None:
        return None
    elif isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    elif split is False:
        return [str(data)]
    elif lower is True:
        return [d.strip().lower() for d in str(data).split(",")]
    elif int_list is True:
        try:
            return [int(d.strip()) for d in str(data).split(",")]
        except ValueError:
            return []
    else:
        return [d.strip() for d in str(data).split(",")]


def is_tag_in_torrent(check_tag, torrent_tags, exact=True):
    """Check if tag is in torrent_tags"""
    tags = get_list(torrent_tags)
    if isinstance(check_tag, str):
        if exact:
            return check_tag in tags
        else:
            tags_to_remove = []
            for tag in tags:
                if check_tag in tag:
                    tags_to_remove.append(tag)
            return tags_to_remove
    elif isinstance(check_tag, list):
        if exact:
            return all(tag in tags for tag in check_tag)
        else:
            tags_to_remove = []
            for tag in tags:
                for ctag in check_tag:
                    if ctag in tag:
                        tags_to_remove.append(tag)
            return tags_to_remove


class TorrentMessages:
    """Contains list of messages to check against a status of a torrent"""

    UNREGISTERED_MSGS = [
        "UNREGISTERED",
        "TORRENT NOT FOUND",
        "TORRENT IS NOT FOUND",
        "NOT REGISTERED",
        "NOT EXIST",
        "UNKNOWN TORRENT",
        "TRUMP",
        "RETITLED",
        "TRUNCATED",
        "TORRENT IS NOT AUTHORIZED FOR USE ON THIS TRACKER",
        "INFOHASH NOT FOUND.",  # blutopia
        "TORRENT HAS BEEN DELETED.",  # blutopia
    ]

    UNREGISTERED_MSGS_BHD = [
        "DEAD",
        "DUPE",
        "COMPLETE SEASON UPLOADED",
        "PROBLEM WITH DESCRIPTION",
        "PROBLEM WITH FILE",
        "PROBLEM WITH PACK",
        "SPECIFICALLY BANNED",
        "TRUMPED",
        "OTHER",
        "TORRENT HAS BEEN DELETED",
    ]

    IGNORE_MSGS = [
        "YOU HAVE REACHED THE CLIENT LIMIT FOR THIS TORRENT",
        "MISSING PASSKEY",
        "MISSING INFO_HASH",
        "PASSKEY IS INVALID",
        "INVALID PASSKEY",
        "EXPECTED VALUE (LIST, DICT, INT OR STRING) IN BENCODED STRING",
        "COULD NOT PARSE BENCODED DATA",
        "STREAM TRUNCATED",
        "GATEWAY TIMEOUT",  # BHD Gateway Timeout
        "ANNOUNCE IS CURRENTLY UNAVAILABLE",  # BHD Announce unavailable
        "TORRENT HAS BEEN POSTPONED",  # BHD Status
        "520 (UNKNOWN HTTP ERROR)",
    ]

    EXCEPTIONS_MSGS = [
        "DOWN",
        "DOWN.",
        "IT MAY BE DOWN,",
        "UNREACHABLE",
        "(UNREACHABLE)",
        "BAD GATEWAY",
        "TRACKER UNAVAILABLE",
    ]


def guess_branch(version, env_version, git_branch):
    if git_branch:
        return git_branch
    elif env_version == "develop":
        return env_version
    elif version[2] > 0:
        dev_version = get_develop()
        if version[1] != dev_version[1] or version[2] <= dev_version[2]:
            return "develop"
    else:
        return "master"


def current_version(version, branch=None):
    if branch == "develop":
        return get_develop()
    elif version[2] > 0:
        new_version = get_develop()
        if version[1] != new_version[1] or new_version[2] >= version[2]:
            return new_version
    else:
        return get_master()


develop_version = None


def get_develop():
    global develop_version
    if develop_version is None:
        develop_version = get_version("develop")
    return develop_version


master_version = None


def get_master():
    global master_version
    if master_version is None:
        master_version = get_version("master")
    return master_version


def get_version(level):
    try:
        url = f"https://raw.githubusercontent.com/StuffAnThings/qbit_manage/{level}/VERSION"
        return parse_version(requests.get(url).content.decode().strip(), text=level)
    except requests.exceptions.ConnectionError:
        return "Unknown", "Unknown", 0


def parse_version(version, text="develop"):
    version = version.replace("develop", text)
    split_version = version.split(f"-{text}")
    return version, split_version[0], int(split_version[1]) if len(split_version) > 1 else 0


class check:
    """Check for attributes in config."""

    def __init__(self, config):
        self.config = config

    def overwrite_attributes(self, data, attribute):
        """Overwrite attributes in config."""
        yaml = YAML(self.config.config_path)
        if data is not None and attribute in yaml.data:
            yaml.data[attribute] = data
            yaml.save()

    def check_for_attribute(
        self,
        data,
        attribute,
        parent=None,
        subparent=None,
        test_list=None,
        default=None,
        do_print=True,
        default_is_none=False,
        req_default=False,
        var_type="str",
        min_int=0,
        throw=False,
        save=True,
        make_dirs=False,
    ):
        """
        Check for attribute in config.

        Args:
            data (dict): The configuration data to search.
            attribute (str): The name of the attribute key to search for.
            parent (str, optional): The name of the top level attribute to search under. Defaults to None.
            subparent (str, optional): The name of the second level attribute to search under. Defaults to None.
            test_list (dict, optional): A dictionary of valid values for the attribute. Defaults to None.
            default (any, optional): The default value to use if the attribute is not found. Defaults to None.
            do_print (bool, optional): Whether to print warning messages. Defaults to True.
            default_is_none (bool, optional): Whether to treat a None value as a valid default. Defaults to False.
            req_default (bool, optional): Whether to raise an error if no default value is provided. Defaults to False.
            var_type (str, optional): The expected type of the attribute value. Defaults to "str".
            min_int (int, optional): The minimum value for an integer attribute. Defaults to 0.
            throw (bool, optional): Whether to raise an error if the attribute value is invalid. Defaults to False.
            save (bool, optional): Whether to save the default value to the config if it is used. Defaults to True.
            make_dirs (bool, optional): Whether to create directories for path attributes if they do not exist. Defaults to False.

        Returns:
            any: The value of the attribute, or the default value if it is not found.

        Raises:
            Failed: If the attribute value is invalid or a required default value is missing.
        """
        endline = ""
        if parent is not None:
            if subparent is not None:
                if data and parent in data and subparent in data[parent]:
                    data = data[parent][subparent]
                else:
                    data = None
                    do_print = False
            else:
                if data and parent in data:
                    data = data[parent]
                else:
                    data = None
                    do_print = False

        if subparent is not None:
            text = f"{parent}->{subparent} sub-attribute {attribute}"
        elif parent is None:
            text = f"{attribute} attribute"
        else:
            text = f"{parent} sub-attribute {attribute}"

        if data is None or attribute not in data or (attribute in data and data[attribute] is None and not default_is_none):
            message = f"{text} not found"
            if parent and save is True:
                yaml = YAML(self.config.config_path)
                if subparent:
                    endline = f"\n{subparent} sub-attribute {attribute} added to config"
                    if subparent not in yaml.data[parent] or not yaml.data[parent][subparent]:
                        yaml.data[parent][subparent] = {attribute: default}
                    elif attribute not in yaml.data[parent]:
                        if isinstance(yaml.data[parent][subparent], str):
                            yaml.data[parent][subparent] = {attribute: default}
                        yaml.data[parent][subparent][attribute] = default
                    else:
                        endline = ""
                else:
                    endline = f"\n{parent} sub-attribute {attribute} added to config"
                    if parent not in yaml.data or not yaml.data[parent]:
                        yaml.data[parent] = {attribute: default}
                    elif attribute not in yaml.data[parent] or (
                        attribute in yaml.data[parent] and yaml.data[parent][attribute] is None
                    ):
                        yaml.data[parent][attribute] = default
                    else:
                        endline = ""
                yaml.save()
            if default_is_none and var_type in ["list", "int_list"]:
                return []
        elif data[attribute] is None:
            if default_is_none and var_type == "list":
                return []
            elif default_is_none:
                return None
            else:
                message = f"{text} is blank"
        elif var_type == "url":
            if data[attribute].endswith(("\\", "/")):
                return data[attribute][:-1]
            else:
                return data[attribute]
        elif var_type == "bool":
            if isinstance(data[attribute], bool):
                return data[attribute]
            else:
                message = f"{text} must be either true or false"
                throw = True
        elif var_type == "int":
            if isinstance(data[attribute], int) and data[attribute] >= min_int:
                return data[attribute]
            else:
                message = f"{text} must an integer >= {min_int}"
                throw = True
        elif var_type == "float":
            try:
                data[attribute] = float(data[attribute])
            except Exception:
                pass
            if isinstance(data[attribute], float) and data[attribute] >= min_int:
                return data[attribute]
            else:
                message = f"{text} must a float >= {float(min_int)}"
                throw = True
        elif var_type == "time_parse":
            if isinstance(data[attribute], int) and data[attribute] >= min_int:
                return data[attribute]
            else:
                try:
                    parsed_seconds = parse(data[attribute])
                    if parsed_seconds is not None:
                        return int(parsed_seconds / 60)
                    else:
                        message = f"Unable to parse {text}, must be a valid time format."
                        throw = True
                except Exception:
                    message = f"Unable to parse {text}, must be a valid time format."
                    throw = True
        elif var_type == "path":
            if os.path.exists(os.path.abspath(data[attribute])):
                return os.path.join(data[attribute], "")
            else:
                if make_dirs:
                    try:
                        os.makedirs(data[attribute], exist_ok=True)
                        return os.path.join(data[attribute], "")
                    except OSError:
                        message = f"Path {os.path.abspath(data[attribute])} does not exist and can't be created"
                else:
                    message = f"Path {os.path.abspath(data[attribute])} does not exist"
        elif var_type == "list":
            return get_list(data[attribute], split=False)
        elif var_type == "list_path":
            temp_list = [p for p in get_list(data[attribute], split=False) if os.path.exists(os.path.abspath(p))]
            if len(temp_list) > 0:
                return temp_list
            else:
                message = "No Paths exist"
        elif var_type == "lower_list":
            return get_list(data[attribute], lower=True)
        elif test_list is None or data[attribute] in test_list:
            return data[attribute]
        else:
            message = f"{text}: {data[attribute]} is an invalid input"
        if var_type == "path" and default:
            default_path = os.path.abspath(default)
            if make_dirs and not os.path.exists(default_path):
                os.makedirs(default, exist_ok=True)
            if os.path.exists(default_path):
                default = os.path.join(default, "")
                message = message + f", using {default} as default"
        elif var_type == "path" and default:
            if data and attribute in data and data[attribute]:
                message = f"neither {data[attribute]} or the default path {default} could be found"
            else:
                message = f"no {text} found and the default path {default} could not be found"
            default = None
        if (default is not None or default_is_none) and not message:
            message = message + f" using {default} as default"
        message = message + endline
        if req_default and default is None:
            raise Failed(f"Config Error: {attribute} attribute must be set under {parent}.")
        options = ""
        if test_list:
            for option, description in test_list.items():
                if len(options) > 0:
                    options = f"{options}\n"
                options = f"{options}    {option} ({description})"
        if (default is None and not default_is_none) or throw:
            if len(options) > 0:
                message = message + "\n" + options
            raise Failed(f"Config Error: {message}")
        if do_print:
            logger.print_line(f"Config Warning: {message}", "warning")
            if data and attribute in data and data[attribute] and test_list is not None and data[attribute] not in test_list:
                logger.print_line(options)
        return default


class Failed(Exception):
    """Exception raised for errors in the input."""

    pass


def list_in_text(text, search_list, match_all=False):
    """
    Check if elements from a search list are present in a given text.

    Args:
        text (str): The text to search in.
        search_list (list or set): The list of elements to search for in the text.
        match_all (bool, optional): If True, all elements in the search list must be present in the text.
                                    If False, at least one element must be present. Defaults to False.

    Returns:
        bool: True if the search list elements are found in the text, False otherwise.
    """
    if isinstance(search_list, list):
        search_list = set(search_list)
    contains = {x for x in search_list if " " in x}
    exception = search_list - contains
    if match_all:
        if all(x == m for m in text.split(" ") for x in exception) or all(x in text for x in contains):
            return True
    else:
        if any(x == m for m in text.split(" ") for x in exception) or any(x in text for x in contains):
            return True
    return False


def trunc_val(stg, delm, num=3):
    """Truncate the value of the torrent url to remove sensitive information"""
    try:
        val = delm.join(stg.split(delm, num)[:num])
    except IndexError:
        val = None
    return val


def move_files(src, dest, mod=False):
    """Move files from source to destination, mod variable is to change the date modified of the file being moved"""
    dest_path = os.path.dirname(dest)
    to_delete = False
    if os.path.isdir(dest_path) is False:
        os.makedirs(dest_path, exist_ok=True)
    try:
        if mod is True:
            mod_time = time.time()
            os.utime(src, (mod_time, mod_time))
        shutil.move(src, dest)
    except PermissionError as perm:
        logger.warning(f"{perm} : Copying files instead.")
        try:
            shutil.copyfile(src, dest)
        except Exception as ex:
            logger.stacktrace()
            logger.error(ex)
            return to_delete
        if os.path.isfile(src):
            logger.warning(f"Removing original file: {src}")
            try:
                os.remove(src)
            except OSError as e:
                logger.warning(f"Error: {e.filename} - {e.strerror}.")
        to_delete = True
    except FileNotFoundError as file:
        logger.warning(f"{file} : source: {src} -> destination: {dest}")
    except Exception as ex:
        logger.stacktrace()
        logger.error(ex)
    return to_delete


def delete_files(file_path):
    """Try to delete the file directly."""
    try:
        os.remove(file_path)
    except FileNotFoundError as e:
        logger.warning(f"File not found: {e.filename} - {e.strerror}.")
    except PermissionError as e:
        logger.warning(f"Permission denied: {e.filename} - {e.strerror}.")
    except OSError as e:
        logger.error(f"Error deleting file: {e.filename} - {e.strerror}.")


def copy_files(src, dest):
    """Copy files from source to destination"""
    dest_path = os.path.dirname(dest)
    if os.path.isdir(dest_path) is False:
        os.makedirs(dest_path)
    try:
        shutil.copyfile(src, dest)
    except Exception as ex:
        logger.stacktrace()
        logger.error(ex)


def remove_empty_directories(pathlib_root_dir, excluded_paths=None):
    """Remove empty directories recursively, optimized version."""
    pathlib_root_dir = Path(pathlib_root_dir)
    if excluded_paths is not None:
        # Ensure excluded_paths is a set of Path objects for efficient lookup
        excluded_paths = {Path(p) for p in excluded_paths}

    for root, dirs, files in os.walk(pathlib_root_dir, topdown=False):
        root_path = Path(root)
        # Skip excluded paths
        if excluded_paths and root_path in excluded_paths:
            continue

        # Attempt to remove the directory if it's empty
        try:
            os.rmdir(root)
        except PermissionError as perm:
            logger.warning(f"{perm} : Unable to delete folder {root} as it has permission issues. Skipping...")
            pass
        except OSError:
            # Directory not empty or other error - safe to ignore here
            pass

    # Attempt to remove the root directory if it's now empty and not excluded
    if not excluded_paths or pathlib_root_dir not in excluded_paths:
        try:
            pathlib_root_dir.rmdir()
        except PermissionError as perm:
            logger.warning(f"{perm} :  Unable to delete folder {root} as it has permission issues. Skipping...")
            pass
        except OSError:
            pass


class CheckHardLinks:
    """
    Class to check for hardlinks
    """

    def __init__(self, root_dir, remote_dir):
        self.root_dir = root_dir
        self.remote_dir = remote_dir
        self.root_files = set(get_root_files(self.root_dir, self.remote_dir))
        self.get_inode_count()

    def get_inode_count(self):
        self.inode_count = {}
        for file in self.root_files:
            try:
                inode_no = os.stat(file.replace(self.root_dir, self.remote_dir)).st_ino
            except PermissionError as perm:
                logger.warning(f"{perm} : file {file} has permission issues. Skipping...")
                continue
            except FileNotFoundError as file_not_found_error:
                logger.warning(f"{file_not_found_error} : File {file} not found. Skipping...")
                continue
            except Exception as ex:
                logger.stacktrace()
                logger.error(ex)
                continue
            if inode_no in self.inode_count:
                self.inode_count[inode_no] += 1
            else:
                self.inode_count[inode_no] = 1

    def nohardlink(self, file, notify, ignore_root_dir):
        """
        Check if there are any hard links
        Will check if there are any hard links if it passes a file or folder
        If a folder is passed, it will take the largest file in that folder and only check for hardlinks
        of the remaining files where the file is greater size a percentage of the largest file
        This fixes the bug in #192
        """

        def has_hardlinks(self, file, ignore_root_dir):
            """
            Check if a file has hard links.

            Args:
                file (str): The path to the file.
                ignore_root_dir (bool): Whether to ignore the root directory.

            Returns:
                bool: True if the file has hard links, False otherwise.
            """
            if ignore_root_dir:
                return os.stat(file).st_nlink - self.inode_count.get(os.stat(file).st_ino, 1) > 0
            else:
                return os.stat(file).st_nlink > 1

        check_for_hl = True
        try:
            if os.path.isfile(file):
                if os.path.islink(file):
                    logger.warning(f"Symlink found in {file}, unable to determine hardlinks. Skipping...")
                    return False
                logger.trace(f"Checking file: {file}")
                logger.trace(f"Checking file inum: {os.stat(file).st_ino}")
                logger.trace(f"Checking no of hard links: {os.stat(file).st_nlink}")
                logger.trace(f"Checking inode_count dict: {self.inode_count.get(os.stat(file).st_ino)}")
                logger.trace(f"ignore_root_dir: {ignore_root_dir}")
                # https://github.com/StuffAnThings/qbit_manage/issues/291 for more details
                if has_hardlinks(self, file, ignore_root_dir):
                    logger.trace(f"Hardlinks found in {file}.")
                    check_for_hl = False
            else:
                sorted_files = sorted(Path(file).rglob("*"), key=lambda x: os.stat(x).st_size, reverse=True)
                logger.trace(f"Folder: {file}")
                logger.trace(f"Files Sorted by size: {sorted_files}")
                threshold = 0.5
                if not sorted_files:
                    msg = (
                        f"Nohardlink Error: Unable to open the folder {file}. "
                        "Please make sure folder exists and qbit_manage has access to this directory."
                    )
                    notify(msg, "nohardlink")
                    logger.warning(msg)
                else:
                    largest_file_size = os.stat(sorted_files[0]).st_size
                    logger.trace(f"Largest file: {sorted_files[0]}")
                    logger.trace(f"Largest file size: {largest_file_size}")
                    for files in sorted_files:
                        if os.path.islink(files):
                            logger.warning(f"Symlink found in {files}, unable to determine hardlinks. Skipping...")
                            continue
                        file_size = os.stat(files).st_size
                        file_no_hardlinks = os.stat(files).st_nlink
                        logger.trace(f"Checking file: {files}")
                        logger.trace(f"Checking file inum: {os.stat(files).st_ino}")
                        logger.trace(f"Checking file size: {file_size}")
                        logger.trace(f"Checking no of hard links: {file_no_hardlinks}")
                        logger.trace(f"Checking inode_count dict: {self.inode_count.get(os.stat(files).st_ino)}")
                        logger.trace(f"ignore_root_dir: {ignore_root_dir}")
                        if has_hardlinks(self, files, ignore_root_dir) and file_size >= (largest_file_size * threshold):
                            logger.trace(f"Hardlinks found in {files}.")
                            check_for_hl = False
        except PermissionError as perm:
            logger.warning(f"{perm} : file {file} has permission issues. Skipping...")
            return False
        except FileNotFoundError as file_not_found_error:
            logger.warning(f"{file_not_found_error} : File {file} not found. Skipping...")
            return False
        except Exception as ex:
            logger.stacktrace()
            logger.error(ex)
            return False
        return check_for_hl


def get_root_files(root_dir, remote_dir, exclude_dir=None):
    local_exclude_dir = exclude_dir.replace(remote_dir, root_dir) if exclude_dir and remote_dir != root_dir else exclude_dir
    root_files = [
        os.path.join(path.replace(remote_dir, root_dir) if remote_dir != root_dir else path, name)
        for path, subdirs, files in os.walk(remote_dir if remote_dir != root_dir else root_dir)
        for name in files
        if not local_exclude_dir or local_exclude_dir not in path
    ]
    return root_files


def load_json(file):
    """Load json file if exists"""
    if os.path.isfile(file):
        file = open(file)
        data = json.load(file)
        file.close()
    else:
        data = {}
    return data


def save_json(torrent_json, dest):
    """Save json file to destination"""
    with open(dest, "w", encoding="utf-8") as file:
        json.dump(torrent_json, file, ensure_ascii=False, indent=4)


class GracefulKiller:
    """
    Class to catch SIGTERM and SIGINT signals.
    Gracefully kill script when docker stops.
    """

    kill_now = False

    def __init__(self):
        # signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        """Set kill_now to True to exit gracefully."""
        self.kill_now = True


def human_readable_size(size, decimal_places=3):
    """Convert bytes to human readable size"""
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f}{unit}"


class YAML:
    """Class to load and save yaml files"""

    def __init__(self, path=None, input_data=None, check_empty=False, create=False):
        self.path = path
        self.input_data = input_data
        self.yaml = ruamel.yaml.YAML()
        self.yaml.indent(mapping=2, sequence=2)
        try:
            if input_data:
                self.data = self.yaml.load(input_data)
            else:
                if create and not os.path.exists(self.path):
                    with open(self.path, "w"):
                        pass
                    self.data = {}
                else:
                    with open(self.path, encoding="utf-8") as filepath:
                        self.data = self.yaml.load(filepath)
        except ruamel.yaml.error.YAMLError as yerr:
            err = str(yerr).replace("\n", "\n      ")
            raise Failed(f"YAML Error: {err}") from yerr
        except Exception as yerr:
            raise Failed(f"YAML Error: {yerr}") from yerr
        if not self.data or not isinstance(self.data, dict):
            if check_empty:
                raise Failed("YAML Error: File is empty")
            self.data = {}

    def save(self):
        """Save yaml file"""
        if self.path:
            with open(self.path, "w") as filepath:
                self.yaml.dump(self.data, filepath)
