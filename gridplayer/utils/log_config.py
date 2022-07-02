import logging
import sys
from logging.config import dictConfig
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore

DISABLED = logging.CRITICAL + 1


class QueueListenerRoot(QueueListener):
    def __init__(self, queue):
        super().__init__(queue, *logging.root.handlers, respect_handler_level=True)

    def handle(self, record):
        if record.levelno < logging.root.level:
            return

        super().handle(record)


class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        """Not used"""

    def isatty(self):
        return False


class QtLogHandler(object):
    log_level_map = {
        QtCore.QtDebugMsg: logging.DEBUG,
        QtCore.QtInfoMsg: logging.INFO,
        QtCore.QtWarningMsg: logging.WARNING,
        QtCore.QtCriticalMsg: logging.ERROR,
        QtCore.QtFatalMsg: logging.CRITICAL,
    }

    def __init__(self):
        self._log = logging.getLogger("QT")

    def handle(self, mode, context, message):
        log_level = self.log_level_map[mode]

        if context.file is not None:
            log_msg_head = (
                f"qt_message_handler: line: {context.line},"
                f" func: {context.function},"
                f" file: {context.file}"
            )

            self._log.log(log_level, log_msg_head)

        self._log.log(log_level, message.strip())


def config_log(
    log_path: Path,
    log_level: int,
    max_log_size: Optional[int] = None,
    max_log_backups: Optional[int] = None,
):
    config = {
        "version": 1,
        "formatters": {
            # Modify log message format here or replace with your custom formatter class
            "my_formatter": {
                "format": "%(asctime)s (%(process)d) | %(name)s |"  # noqa: WPS323
                " %(levelname)s | %(message)s"
            }
        },
        "handlers": {
            "console_stderr": {
                # Sends log messages to stderr
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "my_formatter",
                "stream": sys.__stderr__,  # noqa: WPS609
            },
            "file": {
                # Sends all log messages to a file
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "my_formatter",
                "filename": str(log_path),
                "encoding": "utf8",
            },
        },
        "root": {
            # In general, this should be kept at 'NOTSET'.
            # Otherwise it would interfere with the log levels set for each handler.
            "level": log_level,
            "handlers": ["console_stderr", "file"],
        },
    }

    if max_log_size is not None and max_log_backups is not None:
        config["handlers"]["file"]["class"] = "logging.handlers.RotatingFileHandler"
        config["handlers"]["file"]["maxBytes"] = max_log_size
        config["handlers"]["file"]["backupCount"] = max_log_backups

    dictConfig(config)


def set_root_level(log_level):
    logging.root.setLevel(log_level)


def child_process_config(queue, log_level):
    h = QueueHandler(queue)

    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(log_level)
