"""
Logging configuration.

Mirrors what v1 got for free from syslog: a durable, timestamped record
of watering activity you can review after the fact. Since every zone
activation -- manual or automatic -- already flows through
RelayController, logging it once there (see relay.py) covers both
without needing separate call sites in the routes or the scheduler.

Two handlers:
  - console: useful when running interactively, and automatically
    captured by systemd's journal once this runs as a service
  - a daily-rotating file: gives its own independent, greppable history
    (like v1's user.log) without needing journalctl to look back

LOG_DIR is relative to the process's working directory, matching how
config.py's DEFAULT_CONFIG_PATH already works -- both assume you're
running from the project root (~/sprinkles). The eventual systemd unit
will need WorkingDirectory set to match, for the same reason.
"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "sprinkles.log"
BACKUP_DAYS = 30  # how many rotated daily files to keep

FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        LOG_FILE, when="midnight", backupCount=BACKUP_DAYS
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)

    # uvicorn logs every HTTP request at INFO by default (its own access
    # log, separate from everything above). For a LAN appliance polled
    # every few seconds by the status page, that's pure noise -- the
    # operationally meaningful history is already fully covered by our
    # own app.* loggers. uvicorn's startup/shutdown/error messages
    # (the "uvicorn" and "uvicorn.error" loggers) are left alone.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
