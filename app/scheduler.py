"""
Automatic watering scheduler.

Runs forever as a background asyncio task for the lifetime of the process
(this is not a daemon in the v1 sense -- it's one task living inside the
same process that also serves the web UI). Each pass:

  1. Figures out the next moment it needs to act: today's trigger time,
     right now if there's unfinished work from an earlier crash, or
     tomorrow's trigger time if today's cycle already completed.
  2. Sleeps until then.
  3. Builds the day's zone queue and runs it end to end.

Crash recovery falls out of this for free: "unfinished work" and "normal
daily trigger" are answered by the same due_zones() check, so there's no
separate recovery code path -- see next_trigger_time().
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from app.config import DEFAULT_CONFIG_PATH, SprinklerConfig, load_config, save_config
from app.relay import RelayController

logger = logging.getLogger(__name__)

# Real minutes in production. Tests shrink this so a "minute" takes
# milliseconds instead of actually waiting.
SECONDS_PER_MINUTE = 60


def next_trigger_time(config: SprinklerConfig, now: datetime) -> datetime:
    """When the scheduler should next wake up and act."""
    today = now.date()
    water_dt = datetime.combine(today, config.water_tod)

    if now < water_dt:
        return water_dt                                             # not time yet
    if config.due_zones(today):
        return now                                                   # crash recovery: resume now
    return datetime.combine(today + timedelta(days=1), config.water_tod)  # done for today


async def _run_daily_queue(
    config: SprinklerConfig, relay: RelayController, config_path: Path
) -> None:
    today = date.today()
    queue = config.due_zones(today)
    logger.info("Running daily queue: %s", [z.name for z in queue])

    for zone in queue:
        relay.activate(zone.name)
        await asyncio.sleep(zone.duration * SECONDS_PER_MINUTE)

        if relay.active_zone != zone.name:
            # A manual command took control mid-cycle. Defer to it: don't
            # mark this zone as run, don't touch relay state again. It's
            # still "due" so the next pass will retry it.
            logger.warning(
                "Zone %s was overridden mid-cycle; stopping today's queue", zone.name
            )
            return

        zone.last_run = today
        save_config(config, config_path)

    relay.deactivate_all()


async def run_forever(
    relay: RelayController, config_path: Path = DEFAULT_CONFIG_PATH
) -> None:
    while True:
        config = load_config(config_path)  # fresh read -- picks up web-UI edits
        now = datetime.now()
        trigger = next_trigger_time(config, now)

        # Subtract POSIX timestamps, not the naive datetimes themselves:
        # naive subtraction measures wall-clock difference, which is an
        # hour off whenever the wait spans a DST change (on 2026-11-01 it
        # woke at 02:00 instead of 03:00). .timestamp() on a naive
        # datetime goes through mktime() and honors the local zone.
        wait_seconds = trigger.timestamp() - now.timestamp()
        if wait_seconds > 0:
            logger.info("Next watering cycle at %s (%.0f min from now)", trigger, wait_seconds / 60)
            await asyncio.sleep(wait_seconds)
        else:
            logger.info("Trigger time already passed (%s) -- running due zones now", trigger)

        config = load_config(config_path)  # re-read in case it changed while sleeping
        await _run_daily_queue(config, relay, config_path)
