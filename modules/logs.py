"""Logging module"""

import io
import json
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


def rotated_log_name(default_name):
    """Keep the original extension after the rotation number."""
    base_name, separator, rotation = default_name.rpartition(".")
    stem, extension = os.path.splitext(base_name)
    if not separator or not rotation.isdigit() or not extension:
        return default_name
    return f"{stem}.{rotation}{extension}"


def canonical_log_name(log_file):
    """Return the canonical text-log filename for any configured name."""
    stem, _ = os.path.splitext(log_file)
    return f"{stem}.txt"


def _write_combined_log(source_files, destination):
    """Combine oldest-to-newest log files into one retained archive."""
    temporary = f"{destination}.migrating-{os.getpid()}"
    suffix = 0
    while os.path.exists(temporary):
        suffix += 1
        temporary = f"{destination}.migrating-{os.getpid()}-{suffix}"
    try:
        with open(temporary, "wb") as output:
            for source_file in source_files:
                with open(source_file, "rb") as source:
                    data = source.read()
                output.write(data)
                if data and not data.endswith(b"\n"):
                    output.write(b"\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def migrate_rotated_logs(log_file, backup_count):
    """Normalize one log stem while preserving order and retention."""
    canonical_name = canonical_log_name(log_file)
    stem, _ = os.path.splitext(canonical_name)
    legacy_active = f"{stem}.log"
    archive_files = []
    migration_needed = os.path.isfile(legacy_active)

    if os.path.isfile(legacy_active):
        if not os.path.exists(canonical_name):
            os.replace(legacy_active, canonical_name)
        else:
            archive_files.append((1, 0, legacy_active))

    directory = os.path.dirname(canonical_name) or "."
    stem_name = os.path.basename(stem)
    archive_pattern = re.compile(
        rf"^{re.escape(stem_name)}(?:(?:\.log\.(?P<suffix_rotation>\d+))|(?:\.(?P<prefix_rotation>\d+)\.log)|"
        rf"(?:\.txt\.(?P<txt_rotation>\d+))|(?:\.(?P<canonical_rotation>\d+)\.txt))$"
    )
    for filename in os.listdir(directory):
        match = archive_pattern.fullmatch(filename)
        if not match:
            continue
        rotation = int(next(value for value in match.groupdict().values() if value is not None))
        if match.group("canonical_rotation") is None:
            migration_needed = True
        archive_files.append((rotation, 1, os.path.join(directory, filename)))

    if not migration_needed:
        return

    ordered_archives = sorted(archive_files, key=lambda item: (item[0], item[1], -os.stat(item[2]).st_mtime_ns, item[2]))
    staged_archives = []
    for index, (_, _, archive_name) in enumerate(ordered_archives):
        temporary = f"{stem}.migrating-{os.getpid()}-{index}"
        suffix = 0
        while os.path.exists(temporary):
            suffix += 1
            temporary = f"{stem}.migrating-{os.getpid()}-{index}-{suffix}"
        os.replace(archive_name, temporary)
        staged_archives.append(temporary)

    if backup_count <= 0 and staged_archives:
        sources = list(reversed(staged_archives))
        if os.path.isfile(canonical_name):
            sources.append(canonical_name)
        _write_combined_log(sources, canonical_name)
        for source in staged_archives:
            os.remove(source)
        return

    retained = staged_archives[: max(backup_count - 1, 0)]
    overflow = staged_archives[len(retained) :]
    for rotation, staged_name in enumerate(retained, start=1):
        os.replace(staged_name, f"{stem}.{rotation}.txt")
    if overflow:
        oldest_rotation = len(retained) + 1
        destination = f"{stem}.{oldest_rotation}.txt"
        if len(overflow) == 1:
            os.replace(overflow[0], destination)
        else:
            _write_combined_log(list(reversed(overflow)), destination)
            for source in overflow:
                os.remove(source)


def migrate_log_directory(log_dir, backup_count):
    """Migrate every legacy log stem in the configured logs directory."""
    legacy_patterns = (
        re.compile(r"^(?P<stem>.+)\.log\.\d+$"),
        re.compile(r"^(?P<stem>.+)\.\d+\.log$"),
        re.compile(r"^(?P<stem>.+)\.txt\.\d+$"),
        re.compile(r"^(?P<stem>.+)\.log$"),
    )
    stems = set()
    for filename in os.listdir(log_dir):
        for pattern in legacy_patterns:
            match = pattern.fullmatch(filename)
            if match:
                stems.add(match.group("stem"))
                break
    for stem in sorted(stems):
        migrate_rotated_logs(os.path.join(log_dir, f"{stem}.txt"), backup_count)


def fmt_filter(record):
    """Filter log message"""
    record.levelname = f"[{record.levelname}]"
    record.filename = f"[{record.filename}:{record.lineno}]"
    return True


_srcfile = os.path.normcase(fmt_filter.__code__.co_filename)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record (used when log_format='json')."""

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname.strip("[]"),
            "logger": record.name,
            "source": f"{os.path.basename(record.pathname)}:{record.lineno}",
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class MyLogger:
    """Logger class"""

    def __init__(
        self,
        logger_name,
        log_file,
        log_level,
        default_dir,
        screen_width,
        separating_character,
        ignore_ghost,
        log_size,
        log_count,
        log_format="text",
    ):
        """Initialize logger"""
        self.logger_name = logger_name
        self.default_dir = default_dir
        self.screen_width = screen_width
        self.separating_character = separating_character
        self.ignore_ghost = ignore_ghost
        self.log_dir = os.path.join(default_dir, LOG_DIR)
        configured_log = log_file if os.path.exists(os.path.dirname(log_file)) else os.path.join(self.log_dir, log_file)
        self.main_log = canonical_log_name(configured_log)
        self.main_handler = None
        self.save_errors = False
        self.saved_errors = []
        self.config_handlers = {}
        self.secrets = set()
        self.spacing = 0
        self.log_size = log_size
        self.log_count = log_count
        self.log_format = log_format
        os.makedirs(self.log_dir, exist_ok=True)
        migrate_log_directory(self.log_dir, self.log_count)
        if os.path.dirname(self.main_log) != self.log_dir:
            migrate_rotated_logs(self.main_log, self.log_count)
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
        self._formatter(handler=cmd_handler)

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
        log_file = canonical_log_name(log_file)
        max_bytes = 1024 * 1024 * self.log_size
        migrate_rotated_logs(log_file, self.log_count)
        _handler = RotatingFileHandler(
            log_file, delay=True, mode="w", maxBytes=max_bytes, backupCount=self.log_count, encoding="utf-8"
        )
        _handler.namer = rotated_log_name
        self._formatter(handler=_handler)
        return _handler

    def _formatter(self, handler=None, border=True, log_only=False, space=False):
        """Format log message"""
        handlers = [handler] if handler else self._logger.handlers
        if self.log_format == "json":
            for h in handlers:
                h.setFormatter(JsonFormatter())
            return
        console = f"| %(message)-{self.screen_width - 2}s |" if border else f"%(message)-{self.screen_width - 2}s"
        file = f"{' ' * 65}" if space else "[%(asctime)s] %(filename)-27s %(levelname)-10s "
        for h in handlers:
            if not log_only or isinstance(h, RotatingFileHandler):
                h.setFormatter(logging.Formatter(f"{file if isinstance(h, RotatingFileHandler) else ''}{console}"))

    def add_main_handler(self):
        """Add main handler to logger"""
        self.main_handler = self._get_handler(self.main_log)
        if self.log_format != "json":
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
            self.config_handlers[config_key] = self._get_handler(os.path.join(self.log_dir, config_key + ".txt"))
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
        if self.log_format == "json":
            if text:
                for txt in str(text).split("\n"):
                    self.print_line(txt, loglevel)
            return [text]
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
        if self.ignore_ghost or self.log_format == "json":
            return
        try:
            final_text = f"| {text}"
        except UnicodeEncodeError:
            text = text.encode("utf-8")
            final_text = f"| {text}"
        print(self._space(final_text), end="\r")
        self.spacing = len(text) + 2

    def exorcise(self):
        """Exorcise ghost"""
        if self.ignore_ghost or self.log_format == "json":
            return
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
        if "\n" in msg and self.log_format != "json":
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
                pathname, lno, func_name, sinfo = self.find_caller(stack_info, stacklevel)
            except ValueError:
                pathname, lno, func_name, sinfo = "(unknown file)", 0, "(unknown function)", None
            if exc_info:
                if isinstance(exc_info, BaseException):
                    exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
                elif not isinstance(exc_info, tuple):
                    exc_info = sys.exc_info()
            record = self._logger.makeRecord(
                self._logger.name, level, pathname, lno, msg, args, exc_info, func_name, extra, sinfo
            )
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
