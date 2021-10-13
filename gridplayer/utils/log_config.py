import logging
import logging.config
import logging.handlers
import multiprocessing
import sys
import time
from random import random

from PyQt5 import QtCore

DISABLED = logging.CRITICAL + 1


class QueueListenerRoot(logging.handlers.QueueListener):
    def __init__(self, queue):
        super().__init__(queue, *logging.root.handlers, respect_handler_level=True)

    def handle(self, record):
        record = self.prepare(record)

        if record.levelno < logging.root.level:
            return

        for handler in self.handlers:
            if not self.respect_handler_level:
                process = True
            else:
                process = record.levelno >= handler.level
            if process:
                handler.handle(record)


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
        pass


class QtLogHandler:
    log_level_map = {
        QtCore.QtDebugMsg: logging.DEBUG,
        QtCore.QtInfoMsg: logging.INFO,
        QtCore.QtWarningMsg: logging.WARNING,
        QtCore.QtCriticalMsg: logging.ERROR,
        QtCore.QtFatalMsg: logging.CRITICAL,
    }

    def __init__(self):
        self._logger = logging.getLogger("QT")

    def handle(self, mode, context, message):
        log_level = self.log_level_map[mode]

        if context.file is not None:
            log_msg_head = (
                f"qt_message_handler: line: {context.line},"
                f" func: {context.function},"
                f" file: {context.file}"
            )

            self._logger.log(log_level, log_msg_head)

        self._logger.log(log_level, message.strip())


def config_log(log_path, log_level):
    config = {
        "version": 1,
        "formatters": {
            # Modify log message format here or replace with your custom formatter class
            "my_formatter": {
                "format": "%(asctime)s (%(process)d) | %(name)s | %(levelname)s | %(message)s"
            }
        },
        "handlers": {
            "console_stderr": {
                # Sends log messages to stderr
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "my_formatter",
                "stream": sys.__stderr__,
            },
            "file": {
                # Sends all log messages to a file
                "class": "logging.FileHandler",
                "level": "DEBUG",
                "formatter": "my_formatter",
                "filename": log_path,
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

    logging.config.dictConfig(config)


def set_root_level(log_level):
    logging.root.setLevel(log_level)


def override_stdout():
    stdout_logger = logging.getLogger("STDOUT")
    sys.stdout = StreamToLogger(stdout_logger, logging.INFO)

    stderr_logger = logging.getLogger("STDERR")
    sys.stderr = StreamToLogger(stderr_logger, logging.ERROR)


def child_process_config(queue, log_level):
    # for h in logging.root.handlers[:]:
    #     logging.root.removeHandler(h)
    #     h.close()

    h = logging.handlers.QueueHandler(queue)
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(log_level)

    override_stdout()
