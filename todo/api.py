"""
基础API操作
包含任务列表和任务的CRUD操作
"""
import logging
from typing import Dict, Any

from config import Config

logger = logging.getLogger(__name__)


class ApiMixin:
    """基础API操作混入类"""
    
    async def get_task_lists(self) -> Dict[str, Any]:
        """获取所有任务列表"""
        return await self._make_request("GET", "/me/todo/lists")
    
    async def create_task_list(self, name: str) -> Dict[str, Any]:
        """创建新的任务列表"""
        data = {"displayName": name}
        return await self._make_request("POST", "/me/todo/lists", data)
    
    async def update_task_list(self, list_id: str, name: str) -> Dict[str, Any]:
        """更新任务列表"""
        data = {"displayName": name}
        return await self._make_request("PATCH", f"/me/todo/lists/{list_id}", data)
    
    async def delete_task_list(self, list_id: str) -> Dict[str, Any]:
        """删除任务列表"""
        return await self._make_request("DELETE", f"/me/todo/lists/{list_id}")
    
    async def get_tasks(self, list_id: str = None, filter_query: str = None) -> Dict[str, Any]:
        """获取任务"""
        if not list_id:
            lists_result = await self.get_task_lists()
            if "value" in lists_result and lists_result["value"]:
                for task_list in lists_result["value"]:
                    if task_list.get("wellknownListName") == "defaultList":
                        list_id = task_list["id"]
                        break
                if not list_id:
                    list_id = lists_result["value"][0]["id"]
            else:
                return {"error": "没有找到任务列表"}
        
        endpoint = f"/me/todo/lists/{list_id}/tasks"
        if filter_query:
            endpoint += f"?$filter={filter_query}"
        
        return await self._make_request("GET", endpoint)
    
    async def create_task(self, list_id: str, title: str, description: str = None, 
                         due_date: str = None) -> Dict[str, Any]:
        """创建新任务"""
        data = {"title": title}
        
        if description:
            data["body"] = {
                "content": description,
                "contentType": "text"
            }
        
        if due_date:
            data["dueDateTime"] = {
                "dateTime": due_date,
                "timeZone": Config.TIMEZONE
            }
        
        return await self._make_request("POST", f"/me/todo/lists/{list_id}/tasks", data)
    
    async def create_task_with_reminder(self, list_id: str, title: str, description: str = None,
                                       due_date: str = None, reminder_datetime: str = None) -> Dict[str, Any]:
        """创建带提醒的任务"""
        data = {"title": title}
        
        if description:
            data["body"] = {
                "content": description,
                "contentType": "text"
            }
        
        if due_date:
            data["dueDateTime"] = {
                "dateTime": due_date,
                "timeZone": Config.TIMEZONE
            }
        
        if reminder_datetime:
            data["reminderDateTime"] = {
                "dateTime": reminder_datetime,
                "timeZone": Config.TIMEZONE
            }
        
        return await self._make_request("POST", f"/me/todo/lists/{list_id}/tasks", data)
    
    async def update_task(self, list_id: str, task_id: str, title: str = None, 
                         description: str = None, status: str = None,
                         due_date: str = None, reminder_datetime: str = None) -> Dict[str, Any]:
        """更新任务"""
        data = {}
        
        if title:
            data["title"] = title
        
        if description:
            data["body"] = {
                "content": description,
                "contentType": "text"
            }
        
        if status:
            data["status"] = status
        
        if due_date:
            data["dueDateTime"] = {
                "dateTime": due_date,
                "timeZone": Config.TIMEZONE
            }
        
        if reminder_datetime:
            data["reminderDateTime"] = {
                "dateTime": reminder_datetime,
                "timeZone": Config.TIMEZONE
            }
        
        return await self._make_request("PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", data)
    
    async def delete_task(self, list_id: str, task_id: str) -> Dict[str, Any]:
        """删除任务"""
        return await self._make_request("DELETE", f"/me/todo/lists/{list_id}/tasks/{task_id}")
