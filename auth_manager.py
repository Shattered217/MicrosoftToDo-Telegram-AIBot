import logging
import time
from typing import Dict, Set, Optional, Callable
from datetime import datetime, timedelta
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import Config

logger = logging.getLogger(__name__)


class AuthManager:
    """统一的鉴权管理器"""
    
    def __init__(self):
        self.admin_ids: Set[int] = set(Config.TELEGRAM_ADMIN_IDS)
        self.blacklist: Set[int] = set()
        self.whitelist: Set[int] = set()
        
        # 速率限制配置
        self.rate_limit_window = 60  # 时间窗口（秒）
        self.rate_limit_max_requests = 30  # 最大请求数
        self.user_requests: Dict[int, list] = {}  # {user_id: [timestamp, timestamp, ...]}
        
        # 访问统计
        self.access_stats: Dict[int, Dict] = {}  # {user_id: {count, first_access, last_access, username}}
        
        logger.info(f"鉴权管理器初始化完成，管理员ID: {self.admin_ids}")
    
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否是管理员"""
        return user_id in self.admin_ids
    
    def is_blacklisted(self, user_id: int) -> bool:
        """检查用户是否在黑名单中"""
        return user_id in self.blacklist
    
    def is_whitelisted(self, user_id: int) -> bool:
        """检查用户是否在白名单中"""
        return user_id in self.whitelist
    
    def add_to_blacklist(self, user_id: int) -> bool:
        """添加用户到黑名单"""
        if user_id in self.admin_ids:
            logger.warning(f"尝试将管理员 {user_id} 加入黑名单，操作被拒绝")
            return False
        self.blacklist.add(user_id)
        logger.warning(f"用户 {user_id} 已加入黑名单")
        return True
    
    def remove_from_blacklist(self, user_id: int):
        """从黑名单移除用户"""
        self.blacklist.discard(user_id)
        logger.info(f"用户 {user_id} 已从黑名单移除")
    
    def add_to_whitelist(self, user_id: int):
        """添加用户到白名单（临时访问权限）"""
        self.whitelist.add(user_id)
        logger.info(f"用户 {user_id} 已加入白名单")
    
    def remove_from_whitelist(self, user_id: int):
        """从白名单移除用户"""
        self.whitelist.discard(user_id)
        logger.info(f"用户 {user_id} 已从白名单移除")
    
    def check_rate_limit(self, user_id: int) -> tuple[bool, Optional[int]]:
        """
        检查速率限制
        返回: (是否允许, 剩余等待秒数)
        """
        now = time.time()
        
        # 清理过期的请求记录
        if user_id in self.user_requests:
            self.user_requests[user_id] = [
                ts for ts in self.user_requests[user_id]
                if now - ts < self.rate_limit_window
            ]
        else:
            self.user_requests[user_id] = []
        
        # 检查是否超过限制
        if len(self.user_requests[user_id]) >= self.rate_limit_max_requests:
            oldest_request = min(self.user_requests[user_id])
            wait_time = int(self.rate_limit_window - (now - oldest_request))
            return False, wait_time
        
        # 记录本次请求
        self.user_requests[user_id].append(now)
        return True, None
    
    def record_access(self, user_id: int, username: Optional[str] = None, action: str = "unknown"):
        """记录用户访问"""
        now = datetime.now()
        
        if user_id not in self.access_stats:
            self.access_stats[user_id] = {
                'count': 0,
                'first_access': now,
                'last_access': now,
                'username': username,
                'actions': {}
            }
        
        self.access_stats[user_id]['count'] += 1
        self.access_stats[user_id]['last_access'] = now
        if username:
            self.access_stats[user_id]['username'] = username
        
        # 记录具体操作
        if action not in self.access_stats[user_id]['actions']:
            self.access_stats[user_id]['actions'][action] = 0
        self.access_stats[user_id]['actions'][action] += 1
    
    def get_access_stats(self, user_id: Optional[int] = None) -> Dict:
        """获取访问统计"""
        if user_id:
            return self.access_stats.get(user_id, {})
        return self.access_stats
    
    def has_permission(self, user_id: int) -> bool:
        """检查用户是否有访问权限"""
        # 黑名单优先级最高
        if self.is_blacklisted(user_id):
            return False
        
        # 管理员或白名单用户
        return self.is_admin(user_id) or self.is_whitelisted(user_id)
    
    async def check_permission(
        self, 
        update: Update, 
        check_rate_limit: bool = True,
        action: str = "unknown"
    ) -> tuple[bool, Optional[str]]:
        """
        统一的权限检查
        返回: (是否允许, 错误信息)
        """
        user = update.effective_user
        if not user:
            return False, "无法识别用户信息"
        
        user_id = user.id
        username = user.username or user.first_name or "未知用户"
        
        # 记录访问
        self.record_access(user_id, username, action)
        
        # 检查黑名单
        if self.is_blacklisted(user_id):
            logger.warning(f"黑名单用户尝试访问: ID={user_id}, 用户名=@{username}")
            return False, f"您已被封禁，无法使用此机器人\n\n用户ID: `{user_id}`"
        
        # 检查权限
        if not self.has_permission(user_id):
            logger.warning(f"未授权用户尝试访问: ID={user_id}, 用户名=@{username}, 操作={action}")
            error_msg = f"""**访问被拒绝**

❌ 您没有权限使用此机器人

**您的信息：**
• 用户ID: `{user_id}`
• 用户名: @{username}
• 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

如果您认为这是错误，请联系管理员并提供您的用户ID。"""
            return False, error_msg
        
        # 检查速率限制（管理员豁免）
        if check_rate_limit and not self.is_admin(user_id):
            allowed, wait_time = self.check_rate_limit(user_id)
            if not allowed:
                logger.warning(f"用户 {user_id} 触发速率限制")
                error_msg = f"""**请求过于频繁**

⏱️ 请稍后再试

您在 {self.rate_limit_window} 秒内已发送 {self.rate_limit_max_requests} 个请求。

请等待 {wait_time} 秒后再继续使用。"""
                return False, error_msg
        
        return True, None


# 全局鉴权管理器实例
auth_manager = AuthManager()


def require_auth(check_rate_limit: bool = True, action: str = None):
    """
    权限检查装饰器
    
    使用方法:
    @require_auth()
    async def my_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # 自动获取操作名称
            action_name = action or func.__name__.replace('_command', '').replace('_', ' ')
            
            # 权限检查
            allowed, error_msg = await auth_manager.check_permission(
                update, 
                check_rate_limit=check_rate_limit,
                action=action_name
            )
            
            if not allowed:
                if update.message:
                    await update.message.reply_text(error_msg, parse_mode='Markdown')
                elif update.callback_query:
                    await update.callback_query.answer("权限不足", show_alert=True)
                    await update.callback_query.edit_message_text(error_msg, parse_mode='Markdown')
                return None
            
            # 执行原函数
            return await func(self, update, context, *args, **kwargs)
        
        return wrapper
    return decorator


def require_admin(func: Callable):
    """
    管理员权限装饰器（严格模式，不允许白名单用户）
    
    使用方法:
    @require_admin
    async def admin_only_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        ...
    """
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        if not auth_manager.is_admin(user_id):
            error_msg = "**权限不足**\n\n此操作仅限管理员使用。"
            if update.message:
                await update.message.reply_text(error_msg, parse_mode='Markdown')
            elif update.callback_query:
                await update.callback_query.answer("仅限管理员", show_alert=True)
            return None
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper

