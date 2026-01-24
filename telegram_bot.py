"""
Microsoft Todo Telegram Bot
主入口文件 - 通过混入类组合各处理器模块
"""
import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from config import Config
from ai_service import AIService
from microsoft_todo_client import MicrosoftTodoDirectClient
from auth_manager import auth_manager

from handlers.commands import CommandHandlers
from handlers.menu import MenuHandlers
from handlers.token import TokenHandlers
from handlers.admin import AdminHandlers
from handlers.message import MessageHandlers
from handlers.utils import UtilsHandlers

logger = logging.getLogger(__name__)


class TodoTelegramBot(
    CommandHandlers, 
    MenuHandlers, 
    TokenHandlers, 
    AdminHandlers, 
    MessageHandlers, 
    UtilsHandlers
):
    """
    主 Bot 类，通过多重继承组合所有处理器功能
    
    继承的处理器：
    - CommandHandlers: 基础命令 (start, help, list, active, summary, menu)
    - MenuHandlers: 菜单回调处理
    - TokenHandlers: Token管理相关
    - AdminHandlers: 管理员命令
    - MessageHandlers: 文本和图片消息处理
    - UtilsHandlers: 工具方法
    """

    def __init__(self):
        self.config = Config()
        self.ai_service = AIService()
        self.todo_client = MicrosoftTodoDirectClient()
        self.application = None
        self.pending_auth = {}
        self.pending_decompose = {}
        self.auth_manager = auth_manager

    async def start(self):
        """启动 Bot"""
        config_errors = Config.validate()
        if config_errors:
            raise ValueError(f"配置错误: {', '.join(config_errors)}")

        logger.info("使用直接Microsoft Graph API客户端")

        builder = Application.builder().token(Config.TELEGRAM_BOT_TOKEN)
        if Config.TELEGRAM_BASE_URL:
            builder = builder.base_url(Config.TELEGRAM_BASE_URL)
            logger.info(f"使用自定义 Telegram Base URL: {Config.TELEGRAM_BASE_URL}")

        self.application = builder.build()

        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("list", self.list_command))
        self.application.add_handler(CommandHandler("active", self.active_command))
        self.application.add_handler(CommandHandler("summary", self.summary_command))
        self.application.add_handler(CommandHandler("refresh_token", self.refresh_token_command))
        self.application.add_handler(CommandHandler("get_auth_link", self.get_auth_link_command))
        self.application.add_handler(CommandHandler("token_status", self.token_status_command))

        self.application.add_handler(CommandHandler("blacklist_add", self.blacklist_add_command))
        self.application.add_handler(CommandHandler("blacklist_remove", self.blacklist_remove_command))
        self.application.add_handler(CommandHandler("whitelist_add", self.whitelist_add_command))
        self.application.add_handler(CommandHandler("whitelist_remove", self.whitelist_remove_command))
        self.application.add_handler(CommandHandler("access_stats", self.access_stats_command))

        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        self.application.add_error_handler(self.error_handler)

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

        logger.info("Telegram Bot已启动")

    async def stop(self):
        """停止 Bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        await self.todo_client.close()
        logger.info("Telegram Bot已停止")

    async def run_forever(self):
        """持续运行 Bot"""
        try:
            await self.start()
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
        finally:
            await self.stop()
