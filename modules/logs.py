"""Logging module"""

import io
import logging
import os
import re
import sys
import traceback
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"

CRITICAL = 50
FATAL = CRITICAL
ERROR = 40
WARNING = 30
WARN = WARNING
DRYRUN = 25
INFO = 20
DEBUG = 10
TRACE = 1


def fmt_filter(record):
    """Filter log message"""
    record.levelname = f"[{record.levelname}]"
    record.filename = f"[{record.filename}:{record.lineno}]"
    return True


_srcfile = os.path.normcase(fmt_filter.__code__.co_filename)


class MyLogger:
    """Logger class"""

    def __init__(
        self, logger_name, log_file, log_level, default_dir, screen_width, separating_character, ignore_ghost, log_size, log_count
    ):
        """Initialize logger"""
        self.logger_name = logger_name
        self.default_dir = default_dir
        self.screen_width = screen_width
        self.separating_character = separating_character
        self.ignore_ghost = ignore_ghost
        self.log_dir = os.path.join(default_dir, LOG_DIR)
        self.main_log = log_file if os.path.exists(os.path.dirname(log_file)) else os.path.join(self.log_dir, log_file)
        self.main_handler = None
        self.save_errors = False
        self.saved_errors = []
        self.config_handlers = {}
        self.secrets = set()
        self.spacing = 0
        self.log_size = log_size
        self.log_count = log_count
        os.makedirs(self.log_dir, exist_ok=True)
        self._logger = logging.getLogger(self.logger_name)
        logging.DRYRUN = DRYRUN
        logging.addLevelName(DRYRUN, "DRYRUN")
        setattr(self._logger, "dryrun", lambda dryrun, *args: self._logger._log(DRYRUN, dryrun, args))
        logging.TRACE = TRACE
        logging.addLevelName(TRACE, "TRACE")
        setattr(self._logger, "trace", lambda trace, *args: self._logger._log(TRACE, trace, args))
        self._log_level = getattr(logging, log_level.upper())
        self._logger.setLevel(self._log_level)

        cmd_handler = logging.StreamHandler()
        cmd_handler.setLevel(self._log_level)

        self._logger.addHandler(cmd_handler)

    def get_level(self):
        """Get the current log level"""
        return self._log_level

    def set_level(self, log_level):
        """Set the log level for the logger and all its handlers"""
        self._log_level = getattr(logging, log_level.upper())
        self._logger.setLevel(self._log_level)
        for handler in self._logger.handlers:
            handler.setLevel(self._log_level)

    def clear_errors(self):
        """Clear saved errors"""
        self.saved_errors = []

    def _get_handler(self, log_file):
        """Get handler for log file"""
        max_bytes = 1024 * 1024 * self.log_size
        _handler = RotatingFileHandler(
            log_file, delay=True, mode="w", maxBytes=max_bytes, backupCount=self.log_count, encoding="utf-8"
        )
        self._formatter(handler=_handler)
        return _handler

    def _formatter(self, handler=None, border=True, log_only=False, space=False):
        """Format log message"""
        console = f"| %(message)-{self.screen_width - 2}s |" if border else f"%(message)-{self.screen_width - 2}s"
        file = f"{' ' * 65}" if space else "[%(asctime)s] %(filename)-27s %(levelname)-10s "
        handlers = [handler] if handler else self._logger.handlers
        for h in handlers:
            if not log_only or isinstance(h, RotatingFileHandler):
                h.setFormatter(logging.Formatter(f"{file if isinstance(h, RotatingFileHandler) else ''}{console}"))

    def add_main_handler(self):
        """Add main handler to logger"""
        self.main_handler = self._get_handler(self.main_log)
        self.main_handler.addFilter(fmt_filter)
        self._logger.addHandler(self.main_handler)

    def remove_main_handler(self):
        """Remove main handler from logger"""
        self._logger.removeHandler(self.main_handler)

    def add_config_handler(self, config_key):
        """Add config handler to logger"""
        if config_key in self.config_handlers:
            self._logger.addHandler(self.config_handlers[config_key])
        else:
            self.config_handlers[config_key] = self._get_handler(os.path.join(self.log_dir, config_key + ".log"))
            self._logger.addHandler(self.config_handlers[config_key])

    def remove_config_handler(self, config_key):
        """Remove config handler from logger"""
        if config_key in self.config_handlers:
            self._logger.removeHandler(self.config_handlers[config_key])

    def _centered(self, text, sep=" ", side_space=True, left=False):
        """Center text"""
        if len(text) > self.screen_width - 2:
            return text
        space = self.screen_width - len(text) - 2
        text = f"{' ' if side_space else sep}{text}{' ' if side_space else sep}"
        if space % 2 == 1:
            text += sep
            space -= 1
        side = int(space / 2) - 1
        final_text = f"{text}{sep * side}{sep * side}" if left else f"{sep * side}{text}{sep * side}"
        return final_text

    def separator(self, text=None, space=True, border=True, side_space=True, left=False, loglevel="INFO"):
        """Print separator"""
        sep = " " if space else self.separating_character
        for handler in self._logger.handlers:
            self._formatter(handler, border=False)
        border_text = f"|{self.separating_character * self.screen_width}|"
        if border:
            self.print_line(border_text, loglevel)
        if text:
            text_list = text.split("\n")
            for txt in text_list:
                self.print_line(f"|{sep}{self._centered(txt, sep=sep, side_space=side_space, left=left)}{sep}|", loglevel)
            if border:
                self.print_line(border_text, loglevel)
        for handler in self._logger.handlers:
            self._formatter(handler)
        return [text]

    def print_line(self, msg, loglevel="INFO", *args, **kwargs):
        """Print line"""
        loglvl = getattr(logging, loglevel.upper())
        if self._logger.isEnabledFor(loglvl):
            self._log(loglvl, str(msg), args, **kwargs)
        return [str(msg)]

    def trace(self, msg, *args, **kwargs):
        """Print trace"""
        if self._logger.isEnabledFor(TRACE):
            self._log(TRACE, str(msg), args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """Print debug"""
        if self._logger.isEnabledFor(DEBUG):
            self._log(DEBUG, str(msg), args, **kwargs)

    def info_center(self, msg, *args, **kwargs):
        """Print info centered"""
        self.info(self._centered(str(msg)), *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """Print info"""
        if self._logger.isEnabledFor(INFO):
            self._log(INFO, str(msg), args, **kwargs)

    def dryrun(self, msg, *args, **kwargs):
        """Print dryrun"""
        if self._logger.isEnabledFor(DRYRUN):
            self._log(DRYRUN, str(msg), args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """Print warning"""
        if self._logger.isEnabledFor(WARNING):
            self._log(WARNING, str(msg), args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Print error"""
        if self.save_errors:
            self.saved_errors.append(msg)
        if self._logger.isEnabledFor(ERROR):
            self._log(ERROR, str(msg), args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """Print critical"""
        if self.save_errors:
            self.saved_errors.append(msg)
        if self._logger.isEnabledFor(CRITICAL):
            self._log(CRITICAL, str(msg), args, **kwargs)

    def stacktrace(self):
        """Print stacktrace"""
        self.debug(traceback.format_exc())

    def _space(self, display_title):
        """Add spaces to display title"""
        display_title = str(display_title)
        space_length = self.spacing - len(display_title)
        if space_length > 0:
            display_title += " " * space_length
        return display_title

    def ghost(self, text):
        """Print ghost"""
        if not self.ignore_ghost:
            try:
                final_text = f"| {text}"
            except UnicodeEncodeError:
                text = text.encode("utf-8")
                final_text = f"| {text}"
            print(self._space(final_text), end="\r")
            self.spacing = len(text) + 2

    def exorcise(self):
        """Exorcise ghost"""
        if not self.ignore_ghost:
            print(self._space(" "), end="\r")
            self.spacing = 0

    def secret(self, text):
        """Add secret"""
        if str(text) not in self.secrets and str(text):
            self.secrets.add(str(text))

    def insert_space(self, display_title, space_length=0):
        """Insert space"""
        display_title = str(display_title)
        if space_length == 0:
            space_length = self.spacing - len(display_title)
        if space_length > 0:
            display_title = " " * space_length + display_title
        return display_title

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        """Log"""
        log_only = False
        if self.spacing > 0:
            self.exorcise()
        if "\n" in msg:
            for i, line in enumerate(msg.split("\n")):
                self._log(level, line, args, exc_info=exc_info, extra=extra, stack_info=stack_info, stacklevel=stacklevel)
                if i == 0:
                    self._formatter(log_only=True, space=True)
            log_only = True
        else:
            for secret in sorted(self.secrets, reverse=True):
                if secret in msg:
                    msg = msg.replace(secret, "(redacted)")
            if "HTTPConnectionPool" in msg:
                msg = re.sub("HTTPConnectionPool\\((.*?)\\)", "HTTPConnectionPool(redacted)", msg)
            if "HTTPSConnectionPool" in msg:
                msg = re.sub("HTTPSConnectionPool\\((.*?)\\)", "HTTPSConnectionPool(redacted)", msg)
            try:
                if not _srcfile:
                    raise ValueError
                func, lno, func, sinfo = self.find_caller(stack_info, stacklevel)
            except ValueError:
                func, lno, func, sinfo = "(unknown file)", 0, "(unknown function)", None
            if exc_info:
                if isinstance(exc_info, BaseException):
                    exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
                elif not isinstance(exc_info, tuple):
                    exc_info = sys.exc_info()
            record = self._logger.makeRecord(self._logger.name, level, func, lno, msg, args, exc_info, func, extra, sinfo)
            self._logger.handle(record)
        if log_only:
            self._formatter()

    def find_caller(self, stack_info=False, stacklevel=1):
        """Find caller"""
        frm = logging.currentframe()
        if frm is not None:
            frm = frm.f_back
        orig_f = frm
        while frm and stacklevel > 1:
            frm = frm.f_back
            stacklevel -= 1
        if not frm:
            frm = orig_f
        rvf = "(unknown file)", 0, "(unknown function)", None
        while hasattr(frm, "f_code"):
            code = frm.f_code
            filename = os.path.normcase(code.co_filename)
            if filename == _srcfile:
                frm = frm.f_back
                continue
            sinfo = None
            if stack_info:
                sio = io.StringIO()
                sio.write("Stack (most recent call last):\n")
                traceback.print_stack(frm, file=sio)
                sinfo = sio.getvalue()
                if sinfo[-1] == "\n":
                    sinfo = sinfo[:-1]
                sio.close()
            rvf = (code.co_filename, frm.f_lineno, code.co_name, sinfo)
            break
        return rvf
