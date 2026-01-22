"""
Microsoft Todo 直接客户端
使用 Microsoft Graph API 进行任务管理
通过混入类组合各功能模块
"""
import json
import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz
from config import Config

# 导入功能混入类
from todo.token_manager import TokenManagerMixin
from todo.api import ApiMixin
from todo.compat import CompatMixin

logger = logging.getLogger(__name__)


class MicrosoftTodoDirectClient(TokenManagerMixin, ApiMixin, CompatMixin):
    """
    Microsoft Todo 直接客户端
    
    通过多重继承组合所有功能：
    - TokenManagerMixin: Token刷新管理
    - ApiMixin: 基础API操作（任务列表、任务CRUD）
    - CompatMixin: 兼容性方法（简化接口）
    """
    
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
