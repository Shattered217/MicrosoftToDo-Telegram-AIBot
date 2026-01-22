"""
Token管理处理器
包含令牌状态、刷新、授权链接等功能
"""
import asyncio
import logging
import uuid
from datetime import datetime
import requests

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes

from config import Config

logger = logging.getLogger(__name__)


class TokenHandlers:
    """Token管理处理器混入类"""

    async def token_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not await self._check_admin_permission(update):
            return

        try:
            status_message = "令牌状态\n\n"

            def _mask_tail(value: str, tail_len: int = 8) -> str:
                if not value:
                    return "未设置"
                if len(value) <= tail_len:
                    return value
                return f"***{value[-tail_len:]}"

            if Config.MS_TODO_ACCESS_TOKEN:
                status_message += (
                    f"访问令牌: {_mask_tail(Config.MS_TODO_ACCESS_TOKEN)}\n"
                )
            else:
                status_message += "访问令牌: 未设置\n"

            if Config.MS_TODO_REFRESH_TOKEN:
                if Config.MS_TODO_REFRESH_TOKEN == "client_credentials_flow":
                    status_message += "刷新令牌: 客户端凭据流\n"
                else:
                    status_message += (
                        f"刷新令牌: {_mask_tail(Config.MS_TODO_REFRESH_TOKEN)}\n"
                    )
            else:
                status_message += "刷新令牌: 未设置\n"

            if Config.MS_TODO_CLIENT_SECRET:
                status_message += f"账户类型: 工作/学校账户\n"
                status_message += f"Tenant ID: {Config.MS_TODO_TENANT_ID}\n"
            else:
                status_message += "账户类型: 个人账户\n"

            status_message += "\n测试连接...\n"
            test_result = await self.todo_client.get_task_lists()
            if "error" not in test_result:
                status_message += "令牌有效，连接正常\n"
            else:
                error_msg = str(test_result.get("error", "未知错误"))
                status_message += f"令牌可能已过期: {error_msg}\n"
                status_message += (
                    "\n使用 /refresh_token 刷新令牌或 /get_auth_link 重新授权"
                )

            reply_msg = await update.message.reply_text(status_message)
            
            # 30秒后自动删除消息
            asyncio.create_task(self._auto_delete_messages(
                chat_id=update.effective_chat.id,
                message_ids=[update.message.message_id, reply_msg.message_id],
                delay=30
            ))

        except Exception as e:
            logger.error(f"检查令牌状态失败: {e}")
            await update.message.reply_text(f"检查令牌状态失败: {str(e)}")

    async def refresh_token_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not await self._check_admin_permission(update):
            return

        try:
            await update.message.reply_text("正在刷新访问令牌...")

            success = await self.todo_client.refresh_token_manually()

            if success:
                new_access_token = self.todo_client.access_token
                new_refresh_token = self.todo_client.refresh_token

                if await self._save_tokens_to_env(new_access_token, new_refresh_token):
                    reply_msg = await update.message.reply_text(
                        "令牌刷新成功！\n\n"
                        f"新访问令牌: ***{new_access_token[-8:]}\n"
                        "已自动保存到配置文件\n\n"
                        "⏰ 此消息30秒后自动删除"
                    )
                else:
                    reply_msg = await update.message.reply_text(
                        "令牌刷新成功但保存失败\n\n"
                        f"新访问令牌: ***{new_access_token[-8:]}\n"
                        "请联系管理员手动更新配置文件\n\n"
                        "⏰ 此消息30秒后自动删除"
                    )
                
                # 30秒后自动删除消息
                asyncio.create_task(self._auto_delete_messages(
                    chat_id=update.effective_chat.id,
                    message_ids=[update.message.message_id, reply_msg.message_id],
                    delay=30
                ))
            else:
                await update.message.reply_text(
                    "令牌刷新失败\n\n"
                    "可能原因：\n"
                    "• 刷新令牌已过期（90天有效期）\n"
                    "• 网络连接问题\n"
                    "• 服务器配置问题\n\n"
                    "请使用 /get_auth_link 重新授权"
                )

        except Exception as e:
            logger.error(f"刷新令牌失败: {e}")
            await update.message.reply_text(f"刷新令牌失败: {str(e)}")

    async def get_auth_link_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not await self._check_admin_permission(update):
            return

        try:
            user_id = update.effective_user.id

            auth_url = self._generate_auth_url()

            session_id = str(uuid.uuid4())
            self.pending_auth[user_id] = {
                "session_id": session_id,
                "timestamp": datetime.now(),
                "expecting_code": True,
            }

            message = f"""Microsoft To-Do 授权

请点击下面的链接进行授权：
{auth_url}

授权步骤：
1. 点击上面的链接
2. 使用您的Microsoft账户登录
3. 同意应用权限请求
4. 复制浏览器地址栏中的授权码（code=后面的部分）
5. 发送授权码给我

授权链接有效期：10分钟
会话ID: {session_id[:8]}...

获取授权码后，直接发送给我即可自动更新令牌！"""

            await update.message.reply_text(message)

            # 设置清理任务（如果 job_queue 可用）
            if context.job_queue:
                context.job_queue.run_once(
                    self._cleanup_auth_session,
                    600,
                    data=user_id,
                    name=f"cleanup_auth_{user_id}",
                )

        except Exception as e:
            logger.error(f"生成授权链接失败: {e}")
            await update.message.reply_text(f"生成授权链接失败: {str(e)}")

    def _generate_auth_url(self):
        client_id = Config.MS_TODO_CLIENT_ID
        redirect_uri = "http://localhost:3000/callback"

        if Config.MS_TODO_CLIENT_SECRET:
            authority = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}"
        else:
            authority = "https://login.microsoftonline.com/consumers"

        scopes = "offline_access https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read"

        return (
            f"{authority}/oauth2/v2.0/authorize"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&response_mode=query"
            f"&scope={scopes}"
            f"&state=telegram_bot"
        )

    async def _save_tokens_to_env(self, access_token: str, refresh_token: str) -> bool:
        try:
            env_lines = []
            try:
                with open(".env", "r", encoding="utf-8") as f:
                    env_lines = f.readlines()
            except FileNotFoundError:
                pass

            access_token_found = False
            refresh_token_found = False

            for i, line in enumerate(env_lines):
                if line.startswith("MS_TODO_ACCESS_TOKEN="):
                    env_lines[i] = f"MS_TODO_ACCESS_TOKEN={access_token}\n"
                    access_token_found = True
                elif line.startswith("MS_TODO_REFRESH_TOKEN="):
                    env_lines[i] = f"MS_TODO_REFRESH_TOKEN={refresh_token}\n"
                    refresh_token_found = True

            if not access_token_found:
                env_lines.append(f"MS_TODO_ACCESS_TOKEN={access_token}\n")
            if not refresh_token_found:
                env_lines.append(f"MS_TODO_REFRESH_TOKEN={refresh_token}\n")

            with open(".env", "w", encoding="utf-8") as f:
                f.writelines(env_lines)

            Config.MS_TODO_ACCESS_TOKEN = access_token
            Config.MS_TODO_REFRESH_TOKEN = refresh_token

            return True

        except Exception as e:
            logger.error(f"保存令牌失败: {e}")
            return False

    async def _handle_auth_code(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, auth_code: str
    ):
        user_id = update.effective_user.id

        try:
            await update.message.reply_text("正在处理授权码...")

            if not auth_code or len(auth_code) < 10:
                await update.message.reply_text(
                    "授权码格式无效\n\n"
                    "请确保复制完整的授权码（code=后面的部分）\n"
                    "授权码通常很长，请仔细检查是否完整复制"
                )
                return

            success = await self._exchange_code_for_tokens(auth_code)

            if success:
                if user_id in self.pending_auth:
                    del self.pending_auth[user_id]

                await update.message.reply_text(
                    "授权成功！\n\n"
                    "新令牌已获取并保存\n"
                    "配置文件已自动更新\n\n"
                    "现在您可以正常使用待办事项功能了！\n"
                    "使用 /token_status 查看令牌状态"
                )
            else:
                await update.message.reply_text(
                    "授权失败\n\n"
                    "可能原因：\n"
                    "• 授权码已过期或无效\n"
                    "• 网络连接问题\n"
                    "• 应用配置问题\n\n"
                    "请使用 /get_auth_link 重新获取授权链接"
                )

        except Exception as e:
            logger.error(f"处理授权码失败: {e}")
            await update.message.reply_text(f"处理授权码时出错: {str(e)}")

    async def _exchange_code_for_tokens(self, code: str) -> bool:
        try:
            client_id = Config.MS_TODO_CLIENT_ID
            redirect_uri = "http://localhost:3000/callback"

            if Config.MS_TODO_CLIENT_SECRET:
                authority = (
                    f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}"
                )
            else:
                authority = "https://login.microsoftonline.com/consumers"

            token_url = f"{authority}/oauth2/v2.0/token"
            scopes = "offline_access https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read"

            data = {
                "client_id": client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "scope": scopes,
            }

            if Config.MS_TODO_CLIENT_SECRET:
                data["client_secret"] = Config.MS_TODO_CLIENT_SECRET

            response = requests.post(token_url, data=data, verify=False)
            result = response.json()

            if "error" in result:
                logger.error(f"令牌交换失败: {result}")
                return False

            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")

            if access_token and refresh_token:
                self.todo_client.access_token = access_token
                self.todo_client.refresh_token = refresh_token

                return await self._save_tokens_to_env(access_token, refresh_token)

            return False

        except Exception as e:
            logger.error(f"令牌交换异常: {e}")
            return False

    async def _cleanup_auth_session(self, context: ContextTypes.DEFAULT_TYPE):
        """job_queue 调用的清理方法"""
        user_id = context.job.data
        if user_id in self.pending_auth:
            del self.pending_auth[user_id]
            logger.info(f"清理过期的授权会话: {user_id}")
    
    async def _delayed_cleanup_auth_session(self, user_id: int, delay: int):
        """延迟清理授权会话（不依赖 job_queue）"""
        await asyncio.sleep(delay)
        if user_id in self.pending_auth:
            del self.pending_auth[user_id]
            logger.info(f"清理过期的授权会话: {user_id}")

    async def _handle_menu_token_manage(self, query, context):
        message = "**令牌管理**\n\n"
        keyboard = [
            [InlineKeyboardButton("📊 查看令牌状态", callback_data="token_status")],
            [InlineKeyboardButton("🔄 刷新令牌", callback_data="token_refresh")],
            [InlineKeyboardButton("🔗 获取授权链接", callback_data="token_auth_link")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, reply_markup=reply_markup)

    async def _handle_token_status_callback(self, query, context):
        try:
            status_message = "**令牌状态**\n\n"

            def _mask_tail(value: str, tail_len: int = 8) -> str:
                if not value:
                    return "未设置"
                if len(value) <= tail_len:
                    return value
                return f"***{value[-tail_len:]}"

            if Config.MS_TODO_ACCESS_TOKEN:
                status_message += (
                    f"访问令牌: {_mask_tail(Config.MS_TODO_ACCESS_TOKEN)}\n"
                )
            else:
                status_message += "访问令牌: 未设置\n"

            if Config.MS_TODO_REFRESH_TOKEN:
                if Config.MS_TODO_REFRESH_TOKEN == "client_credentials_flow":
                    status_message += "刷新令牌: 客户端凭据流\n"
                else:
                    status_message += (
                        f"刷新令牌: {_mask_tail(Config.MS_TODO_REFRESH_TOKEN)}\n"
                    )
            else:
                status_message += "刷新令牌: 未设置\n"

            if Config.MS_TODO_CLIENT_SECRET:
                status_message += f"账户类型: 工作/学校账户\n"
            else:
                status_message += "账户类型: 个人账户\n"

            status_message += "\n测试连接...\n"
            test_result = await self.todo_client.get_task_lists()
            if "error" not in test_result:
                status_message += "令牌有效，连接正常"
            else:
                error_msg = str(test_result.get("error", "未知错误"))
                status_message += f"令牌可能已过期: {error_msg}\n\n"
                status_message += "使用刷新令牌或重新授权"

            await query.edit_message_text(status_message)

        except Exception as e:
            logger.error(f"检查令牌状态失败: {e}")
            await query.edit_message_text(f"检查令牌状态失败: {str(e)}")

    async def _handle_token_refresh_callback(self, query, context):
        try:
            await query.edit_message_text("正在刷新访问令牌...")

            success = await self.todo_client.refresh_token_manually()

            if success:
                new_access_token = self.todo_client.access_token
                new_refresh_token = self.todo_client.refresh_token

                if await self._save_tokens_to_env(new_access_token, new_refresh_token):
                    await query.edit_message_text(
                        "**令牌刷新成功！**\n\n"
                        f"新访问令牌: ***{new_access_token[-8:]}\n"
                        "已自动保存到配置文件"
                    )
                else:
                    await query.edit_message_text(
                        "**令牌刷新成功但保存失败**\n\n"
                        f"新访问令牌: ***{new_access_token[-8:]}\n"
                        "请联系管理员手动更新配置文件"
                    )
            else:
                await query.edit_message_text(
                    "**令牌刷新失败**\n\n"
                    "可能原因：\n"
                    "• 刷新令牌已过期（90天有效期）\n"
                    "• 网络连接问题\n"
                    "• 服务器配置问题\n\n"
                    "请重新获取授权链接"
                )

        except Exception as e:
            logger.error(f"刷新令牌失败: {e}")
            await query.edit_message_text(f"刷新令牌失败: {str(e)}")

    async def _handle_token_auth_link_callback(self, query, context):
        try:
            user_id = query.from_user.id

            auth_url = self._generate_auth_url()

            session_id = str(uuid.uuid4())
            self.pending_auth[user_id] = {
                "session_id": session_id,
                "timestamp": datetime.now(),
                "expecting_code": True,
            }

            message = f"""**Microsoft To-Do 授权**

请点击下面的链接进行授权：
{auth_url}

**授权步骤：**
1. 点击上面的链接
2. 使用您的Microsoft账户登录
3. 同意应用权限请求
4. 复制浏览器地址栏中的授权码（code=后面的部分）
5. 发送授权码给我

授权链接有效期：10分钟
会话ID: {session_id[:8]}...

获取授权码后，直接发送给我即可自动更新令牌！"""

            await query.edit_message_text(message)

            # 在后台延迟清理会话（不依赖 job_queue）
            asyncio.create_task(self._delayed_cleanup_auth_session(user_id, 600))

        except Exception as e:
            logger.error(f"生成授权链接失败: {e}")
            await query.edit_message_text(f"生成授权链接失败: {str(e)}")
