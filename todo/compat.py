"""
兼容性方法
提供简化的待办事项操作接口
"""
import logging
from typing import Dict, Any, List

from config import Config

logger = logging.getLogger(__name__)


class CompatMixin:
    """兼容性方法混入类"""
    
    async def create_todo(self, title: str, description: str = "", due_date: str = None, 
                         reminder_date: str = None, reminder_time: str = None) -> Dict[str, Any]:
        """创建待办事项（兼容性方法）"""
        lists_result = await self.get_task_lists()
        if "error" in lists_result:
            return lists_result
        
        list_id = None
        if "value" in lists_result and lists_result["value"]:
            for task_list in lists_result["value"]:
                if task_list.get("wellknownListName") == "defaultList":
                    list_id = task_list["id"]
                    break
            if not list_id:
                list_id = lists_result["value"][0]["id"]
        
        if not list_id:
            return {"error": "没有找到可用的任务列表"}
        
        from utils.datetime_helper import to_utc_iso
        
        due_datetime = None
        if due_date:
            due_datetime = to_utc_iso(due_date, "23:59", Config.TIMEZONE)
        
        reminder_datetime = None
        if reminder_date:
            time_part = reminder_time or "09:00"
            reminder_datetime = to_utc_iso(reminder_date, time_part, Config.TIMEZONE)
        
        return await self.create_task_with_reminder(list_id, title, description, due_datetime, reminder_datetime)
    
    async def list_todos(self) -> List[Dict[str, Any]]:
        """获取所有待办事项（兼容性方法）"""
        result = await self.get_tasks()
        if "value" in result:
            return result["value"]
        elif "error" in result:
            logger.error(f"获取任务失败: {result['error']}")
            return []
        else:
            return []
    
    async def list_active_todos(self) -> List[Dict[str, Any]]:
        """获取活跃的待办事项（兼容性方法）"""
        result = await self.get_tasks(filter_query="status ne 'completed'")
        if "value" in result:
            return result["value"]
        elif "error" in result:
            logger.error(f"获取活跃任务失败: {result['error']}")
            return []
        else:
            return []
    
    async def _find_list_id_for_task(self, todo_id: str) -> str:
        """根据任务ID查找其所在的列表ID"""
        lists_result = await self.get_task_lists()
        if "value" in lists_result:
            for task_list in lists_result["value"]:
                tasks_result = await self.get_tasks(task_list["id"])
                if "value" in tasks_result:
                    for task in tasks_result["value"]:
                        if task["id"] == todo_id:
                            return task_list["id"]
        return None
    
    async def complete_todo(self, todo_id: str, list_id: str = None) -> Dict[str, Any]:
        """标记待办事项为完成"""
        if not list_id:
            list_id = await self._find_list_id_for_task(todo_id)
        
        if not list_id:
            return {"error": "找不到任务所在的列表"}
        
        return await self.update_task(list_id, todo_id, status="completed")
    
    async def update_todo(self, todo_id: str, title: str = None, description: str = None,
                        due_date: str = None, reminder_date: str = None, 
                        reminder_time: str = None, list_id: str = None) -> Dict[str, Any]:
        """更新待办事项"""
        if not list_id:
            list_id = await self._find_list_id_for_task(todo_id)
        
        if not list_id:
            return {"error": "找不到任务所在的列表"}
        
        from utils.datetime_helper import to_utc_iso
        
        reminder_datetime = None
        if reminder_date:
            time_part = reminder_time or "09:00"
            reminder_datetime = to_utc_iso(reminder_date, time_part, Config.TIMEZONE)
        
        formatted_due_date = None
        if due_date:
            if 'T' in due_date:
                formatted_due_date = due_date
            else:
                formatted_due_date = to_utc_iso(due_date, "00:00", Config.TIMEZONE)
        
        return await self.update_task(
            list_id, 
            todo_id, 
            title=title, 
            description=description,
            due_date=formatted_due_date,
            reminder_datetime=reminder_datetime
        )
    
    async def delete_todo(self, todo_id: str, list_id: str = None) -> Dict[str, Any]:
        """删除待办事项"""
        if not list_id:
            list_id = await self._find_list_id_for_task(todo_id)
        
        if not list_id:
            return {"error": "找不到任务所在的列表"}
        
        return await self.delete_task(list_id, todo_id)
    
    async def search_todos_by_title(self, title: str) -> List[Dict[str, Any]]:
        """根据标题搜索待办事项（兼容性方法）"""
        result = await self.get_tasks(filter_query=f"contains(title,'{title}')")
        if "value" in result:
            return result["value"]
        else:
            return []
    
    async def summarize_active_todos(self) -> str:
        """获取活跃待办事项的摘要（兼容性方法）"""
        tasks = await self.list_active_todos()
        if not tasks:
            return "当前没有活跃的待办事项。"
        
        summary = f"您有 {len(tasks)} 个未完成的待办事项：\n"
        for i, task in enumerate(tasks[:10], 1):
            title = task.get("title", "无标题")
            summary += f"{i}. {title}\n"
        
        if len(tasks) > 10:
            summary += f"...还有 {len(tasks) - 10} 个待办事项"
        
        return summary
