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


class check:
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
        default_int=0,
        throw=False,
        save=True,
        make_dirs=False,
    ):
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
        elif var_type == "int":
            if isinstance(data[attribute], int) and data[attribute] >= default_int:
                return data[attribute]
            else:
                message = f"{text} must an integer >= {default_int}"
        elif var_type == "float":
            try:
                data[attribute] = float(data[attribute])
            except:
                pass
            if isinstance(data[attribute], float) and data[attribute] >= default_int:
                return data[attribute]
            else:
                message = f"{text} must a float >= {float(default_int)}"
        elif var_type == "path":
            if os.path.exists(os.path.abspath(data[attribute])):
                return os.path.join(data[attribute], "")
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
        if var_type == "path" and default and os.path.exists(os.path.abspath(default)):
            return os.path.join(default, "")
        elif var_type == "path" and default and make_dirs:
            os.makedirs(default, exist_ok=True)
            return os.path.join(default, "")
        elif var_type == "path" and default:
            if data and attribute in data and data[attribute]:
                message = f"neither {data[attribute]} or the default path {default} could be found"
            else:
                message = f"no {text} found and the default path {default} could not be found"
            default = None
        if default is not None or default_is_none:
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
    pass


def list_in_text(text, search_list, match_all=False):
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


# truncate the value of the torrent url to remove sensitive information
def trunc_val(s, d, n=3):
    try:
        x = d.join(s.split(d, n)[:n])
    except IndexError:
        x = None
    return x


# Move files from source to destination, mod variable is to change the date modified of the file being moved
def move_files(src, dest, mod=False):
    dest_path = os.path.dirname(dest)
    toDelete = False
    if os.path.isdir(dest_path) is False:
        os.makedirs(dest_path)
    try:
        if mod is True:
            modTime = time.time()
            os.utime(src, (modTime, modTime))
        shutil.move(src, dest)
    except PermissionError as p:
        logger.warning(f"{p} : Copying files instead.")
        shutil.copyfile(src, dest)
        toDelete = True
    except Exception as e:
        logger.stacktrace()
        logger.error(e)
    return toDelete


# Copy Files from source to destination
def copy_files(src, dest):
    dest_path = os.path.dirname(dest)
    if os.path.isdir(dest_path) is False:
        os.makedirs(dest_path)
    try:
        shutil.copyfile(src, dest)
    except Exception as e:
        logger.stacktrace()
        logger.error(e)


# Remove any empty directories after moving files
def remove_empty_directories(pathlib_root_dir, pattern):
    pathlib_root_dir = Path(pathlib_root_dir)
    # list all directories recursively and sort them by path,
    # longest first
    L = sorted(
        pathlib_root_dir.glob(pattern),
        key=lambda p: len(str(p)),
        reverse=True,
    )
    for pdir in L:
        try:
            pdir.rmdir()  # remove directory if empty
        except OSError:
            continue  # catch and continue if non-empty


# will check if there are any hard links if it passes a file or folder
def nohardlink(file):
    check = True
    if os.path.isfile(file):
        if os.stat(file).st_nlink > 1:
            check = False
    else:
        for path, subdirs, files in os.walk(file):
            for x in files:
                if os.stat(os.path.join(path, x)).st_nlink > 1:
                    check = False
    return check


# Load json file if exists
def load_json(file):
    if os.path.isfile(file):
        f = open(file)
        data = json.load(f)
        f.close()
    else:
        data = {}
    return data


# Save json file overwrite if exists
def save_json(torrent_json, dest):
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(torrent_json, f, ensure_ascii=False, indent=4)


# Gracefully kill script when docker stops
class GracefulKiller:
    kill_now = False

    def __init__(self):
        # signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True


def human_readable_size(size, decimal_places=3):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f}{unit}"


class YAML:
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
                    with open(self.path, encoding="utf-8") as fp:
                        self.data = self.yaml.load(fp)
        except ruamel.yaml.error.YAMLError as e:
            e = str(e).replace("\n", "\n      ")
            raise Failed(f"YAML Error: {e}")
        except Exception as e:
            raise Failed(f"YAML Error: {e}")
        if not self.data or not isinstance(self.data, dict):
            if check_empty:
                raise Failed("YAML Error: File is empty")
            self.data = {}

    def save(self):
        if self.path:
            with open(self.path, "w") as fp:
                self.yaml.dump(self.data, fp)
