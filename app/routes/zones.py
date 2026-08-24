"""
Manual zone control. Every route here returns the same HTML fragment
(the rendered zone list) so that whether the browser gets here by polling
or by clicking a button, the page always reflects the true current state
of the relay controller -- there's no separate "client-side state" to get
out of sync.
"""
from fastapi import APIRouter, HTTPException, Request

from app.config import load_config
from app.templating import templates

router = APIRouter(prefix="/zones")


def _render_zone_list(request: Request):
    relay = request.app.state.relay
    config = load_config()
    return templates.TemplateResponse(
        request,
        "partials/zone_list.html",
        {"zones": config.zone_group, "active_zone": relay.active_zone},
    )


@router.get("/list")
async def list_zones(request: Request):
    """Polled every 5s by the page so it reflects automatic activity too,
    not just manual actions taken from this browser."""
    return _render_zone_list(request)


@router.post("/{zone_name}/on")
async def turn_on(zone_name: str, request: Request):
    config = load_config()
    if zone_name not in {z.name for z in config.zone_group}:
        raise HTTPException(status_code=404, detail=f"Unknown zone: {zone_name}")

    request.app.state.relay.activate(zone_name)
    return _render_zone_list(request)


@router.post("/off")
async def turn_off(request: Request):
    request.app.state.relay.deactivate_all()
    return _render_zone_list(request)
