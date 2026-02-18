"""
时间有效性校验模块

当主意图分析AI输出 reminder_in_days=0 时，
调用此模块让AI二次判断：指定时间是否已过，是否需要将 days 调整为 1（明天）。

设计原则：
- 职责单一：只做"时间是否已过"这一件事
- 解耦：不依赖 AIService 类，接受 client/model 作为参数
- 可测试：输入输出均为简单数据类型
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_time_validation_tools() -> list:
    """
    获取时间校验的 Function Calling 工具定义。
    此函数定义放在 function_tools.py 中统一管理，
    这里仅作 re-export 供 time_validator 内部使用。
    """
    from ai.function_tools import get_time_validation_tools as _get
    return _get()


async def validate_reminder_time(
    client,
    model: str,
    current_time: str,
    reminder_in_days: int,
    reminder_in_hours: int,
    reminder_in_minutes: int = 0,
) -> int:
    """
    让 AI 判断提醒时间是否已过，返回修正后的 reminder_in_days。

    仅在 reminder_in_days == 0 时才调用（今天的时间才需要判断是否已过）。
    如果 reminder_in_days >= 1，直接返回原值，无需校验。

    Args:
        client:              AsyncOpenAI client 实例
        model:               模型名称
        current_time:        当前时间字符串，格式 "YYYY-MM-DD HH:MM"
        reminder_in_days:    AI 原始输出的天数偏移
        reminder_in_hours:   AI 原始输出的小时（绝对时间 0-23）
        reminder_in_minutes: AI 原始输出的分钟数

    Returns:
        修正后的 reminder_in_days（0 或 1）
    """
    if reminder_in_days != 0:
        return reminder_in_days

    from ai.function_tools import get_time_validation_tools
    tools = get_time_validation_tools()

    prompt = (
        f"当前时间是 {current_time}。"
        f"用户设置的提醒时间是今天（days=0）的 {reminder_in_hours:02d}:{reminder_in_minutes:02d}。"
        f"请判断这个时间是否已经过了？如果已过，应该改为明天（days=1）；如果还没过，保持今天（days=0）。"
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "validate_time"}},
            temperature=0,
            max_tokens=100,
        )

        message = response.choices[0].message
        if message.tool_calls:
            args = json.loads(message.tool_calls[0].function.arguments)
            corrected_days = args.get("reminder_in_days", reminder_in_days)
            if corrected_days != reminder_in_days:
                logger.info(
                    f"时间校验: {reminder_in_hours:02d}:{reminder_in_minutes:02d} "
                    f"在 {current_time} 已过，days 修正 {reminder_in_days} → {corrected_days}"
                )
            else:
                logger.debug(
                    f"时间校验: {reminder_in_hours:02d}:{reminder_in_minutes:02d} "
                    f"在 {current_time} 未过，保持 days={corrected_days}"
                )
            return corrected_days

    except Exception as e:
        logger.warning(f"时间校验失败，保持原值 days={reminder_in_days}: {e}")

    return reminder_in_days
