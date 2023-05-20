""" Utility functions for qBit Manage. """
import json
import logging
import os
import shutil
import signal
import time
from pathlib import Path

import ruamel.yaml

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


class check:
    """Check for attributes in config."""

    def __init__(self, config):
        self.config = config

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
        """Check for attribute in config."""
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
            except:
                pass
            if isinstance(data[attribute], float) and data[attribute] >= min_int:
                return data[attribute]
            else:
                message = f"{text} must a float >= {float(min_int)}"
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
    """Check if a list of strings is in a string"""
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
        shutil.copyfile(src, dest)
        to_delete = True
    except FileNotFoundError as file:
        logger.warning(f"{file} : source: {src} -> destination: {dest}")
    except Exception as ex:
        logger.stacktrace()
        logger.error(ex)
    return to_delete


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


def remove_empty_directories(pathlib_root_dir, pattern):
    """Remove empty directories recursively."""
    pathlib_root_dir = Path(pathlib_root_dir)
    try:
        # list all directories recursively and sort them by path,
        # longest first
        longest = sorted(
            pathlib_root_dir.glob(pattern),
            key=lambda p: len(str(p)),
            reverse=True,
        )
        longest.append(pathlib_root_dir)  # delete the folder itself if it's empty
        for pdir in longest:
            try:
                pdir.rmdir()  # remove directory if empty
            except (FileNotFoundError, OSError):
                continue  # catch and continue if non-empty, folders within could already be deleted if run in parallel
    except FileNotFoundError:
        pass  # if this is being run in parallel, pathlib_root_dir could already be deleted


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
            inode_no = os.stat(file.replace(self.root_dir, self.remote_dir)).st_ino
            if inode_no in self.inode_count:
                self.inode_count[inode_no] += 1
            else:
                self.inode_count[inode_no] = 1

    def nohardlink(self, file, notify):
        """
        Check if there are any hard links
        Will check if there are any hard links if it passes a file or folder
        If a folder is passed, it will take the largest file in that folder and only check for hardlinks
        of the remaining files where the file is greater size a percentage of the largest file
        This fixes the bug in #192
        """
        check_for_hl = True
        if os.path.isfile(file):
            logger.trace(f"Checking file: {file}")
            logger.trace(f"Checking file inum: {os.stat(file).st_ino}")
            logger.trace(f"Checking no of hard links: {os.stat(file).st_nlink}")
            logger.tract(f"Checking inode_count dict: {self.inode_count.get(os.stat(file).st_ino)}")
            # https://github.com/StuffAnThings/qbit_manage/issues/291 for more details
            if os.stat(file).st_nlink - self.inode_count.get(os.stat(file).st_ino, 1) > 0:
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
                    file_size = os.stat(files).st_size
                    file_no_hardlinks = os.stat(files).st_nlink
                    logger.trace(f"Checking file: {file}")
                    logger.trace(f"Checking file inum: {os.stat(file).st_ino}")
                    logger.trace(f"Checking file size: {file_size}")
                    logger.trace(f"Checking no of hard links: {file_no_hardlinks}")
                    logger.tract(f"Checking inode_count dict: {self.inode_count.get(os.stat(file).st_ino)}")
                    if file_no_hardlinks - self.inode_count.get(os.stat(file).st_ino, 1) > 0 and file_size >= (
                        largest_file_size * threshold
                    ):
                        check_for_hl = False
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
