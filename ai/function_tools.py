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
            "description": f"分析用户的任务意图。当前时间{current_time}({current_hour}点)。若时间已过必须推断为明天！",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["CREATE", "UPDATE", "COMPLETE", "DELETE", "LIST", "SEARCH"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "due_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "reminder_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "reminder_time": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"},
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
                    "due_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "reminder_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "reminder_time": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reasoning": {"type": "string"}
                },
                "required": ["todo_id", "action", "confidence", "reasoning"]
            }
        }
    }]


def get_decompose_tools(current_time: str) -> list:
    """获取任务拆解的Function Calling工具定义"""
    from datetime import datetime
    now = datetime.strptime(current_time, "%Y-%m-%d %H:%M")
    current_date = now.strftime("%Y-%m-%d")
    
    return [{
        "type": "function",
        "function": {
            "name": "decompose_complex_task",
            "description": f"拆解复杂任务。当前{current_time}",
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
                                "due_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
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
            "description": f"分析图片内容提取待办事项。当前{current_time}。",
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
                    "due_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "reminder_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                    "reminder_time": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"},
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
