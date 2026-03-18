from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo


def _safe_zoneinfo(tz_name: str) -> ZoneInfo:
    mapped = {
        "China Standard Time": "Asia/Shanghai",
        "UTC": "UTC",
    }.get(tz_name, tz_name)
    try:
        return ZoneInfo(mapped)
    except Exception as e:
        raise ValueError(f"invalid timezone: {tz_name}") from e


def _parse_time(time_str: str) -> tuple[int, int, int]:
    t = (time_str or "").strip()
    if not t:
        return 0, 0, 0
    parts = t.split(":")
    if len(parts) < 2:
        raise ValueError("time must be HH:MM or HH:MM:SS")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) >= 3 else 0
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
        raise ValueError("invalid time")
    return h, m, s


def to_utc_iso(date_str: str, time_str: str, tz_name: str) -> str:
    d = (date_str or "").strip()
    if not d:
        raise ValueError("date_str is required")
    year, month, day = (int(x) for x in d.split("-"))
    hh, mm, ss = _parse_time(time_str)
    tz = _safe_zoneinfo(tz_name)
    local = datetime(year, month, day, hh, mm, ss, tzinfo=tz)
    utc = local.astimezone(ZoneInfo("UTC"))
    return utc.replace(microsecond=0).isoformat(timespec="seconds")


def calculate_relative_time(target_iso: str, *, now: Optional[datetime] = None) -> str:
    base = now or datetime.now(tz=_safe_zoneinfo("UTC"))
    target = datetime.fromisoformat(target_iso.replace("Z", "+00:00"))
    if target.tzinfo is None:
        target = target.replace(tzinfo=_safe_zoneinfo("UTC"))

    delta_s = int((target - base).total_seconds())
    past = delta_s < 0
    s = abs(delta_s)

    if s < 60:
        out = f"{s}s"
    elif s < 3600:
        out = f"{s // 60}m"
    elif s < 86400:
        out = f"{s // 3600}h"
    else:
        out = f"{s // 86400}d"
    return f"{out} ago" if past else f"in {out}"
