"""
Sprinkler system configuration: schema, loading, and persistence.

This replaces v1's config file semantics, with two intentional changes:

1. Dates are stored as ISO 8601 (YYYY-MM-DD) instead of MM/DD/YYYY.
   Unambiguous, sorts correctly as a plain string, and is what Python's
   stdlib expects natively -- no custom parsing needed. waterTOD ("03:00")
   was already ISO-compatible and needs no change.

2. The top-level "mode" field is gone. In v1 it existed so the daemon
   could report live status to a separate CLI process via file/socket.
   In v2 everything's one process, so "what's happening right now" is
   just in-memory state (owned by the scheduler), not something that
   needs to be written to disk on every transition. This file holds
   *desired* configuration only -- not runtime status.
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

from pydantic import BaseModel, Field


class Zone(BaseModel):
    name: str
    enabled: bool
    pin: int                                   # I2C register address on the relay board
    interval: int = Field(gt=0)                 # minimum days between auto runs
    duration: int = Field(gt=0)                 # minutes to run
    last_run: date | None = Field(default=None, alias="lastRun")

    model_config = {"populate_by_name": True, "validate_assignment": True}

    def is_due(self, today: date) -> bool:
        """Enabled, and either never run or at/past its interval --
        interval=1 means "every day", interval=3 means "every 3rd day"."""
        if not self.enabled:
            return False
        if self.last_run is None:
            return True
        return (today - self.last_run).days >= self.interval


class SprinklerConfig(BaseModel):
    water_tod: time = Field(alias="waterTOD")
    delay_day: date | None = Field(default=None, alias="delayDay")
    zone_group: list[Zone] = Field(alias="zoneGroup")

    model_config = {"populate_by_name": True, "validate_assignment": True}

    def is_delayed(self, today: date) -> bool:
        return self.delay_day is not None and today <= self.delay_day

    def due_zones(self, today: date) -> list[Zone]:
        """Zones eligible for today's automatic cycle, in config order."""
        if self.is_delayed(today):
            return []
        return [z for z in self.zone_group if z.is_due(today)]


DEFAULT_CONFIG_PATH = Path("sprinkles-config.json")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> SprinklerConfig:
    return SprinklerConfig.model_validate_json(path.read_text())


def save_config(config: SprinklerConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Writes immediately -- called synchronously after any zone completes,
    or any web-UI edit, so the file on disk always reflects reality."""
    path.write_text(config.model_dump_json(by_alias=True, indent=2))
