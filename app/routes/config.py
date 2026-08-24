"""
Config editing. Every route saves immediately and re-renders the relevant
fragment from the freshly-saved file -- there's no separate 'commit'
step, and no way for the on-screen state to drift from what's on disk.
"""
from __future__ import annotations

from datetime import date, time, timedelta

from fastapi import APIRouter, Form, HTTPException, Request

from app.config import load_config, save_config
from app.templating import templates

router = APIRouter(prefix="/config")


def _render_page(request: Request):
    config = load_config()
    return templates.TemplateResponse(
        request,
        "config.html",
        {"config": config, "zones": config.zone_group, "active_nav": "config"},
    )


def _render_zone_editor(request: Request):
    config = load_config()
    return templates.TemplateResponse(
        request, "partials/zone_editor.html", {"zones": config.zone_group}
    )


def _render_settings(request: Request):
    config = load_config()
    return templates.TemplateResponse(
        request, "partials/settings.html", {"config": config}
    )


@router.get("")
async def config_page(request: Request):
    return _render_page(request)


@router.post("/zones/{zone_name}")
async def update_zone(
    zone_name: str,
    request: Request,
    enabled: bool = Form(False),  # unchecked checkboxes aren't submitted at all
    interval: int = Form(..., gt=0),
    duration: int = Form(..., gt=0),
):
    config = load_config()
    zone = next((z for z in config.zone_group if z.name == zone_name), None)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Unknown zone: {zone_name}")

    zone.enabled = enabled
    zone.interval = interval
    zone.duration = duration
    save_config(config)

    return _render_zone_editor(request)


@router.post("/settings/water-tod")
async def update_water_tod(request: Request, water_tod: time = Form(...)):
    config = load_config()
    config.water_tod = water_tod
    save_config(config)
    return _render_settings(request)


@router.post("/settings/delay")
async def set_delay(request: Request, days: int = Form(...)):
    config = load_config()
    config.delay_day = date.today() + timedelta(days=days)
    save_config(config)
    return _render_settings(request)


@router.post("/settings/delay/clear")
async def clear_delay(request: Request):
    config = load_config()
    config.delay_day = None
    save_config(config)
    return _render_settings(request)
