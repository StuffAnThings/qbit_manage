"""Utility functions for qBit Manage."""

import glob
import json
import logging
import os
import platform
import re
import shutil
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatch
from pathlib import Path

import requests
import ruamel.yaml
from pytimeparse2 import parse


class LoggerProxy:
    """Proxy that defers attribute access to the active logger instance.

    This allows modules that import `util.logger` at import time to still
    route all logging calls to the final MyLogger instance once it is
    initialized and set via `set_logger`.
    """

    def __init__(self):
        self._logger = None

    def set_logger(self, logger):
        self._logger = logger

    def __getattr__(self, name):
        # If MyLogger is set, delegate to it; otherwise, fallback to std logging.
        if self._logger is not None:
            return getattr(self._logger, name)
        fallback = logging.getLogger("qBit Manage")
        return getattr(fallback, name)


logger = LoggerProxy()


def get_list(data, lower=False, split=True, int_list=False, upper=False):
    """Return a list from a string or list."""
    if data is None:
        return None
    elif isinstance(data, list):
        if lower is True:
            return [d.strip().lower() for d in data]
        if upper is True:
            return [d.strip().upper() for d in data]
        return data
    elif isinstance(data, dict):
        return [data]
    elif split is False:
        return [str(data)]
    elif lower is True:
        return [d.strip().lower() for d in str(data).split(",")]
    elif upper is True:
        return [d.strip().upper() for d in str(data).split(",")]
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


def format_stats_summary(stats: dict, config) -> list[str]:
    """
    Formats the statistics summary into a human-readable list of strings.

    Args:
        stats (dict): The dictionary containing the statistics.
        config (Config): The Config object to access tracker_error_tag and nohardlinks_tag.

    Returns:
        list[str]: A list of formatted strings, each representing a statistic.
    """
    stats_output = []
    for stat_key, stat_value in stats.items():
        if stat_key == "executed_commands":
            if stat_value:
                stats_output.append(f"Executed Commands: {', '.join(stat_value)}")
        elif isinstance(stat_value, (int, float)) and stat_value > 0:
            display_key = stat_key.replace("_", " ").title()
            if stat_key == "tagged_tracker_error" and hasattr(config, "tracker_error_tag"):
                display_key = f"{config.tracker_error_tag} Torrents Tagged"
            elif stat_key == "untagged_tracker_error" and hasattr(config, "tracker_error_tag"):
                display_key = f"{config.tracker_error_tag} Torrents Untagged"
            elif stat_key == "tagged_noHL" and hasattr(config, "nohardlinks_tag"):
                display_key = f"{config.nohardlinks_tag} Torrents Tagged"
            elif stat_key == "untagged_noHL" and hasattr(config, "nohardlinks_tag"):
                display_key = f"{config.nohardlinks_tag} Torrents Untagged"
            elif stat_key == "rem_unreg":
                display_key = "Unregistered Torrents Removed"
            elif stat_key == "deleted_contents":
                display_key = "Torrents + Contents Deleted"
            elif stat_key == "updated_share_limits":
                display_key = "Share Limits Updated"
            elif stat_key == "cleaned_share_limits":
                display_key = "Torrents Removed from Meeting Share Limits"
            elif stat_key == "recycle_emptied":
                display_key = "Files Deleted from Recycle Bin"
            elif stat_key == "orphaned_emptied":
                display_key = "Files Deleted from Orphaned Data"
            elif stat_key == "orphaned":
                display_key = "Orphaned Files"
            elif stat_key == "added":
                display_key = "Torrents Added"
            elif stat_key == "resumed":
                display_key = "Torrents Resumed"
            elif stat_key == "rechecked":
                display_key = "Torrents Rechecked"
            elif stat_key == "deleted":
                display_key = "Torrents Deleted"
            elif stat_key == "categorized":
                display_key = "Torrents Categorized"
            elif stat_key == "tagged":
                display_key = "Torrents Tagged"

            stats_output.append(f"Total {display_key}: {stat_value}")
    return stats_output


def in_docker():
    # Docker 1.13+ puts this file inside containers
    if os.path.exists("/.dockerenv"):
        return True

    # Fallback: check cgroup info
    try:
        with open("/proc/1/cgroup") as f:
            return any("docker" in line or "kubepods" in line or "containerd" in line or "lxc" in line for line in f)
    except FileNotFoundError:
        pass

    return False


# Global variables for get_arg function
test_value = None
static_envs = []


def get_arg(env_str, default, arg_bool=False, arg_int=False):
    """
    Get value from environment variable(s) with type conversion and fallback support.

    Args:
        env_str (str or list): Environment variable name(s) to check
        default: Default value to return if no environment variable is set
        arg_bool (bool): Convert result to boolean
        arg_int (bool): Convert result to integer

    Returns:
        Value from environment variable or default, with optional type conversion
    """
    global test_value
    env_vars = [env_str] if not isinstance(env_str, list) else env_str
    final_value = None
    static_envs.extend(env_vars)
    for env_var in env_vars:
        env_value = os.environ.get(env_var)
        if env_var == "BRANCH_NAME":
            test_value = env_value
        if env_value is not None:
            final_value = env_value
            break
    if final_value or (arg_int and final_value == 0):
        if arg_bool:
            if final_value is True or final_value is False:
                return final_value
            elif final_value.lower() in ["t", "true"]:
                return True
            else:
                return False
        elif arg_int:
            try:
                return int(final_value)
            except ValueError:
                return default
        else:
            return str(final_value)
    else:
        return default


def runtime_path(*parts) -> Path:
    """
    Resolve a bundled/runtime-safe path for assets.
    - In PyInstaller bundles, files are extracted under sys._MEIPASS.
    - In source runs, resolve relative to the project root.
    """
    if hasattr(sys, "_MEIPASS"):  # type: ignore[attr-defined]
        return Path(getattr(sys, "_MEIPASS")).joinpath(*parts)  # type: ignore[arg-type]
    # modules/util.py =&gt; project root is parent of modules/
    return Path(__file__).resolve().parent.parent.joinpath(*parts)


def _platform_config_base() -> Path:
    """Return the platform-specific base directory for app config."""
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "qbit-manage"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "qbit-manage"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else home / ".config"
        return base / "qbit-manage"


def get_default_config_dir(config_hint: str = None, config_dir: str = None) -> str:
    """
    Determine the default persistent config directory, leveraging a provided config path/pattern first.

    Resolution order:
    1) If config_dir is provided, use it directly (takes precedence over config_hint)
    2) If config_hint is an absolute path or contains a directory component, use its parent directory
    3) Otherwise, if config_hint is a name/pattern (e.g. 'config.yml'), search common bases for:
          - A direct match to that filename/pattern
          - OR a persisted scheduler file 'qbm_settings.yml' or legacy 'schedule.yml' (so we don't lose an existing schedule)
        Common bases (in order):
          - /config (container volume)
          - repository ./config
          - user OS config directory
        Return the first base containing either.
    4) Fallback to legacy-ish behavior:
          - /config if it contains any *.yml.sample / *.yaml.sample
          - otherwise user OS config directory
    """
    # 1) If config_dir is provided, use it directly (takes precedence)
    if config_dir:
        p = Path(config_dir).expanduser()
        return str(p.resolve())

    # 2) If a direct path is provided, prefer its parent directory
    if config_hint:
        primary = str(config_hint).split(",")[0].strip()  # take first if comma-separated
        if primary:
            p = Path(primary).expanduser()
            # If absolute or contains a parent component, use that directory
            if p.is_absolute() or (str(p.parent) not in (".", "")):
                base = p if p.is_dir() else p.parent
                return str(base.resolve())

            # 2) Try to resolve a plain filename/pattern or schedule.yml in common bases
            candidates = []
            if os.path.isdir("/config"):
                candidates.append(Path("/config"))
            repo_config = Path(__file__).resolve().parent.parent / "config"
            candidates.append(repo_config)
            candidates.append(_platform_config_base())

            for base in candidates:
                try:
                    # Match the primary pattern OR detect existing settings files (persistence)
                    if list(base.glob(primary)) or (base / "qbm_settings.yml").exists() or (base / "schedule.yml").exists():
                        return str(base.resolve())
                except Exception:
                    # ignore and continue to next base
                    pass

    # 3) Fallbacks
    has_yaml_sample = glob.glob(os.path.join("/config", "*.yml.sample")) or glob.glob(os.path.join("/config", "*.yaml.sample"))
    has_yaml = glob.glob(os.path.join("/config", "*.yml")) or glob.glob(os.path.join("/config", "*.yaml"))
    if os.path.isdir("/config") and (has_yaml_sample or has_yaml):
        return "/config"
    return str(_platform_config_base())


def ensure_config_dir_initialized(config_dir) -> str:
    """
    Ensure the config directory exists and is initialized:
    - Creates the config directory
    - Creates logs/ and .backups/ subdirectories
    - Creates an empty config.yml if no *.yml/*.yaml present
    Returns the absolute config directory as a string.
    """
    p = Path(config_dir).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    (p / "logs").mkdir(parents=True, exist_ok=True)
    (p / ".backups").mkdir(parents=True, exist_ok=True)

    has_yaml = any(p.glob("*.yml")) or any(p.glob("*.yaml"))
    if not has_yaml:
        dest = p / "config.yml"
        try:
            dest.touch()  # Create empty file
        except Exception:
            # Non-fatal; if creation fails, user can create a config manually
            pass

    return str(p)


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
        "TRACKER NICHT REGISTRIERT.",
        "TORRENT EXISTIERT NICHT",
        "TORRENT NICHT GEFUNDEN",
        "TORRENT DELETED",  # NexusPHP
        "TORRENT BANNED",  # NexusPHP
    ]

    UNREGISTERED_MSGS_BHD = [
        "DEAD",
        "DUPE",
        "COMPLETE SEASON UPLOADED",
        "COMPLETE SEASON UPLOADED:",
        "PROBLEM WITH DESCRIPTION",
        "PROBLEM WITH FILE",
        "PROBLEM WITH PACK",
        "SPECIFICALLY BANNED",
        "TRUMPED",
        "OTHER",
        "TORRENT HAS BEEN DELETED",
        "NUKED",
        "SEASON PACK:",
        "SEASON PACK OUT",
        "SEASON PACK UPLOADED",
    ]

    IGNORE_MSGS = [
        "YOU HAVE REACHED THE CLIENT LIMIT FOR THIS TORRENT",
        "PASSKEY",  # Any mention of passkeys should be a clear sign it should NOT be deleted
        "MISSING INFO_HASH",
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
develop_version_ts = 0.0


def get_develop():
    """Return latest develop version using TTL cache."""
    global develop_version, develop_version_ts
    ttl = _get_version_cache_ttl_seconds()
    now = time.time()
    if develop_version is not None and (now - develop_version_ts) < ttl:
        return develop_version
    value = get_version("develop")
    # Only cache successful lookups
    if value and value[0] != "Unknown":
        develop_version = value
        develop_version_ts = now
    return value


master_version = None
master_version_ts = 0.0


def _get_version_cache_ttl_seconds() -> int:
    """Resolve TTL for version cache from env QBM_VERSION_CACHE_TTL.

    Accepts seconds (e.g., "600") or human strings (e.g., "10m", "1h").
    Defaults to 600 seconds (10 minutes) if unset or invalid.
    """
    raw = os.environ.get("QBM_VERSION_CACHE_TTL", "600")
    secs = None
    try:
        secs = int(raw)
    except Exception:
        try:
            secs = parse(raw) if raw else None
        except Exception:
            secs = None
    if not secs or secs < 1:
        secs = 600
    return int(secs)


def get_master():
    """Return latest master version using TTL cache."""
    global master_version, master_version_ts
    ttl = _get_version_cache_ttl_seconds()
    now = time.time()
    if master_version is not None and (now - master_version_ts) < ttl:
        return master_version
    value = get_version("master")
    # Only cache successful lookups
    if value and value[0] != "Unknown":
        master_version = value
        master_version_ts = now
    return value


def get_version(level):
    try:
        # Always fetch fresh; bust caches and disable intermediaries
        url = f"https://raw.githubusercontent.com/StuffAnThings/qbit_manage/refs/heads/{level}/VERSION"
        params = {"ts": int(time.time())}
        headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/plain",
            "User-Agent": "qbit_manage-version-check",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        return parse_version(resp.text.strip(), text=level)
    except Exception:
        return "Unknown", "Unknown", 0


def parse_version(version, text="develop"):
    version = version.replace("develop", text)
    split_version = version.split(f"-{text}")
    return version, split_version[0], int(split_version[1]) if len(split_version) > 1 else 0


def get_current_version():
    """
    Get the current qBit Manage version using the same logic as qbit_manage.py:400-411.
    This function centralizes version parsing logic to avoid duplication.

    Returns:
        tuple: (version_tuple, branch) where version_tuple is (version_string, base_version, build_number)
               and branch is the detected branch name
    """
    # Initialize version tuple
    version = ("Unknown", "Unknown", 0)

    # Read and parse VERSION file with PyInstaller-safe resolution
    try:
        # Prefer bundled path when running as a frozen app
        version_path = None
        try:
            bundled = runtime_path("VERSION")
            if bundled.exists():
                version_path = bundled
        except Exception:
            pass

        # Fallback to repository structure: modules/../VERSION
        if version_path is None:
            repo_relative = Path(__file__).resolve().parent.parent / "VERSION"
            if repo_relative.exists():
                version_path = repo_relative

        # If we found a version file, parse it
        if version_path is not None:
            with open(version_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        version = parse_version(line)
                        break
        # If not found, leave version as ("Unknown", "Unknown", 0)
    except Exception as e:
        # Non-fatal in frozen apps; keep noise low if VERSION is missing
        logger.debug(f"VERSION read fallback hit: {e}")

    # Get environment version (same as qbit_manage.py:282)
    env_version = os.environ.get("BRANCH_NAME", "master")

    # Get git branch (same logic as qbit_manage.py:275-280)
    git_branch = None
    try:
        from git import InvalidGitRepositoryError
        from git import Repo

        try:
            git_branch = Repo(path=".").head.ref.name  # noqa
        except InvalidGitRepositoryError:
            git_branch = None
    except ImportError:
        git_branch = None

    # Guess branch and format version (same logic as qbit_manage.py:407-410)
    branch = guess_branch(version, env_version, git_branch)
    if branch is None:
        branch = "Unknown"
    version = (version[0].replace("develop", branch), version[1].replace("develop", branch), version[2])

    return version, branch


class check:
    """Check for attributes in config."""

    def __init__(self, config):
        self.config = config

    def overwrite_attributes(self, data, attribute, parent=None):
        """
        Overwrite attributes in config.

        Args:
            data: The new data to replace the attribute with
            attribute: The attribute name to search for
            parent: Optional parent attribute to restrict the search to
        """
        if data is None:
            return

        yaml = YAML(self.config.config_path)

        # Define the recursive search function once
        def find_and_replace_attribute(dictionary, attr, new_data):
            """Recursively search for attribute in nested dictionaries and replace it."""
            for key, value in dictionary.items():
                if key == attr:
                    dictionary[key] = new_data
                    return True
                elif isinstance(value, dict):
                    if find_and_replace_attribute(value, attr, new_data):
                        return True
            return False

        # Determine the root dictionary to search in
        if parent is not None:
            # Only search within parent if it exists and is a dictionary
            if parent not in yaml.data or not isinstance(yaml.data[parent], dict):
                return

            root_dict = yaml.data[parent]

            # Check if attribute exists directly in parent
            if attribute in root_dict:
                root_dict[attribute] = data
                yaml.save()
                return
        else:
            # Search in the entire yaml.data
            root_dict = yaml.data

            # Check if attribute exists at top level
            if attribute in root_dict:
                root_dict[attribute] = data
                yaml.save()
                return

        # If not found directly, search recursively
        if find_and_replace_attribute(root_dict, attribute, data):
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
        elif var_type == "size_parse":
            # Accepts values like "200MB", "1.5GB", "750MiB", "1024", case-insensitive
            # Returns bytes as an integer
            try:
                # If already an int and valid, treat as bytes
                if isinstance(data[attribute], int) and data[attribute] >= min_int:
                    return int(data[attribute])
                # If float-like numeric provided, also treat as bytes
                if isinstance(data[attribute], float) and data[attribute] >= float(min_int):
                    return int(data[attribute])
                parsed_bytes = parse_size_to_bytes(str(data[attribute]))
                if parsed_bytes is not None and parsed_bytes >= min_int:
                    return int(parsed_bytes)
                else:
                    message = f"Unable to parse {text}, must be a valid size format like '500MB', '4GB', or '1024'."
                    throw = True
            except Exception:
                message = f"Unable to parse {text}, must be a valid size format like '500MB', '4GB', or '1024'."
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
        elif var_type == "upper_list":
            return get_list(data[attribute], upper=True)
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

    # Use ThreadPoolExecutor for timeout protection without thread exhaustion
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            # Submit move operation with timeout
            future = executor.submit(_move_file_operation, src, dest, mod)
            result = future.result(timeout=300.0)  # 5 minute timeout for file operations
            to_delete = result

        except TimeoutError:
            logger.warning(f"Timeout moving file (permission issue?): {src} -> {dest}")
            return to_delete

        except PermissionError as perm:
            logger.warning(f"{perm} : Copying files instead.")

            try:
                # Use the existing copy_files function
                copy_files(src, dest)

            except Exception as ex:
                logger.stacktrace()
                logger.error(ex)
                return to_delete

            if os.path.isfile(src):
                logger.warning(f"Removing original file: {src}")

                try:
                    # Submit remove operation with timeout
                    future = executor.submit(_remove_file_operation, src)
                    future.result(timeout=300.0)

                except TimeoutError:
                    logger.warning(f"Timeout removing original file (permission issue?): {src}")
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
    """Try to delete the file directly with timeout protection."""

    # Use ThreadPoolExecutor for timeout protection without thread exhaustion
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            # Submit delete operation with timeout
            future = executor.submit(_remove_file_operation, file_path)
            future.result(timeout=300.0)  # 5 minute timeout for file operations

        except TimeoutError:
            logger.warning(f"Timeout deleting file (permission issue?): {file_path}")
            return

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


def _move_file_operation(src, dest, mod):
    """Internal function for move operation."""
    if mod is True:
        mod_time = time.time()
        os.utime(src, (mod_time, mod_time))
    shutil.move(src, dest)
    return True


def _remove_file_operation(src):
    """Internal function for remove operation."""
    os.remove(src)


def remove_empty_directories(pathlib_root_dir, excluded_paths=None, exclude_patterns=[]):
    """Remove empty directories recursively with optimized performance."""
    pathlib_root_dir = Path(pathlib_root_dir)

    # Early return for non-existent paths
    if not pathlib_root_dir.exists():
        return

    # Optimize excluded paths handling
    excluded_paths_set = set()
    if excluded_paths is not None:
        excluded_paths_set = {Path(p).resolve() for p in excluded_paths}

    # Pre-compile exclude patterns for better performance
    compiled_patterns = []
    for pattern in exclude_patterns:
        # Convert to regex for faster matching

        regex_pattern = fnmatch.translate(pattern)
        compiled_patterns.append(re.compile(regex_pattern))

    # Cache directory checks to avoid redundant operations
    directories_to_check = []

    # Collect all directories in single pass
    for root, dirs, files in os.walk(pathlib_root_dir, topdown=False):
        root_path = Path(root).resolve()

        # Skip excluded paths efficiently
        if excluded_paths_set and root_path in excluded_paths_set:
            continue

        # Check exclude patterns efficiently
        if compiled_patterns:
            root_str = str(root_path) + os.sep
            if any(pattern.match(root_str) for pattern in compiled_patterns):
                continue

        # Only add directories that might be empty (no files)
        if not files:
            directories_to_check.append(root_path)

    # Remove empty directories in batch
    removed_dirs = set()
    for dir_path in directories_to_check:
        try:
            os.rmdir(dir_path)
            removed_dirs.add(dir_path)
        except PermissionError as perm:
            logger.warning(f"{perm} : Unable to delete folder {dir_path} as it has permission issues. Skipping...")
        except OSError:
            # Directory not empty - expected
            pass

    # Attempt root directory removal if it's now empty
    if not excluded_paths_set or pathlib_root_dir.resolve() not in excluded_paths_set:
        try:
            pathlib_root_dir.rmdir()
        except PermissionError as perm:
            logger.warning(f"{perm} : Unable to delete root folder {pathlib_root_dir} as it has permission issues. Skipping...")
        except OSError:
            pass


class CheckHardLinks:
    """
    Class to check for hardlinks
    """

    def __init__(self, config):
        self.root_dir = config.root_dir
        self.remote_dir = config.remote_dir
        self.orphaned_dir = config.orphaned_dir if config.orphaned_dir else ""
        self.recycle_dir = config.recycle_dir if config.recycle_dir else ""
        self.root_files = set(
            get_root_files(self.root_dir, self.remote_dir)
            + get_root_files(self.orphaned_dir, "")
            + get_root_files(self.recycle_dir, "")
        )
        self.get_inode_count()

    def get_inode_count(self):
        self.inode_count = {}
        for file in self.root_files:
            # Only check hardlinks for files that are symlinks
            if os.path.isfile(file) and os.path.islink(file):
                continue
            else:
                try:
                    inode_no = os.stat(path_replace(file, self.root_dir, self.remote_dir)).st_ino
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
                threshold = 0.1
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
    """
    Get all files in root directory with optimized path handling and filtering.

    Windows/UNC-safe:
    - If remote_dir is empty or effectively the same as root_dir, walk root_dir directly.
    - Otherwise, walk remote_dir (the accessible path) and map paths back to the root_dir representation.
    """
    if not root_dir:
        return []

    # Normalize for robust equality checks across platforms (handles UNC vs local, slashes, case on Windows)
    try:
        rd_norm = os.path.normcase(os.path.normpath(root_dir)) if root_dir else ""
        rem_norm = os.path.normcase(os.path.normpath(remote_dir)) if remote_dir else ""
    except Exception:
        rd_norm = root_dir or ""
        rem_norm = remote_dir or ""

    # Treat missing/empty remote_dir as "same path" (walk root_dir directly)
    is_same_path = (not remote_dir) or (rem_norm == rd_norm)

    # Determine which base directory to walk and validate it exists
    base_to_walk = root_dir if is_same_path else remote_dir
    if not base_to_walk or not os.path.isdir(base_to_walk):
        return []

    # Build an exclude path in the correct namespace
    local_exclude_dir = None
    if exclude_dir:
        if is_same_path:
            local_exclude_dir = exclude_dir
        else:
            # Convert an exclude in remote namespace to root namespace for comparison after replacement
            try:
                local_exclude_dir = path_replace(exclude_dir, remote_dir, root_dir)
            except Exception:
                local_exclude_dir = None

    root_files = []

    if is_same_path:
        # Fast path when paths are the same or remote_dir not provided
        for path, subdirs, files in os.walk(base_to_walk):
            if local_exclude_dir and os.path.normcase(local_exclude_dir) in os.path.normcase(path):
                continue
            for name in files:
                root_files.append(os.path.join(path, name))
    else:
        # Walk the accessible remote_dir and convert to root_dir representation once per directory
        for path, subdirs, files in os.walk(base_to_walk):
            replaced_path = path_replace(path, remote_dir, root_dir)
            if local_exclude_dir and os.path.normcase(local_exclude_dir) in os.path.normcase(replaced_path):
                continue
            for name in files:
                root_files.append(os.path.join(replaced_path, name))

    return root_files


def load_json(file):
    """Load json file if exists"""
    if os.path.isfile(truncate_filename(file)):
        file = open(file)
        data = json.load(file)
        file.close()
    else:
        data = {}
    return data


def truncate_filename(filename, max_length=255, offset=0):
    """
    Truncate filename if necessary.

    Args:
        filename (str): The original filename.
        max_length (int, optional): The maximum length of the truncated filename. Defaults to 255.
        offset (int, optional): The number of characters to keep from the end of the base name. Defaults to 0.

    Returns:
        str: The truncated filename.

    """
    base, ext = os.path.splitext(filename)
    if len(filename) > max_length:
        max_base_length = max_length - len(ext) - offset
        truncated_base = base[:max_base_length]
        truncated_base_offset = base[-offset:] if offset > 0 else ""
        truncated_filename = f"{truncated_base}{truncated_base_offset}{ext}"
    else:
        truncated_filename = filename
    return truncated_filename


def save_json(torrent_json, dest):
    """Save json file to destination, truncating filename if necessary."""
    max_filename_length = 255  # Typical maximum filename length on many filesystems
    directory, filename = os.path.split(dest)
    filename, ext = os.path.splitext(filename)

    if len(filename) > (max_filename_length - len(ext)):
        truncated_filename = truncate_filename(filename, max_filename_length)
        dest = os.path.join(directory, truncated_filename)
        logger.warning(f"Filename too long, truncated to: {dest}")

    try:
        with open(dest, "w", encoding="utf-8") as file:
            json.dump(torrent_json, file, ensure_ascii=False, indent=4)
    except FileNotFoundError as e:
        logger.error(f"Failed to save JSON file: {e.filename} - {e.strerror}.")
    except OSError as e:
        logger.error(f"OS error occurred: {e.filename} - {e.strerror}.")


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


def parse_size_to_bytes(value):
    """
    Parse a human-readable size string into bytes.
    Accepts units: B, KB, MB, GB, TB, PB and binary variants KiB, MiB, GiB, TiB, PiB (case-insensitive).
    Examples: "200MB", "1.5GB", "750MiB", "1024", 2048
    Returns:
        int: number of bytes, or None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return None
    s = str(value).strip()
    if s == "":
        return None
    # Match number and optional unit
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgGtTpP]i?[bB])?\s*$", s)
    if not m:
        # If pure integer without unit
        try:
            return int(float(s))
        except Exception:
            return None
    num = float(m.group(1))
    unit = m.group(2).lower() if m.group(2) else "b"

    # Normalize common forms to binary multiples (base 1024) to match qBittorrent bytes
    # Treat KB/MB/GB as KiB/MiB/GiB equivalents
    multipliers = {
        "b": 1,
        "kb": 1024,
        "kib": 1024,
        "mb": 1024**2,
        "mib": 1024**2,
        "gb": 1024**3,
        "gib": 1024**3,
        "tb": 1024**4,
        "tib": 1024**4,
        "pb": 1024**5,
        "pib": 1024**5,
    }
    mul = multipliers.get(unit, None)
    if mul is None:
        return None
    return int(num * mul)


def path_replace(path, old_path, new_path):
    """
    Cross-platform safe path replacement that handles different path separators.

    This function replaces old_path with new_path in the given path, accounting for
    differences in path separators between Windows (\\) and Unix-like systems (/).

    Args:
        path (str): The path to modify
        old_path (str): The path segment to replace
        new_path (str): The replacement path segment

    Returns:
        str: The modified path with cross-platform compatibility
    """
    if not path or not old_path:
        return path

    # Normalize all paths to use forward slashes for comparison
    if isinstance(path, list):
        path = path[0]
    if isinstance(old_path, list):
        old_path = old_path[0]
    if isinstance(new_path, list):
        new_path = new_path[0]
    path_norm = path.replace("\\", "/")
    old_norm = old_path.replace("\\", "/")
    new_norm = new_path.replace("\\", "/") if new_path else ""

    # Perform the replacement on normalized paths
    if path_norm.startswith(old_norm):
        result = new_norm + path_norm[len(old_norm) :]
    elif old_norm in path_norm:
        result = path_norm.replace(old_norm, new_norm, 1)
    else:
        return path

    # Convert back to the platform's preferred separator
    return os.path.normpath(result)


class YAML:
    """Class to load and save yaml files with !ENV tag preservation and environment variable resolution"""

    def __init__(self, path=None, input_data=None, check_empty=False, create=False):
        self.path = path
        self.input_data = input_data
        self.yaml = ruamel.yaml.YAML()
        self.yaml.indent(mapping=2, sequence=2)

        # Add constructor for !ENV tag
        self.yaml.Constructor.add_constructor("!ENV", self._env_constructor)
        # Add representer for !ENV tag
        self.yaml.Representer.add_representer(EnvStr, self._env_representer)

        try:
            if input_data is not None:
                if input_data == "":
                    # Empty string means initialize with empty data for writing
                    self.data = {}
                else:
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

    def _env_constructor(self, loader, node):
        """Constructor for !ENV tag"""
        value = loader.construct_scalar(node)
        # Resolve the environment variable at runtime
        env_value = os.getenv(value)
        # If environment variable is not found, use an empty string as default for schema generation
        if env_value is None:
            logger.warning(f"Environment variable '{value}' not found. Using empty string for schema generation.")
            env_value = ""
        # Return a custom string subclass that preserves the !ENV tag
        return EnvStr(value, env_value)

    def _env_representer(self, dumper, data):
        """Representer for EnvStr class"""
        return dumper.represent_scalar("!ENV", data.env_var)

    def save(self):
        """Save yaml file with !ENV tags preserved"""
        if self.path:
            with open(self.path, "w", encoding="utf-8") as filepath:
                self.yaml.dump(self.data, filepath)
        else:
            raise ValueError("YAML path is None or empty")

    def save_preserving_format(self, new_data):
        """Save yaml file while preserving original formatting, comments, and structure"""
        if not self.path:
            raise ValueError("YAML path is None or empty")

        # Load the original file to preserve formatting
        original_yaml = ruamel.yaml.YAML()
        original_yaml.preserve_quotes = True
        original_yaml.map_indent = 2
        original_yaml.sequence_indent = 2
        original_yaml.sequence_dash_offset = 0

        # Add constructor and representer for !ENV tag
        original_yaml.Constructor.add_constructor("!ENV", self._env_constructor)
        original_yaml.Representer.add_representer(EnvStr, self._env_representer)

        try:
            # Load the original file with formatting preserved
            with open(self.path, encoding="utf-8") as filepath:
                original_data = original_yaml.load(filepath)

            # If original file is empty or None, use new data directly
            if not original_data:
                original_data = original_yaml.load("{}")

            # Recursively update the original data with new values while preserving structure
            self._deep_update_preserving_format(original_data, new_data)

            # Save with preserved formatting
            with open(self.path, "w", encoding="utf-8") as filepath:
                original_yaml.dump(original_data, filepath)

        except FileNotFoundError:
            # If file doesn't exist, create it with new data
            with open(self.path, "w", encoding="utf-8") as filepath:
                original_yaml.dump(new_data, filepath)
        except Exception as e:
            logger.error(f"Error preserving YAML format: {e}")
            # Fallback to regular save
            self.data = new_data
            self.save()

    def _deep_update_preserving_format(self, original, new_data):
        """Recursively update original data with new data while preserving formatting"""
        if not isinstance(new_data, dict):
            return new_data

        if not isinstance(original, dict):
            return new_data

        for key, value in new_data.items():
            if key in original:
                if isinstance(value, dict) and isinstance(original[key], dict):
                    # Recursively update nested dictionaries
                    self._deep_update_preserving_format(original[key], value)
                else:
                    # Update the value while preserving any YAML formatting
                    original[key] = value
            else:
                # Add new key-value pairs
                original[key] = value

        # Remove keys that exist in original but not in new_data
        keys_to_remove = []
        for key in original:
            if key not in new_data:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del original[key]

        return original


class EnvStr(str):
    """Custom string subclass to preserve !ENV tags"""

    def __new__(cls, env_var, resolved_value):
        # Create a new string instance with the resolved value
        instance = super().__new__(cls, resolved_value)
        instance.env_var = env_var  # Store the environment variable name
        return instance

    def __repr__(self):
        """Return the resolved value as a string"""
        return super().__repr__()


def get_matching_config_files(config_pattern: str, default_dir: str, use_config_dir_mode: bool = False) -> list:
    """Get list of config files matching a pattern.

    Args:
        config_pattern (str): Config file pattern (e.g. "config.yml" or "config*.yml")
        default_dir (str): Default directory to look for configs
        use_config_dir_mode (bool): If True, use new config-dir approach (find all .yml/.yaml files)
                                   If False, use legacy config-file approach (pattern matching)

    Returns:
        list: List of matching config file names

    Raises:
        Failed: If no matching config files found
    """
    # Check docker config first
    if os.path.isdir("/config") and glob.glob(os.path.join("/config", config_pattern)):
        search_dir = "/config"
    else:
        search_dir = default_dir

    if use_config_dir_mode:
        # New --config-dir approach: find all .yml and .yaml files, excluding reserved files
        config_files = []
        for pattern in ["*.yml", "*.yaml"]:
            glob_configs = glob.glob(os.path.join(search_dir, pattern))
            for config_file in glob_configs:
                filename = os.path.basename(config_file)
                # Exclude reserved files
                if filename not in ("schedule.yml", "qbm_settings.yml"):
                    config_files.append(filename)

        if config_files:
            # Return just the filenames without paths, sorted for consistency
            return sorted(config_files)
        else:
            raise Failed(f"Config Error: Unable to find any config files in '{search_dir}'")
    else:
        # Legacy --config-file approach: pattern matching
        # Handle single file vs pattern
        if "*" not in config_pattern:
            # For single file, check if it exists
            if os.path.exists(os.path.join(search_dir, config_pattern)):
                return [config_pattern]
            else:
                raise Failed(f"Config Error: Unable to find config file '{config_pattern}' in '{search_dir}'")
        else:
            # For patterns, use glob matching
            glob_configs = glob.glob(os.path.join(search_dir, config_pattern))
            if glob_configs:
                # Return just the filenames without paths
                return [os.path.basename(x) for x in glob_configs]
            else:
                raise Failed(f"Config Error: Unable to find any config files in the pattern '{config_pattern}' in '{search_dir}'")


def execute_qbit_commands(qbit_manager, commands, stats, hashes=None):
    """Execute qBittorrent management commands and update stats.

    Args:
        qbit_manager: The qBittorrent manager instance
        commands: Dictionary of command flags (e.g., {"cat_update": True, "tag_update": False})
        stats: Dictionary to update with execution statistics
        hashes: Optional list of torrent hashes to process (for web API)

    Returns:
        None (modifies stats dictionary in place)
    """
    # Import here to avoid circular imports
    from modules.core.category import Category
    from modules.core.recheck import ReCheck
    from modules.core.remove_orphaned import RemoveOrphaned
    from modules.core.remove_unregistered import RemoveUnregistered
    from modules.core.share_limits import ShareLimits
    from modules.core.tag_nohardlinks import TagNoHardLinks
    from modules.core.tags import Tags
    from modules.qbit_error_handler import safe_execute_with_qbit_error_handling

    # Initialize executed_commands list
    if "executed_commands" not in stats:
        stats["executed_commands"] = []

    # Set Category
    if commands.get("cat_update"):
        if hashes is not None:
            result = safe_execute_with_qbit_error_handling(
                lambda: Category(qbit_manager, hashes).stats, "Category Update (with hashes)"
            )
        else:
            result = safe_execute_with_qbit_error_handling(lambda: Category(qbit_manager).stats, "Category Update")

        if result is not None:
            if "categorized" not in stats:
                stats["categorized"] = 0
            stats["categorized"] += result
            stats["executed_commands"].append("cat_update")
        else:
            logger.warning("Category Update operation skipped due to API errors")

    # Set Tags
    if commands.get("tag_update"):
        if hashes is not None:
            result = safe_execute_with_qbit_error_handling(lambda: Tags(qbit_manager, hashes).stats, "Tags Update (with hashes)")
        else:
            result = safe_execute_with_qbit_error_handling(lambda: Tags(qbit_manager).stats, "Tags Update")

        if result is not None:
            stats["tagged"] += result
            stats["executed_commands"].append("tag_update")
        else:
            logger.warning("Tags Update operation skipped due to API errors")

    # Remove Unregistered Torrents and tag errors
    if commands.get("rem_unregistered") or commands.get("tag_tracker_error"):
        if hashes is not None:
            rem_unreg = safe_execute_with_qbit_error_handling(
                lambda: RemoveUnregistered(qbit_manager, hashes), "Remove Unregistered Torrents (with hashes)"
            )
        else:
            rem_unreg = safe_execute_with_qbit_error_handling(
                lambda: RemoveUnregistered(qbit_manager), "Remove Unregistered Torrents"
            )

        if rem_unreg is not None:
            # Initialize stats if they don't exist
            for key in ["rem_unreg", "deleted", "deleted_contents", "tagged_tracker_error", "untagged_tracker_error"]:
                if key not in stats:
                    stats[key] = 0

            stats["rem_unreg"] += rem_unreg.stats_deleted + rem_unreg.stats_deleted_contents
            stats["deleted"] += rem_unreg.stats_deleted
            stats["deleted_contents"] += rem_unreg.stats_deleted_contents
            stats["tagged_tracker_error"] += rem_unreg.stats_tagged
            stats["untagged_tracker_error"] += rem_unreg.stats_untagged
            stats["tagged"] += rem_unreg.stats_tagged
            stats["executed_commands"].extend([cmd for cmd in ["rem_unregistered", "tag_tracker_error"] if commands.get(cmd)])
        else:
            logger.warning("Remove Unregistered Torrents operation skipped due to API errors")

    # Recheck Torrents
    if commands.get("recheck"):
        if hashes is not None:
            recheck = safe_execute_with_qbit_error_handling(
                lambda: ReCheck(qbit_manager, hashes), "Recheck Torrents (with hashes)"
            )
        else:
            recheck = safe_execute_with_qbit_error_handling(lambda: ReCheck(qbit_manager), "Recheck Torrents")

        if recheck is not None:
            if "rechecked" not in stats:
                stats["rechecked"] = 0
            if "resumed" not in stats:
                stats["resumed"] = 0
            stats["rechecked"] += recheck.stats_rechecked
            stats["resumed"] += recheck.stats_resumed
            stats["executed_commands"].append("recheck")
        else:
            logger.warning("Recheck Torrents operation skipped due to API errors")

    # Remove Orphaned Files
    if commands.get("rem_orphaned"):
        result = safe_execute_with_qbit_error_handling(lambda: RemoveOrphaned(qbit_manager).stats, "Remove Orphaned Files")

        if result is not None:
            if "orphaned" not in stats:
                stats["orphaned"] = 0
            stats["orphaned"] += result
            stats["executed_commands"].append("rem_orphaned")
        else:
            logger.warning("Remove Orphaned Files operation skipped due to API errors")

    # Tag NoHardLinks
    if commands.get("tag_nohardlinks"):
        if hashes is not None:
            no_hardlinks = safe_execute_with_qbit_error_handling(
                lambda: TagNoHardLinks(qbit_manager, hashes), "Tag NoHardLinks (with hashes)"
            )
        else:
            no_hardlinks = safe_execute_with_qbit_error_handling(lambda: TagNoHardLinks(qbit_manager), "Tag NoHardLinks")

        if no_hardlinks is not None:
            if "tagged_noHL" not in stats:
                stats["tagged_noHL"] = 0
            if "untagged_noHL" not in stats:
                stats["untagged_noHL"] = 0
            stats["tagged"] += no_hardlinks.stats_tagged
            stats["tagged_noHL"] += no_hardlinks.stats_tagged
            stats["untagged_noHL"] += no_hardlinks.stats_untagged
            stats["executed_commands"].append("tag_nohardlinks")
        else:
            logger.warning("Tag NoHardLinks operation skipped due to API errors")

    # Set Share Limits
    if commands.get("share_limits"):
        if hashes is not None:
            share_limits = safe_execute_with_qbit_error_handling(
                lambda: ShareLimits(qbit_manager, hashes), "Share Limits (with hashes)"
            )
        else:
            share_limits = safe_execute_with_qbit_error_handling(lambda: ShareLimits(qbit_manager), "Share Limits")

        if share_limits is not None:
            if "updated_share_limits" not in stats:
                stats["updated_share_limits"] = 0
            if "cleaned_share_limits" not in stats:
                stats["cleaned_share_limits"] = 0
            stats["tagged"] += share_limits.stats_tagged
            stats["updated_share_limits"] += share_limits.stats_tagged
            stats["deleted"] += share_limits.stats_deleted
            stats["deleted_contents"] += share_limits.stats_deleted_contents
            stats["cleaned_share_limits"] += share_limits.stats_deleted + share_limits.stats_deleted_contents
            stats["executed_commands"].append("share_limits")
        else:
            logger.warning("Share Limits operation skipped due to API errors")
