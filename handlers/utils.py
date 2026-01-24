"""
工具方法
包含 reaction、自动删除消息、错误处理等通用功能
"""
import asyncio
import logging
import traceback

from telegram.ext import ContextTypes
from telegram.error import NetworkError, TimedOut, RetryAfter

logger = logging.getLogger(__name__)


class UtilsHandlers:
    """工具方法混入类"""

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
        error = context.error
        
        if isinstance(error, (NetworkError, TimedOut)):
            logger.debug(f"网络错误（已忽略）: {error}")
            return
        
        if isinstance(error, RetryAfter):
            logger.debug(f"速率限制（已忽略）: {error}")
            return
        
        logger.error(f"更新 {update} 时发生错误: {error}")
        logger.error("".join(traceback.format_exception(None, error, error.__traceback__)))

    async def _react(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_id: int,
        emoji: str,
    ):
        """对消息添加表态（reaction）"""
        emoji_map = {"🤖": "👍", "🖼️": "🔥", "✅": "👏", "❌": "👎"}
        reaction_emoji = emoji_map.get(emoji, emoji)

        try:
            try:
                from telegram import ReactionTypeEmoji
                
                reaction = ReactionTypeEmoji(emoji=reaction_emoji)
                
                await context.bot.set_message_reaction(
                    chat_id=chat_id,
                    message_id=message_id,
                    reaction=[reaction],
                    is_big=False
                )
                logger.debug(f"表态成功: {reaction_emoji}")
                
            except ImportError:
                logger.debug("ReactionTypeEmoji 不可用，跳过表态功能")
                
        except Exception as e:
            logger.debug(f"表态失败: {e}")

    async def _check_admin_permission(self, update) -> bool:
        """检查用户权限"""
        allowed, error_msg = await self.auth_manager.check_permission(update)
        if not allowed and error_msg:
            await update.message.reply_text(error_msg, parse_mode="Markdown")
        return allowed
