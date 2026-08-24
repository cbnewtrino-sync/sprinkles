"""
Hardware interface for sprinkler valve relays.

The relay board is controlled over I2C, not GPIO. Each zone's "pin" value
from config is actually an I2C register address on the relay board (this
is what the v1 C++ code passed to wiringPiI2CWriteReg8()) -- writing 0xFF
turns that relay on, 0x00 turns it off. There's no GPIO pin mapping to get
right here, which removes a whole category of risk we'd otherwise have
had to verify against v1's source.

All I2C access for zone control goes through this module -- same design
principle as v1's isolated relay class. Centralizing it here gives us two
guarantees for free, enforced in one place instead of duplicated at every
call site:

  1. Only one zone valve is ever open at a time (v1's rule, preserved).
  2. No zone can stay open longer than MAX_RUNTIME_MINUTES, regardless of
     what asked for it, as a hard safety net independent of the scheduler.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from smbus2 import SMBus

logger = logging.getLogger(__name__)

I2C_BUS = 1         # the standard I2C bus exposed on the Pi's 40-pin header
I2C_ADDRESS = 0x10  # relay board address, set by onboard DIP switches
                    # (all switches off = 0x10, the default -- this is
                    # what lets up to 4 boards be stacked with distinct
                    # addresses; we only have the one board)

RELAY_ON = 0xFF
RELAY_OFF = 0x00

MAX_RUNTIME_MINUTES = 60  # hard cap, independent of any configured duration


class I2CBus(Protocol):
    """The one method we actually use from smbus2.SMBus -- named as a
    Protocol so tests can substitute a fake bus without touching real
    hardware, the same way the mock pin factory let us test GPIO before."""

    def write_byte_data(self, i2c_addr: int, register: int, value: int) -> None: ...


class RelayController:
    """Owns the I2C relay board and enforces 'one zone open at a time'."""

    def __init__(self, zone_pins: dict[str, int], bus: I2CBus | None = None):
        """zone_pins: {zone_name: config pin number}. Here "pin" doubles
        as the I2C register address for that zone's relay."""
        self._zone_pins = dict(zone_pins)
        self._bus: I2CBus = bus if bus is not None else SMBus(I2C_BUS)
        self._active_zone: str | None = None
        self._watchdog: asyncio.Task | None = None

    @property
    def active_zone(self) -> str | None:
        return self._active_zone

    def activate(self, zone_name: str) -> None:
        """Open the given zone's valve, closing any other zone first."""
        if zone_name not in self._zone_pins:
            raise ValueError(f"Unknown zone: {zone_name}")

        self.deactivate_all()

        register = self._zone_pins[zone_name]
        self._bus.write_byte_data(I2C_ADDRESS, register, RELAY_ON)
        self._active_zone = zone_name
        logger.info("Zone %s activated", zone_name)

        self._watchdog = asyncio.create_task(self._auto_shutoff(zone_name))

    def deactivate_all(self) -> None:
        """Close every valve. Safe to call any time, including at startup
        (this is what makes the crash/power-loss recovery story work)."""
        current = asyncio.current_task()
        if self._watchdog is not None and self._watchdog is not current:
            self._watchdog.cancel()
        self._watchdog = None

        for register in self._zone_pins.values():
            self._bus.write_byte_data(I2C_ADDRESS, register, RELAY_OFF)

        if self._active_zone is not None:
            logger.info("Zone %s deactivated", self._active_zone)
        self._active_zone = None

    async def _auto_shutoff(self, zone_name: str) -> None:
        """Safety net: force this zone off if it's still running after
        MAX_RUNTIME_MINUTES, no matter what asked for it to run that long."""
        await asyncio.sleep(MAX_RUNTIME_MINUTES * 60)
        if self._active_zone == zone_name:
            logger.warning(
                "Zone %s exceeded max runtime (%d min) - forcing off",
                zone_name, MAX_RUNTIME_MINUTES,
            )
            self.deactivate_all()
