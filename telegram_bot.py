"""
Microsoft Todo Telegram Bot
主入口文件 - 通过混入类组合各处理器模块
"""
import asyncio
import logging
from io import BytesIO
from typing import Optional
from telegram import (
    Update,
    Bot,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
)

try:
    from telegram import ReactionTypeEmoji  # Bot API >= 6.7 / PTB >= 21.x
except Exception:
    ReactionTypeEmoji = None  # 兼容旧版本，运行时判定
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from PIL import Image
import requests
from datetime import datetime, timedelta

from config import Config
from ai_service import AIService
from microsoft_todo_client import MicrosoftTodoDirectClient
from auth_manager import auth_manager, require_auth, require_admin

# 导入处理器混入类
from handlers.commands import CommandHandlers
from handlers.menu import MenuHandlers
from handlers.token import TokenHandlers
from handlers.admin import AdminHandlers

import os
import uuid

logger = logging.getLogger(__name__)


class TodoTelegramBot(CommandHandlers, MenuHandlers, TokenHandlers, AdminHandlers):
    """
    主 Bot 类，通过多重继承组合所有处理器功能
    
    继承的处理器：
    - CommandHandlers: 基础命令 (start, help, list, active, summary, menu)
    - MenuHandlers: 菜单回调处理
    - TokenHandlers: Token管理相关
    - AdminHandlers: 管理员命令 (黑白名单, 统计)
    """

    def __init__(self):
        self.config = Config()
        self.ai_service = AIService()
        self.todo_client = MicrosoftTodoDirectClient()
        self.application = None
        self.pending_auth = {}
        self.auth_manager = auth_manager  # 使用全局鉴权管理器

    async def start(self):
        config_errors = Config.validate()
        if config_errors:
            raise ValueError(f"配置错误: {', '.join(config_errors)}")

        logger.info("使用直接Microsoft Graph API客户端")

        builder = Application.builder().token(Config.TELEGRAM_BOT_TOKEN)
        if Config.TELEGRAM_BASE_URL:
            # 使用自定义的 Telegram Bot API Base URL（例如通过边缘节点/反向代理）
            builder = builder.base_url(Config.TELEGRAM_BASE_URL)
            logger.info(f"使用自定义 Telegram Base URL: {Config.TELEGRAM_BASE_URL}")

        self.application = builder.build()

        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("list", self.list_command))
        self.application.add_handler(CommandHandler("active", self.active_command))
        self.application.add_handler(CommandHandler("summary", self.summary_command))
        self.application.add_handler(
            CommandHandler("refresh_token", self.refresh_token_command)
        )
        self.application.add_handler(
            CommandHandler("get_auth_link", self.get_auth_link_command)
        )
        self.application.add_handler(
            CommandHandler("token_status", self.token_status_command)
        )

        # 鉴权管理命令（仅管理员）
        self.application.add_handler(
            CommandHandler("blacklist_add", self.blacklist_add_command)
        )
        self.application.add_handler(
            CommandHandler("blacklist_remove", self.blacklist_remove_command)
        )
        self.application.add_handler(
            CommandHandler("whitelist_add", self.whitelist_add_command)
        )
        self.application.add_handler(
            CommandHandler("whitelist_remove", self.whitelist_remove_command)
        )
        self.application.add_handler(
            CommandHandler("access_stats", self.access_stats_command)
        )

        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))

        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text)
        )
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        # 添加错误处理器
        self.application.add_error_handler(self.error_handler)

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(
            drop_pending_updates=True,  # 跳过启动前的旧消息
            allowed_updates=Update.ALL_TYPES
        )

        logger.info("Telegram Bot已启动")

    async def _auto_delete_messages(self, chat_id: int, message_ids: list, delay: int = 30):
        """延迟删除消息"""
        await asyncio.sleep(delay)
        for msg_id in message_ids:
            try:
                await self.application.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                logger.debug(f"已自动删除消息 {msg_id}")
            except Exception as e:
                logger.debug(f"删除消息失败 {msg_id}: {e}")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 Telegram 更新过程中的错误"""
        # 只记录关键错误，忽略网络波动等临时性错误
        import traceback
        from telegram.error import NetworkError, TimedOut, RetryAfter
        
        error = context.error
        
        # 忽略常见的网络错误
        if isinstance(error, (NetworkError, TimedOut)):
            logger.debug(f"网络错误（已忽略）: {error}")
            return
        
        if isinstance(error, RetryAfter):
            logger.debug(f"速率限制（已忽略）: {error}")
            return
        
        # 记录其他错误
        logger.error(f"更新 {update} 时发生错误: {error}")
        logger.error("".join(traceback.format_exception(None, error, error.__traceback__)))

    async def stop(self):
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        await self.todo_client.close()
        logger.info("Telegram Bot已停止")

    def _is_admin(self, user_id: int) -> bool:
        """向后兼容的方法"""
        return self.auth_manager.is_admin(user_id)

    async def _react(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_id: int,
        emoji: str,
    ):
        """对消息添加表态（reaction）- 异步版本"""
        # 映射到 Telegram 支持的标准 reaction 表情
        emoji_map = {"🤖": "👍", "🖼️": "🔥", "✅": "👏", "❌": "👎"}
        reaction_emoji = emoji_map.get(
            emoji, emoji
        )  # 如果emoji本身就是标准表情，直接使用

        try:
            # 导入 ReactionTypeEmoji（Bot API >= 6.7）
            try:
                from telegram import ReactionTypeEmoji
                
                # 使用 ReactionTypeEmoji 对象
                reaction = ReactionTypeEmoji(emoji=reaction_emoji)
                
                await context.bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=message_id,
                    reaction=[reaction],
                    is_big=False
                )
                logger.debug(f"表态成功: {reaction_emoji}")
                
            except ImportError:
                # 旧版本的 python-telegram-bot 不支持
                logger.debug("ReactionTypeEmoji 不可用，跳过表态功能")
                
        except Exception as e:
            # 如果 Bot API 不支持表态功能，记录日志但不影响主功能
            logger.debug(f"表态失败 (这是正常的，部分 Bot API 服务器不支持此功能): {e}")

    async def _check_admin_permission(self, update: Update) -> bool:
        """向后兼容的方法（已弃用，请使用 @require_auth 装饰器）"""
        allowed, error_msg = await self.auth_manager.check_permission(update)
        if not allowed and error_msg:
            await update.message.reply_text(error_msg, parse_mode="Markdown")
        return allowed

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        try:
            user_text = update.message.text
            user_id = update.effective_user.id
            logger.info(f"收到文本消息: {user_text}")

            if user_id in self.pending_auth and self.pending_auth[user_id].get(
                "expecting_code"
            ):
                await self._handle_auth_code(update, context, user_text)
                return

            if await self._handle_keyboard_button(update, context, user_text):
                return

            # 对消息进行表态（reaction）而非回复表情
            await self._react(
                context, update.effective_chat.id, update.message.message_id, "🤖"
            )

            existing_todos = await self.todo_client.list_todos()

            analysis = await self.ai_service.analyze_text_for_todos(
                user_text, existing_todos
            )

            result = await self.execute_action(analysis)

            response = await self.ai_service.generate_response(analysis, result)

            # 处理完成后发送新的一条消息
            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            await update.message.reply_text("处理消息时出现错误，请稍后重试。")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        try:
            # 对消息进行表态（reaction）而非回复表情
            await self._react(
                context, update.effective_chat.id, update.message.message_id, "🖼️"
            )

            photo = update.message.photo[-1]
            file = await photo.get_file()

            if file.file_size > Config.MAX_IMAGE_SIZE:
                await update.message.reply_text("图片文件过大，请发送小于5MB的图片。")
                return

            image_data = BytesIO()
            await file.download_to_memory(image_data)
            image_bytes = image_data.getvalue()

            image_format = "jpeg"
            try:
                with Image.open(BytesIO(image_bytes)) as img:
                    image_format = img.format.lower()
            except Exception:
                pass

            if image_format not in Config.ALLOWED_IMAGE_FORMATS:
                await update.message.reply_text(
                    "不支持的图片格式。支持的格式：jpg, jpeg, png, gif, webp"
                )
                return

            logger.info(
                f"收到图片消息，格式: {image_format}, 大小: {len(image_bytes)} bytes"
            )

            existing_todos = await self.todo_client.list_todos()
            caption = (
                (update.message.caption or "").strip()
                if update.message and update.message.caption
                else None
            )

            analysis = await self.ai_service.analyze_image_for_todos(
                image_bytes, image_format, existing_todos, caption
            )

            result = await self.execute_action(analysis)

            response = await self.ai_service.generate_response(analysis, result)

            # 处理完成后发送新的一条消息
            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"处理图片消息失败: {e}")
            await update.message.reply_text("处理图片时出现错误，请稍后重试。")

    async def execute_action(self, analysis: dict) -> any:
        action = analysis.get("action", "QUERY")

        try:
            if action == "CREATE":
                if "items" in analysis:
                    results = []
                    for item in analysis["items"]:
                        item_text = (
                            f"{item.get('title', '')} {item.get('description', '')}"
                        )

                        existing_todos = await self.todo_client.list_todos()

                        detailed_analysis = (
                            await self.ai_service.analyze_text_for_todos(
                                item_text, existing_todos
                            )
                        )

                        result = await self.todo_client.create_todo(
                            title=detailed_analysis.get("title", item.get("title", "")),
                            description=detailed_analysis.get(
                                "description", item.get("description", "")
                            ),
                            due_date=detailed_analysis.get("due_date"),
                            reminder_date=detailed_analysis.get("reminder_date"),
                            reminder_time=detailed_analysis.get("reminder_time"),
                        )
                        results.append(result)
                    return results
                else:
                    return await self.todo_client.create_todo(
                        title=analysis.get("title", ""),
                        description=analysis.get("description", ""),
                        due_date=analysis.get("due_date"),
                        reminder_date=analysis.get("reminder_date"),
                        reminder_time=analysis.get("reminder_time"),
                    )

            elif action == "UPDATE":
                todo_id = analysis.get("todo_id", "")
                if not todo_id:
                    search_results = await self.todo_client.search_todos_by_title(
                        analysis.get("title", "")
                    )
                    if search_results:
                        todo_id = search_results[0].get("id", "")

                if todo_id:
                    # 只传递非空字段
                    update_params = {"todo_id": todo_id}
                    
                    if analysis.get("title"):
                        update_params["title"] = analysis.get("title")
                    if analysis.get("description"):
                        update_params["description"] = analysis.get("description")
                    if analysis.get("due_date"):
                        update_params["due_date"] = analysis.get("due_date")
                    if analysis.get("reminder_date"):
                        update_params["reminder_date"] = analysis.get("reminder_date")
                    if analysis.get("reminder_time"):
                        update_params["reminder_time"] = analysis.get("reminder_time")
                    
                    logger.info(f"更新任务参数: {update_params}")
                    return await self.todo_client.update_todo(**update_params)
                else:
                    return {"error": "未找到要更新的待办事项"}

            elif action == "COMPLETE":
                todo_id = analysis.get("todo_id", "")
                if not todo_id:
                    search_query = analysis.get(
                        "search_query", analysis.get("title", "")
                    )
                    if search_query:
                        search_results = await self.todo_client.search_todos_by_title(
                            search_query
                        )
                        if search_results:
                            todo_id = search_results[0].get("id", "")

                if todo_id:
                    return await self.todo_client.complete_todo(todo_id)
                else:
                    return {"error": "未找到要完成的待办事项"}

            elif action == "DELETE":
                todo_id = analysis.get("todo_id", "")
                if not todo_id:
                    search_query = analysis.get(
                        "search_query", analysis.get("title", "")
                    )
                    if search_query:
                        search_results = await self.todo_client.search_todos_by_title(
                            search_query
                        )
                        if search_results:
                            todo_id = search_results[0].get("id", "")

                if todo_id:
                    return await self.todo_client.delete_todo(todo_id)
                else:
                    return {"error": "未找到要删除的待办事项"}

            elif action == "LIST":
                return await self.todo_client.list_todos()

            elif action == "SEARCH":
                search_query = analysis.get("search_query", "")
                if search_query:
                    return await self.todo_client.search_todos_by_title(search_query)
                else:
                    return {"error": "搜索关键词为空"}

            else:
                return {
                    "message": "我理解了您的消息，但不确定需要执行什么具体操作。您可以更明确地告诉我您想要做什么。"
                }

        except Exception as e:
            logger.error(f"执行操作失败: {e}")
            return {"error": f"操作执行失败: {str(e)}"}

    async def run_forever(self):
        try:
            await self.start()
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
        finally:
            await self.stop()
