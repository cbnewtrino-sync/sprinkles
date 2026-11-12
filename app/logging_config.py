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
import os
import time
from datetime import datetime, timedelta
from datetime import time as dtime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "sprinkles.log"
BACKUP_DAYS = 30  # how many rotated daily files to keep

FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class DailyRotatingFileHandler(TimedRotatingFileHandler):
    """Midnight rotation that stays correct across DST changes.

    The stdlib handler has two flaws that combine badly on the night DST
    ends (fall back), when the first record after midnight is written
    after 2 AM -- which, with a 3 AM watering schedule, is every year:

      1. doRollover() names the rotated file from rolloverAt - 86400 and
         then "corrects" by an hour if DST differs between *now* and that
         moment. On fall-back night that shifts the name back a full day,
         onto a file that already exists.
      2. Seeing that file exists, it returns early ("already rolled
         over") *without* advancing rolloverAt -- so every later record
         retries the same doomed rollover, and rotation stops for good
         until the process restarts. (Seen in production 2026-11-01.)

    The fixes: compute the next midnight with calendar arithmetic rather
    than "+86400 seconds", name the file for the wall-clock day one
    second before the rollover (always the day that just ended, no DST
    correction needed), and advance rolloverAt before any early return.
    Only valid for when="midnight", which is all this app uses.
    """

    def computeRollover(self, currentTime):
        today = datetime.fromtimestamp(currentTime).date()
        return int(datetime.combine(today + timedelta(days=1), dtime()).timestamp())

    def doRollover(self):
        day_ended = time.localtime(self.rolloverAt - 1)
        dfn = self.rotation_filename(
            f"{self.baseFilename}.{time.strftime(self.suffix, day_ended)}"
        )
        # Advance first, so nothing below can leave us retrying forever.
        self.rolloverAt = self.computeRollover(int(time.time()))
        if os.path.exists(dfn):
            return  # already rotated (e.g. a restart raced midnight)

        if self.stream:
            self.stream.close()
            self.stream = None
        self.rotate(self.baseFilename, dfn)
        if self.backupCount > 0:
            for old in self.getFilesToDelete():
                os.remove(old)
        if not self.delay:
            self.stream = self._open()


def configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = DailyRotatingFileHandler(
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
