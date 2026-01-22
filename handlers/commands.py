"""
基础命令处理器
包含 start, help, list, active, summary, menu 等命令
"""
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes

from auth_manager import require_auth

logger = logging.getLogger(__name__)


class CommandHandlers:
    """基础命令处理器混入类"""

    @require_auth()
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = """**欢迎使用待办事项助手！** 🎉

**功能：**
• 创建待办事项（发送文本或图片）
• 标记任务完成
• 查看待办列表
• 搜索特定任务
• 更新任务内容
• 删除不需要的任务

发送消息描述您想要做的事情即可。

使用下方菜单按钮快速操作，或输入 /menu 显示主菜单。
        """

        keyboard = [
            ["📋 查看待办", "⏳ 未完成任务"],
            ["📊 任务摘要", "🔍 搜索任务"],
            ["🔐 令牌状态", "🆘 帮助"],
            ["📱 主菜单"],
        ]
        reply_markup = ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True, one_time_keyboard=False
        )

        await update.message.reply_text(welcome_message, reply_markup=reply_markup)

    @require_auth()
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        is_admin = self.auth_manager.is_admin(user_id)

        help_message = """**使用帮助**

**1. 创建待办事项**  
• "明天要开会讨论项目进度"
• "买牛奶、面包和鸡蛋"
• 发送图片（手写清单、白板等）

**2. 标记完成**  
• "完成了买牛奶的任务"
• "开会任务做完了"

**3. 查看和搜索**  
• /list - 查看所有待办事项
• /active - 查看未完成的待办事项
• /summary - 获取待办事项摘要
• "找一下关于会议的任务"

**4. 令牌管理**  
• /token_status - 查看当前令牌状态
• /get_auth_link - 获取授权链接更新令牌
• /refresh_token - 刷新访问令牌

**5. 更新任务**  
• "把买牛奶改成买酸奶"
• "更新会议时间为下午3点"

**6. 删除任务**  
• "删除买牛奶的任务"

**7. 小贴士**
• 直接用自然语言描述即可，无需特殊格式
• 支持发送图片识别待办事项
• 我会智能理解您的意图并执行相应操作"""

        # 管理员额外帮助
        if is_admin:
            help_message += """

**管理员命令** 👑
• /access_stats - 查看访问统计
• /blacklist_add <user_id> - 封禁用户
• /blacklist_remove <user_id> - 解封用户
• /whitelist_add <user_id> - 添加临时访问权限
• /whitelist_remove <user_id> - 移除临时访问权限"""

        await update.message.reply_text(help_message, parse_mode="Markdown")

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        menu_message = "**主菜单**\n\n请选择您要执行的操作："

        keyboard = [
            [
                InlineKeyboardButton("📋 查看所有待办", callback_data="menu_list_all"),
                InlineKeyboardButton("⏳ 未完成任务", callback_data="menu_list_active"),
            ],
            [
                InlineKeyboardButton("📊 任务摘要", callback_data="menu_summary"),
                InlineKeyboardButton("🔍 搜索任务", callback_data="menu_search"),
            ],
            [
                InlineKeyboardButton(
                    "✅ 快速完成", callback_data="menu_quick_complete"
                ),
                InlineKeyboardButton("🗑️ 快速删除", callback_data="menu_quick_delete"),
            ],
            [
                InlineKeyboardButton("🔐 令牌管理", callback_data="menu_token_manage"),
                InlineKeyboardButton("🆘 帮助", callback_data="menu_help"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            menu_message, reply_markup=reply_markup, parse_mode="Markdown"
        )

    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        try:
            todos = await self.todo_client.list_todos()

            if not todos:
                await update.message.reply_text(
                    "您还没有任何待办事项。发送消息创建第一个吧！"
                )
                return

            message = "**所有待办事项：**\n\n"

            display_todos = todos[:15]

            for i, todo in enumerate(display_todos, 1):
                status = "" if todo.get("completed", False) else ""
                title = todo.get("title", "N/A")
                description = todo.get("description", "")
                todo_id = todo.get("id", "N/A")

                display_title = title[:40] + "..." if len(title) > 40 else title
                message += f"{status} **{i}. {display_title}**\n"

                if description:
                    display_desc = (
                        description[:60] + "..."
                        if len(description) > 60
                        else description
                    )
                    message += f"   {display_desc}\n"

                message += "\n"

                if len(message) > 3500:
                    remaining = len(todos) - i
                    if remaining > 0:
                        message += f"... 还有 {remaining} 个任务，使用具体命令查看更多"
                    break

            if len(todos) > 15:
                message += f"\n总共 {len(todos)} 个任务，显示前 {min(15, len(display_todos))} 个"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"获取待办事项列表失败: {e}")
            await update.message.reply_text("获取待办事项列表时出现错误，请稍后重试。")

    async def active_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        try:
            todos = await self.todo_client.list_active_todos()

            if not todos:
                await update.message.reply_text("太棒了！您没有未完成的待办事项。")
                return

            message = "**未完成的待办事项：**\n\n"

            display_todos = todos[:12]

            for i, todo in enumerate(display_todos, 1):
                title = todo.get("title", "N/A")
                description = todo.get("description", "")
                todo_id = todo.get("id", "N/A")

                display_title = title[:40] + "..." if len(title) > 40 else title
                message += f"**{i}. {display_title}**\n"

                if description:
                    display_desc = (
                        description[:60] + "..."
                        if len(description) > 60
                        else description
                    )
                    message += f"   {display_desc}\n"

                message += "\n"

                if len(message) > 3500:
                    remaining = len(todos) - i
                    if remaining > 0:
                        message += f"... 还有 {remaining} 个未完成任务"
                    break

            if len(todos) > 12:
                message += f"\n总共 {len(todos)} 个未完成任务，显示前 {min(12, len(display_todos))} 个"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"获取活跃待办事项失败: {e}")
            await update.message.reply_text("获取待办事项时出现错误，请稍后重试。")

    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        try:
            summary = await self.todo_client.summarize_active_todos()

            if not summary:
                await update.message.reply_text("暂无待办事项摘要。")
                return

            await update.message.reply_text(f"**待办事项摘要：**\n\n{summary}")

        except Exception as e:
            logger.error(f"获取待办事项摘要失败: {e}")
            await update.message.reply_text("获取摘要时出现错误，请稍后重试。")
