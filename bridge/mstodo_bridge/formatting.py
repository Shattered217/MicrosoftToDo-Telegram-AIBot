"""Time formatting helpers for ESP32 bridge."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

# Shanghai = UTC+8
_SHANGHAI_TZ = timezone(timedelta(hours=8))


def iso_to_date(iso_str: str | None) -> str:
    """Convert ISO datetime to YYYY-MM-DD date string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_SHANGHAI_TZ).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str


def iso_to_shanghai_minute(iso_str: str | None) -> str:
    """Convert ISO datetime to 'YYYY-MM-DD HH:MM' in Shanghai timezone."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str
