from fastapi import APIRouter, Request

from app.config import load_config
from app.templating import templates

router = APIRouter()


@router.get("/")
async def index(request: Request):
    relay = request.app.state.relay
    config = load_config()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"zones": config.zone_group, "active_zone": relay.active_zone, "active_nav": "status"},
    )
