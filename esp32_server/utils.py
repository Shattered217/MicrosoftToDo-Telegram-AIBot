"""
数据格式转换工具
"""
from typing import Dict, Any, List
from datetime import datetime


def convert_task_to_esp32_format(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 Microsoft Graph API 任务格式转换为 ESP32 友好格式
    
    Microsoft Graph 格式:
    {
        "id": "AAMkAGI...",
        "title": "任务标题",
        "body": {"content": "描述", "contentType": "text"},
        "status": "notStarted",
        "importance": "normal",
        "createdDateTime": "2026-01-29T10:00:00.0000000Z",
        ...
    }
    
    ESP32 格式:
    {
        "id": "AAMkAGI...",
        "title": "任务标题",
        "body": "描述",
        "status": "notStarted",
        "importance": "normal",
        "createdDateTime": "2026-01-29T10:00:00Z",
        "isCompleted": false
    }
    """
    body = ""
    if task.get("body"):
        if isinstance(task["body"], dict):
            body = task["body"].get("content", "")
        else:
            body = str(task["body"])
    
    created_dt = task.get("createdDateTime", "")
    if created_dt and "." in created_dt:
        created_dt = created_dt.split(".")[0] + "Z"
    
    modified_dt = task.get("lastModifiedDateTime", "")
    if modified_dt and "." in modified_dt:
        modified_dt = modified_dt.split(".")[0] + "Z"
    
    status = task.get("status", "notStarted")
    is_completed = status == "completed"
    return {
        "id": task.get("id", ""),
        "listId": task.get("listId", ""),
        "title": task.get("title", ""),
        "body": body[:100] if body else "",
        "importance": task.get("importance", "normal"),
        "lastModifiedDateTime": modified_dt,
        "isCompleted": is_completed
    }


def convert_tasks_to_esp32_format(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """批量转换任务列表"""
    return [convert_task_to_esp32_format(task) for task in tasks]


def get_stats_from_tasks(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从任务列表生成统计信息"""
    total = len(tasks)
    completed = len([t for t in tasks if t.get("status") == "completed"])
    pending = total - completed
    
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "completionRate": f"{(completed/total*100):.1f}%" if total > 0 else "0%"
    }
