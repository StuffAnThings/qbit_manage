import logging, traceback
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("qBit Manage")

class TimeoutExpired(Exception):
    pass

class Failed(Exception):
    pass

class NotScheduled(Exception):
    pass

separating_character = "="
screen_width = 100
spacing = 0


def print_multiline(lines, loglevel='INFO'):
    line_list = str(lines).split("\n") 
    for i, line in enumerate(line_list):
        if len(line) > 0 and i != len(line_list)-1:
            logger.log(getattr(logging, loglevel),line)
        if i == 0:
            logger.handlers[1].setFormatter(logging.Formatter(" " * 37 + "| %(message)s"))
    logger.handlers[1].setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-10s | %(message)s"))

def print_stacktrace():
    print_multiline(traceback.format_exc())

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
        logger.log(getattr(logging, loglevel),border_text)
    if text:
        text_list = text.split("\n")
        for t in text_list:
            logger.log(getattr(logging, loglevel),f"|{sep}{centered(t, sep=sep)}{sep}|")
        if border:
            logger.log(getattr(logging, loglevel),border_text)
    for handler in logger.handlers:
        apply_formatter(handler)

def apply_formatter(handler, border=True):
    text = f"| %(message)-{screen_width - 2}s |" if border else f"%(message)-{screen_width - 2}s"
    if isinstance(handler, RotatingFileHandler):
        #text = f"[%(asctime)s] %(filename)-27s %(levelname)-10s {text}"
        text = f"[%(asctime)s] %(levelname)-10s {text}"
    handler.setFormatter(logging.Formatter(text))

def adjust_space(display_title):
    display_title = str(display_title)
    space_length = spacing - len(display_title)
    if space_length > 0:
        display_title += " " * space_length
    return display_title

def insert_space(display_title,space_length=0):
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