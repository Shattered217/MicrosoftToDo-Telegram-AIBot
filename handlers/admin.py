"""
管理员命令处理器
包含黑白名单管理、访问统计等管理员专用功能
"""
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from auth_manager import require_admin

logger = logging.getLogger(__name__)


class AdminHandlers:
    """管理员命令处理器混入类"""

    @require_admin
    async def blacklist_add_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """添加用户到黑名单（仅管理员）"""
        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "**使用方法：**\n"
                    "`/blacklist_add <user_id>`\n\n"
                    "示例: `/blacklist_add 123456789`",
                    parse_mode="Markdown",
                )
                return

            user_id = int(context.args[0])
            success = self.auth_manager.add_to_blacklist(user_id)

            if success:
                await update.message.reply_text(
                    f"✅ 用户 `{user_id}` 已加入黑名单", parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ 无法将管理员加入黑名单", parse_mode="Markdown"
                )

        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID，必须是数字")
        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            await update.message.reply_text(f"操作失败: {str(e)}")

    @require_admin
    async def blacklist_remove_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """从黑名单移除用户（仅管理员）"""
        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "**使用方法：**\n"
                    "`/blacklist_remove <user_id>`\n\n"
                    "示例: `/blacklist_remove 123456789`",
                    parse_mode="Markdown",
                )
                return

            user_id = int(context.args[0])
            self.auth_manager.remove_from_blacklist(user_id)
            await update.message.reply_text(
                f"✅ 用户 `{user_id}` 已从黑名单移除", parse_mode="Markdown"
            )

        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID，必须是数字")
        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            await update.message.reply_text(f"操作失败: {str(e)}")

    @require_admin
    async def whitelist_add_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """添加用户到白名单（临时访问权限，仅管理员）"""
        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "**使用方法：**\n"
                    "`/whitelist_add <user_id>`\n\n"
                    "示例: `/whitelist_add 123456789`\n\n"
                    "白名单用户将获得临时访问权限",
                    parse_mode="Markdown",
                )
                return

            user_id = int(context.args[0])
            self.auth_manager.add_to_whitelist(user_id)
            await update.message.reply_text(
                f"✅ 用户 `{user_id}` 已加入白名单（临时访问权限）",
                parse_mode="Markdown",
            )

        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID，必须是数字")
        except Exception as e:
            logger.error(f"添加白名单失败: {e}")
            await update.message.reply_text(f"操作失败: {str(e)}")

    @require_admin
    async def whitelist_remove_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """从白名单移除用户（仅管理员）"""
        try:
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "**使用方法：**\n"
                    "`/whitelist_remove <user_id>`\n\n"
                    "示例: `/whitelist_remove 123456789`",
                    parse_mode="Markdown",
                )
                return

            user_id = int(context.args[0])
            self.auth_manager.remove_from_whitelist(user_id)
            await update.message.reply_text(
                f"✅ 用户 `{user_id}` 已从白名单移除", parse_mode="Markdown"
            )

        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID，必须是数字")
        except Exception as e:
            logger.error(f"移除白名单失败: {e}")
            await update.message.reply_text(f"操作失败: {str(e)}")

    @require_admin
    async def access_stats_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """查看访问统计（仅管理员）"""
        try:
            stats = self.auth_manager.get_access_stats()

            if not stats:
                await update.message.reply_text("暂无访问记录")
                return

            # 按访问次数排序
            sorted_stats = sorted(
                stats.items(), key=lambda x: x[1]["count"], reverse=True
            )

            message = "**访问统计**\n\n"

            for user_id, data in sorted_stats[:20]:  # 只显示前20个
                username = data.get("username", "未知")
                count = data.get("count", 0)
                last_access = data.get("last_access", datetime.now())
                is_admin = "👑" if self.auth_manager.is_admin(user_id) else ""
                is_blacklisted = (
                    "🚫" if self.auth_manager.is_blacklisted(user_id) else ""
                )
                is_whitelisted = (
                    "✅" if self.auth_manager.is_whitelisted(user_id) else ""
                )

                flags = f"{is_admin}{is_blacklisted}{is_whitelisted}"

                message += f"{flags} `{user_id}` (@{username})\n"
                message += f"   访问 {count} 次\n"
                message += f"   最近: {last_access.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                if len(message) > 3500:
                    await update.message.reply_text(message, parse_mode="Markdown")
                    message = ""

            if message:
                await update.message.reply_text(message, parse_mode="Markdown")

            # 发送汇总信息
            summary = f"\n**统计汇总：**\n"
            summary += f"• 总用户数: {len(stats)}\n"
            summary += f"• 管理员数: {len(self.auth_manager.admin_ids)}\n"
            summary += f"• 白名单用户: {len(self.auth_manager.whitelist)}\n"
            summary += f"• 黑名单用户: {len(self.auth_manager.blacklist)}\n"
            summary += f"• 速率限制: {self.auth_manager.rate_limit_max_requests}次/{self.auth_manager.rate_limit_window}秒"

            await update.message.reply_text(summary, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"获取访问统计失败: {e}")
            await update.message.reply_text(f"获取统计失败: {str(e)}")
