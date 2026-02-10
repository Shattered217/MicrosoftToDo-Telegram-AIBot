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
    
    return [{
        "type": "function",
        "function": {
            "name": "analyze_task_intent",
            "description": f"分析用户的任务意图。当前时间{current_time}({current_hour}点)。时间规则：当天任务(days=0)以现在为基线用hours/minutes；跨天任务(days≥1)以0点为基线，hours表示当天几点(如reminder_in_days:3, reminder_in_hours:9表示3天后9点)",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["CREATE", "UPDATE", "COMPLETE", "DELETE", "LIST", "SEARCH"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "due_in_days": {"type": "integer", "description": "截止日期是几天后（0表示今天）", "minimum": 0},
                    "reminder_in_days": {"type": "integer", "description": "提醒日期是几天后（0表示今天）", "minimum": 0},
                    "reminder_in_hours": {"type": "integer", "description": "当天任务：相对现在几小时；跨天任务：当天的几点(0-23)", "minimum": 0, "maximum": 23},
                    "reminder_in_minutes": {"type": "integer", "description": "分钟数", "minimum": 0, "maximum": 59},
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
    candidates_str = "\n".join([f"[ID: {t['id']}] {t.get('title', '无标题')}" for t in candidates[:10]])
    
    return [{
        "type": "function",
        "function": {
            "name": "resolve_task_match",
            "description": f"匹配任务。用户输入:{user_text}。候选:\n{candidates_str}",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["UPDATE", "COMPLETE", "DELETE", "SEARCH"]},
                    "title": {"type": "string"},
                    "due_in_days": {"type": "integer", "description": "截止日期是几天后", "minimum": 0},
                    "reminder_in_days": {"type": "integer", "description": "提醒日期是几天后", "minimum": 0},
                    "reminder_in_hours": {"type": "integer", "description": "当天任务：相对现在几小时；跨天任务：当天的几点", "minimum": 0, "maximum": 23},
                    "reminder_in_minutes": {"type": "integer", "description": "分钟数", "minimum": 0, "maximum": 59},
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
            "description": f"分析图片内容提取待办事项。当前{current_time}。时间规则：当天任务以现在为基线，跨天任务以0点为基线！",
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
                    "due_in_days": {"type": "integer", "description": "截止日期是几天后", "minimum": 0},
                    "reminder_in_days": {"type": "integer", "description": "提醒日期是几天后", "minimum": 0},
                    "reminder_in_hours": {"type": "integer", "description": "当天任务：相对现在几小时；跨天任务：当天的几点", "minimum": 0, "maximum": 23},
                    "reminder_in_minutes": {"type": "integer", "description": "分钟数", "minimum": 0, "maximum": 59},
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
