import json
import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz
from config import Config

logger = logging.getLogger(__name__)

class MicrosoftTodoDirectClient:
    
    def __init__(self):
        self.access_token = Config.MS_TODO_ACCESS_TOKEN
        self.refresh_token = Config.MS_TODO_REFRESH_TOKEN
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.session = None
        self.client_id = Config.MS_TODO_CLIENT_ID
        self.client_secret = Config.MS_TODO_CLIENT_SECRET
        self.tenant_id = Config.MS_TODO_TENANT_ID
        self.local_tz = pytz.timezone(Config.TIMEZONE)
        self.utc_tz = pytz.UTC
    
    def _convert_to_utc_iso(self, date_str: str, time_str: str = None) -> str:
        """将本地日期时间转换为UTC ISO格式"""
        try:
            if time_str:
                # 组合日期和时间
                dt_str = f"{date_str} {time_str}"
                local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            else:
                # 只有日期，使用默认时间
                local_dt = datetime.strptime(date_str, "%Y-%m-%d")
            
            # 设置为本地时区
            local_dt = self.local_tz.localize(local_dt)
            
            # 转换为UTC
            utc_dt = local_dt.astimezone(self.utc_tz)
            
            # 返回ISO格式字符串（去掉时区信息，因为Graph API要求）
            return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            
        except Exception as e:
            logger.error(f"时区转换失败: {e}")
            # fallback: 直接返回原格式
            if time_str:
                return f"{date_str}T{time_str}:00.000Z"
            else:
                return f"{date_str}T00:00:00.000Z"
        
    async def _ensure_session(self):
        """确保HTTP会话存在"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def _refresh_access_token(self) -> bool:
        """刷新访问令牌"""
        if not self.refresh_token:
            logger.error("没有刷新令牌，无法刷新访问令牌")
            return False
            
        # 检查是否是客户端凭据流
        if self.refresh_token == "client_credentials_flow":
            logger.info("检测到客户端凭据流，重新获取访问令牌")
            return await self._get_client_credentials_token()
        
        if not self.client_id:
            logger.error("缺少client_id，无法刷新令牌")
            logger.info("请在.env文件中设置 MS_TODO_CLIENT_ID")
            return False
        
        await self._ensure_session()
        
        # 根据是否有client_secret选择不同的authority和认证方式
        if self.client_secret:
            # 工作/学校账户
            token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            logger.info("使用工作/学校账户刷新令牌")
        else:
            # 个人账户
            token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
            logger.info("使用个人账户刷新令牌")
        
        data = {
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read offline_access"
        }
        
        # 只有工作/学校账户需要client_secret
        if self.client_secret:
            data["client_secret"] = self.client_secret
        
        try:
            async with self.session.post(token_url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data.get("access_token")
                    if "refresh_token" in token_data:
                        self.refresh_token = token_data["refresh_token"]
                    
                    logger.info("访问令牌刷新成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"令牌刷新失败: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"令牌刷新异常: {e}")
            return False
    
    async def _get_client_credentials_token(self) -> bool:
        """使用客户端凭据流获取访问令牌"""
        if not self.client_secret:
            logger.error("客户端凭据流需要client_secret")
            return False
            
        await self._ensure_session()
        
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        try:
            async with self.session.post(token_url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data.get("access_token")
                    logger.info("客户端凭据流令牌获取成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"客户端凭据流令牌获取失败: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"客户端凭据流异常: {e}")
            return False
    
    async def _make_request(self, method: str, endpoint: str, data: Dict = None, retry_on_401: bool = True) -> Dict[str, Any]:
        """发送HTTP请求到Microsoft Graph API"""
        await self._ensure_session()
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with self.session.request(method, url, headers=headers, json=data) as response:
                if response.status == 401 and retry_on_401:
                    logger.warning("访问令牌已过期，尝试刷新...")
                    # 尝试刷新令牌
                    if await self._refresh_access_token():
                        # 刷新成功，重新发送请求（避免无限递归）
                        return await self._make_request(method, endpoint, data, retry_on_401=False)
                    else:
                        return {"error": "访问令牌无效且刷新失败"}
                
                response_text = await response.text()
                
                if response.status >= 400:
                    logger.error(f"API请求失败: {response.status} - {response_text}")
                    return {"error": f"API请求失败: {response.status} - {response_text}"}
                
                if response_text:
                    return json.loads(response_text)
                else:
                    return {"success": True}
                    
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return {"error": str(e)}
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
    
    async def refresh_token_manually(self) -> bool:
        """手动刷新访问令牌（公共方法）"""
        logger.info("手动刷新访问令牌")
        return await self._refresh_access_token()
    
    # ========== 任务列表管理 ==========
    
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
    
    # ========== 任务管理 ==========
    
    async def get_tasks(self, list_id: str = None, filter_query: str = None) -> Dict[str, Any]:
        """获取任务"""
        if not list_id:
            # 如果没有指定列表ID，获取默认列表
            lists_result = await self.get_task_lists()
            if "value" in lists_result and lists_result["value"]:
                # 查找默认列表或使用第一个列表
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
        
        # 添加提醒设置
        if reminder_datetime:
            data["reminderDateTime"] = {
                "dateTime": reminder_datetime,
                "timeZone": Config.TIMEZONE
            }
        
        return await self._make_request("POST", f"/me/todo/lists/{list_id}/tasks", data)
    
    async def update_task(self, list_id: str, task_id: str, title: str = None, 
                         description: str = None, status: str = None) -> Dict[str, Any]:
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
        
        return await self._make_request("PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", data)
    
    async def delete_task(self, list_id: str, task_id: str) -> Dict[str, Any]:
        """删除任务"""
        return await self._make_request("DELETE", f"/me/todo/lists/{list_id}/tasks/{task_id}")
    
    # ========== 兼容性方法 ==========
    
    async def create_todo(self, title: str, description: str = "", due_date: str = None, 
                         reminder_date: str = None, reminder_time: str = None) -> Dict[str, Any]:
        """创建待办事项（兼容性方法）"""
        # 获取默认列表ID
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
        
        # 组合截止日期（设为当天结束）
        due_datetime = None
        if due_date:
            due_datetime = self._convert_to_utc_iso(due_date, "23:59")
        
        # 组合提醒日期和时间
        reminder_datetime = None
        if reminder_date and reminder_time:
            reminder_datetime = self._convert_to_utc_iso(reminder_date, reminder_time)
        elif reminder_date:
            # 如果只有提醒日期，默认设为上午9点
            reminder_datetime = self._convert_to_utc_iso(reminder_date, "09:00")
        
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
    
    async def complete_todo(self, todo_id: str, list_id: str = None) -> Dict[str, Any]:
        """标记待办事项为完成（兼容性方法）"""
        if not list_id:
            lists_result = await self.get_task_lists()
            if "value" in lists_result:
                for task_list in lists_result["value"]:
                    tasks_result = await self.get_tasks(task_list["id"])
                    if "value" in tasks_result:
                        for task in tasks_result["value"]:
                            if task["id"] == todo_id:
                                list_id = task_list["id"]
                                break
                    if list_id:
                        break
        
        if not list_id:
            return {"error": "找不到任务所在的列表"}
        
        return await self.update_task(list_id, todo_id, status="completed")
    
    async def delete_todo(self, todo_id: str, list_id: str = None) -> Dict[str, Any]:
        """删除待办事项（兼容性方法）"""
        if not list_id:
            lists_result = await self.get_task_lists()
            if "value" in lists_result:
                for task_list in lists_result["value"]:
                    tasks_result = await self.get_tasks(task_list["id"])
                    if "value" in tasks_result:
                        for task in tasks_result["value"]:
                            if task["id"] == todo_id:
                                list_id = task_list["id"]
                                break
                    if list_id:
                        break
        
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
