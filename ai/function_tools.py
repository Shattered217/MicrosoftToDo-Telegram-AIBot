"""
Function Calling工具定义
用于AI意图分析的结构化输出
"""


def get_task_analysis_tools(current_time: str):
    """获取任务分析的Function Calling工具定义"""
    from datetime import datetime
    now = datetime.strptime(current_time, "%Y-%m-%d %H:%M")
    current_date = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    
    # 过期示例
    past_example_hour = (current_hour - 2) % 24
    future_example_hour = (current_hour + 2) % 24
    
    return [{
        "type": "function",
        "function": {
            "name": "analyze_task_intent",
            "description": f"分析用户的任务意图。当前时间{current_time}（{current_hour}点）。"
                f"时间规则："
                f"1) days=几天后(0=今天,1=明天)；"
                f"2) hours=目标日当天的绝对时间(0-23)，如'下午3点'→hours=15；"
                f"3) ⚠️关键规则：必须判断时间是否已过！现在是{current_hour}点，"
                f"如果用户说的时间≤{current_hour}点且没说'明天'，则该时间今天已过，必须设days=1（明天）。"
                f"举例：现在{current_hour}点，用户说'{past_example_hour}点提醒'→已过→days=1,hours={past_example_hour}；"
                f"用户说'{future_example_hour}点提醒'→未过→days=0,hours={future_example_hour}。"
                f"严禁把已过的时间设为days=0！",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["CREATE", "UPDATE", "COMPLETE", "DELETE", "LIST", "SEARCH"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "due_in_days": {"type": "integer", "description": "截止日期是几天后（0=今天，1=明天）", "minimum": 0},
                    "reminder_in_days": {"type": "integer", "description": f"提醒日期是几天后（0=今天，1=明天）。⚠️如果提醒时间(hours)<={current_hour}且用户没说明天，必须设为1", "minimum": 0},
                    "reminder_in_hours": {"type": "integer", "description": "提醒时间：目标日当天的几点(0-23)，绝对时间。如'下午3点'=15，'晚上8点'=20。⚠️只有用户明确说了具体时间才填，否则不要填", "minimum": 0, "maximum": 23},
                    "reminder_in_minutes": {"type": "integer", "description": "提醒时间的分钟数", "minimum": 0, "maximum": 59},
                    "search_query": {"type": "string"},
                    "todo_id": {"type": "string"},
                    "target_description": {"type": "string"},
                    "modification_intent": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reasoning": {"type": "string"}
                },
                "required": ["action", "title", "confidence", "reasoning"]
            }
        }
    }]


def get_task_match_tools(candidates: list, user_text: str, initial_action: str) -> list:
    """获取任务匹配的Function Calling工具定义"""
    def _fmt_task(t: dict) -> str:
        parts = [f"[ID: {t['id']}] {t.get('title', '无标题')}"]
        if t.get('dueDateTime'):
            dt_val = t['dueDateTime']
            if isinstance(dt_val, dict):
                dt_val = dt_val.get('dateTime', '')
            parts.append(f"截止:{dt_val[:10]}")
        if t.get('reminderDateTime'):
            dt_val = t['reminderDateTime']
            if isinstance(dt_val, dict):
                dt_val = dt_val.get('dateTime', '')
            parts.append(f"提醒:{dt_val[:16]}")
        return " ".join(parts)

    candidates_str = "\n".join([_fmt_task(t) for t in candidates[:10]])
    
    return [{
        "type": "function",
        "function": {
            "name": "resolve_task_match",
            "description": (
                f"匹配任务并生成修改参数。用户输入:{user_text}。"
                f"候选任务(含现有日期):\n{candidates_str}。"
                f"⚠️时间规则：hours是绝对时间(0-23)，如果该时间今天已过必须设days=1。"
                f"⚠️UPDATE规则：只输出用户明确要修改的字段，未提及的字段必须为null（不要重置现有日期）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["UPDATE", "COMPLETE", "DELETE", "SEARCH"]},
                    "title": {"type": "string"},
                    "due_in_days": {"type": "integer", "description": "截止日期是几天后（0=今天，1=明天）。⚠️仅当用户明确提到新截止日期时才填，否则必须为null", "minimum": 0},
                    "reminder_in_days": {"type": "integer", "description": "提醒日期是几天后（0=今天，1=明天）。⚠️仅当用户明确提到提醒日期时才填，否则必须为null", "minimum": 0},
                    "reminder_in_hours": {"type": "integer", "description": "提醒时间：目标日当天的几点(0-23)，绝对时间", "minimum": 0, "maximum": 23},
                    "reminder_in_minutes": {"type": "integer", "description": "提醒时间的分钟数", "minimum": 0, "maximum": 59},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reasoning": {"type": "string"}
                },
                "required": ["todo_id", "action", "confidence", "reasoning"]
            }
        }
    }]


def get_decompose_tools(current_time: str, total_days: int = None) -> list:
    """获取任务拆解的Function Calling工具定义"""
    from datetime import datetime
    now = datetime.strptime(current_time, "%Y-%m-%d %H:%M")
    current_date = now.strftime("%Y-%m-%d")
    
    if total_days:
        description = f"拆解复杂任务。当前{current_time}。**严格限制**：原始任务总时长为{total_days}天，所有子任务的累计天数（due_in_days相加）必须≤{total_days}天！due_in_days是每个子任务需要的天数，会被累加。"
    else:
        description = f"拆解复杂任务。当前{current_time}。重要：due_in_days是每个子任务需要的天数，会被累加计算截止时间。"
    
    return [{
        "type": "function",
        "function": {
            "name": "decompose_complex_task",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "original_task": {"type": "string"},
                    "subtasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "due_in_days": {"type": "integer", "description": "完成此子任务需要的天数（会累加到前面任务的时间）", "minimum": 1},
                                "priority": {"type": "integer", "minimum": 1, "maximum": 5}
                            },
                            "required": ["title", "priority"]
                        },
                        "minItems": 2,
                        "maxItems": 10
                    },
                    "estimated_total_days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "reasoning": {"type": "string"}
                },
                "required": ["original_task", "subtasks", "estimated_total_days", "reasoning"]
            }
        }
    }]


def get_image_analysis_tools(current_time: str) -> list:
    """获取图片分析的Function Calling工具定义"""
    return [{
        "type": "function",
        "function": {
            "name": "analyze_image_content",
            "description": f"分析图片内容提取待办事项。当前{current_time}。时间规则：days表示几天后(0=今天)，hours统一为目标日当天的绝对时间(0-23点)，AI直接算好具体几点。⚠️如果时间已过今天，必须设days=1。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["CREATE"],
                        "description": "固定为CREATE，图片只能创建新任务"
                    },
                    "title": {"type": "string", "description": "单个任务的标题"},
                    "description": {"type": "string", "description": "任务详细描述"},
                    "due_in_days": {"type": "integer", "description": "截止日期是几天后（0=今天，1=明天）", "minimum": 0},
                    "reminder_in_days": {"type": "integer", "description": "提醒日期是几天后（0=今天，1=明天）", "minimum": 0},
                    "reminder_in_hours": {"type": "integer", "description": "提醒时间：目标日当天的几点(0-23)，绝对时间", "minimum": 0, "maximum": 23},
                    "reminder_in_minutes": {"type": "integer", "description": "提醒时间的分钟数", "minimum": 0, "maximum": 59},
                    "items": {
                        "type": "array",
                        "description": "如果图片包含多个任务，使用此字段",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"}
                            },
                            "required": ["title"]
                        }
                    },
                    "image_description": {"type": "string", "description": "图片内容总结"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["action", "confidence"]
            }
        }
    }]


def get_time_validation_tools() -> list:
    """
    获取时间校验的 Function Calling 工具定义。
    
    用于 time_validator.validate_reminder_time()：
    让 AI 判断 reminder_in_days=0 时指定的时间是否已过，
    输出修正后的 reminder_in_days（0 保持今天，1 改为明天）。
    """
    return [{
        "type": "function",
        "function": {
            "name": "validate_time",
            "description": (
                "判断用户设置的提醒时间（今天的某个时刻）是否已经过了当前时间。"
                "如果已过，reminder_in_days 应为 1（改为明天）；"
                "如果还没过，reminder_in_days 应为 0（保持今天）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_in_days": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "0=时间未过，保持今天；1=时间已过，改为明天"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "简短说明判断依据"
                    }
                },
                "required": ["reminder_in_days", "reasoning"]
            }
        }
    }]
