"""
Log viewing. Reads directly from the same files logging_config.py writes
-- no separate log storage, no duplication. Today's entries live in the
active file (no suffix); prior days live in files the handler
rotates to at midnight, suffixed with the date of the content they hold
(DailyRotatingFileHandler names each file for the day that just ended,
not the moment rollover happened to fire).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request

from app.logging_config import LOG_FILE
from app.templating import templates

router = APIRouter(prefix="/log")

DAYS_TO_SHOW = 5


def _log_path_for(day: date):
    if day == date.today():
        return LOG_FILE
    return LOG_FILE.with_name(f"{LOG_FILE.name}.{day.isoformat()}")


def _read_day(day: date) -> str | None:
    """Contents for that day, or None if there's nothing to show (file
    doesn't exist yet, or exists but is empty)."""
    path = _log_path_for(day)
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    return text if text.strip() else None


def _last_n_days(n: int) -> list[date]:
    today = date.today()
    return [today - timedelta(days=i) for i in range(n)]


@router.get("")
async def log_page(request: Request):
    today = date.today()
    return templates.TemplateResponse(
        request,
        "log.html",
        {
            "days": _last_n_days(DAYS_TO_SHOW),
            "selected_day": today,
            "day": today,
            "content": _read_day(today),
            "active_nav": "log",
        },
    )


@router.get("/day/{iso_date}")
async def log_day(iso_date: str, request: Request):
    try:
        day = date.fromisoformat(iso_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date")

    return templates.TemplateResponse(
        request,
        "partials/log_panel.html",
        {
            "days": _last_n_days(DAYS_TO_SHOW),
            "selected_day": day,
            "day": day,
            "content": _read_day(day),
        },
    )
