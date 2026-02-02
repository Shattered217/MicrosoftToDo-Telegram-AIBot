"""
统一的日期时间处理模块

该模块提供集中化的时间处理功能，包括：
- 日期时间验证
- 格式规范化
- 时区转换
- 智能时间调整

设计原则：
- 所有函数返回明确的类型或None，不做隐式转换
- 验证失败返回None，不抛出异常（调用方决定如何处理）
- 时间调整逻辑可配置
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time as time_type
from typing import Optional, Tuple
import pytz

logger = logging.getLogger(__name__)


@dataclass
class DateTimeInfo:
    """统一的日期时间信息数据类"""
    date: str  # YYYY-MM-DD格式
    time: str  # HH:MM格式
    datetime_str: str  # YYYY-MM-DDTHH:MM:SS格式


def validate_date(date_str: str) -> Optional[datetime]:
    """
    验证日期字符串格式
    
    Args:
        date_str: 日期字符串，期望格式 YYYY-MM-DD
        
    Returns:
        datetime对象如果格式正确，否则返回None
    """
    if not date_str:
        return None
    
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt
    except ValueError:
        logger.warning(f"无效的日期格式: {date_str}，期望格式: YYYY-MM-DD")
        return None


def validate_time(time_str: str) -> Optional[time_type]:
    """
    验证时间字符串格式
    
    Args:
        time_str: 时间字符串，期望格式 HH:MM
        
    Returns:
        time对象如果格式正确，否则返回None
    """
    if not time_str:
        return None
    
    try:
        t = datetime.strptime(time_str, '%H:%M').time()
        return t
    except ValueError:
        logger.warning(f"无效的时间格式: {time_str}，期望格式: HH:MM")
        return None


def adjust_past_datetime(dt: datetime, now: datetime, 
                        default_offset_minutes: int = 30) -> datetime:
    """
    如果日期时间在过去，自动调整到未来
    
    Args:
        dt: 要检查的日期时间
        now: 当前时间
        default_offset_minutes: 如果在过去，向后推迟的分钟数（默认30分钟）
        
    Returns:
        调整后的日期时间
    """
    if dt <= now:
        adjusted = now + timedelta(minutes=default_offset_minutes)
        logger.info(f"时间已过去，自动调整为{default_offset_minutes}分钟后: "
                   f"{dt.strftime('%Y-%m-%d %H:%M')} -> {adjusted.strftime('%Y-%m-%d %H:%M')}")
        return adjusted
    return dt


def normalize_reminder(reminder_date: str, reminder_time: str, 
                      now: datetime, auto_adjust: bool = False) -> Optional[DateTimeInfo]:
    """
    规范化提醒时间
    
    验证日期和时间格式
    
    Args:
        reminder_date: 提醒日期字符串 (YYYY-MM-DD)
        reminder_time: 提醒时间字符串 (HH:MM)
        now: 当前时间
        auto_adjust: 是否自动调整过去的时间（默认False，让AI负责推断正确时间）
        
    Returns:
        DateTimeInfo对象如果验证成功，否则返回None
    """
    date_obj = validate_date(reminder_date)
    if not date_obj:
        return None
    
    time_obj = validate_time(reminder_time)
    if not time_obj:
        return None
    
    try:
        reminder_datetime = datetime.combine(date_obj.date(), time_obj)
        
        if auto_adjust and reminder_datetime <= now:
            adjusted = adjust_past_datetime(reminder_datetime, now)
            reminder_date = adjusted.strftime('%Y-%m-%d')
            reminder_time = adjusted.strftime('%H:%M')
            reminder_datetime = adjusted
        elif reminder_datetime <= now:
            logger.warning(f"提醒时间在过去: {reminder_date} {reminder_time}，但未启用自动调整")
        
        datetime_str = reminder_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        
        return DateTimeInfo(
            date=reminder_date,
            time=reminder_time,
            datetime_str=datetime_str
        )
    except Exception as e:
        logger.error(f"规范化提醒时间失败: {e}")
        return None


def normalize_due_date(due_date: str, now: datetime, auto_adjust: bool = False) -> Optional[str]:
    """
    规范化提醒时间
    
    验证日期和时间格式，如果提醒时间在过去则自动调整
    
    Args:
        reminder_date: 提醒日期字符串 (YYYY-MM-DD)
        reminder_time: 提醒时间字符串 (HH:MM)
        now: 当前时间
        
    Returns:
        DateTimeInfo对象如果验证成功，否则返回None
    """
    date_obj = validate_date(reminder_date)
    if not date_obj:
        return None
    
    time_obj = validate_time(reminder_time)
    if not time_obj:
        return None
    
    try:
        reminder_datetime = datetime.combine(date_obj.date(), time_obj)
        
        if reminder_datetime <= now:
            adjusted = adjust_past_datetime(reminder_datetime, now)
            reminder_date = adjusted.strftime('%Y-%m-%d')
            reminder_time = adjusted.strftime('%H:%M')
            reminder_datetime = adjusted
        
        datetime_str = reminder_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        
        return DateTimeInfo(
            date=reminder_date,
            time=reminder_time,
            datetime_str=datetime_str
        )
    except Exception as e:
        logger.error(f"规范化提醒时间失败: {e}")
        return None


def normalize_due_date(due_date: str, now: datetime, auto_adjust: bool = False) -> Optional[str]:
    """
    规范化截止日期
    
    验证日期格式
    
    Args:
        due_date: 截止日期字符串 (YYYY-MM-DD)
        now: 当前时间
        auto_adjust: 是否自动调整过去的日期（默认False，让AI负责推断正确日期）
        
    Returns:
        规范化后的日期字符串 (YYYY-MM-DD) 如果验证成功，否则返回None
    """
    date_obj = validate_date(due_date)
    if not date_obj:
        return None
    
    if auto_adjust and date_obj.date() < now.date():
        adjusted_date = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"截止日期在过去，自动调整为明天: {due_date} -> {adjusted_date}")
        return adjusted_date
    elif date_obj.date() < now.date():
        logger.warning(f"截止日期在过去: {due_date}，但未启用自动调整")
    
    return due_date



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
