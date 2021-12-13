import logging, os, shutil, traceback, time, signal
from logging.handlers import RotatingFileHandler
from ruamel import yaml
from pathlib import Path

logger = logging.getLogger('qBit Manage')

def get_list(data, lower=False, split=True, int_list=False):
    if data is None:                return None
    elif isinstance(data, list):    return data
    elif isinstance(data, dict):    return [data]
    elif split is False:            return [str(data)]
    elif lower is True:             return [d.strip().lower() for d in str(data).split(",")]
    elif int_list is True:
        try:                            return [int(d.strip()) for d in str(data).split(",")]
        except ValueError:              return []
    else:                           return [d.strip() for d in str(data).split(",")]

class check:
    def __init__(self, config):
        self.config = config

    def check_for_attribute(self, data, attribute, parent=None, subparent=None, test_list=None, default=None, do_print=True, default_is_none=False, req_default=False, var_type="str", default_int=0, throw=False, save=True):
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
                    #save = False

        if subparent is not None:
            text = f"{parent}->{subparent} sub-attribute {attribute}"
        elif parent is None:
            text = f"{attribute} attribute"
        else:
            text = f"{parent} sub-attribute {attribute}"

        if data is None or attribute not in data:
            message = f"{text} not found"
            if parent and save is True:
                loaded_config, _, _ = yaml.util.load_yaml_guess_indent(open(self.config.config_path))
                if subparent:
                    endline = f"\n{subparent} sub-attribute {attribute} added to config"
                    if subparent not in loaded_config[parent] or not loaded_config[parent][subparent]:
                        loaded_config[parent][subparent] = {attribute: default}
                    elif attribute not in loaded_config[parent]:
                        loaded_config[parent][subparent][attribute] = default
                    else:
                        endline = ""
                else:
                    endline = f"\n{parent} sub-attribute {attribute} added to config"
                    if parent not in loaded_config or not loaded_config[parent]:
                        loaded_config[parent] = {attribute: default}
                    elif attribute not in loaded_config[parent]:
                        loaded_config[parent][attribute] = default
                    else:
                        endline = ""
                yaml.round_trip_dump(loaded_config, open(self.config.config_path, "w"), indent=None, block_seq_indent=2)
            if default_is_none and var_type in ["list", "int_list"]:            return []
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
                return os.path.join(data[attribute],'')
            else:
                message = f"Path {os.path.abspath(data[attribute])} does not exist"
        elif var_type == "list":
            return get_list(data[attribute], split=False)
        elif var_type == "list_path":
            temp_list = [p for p in get_list(
                data[attribute], split=False) if os.path.exists(os.path.abspath(p))]
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
            return os.path.join(default,'')
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
            raise Failed(
                f"Config Error: {attribute} attribute must be set under {parent}.")
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
            print_multiline(f"Config Warning: {message}", "warning")
            if data and attribute in data and data[attribute] and test_list is not None and data[attribute] not in test_list:
                print_multiline(options)
        return default
class Failed(Exception):
    pass

separating_character = "="
screen_width = 100
spacing = 0

def add_dict_list(keys, value, dict_map):
    for key in keys:
        if key in dict_map:
            dict_map[key].append(value)
        else:
            dict_map[key] = [value]

def get_int_list(data, id_type):
    int_values = []
    for value in get_list(data):
        try:                        int_values.append(regex_first_int(value, id_type))
        except Failed as e:         logger.error(e)
    return int_values

def print_line(lines, loglevel='INFO'):
    logger.log(getattr(logging, loglevel.upper()), str(lines))

def print_multiline(lines, loglevel='INFO'):
    for i, line in enumerate(str(lines).split("\n")):
        logger.log(getattr(logging, loglevel.upper()), line)
        if i == 0:
            logger.handlers[1].setFormatter(logging.Formatter(" " * 65 + "| %(message)s"))
    logger.handlers[1].setFormatter(logging.Formatter("[%(asctime)s] %(filename)-27s %(levelname)-10s | %(message)s"))

def print_stacktrace():
    print_multiline(traceback.format_exc(), 'CRITICAL')

def my_except_hook(exctype, value, tb):
    for line in traceback.format_exception(etype=exctype, value=value, tb=tb):
        print_multiline(line, 'CRITICAL')

def centered(text, sep=" "):
    if len(text) > screen_width - 2:
        return text
    space = screen_width - len(text) - 2
    text = f" {text} "
    if space % 2 == 1:
        text += sep
        space -= 1
    side = int(space / 2) - 1
    final_text = f"{sep * side}{text}{sep * side}"
    return final_text

def separator(text=None, space=True, border=True, loglevel='INFO'):
    sep = " " if space else separating_character
    for handler in logger.handlers:
        apply_formatter(handler, border=False)
    border_text = f"|{separating_character * screen_width}|"
    if border:
        logger.log(getattr(logging, loglevel.upper()), border_text)
    if text:
        text_list = text.split("\n")
        for t in text_list:
            logger.log(getattr(logging, loglevel.upper()),
                       f"|{sep}{centered(t, sep=sep)}{sep}|")
        if border:
            logger.log(getattr(logging, loglevel.upper()), border_text)
    for handler in logger.handlers:
        apply_formatter(handler)

def apply_formatter(handler, border=True):
    text = f"| %(message)-{screen_width - 2}s |" if border else f"%(message)-{screen_width - 2}s"
    if isinstance(handler, RotatingFileHandler):
        text = f"[%(asctime)s] %(filename)-27s %(levelname)-10s {text}"
        #text = f"[%(asctime)s] %(levelname)-10s {text}"
    handler.setFormatter(logging.Formatter(text))

def adjust_space(display_title):
    display_title = str(display_title)
    space_length = spacing - len(display_title)
    if space_length > 0:
        display_title += " " * space_length
    return display_title

def insert_space(display_title, space_length=0):
    display_title = str(display_title)
    if space_length == 0:
        space_length = spacing - len(display_title)
    if space_length > 0:
        display_title = " " * space_length + display_title
    return display_title

def print_return(text):
    print(adjust_space(f"| {text}"), end="\r")
    global spacing
    spacing = len(text) + 2

def print_end():
    print(adjust_space(" "), end="\r")
    global spacing
    spacing = 0

# truncate the value of the torrent url to remove sensitive information
def trunc_val(s, d, n=3):
    return d.join(s.split(d, n)[:n])

# Move files from source to destination, mod variable is to change the date modified of the file being moved
def move_files(src, dest, mod=False):
    dest_path = os.path.dirname(dest)
    if os.path.isdir(dest_path) == False:
        os.makedirs(dest_path)
    shutil.move(src, dest)
    if mod == True:
        modTime = time.time()
        os.utime(dest, (modTime, modTime))

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

#will check if there are any hard links if it passes a file or folder
def nohardlink(file):
    check = True
    if (os.path.isfile(file)):
        if (os.stat(file).st_nlink > 1):
            check = False
    else:
        for path, subdirs, files in os.walk(file):
            for x in files:
                if (os.stat(os.path.join(path,x)).st_nlink > 1):
                    check = False
    return check

#Gracefully kill script when docker stops
class GracefulKiller:
  kill_now = False
  def __init__(self):
    #signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)
  def exit_gracefully(self, *args):
    self.kill_now = True