"""
相对时间处理模块

该模块提供相对时间计算和API格式化功能：
- 相对时间计算（几天/小时/分钟后）
- 时区转换
- API格式化

设计原则：
- 使用相对时间而非绝对时间，避免AI推断错误
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
    根据相对时间计算绝对时间
    
    时间基线规则：
    - 当天任务(days=0): 以现在为基线，hours/minutes是相对偏移
    - 跨天任务(days≥1): 以目标日的0点为基线，hours表示当天的几点(0-23)
    
    Args:
        now: 当前时间
        days: 几天后（0表示今天）
        hours: 当天任务-相对现在几小时；跨天任务-当天的几点(0-23)
        minutes: 分钟数
        
    Returns:
        (date_str, time_str): 例如 ("2026-02-13", "09:00")
        
    Examples:
        >>> now = datetime(2026, 2, 10, 23, 30)
        
        # 当天任务：2小时后
        >>> calculate_relative_time(now, days=0, hours=2)
        ("2026-02-11", "01:30")  # 以现在为基线
        
        # 跨天任务：3天后9点
        >>> calculate_relative_time(now, days=3, hours=9)
        ("2026-02-13", "09:00")  # 以0点为基线
    """
    if days == 0:
        # 当天任务：以现在为基线
        target_datetime = now + timedelta(hours=hours, minutes=minutes)
        logger.debug(f"当天任务：现在+{hours}小时{minutes}分钟 = {target_datetime}")
    else:
        # 跨天任务：以目标日的0点为基线
        target_date = now.date() + timedelta(days=days)
        target_datetime = datetime.combine(target_date, datetime.min.time())
        target_datetime = target_datetime + timedelta(hours=hours, minutes=minutes)
        logger.debug(f"跨天任务：{days}天后的{hours}点{minutes}分 = {target_datetime}")
    
    date_str = target_datetime.strftime('%Y-%m-%d')
    time_str = target_datetime.strftime('%H:%M')
    
    logger.debug(f"相对时间计算: days={days}, hours={hours}, minutes={minutes} -> {date_str} {time_str}")
    
    return date_str, time_str
