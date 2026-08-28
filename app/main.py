"""
FastAPI application entrypoint.

Owns process startup/shutdown. The lifespan hook forces every relay off
before anything else happens -- this single line is what converts both
"crashed mid-cycle" and "power came back after an outage" into the same
safe, known state (see relay.py and scheduler.py for the reasoning).

It then launches the scheduler as a background asyncio task that lives
for as long as this process does. There's no separate daemon process --
systemd manages this one process the way it managed the v1 daemon.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import load_config
from app.logging_config import configure_logging
from app.relay import RelayController
from app.routes import config as config_routes
from app.routes import log as log_routes
from app.routes import pages, zones
from app.scheduler import run_forever

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    zone_pins = {z.name: z.pin for z in config.zone_group}
    relay = RelayController(zone_pins)

    # Safety: no matter how we got here (fresh boot, systemd restart after
    # a crash, manual restart), start from a known-closed state.
    relay.deactivate_all()

    app.state.relay = relay
    app.state.scheduler_task = asyncio.create_task(run_forever(relay))
    logger.info("Sprinkles started, scheduler running")

    yield

    app.state.scheduler_task.cancel()
    relay.deactivate_all()
    logger.info("Sprinkles shutting down, all relays closed")


app = FastAPI(title="Sprinkles", lifespan=lifespan)
app.include_router(pages.router)
app.include_router(zones.router)
app.include_router(config_routes.router)
app.include_router(log_routes.router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok", "active_zone": app.state.relay.active_zone}
