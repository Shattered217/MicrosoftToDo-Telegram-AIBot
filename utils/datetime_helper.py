"""
时间处理模块

该模块提供时间计算和API格式化功能：
- 绝对时间计算（days天后的hours点minutes分）
- 时区转换
- API格式化

设计原则：
- hours 统一为绝对时间（0-23点），不做相对偏移
- AI 在 Prompt 阶段算好具体几点，本模块只做日期偏移 + 绝对时间拼接
- 所有函数返回明确的类型，不做隐式转换
"""

import logging
from datetime import datetime, timedelta
from typing import Tuple
import pytz

logger = logging.getLogger(__name__)


def to_utc_iso(local_date: str, local_time: str, timezone: str) -> str:
    """
    将本地日期时间转换为UTC ISO格式
    
    Args:
        local_date: 本地日期 (YYYY-MM-DD)
        local_time: 本地时间 (HH:MM)
        timezone: 时区字符串 (例如: 'Asia/Shanghai')
        
    Returns:
        UTC时间的ISO格式字符串 (YYYY-MM-DDTHH:MM:SS.000Z)
    """
    try:
        dt_str = f"{local_date} {local_time}"
        local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        
        local_tz = pytz.timezone(timezone)
        local_dt = local_tz.localize(local_dt)
        
        utc_dt = local_dt.astimezone(pytz.UTC)
        
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
    except Exception as e:
        logger.error(f"时区转换失败: {e}, 使用简单拼接作为fallback")
        return f"{local_date}T{local_time}:00.000Z"


def format_for_api(date_str: str, time_str: str, timezone: str) -> dict:
    """
    格式化为Microsoft Graph API所需的格式
    
    Args:
        date_str: 日期字符串 (YYYY-MM-DD)
        time_str: 时间字符串 (HH:MM)
        timezone: 时区字符串
        
    Returns:
        符合API格式的字典:
        {
            "dateTime": "YYYY-MM-DDTHH:MM:SS",
            "timeZone": "Asia/Shanghai"
        }
    """
    datetime_str = f"{date_str}T{time_str}:00"
    
    return {
        "dateTime": datetime_str,
        "timeZone": timezone
    }


def calculate_relative_time(
    now: datetime,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0
) -> Tuple[str, str]:
    """
    根据天数偏移和绝对时间计算目标日期时间
    
    统一规则（无特殊分支）：
    - days: 几天后（0=今天, 1=明天, ...）
    - hours: 目标日当天的几点（0-23），绝对时间
    - minutes: 目标时间的分钟数（0-59）
    
    AI 在 Prompt 阶段已算好具体几点，本函数不做加减法推断。
    
    Args:
        now: 当前时间
        days: 几天后（0表示今天）
        hours: 当天的几点(0-23)，绝对时间
        minutes: 分钟数(0-59)
        
    Returns:
        (date_str, time_str): 例如 ("2026-02-18", "15:00")
        
    Examples:
        >>> now = datetime(2026, 2, 18, 23, 30)
        
        # 今天下午3点（即使现在是23:30，仍返回今天15:00）
        >>> calculate_relative_time(now, days=0, hours=15)
        ("2026-02-18", "15:00")
        
        # 明天上午9点
        >>> calculate_relative_time(now, days=1, hours=9)
        ("2026-02-19", "09:00")
        
        # 3天后下午2点半
        >>> calculate_relative_time(now, days=3, hours=14, minutes=30)
        ("2026-02-21", "14:30")
    """
    target_date = now.date() + timedelta(days=days)
    target_datetime = datetime.combine(target_date, datetime.min.time())
    target_datetime = target_datetime + timedelta(hours=hours, minutes=minutes)
    
    date_str = target_datetime.strftime('%Y-%m-%d')
    time_str = target_datetime.strftime('%H:%M')
    
    logger.debug(f"时间计算: days={days}, hours={hours}, minutes={minutes} -> {date_str} {time_str}")
    
    return date_str, time_str


def now_local() -> 'datetime':
    """
    返回当前本地时间（依据 Config.TIMEZONE）。
    """
    from config import Config
    local_tz = pytz.timezone(Config.TIMEZONE)
    return datetime.now(local_tz).replace(tzinfo=None)


def to_local_date(utc_iso: str, timezone: str = None) -> 'date':
    """
    将 Microsoft Graph API 返回的 UTC ISO 字符串转换为本地日期。

    Args:
        utc_iso: UTC 时间字符串，例如 "2026-02-20T00:00:00.0000000"
        timezone: 时区字符串，默认读取 Config.TIMEZONE

    Returns:
        本地日期 (datetime.date)
    """
    from datetime import date as date_type
    try:
        if timezone is None:
            from config import Config
            timezone = Config.TIMEZONE
        dt_str = utc_iso[:19].replace('T', ' ')
        utc_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        utc_dt = pytz.utc.localize(utc_dt)
        local_dt = utc_dt.astimezone(pytz.timezone(timezone))
        return local_dt.date()
    except Exception as e:
        logger.error(f"to_local_date 转换失败: {e}, utc_iso={utc_iso}")
        # fallback
        try:
            return datetime.strptime(utc_iso[:10], "%Y-%m-%d").date()
        except Exception:
            return None
