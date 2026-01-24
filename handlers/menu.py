"""
菜单和回调处理器
包含所有菜单按钮和 InlineKeyboard 回调处理
"""
import logging
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class MenuHandlers:
    """菜单和回调处理器混入类"""

    async def handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            username = query.from_user.username or "未知用户"
            logger.warning(
                f"未授权用户尝试使用回调功能: ID={user_id}, 用户名=@{username}"
            )
            await query.edit_message_text("您没有权限执行此操作。")
            return

        callback_data = query.data

        # 处理任务拆解相关回调
        if callback_data == "decompose_confirm_all":
            await self._handle_decompose_confirm_all(query, context, user_id)
        elif callback_data == "decompose_cancel":
            await self._handle_decompose_cancel(query, context, user_id)
        elif callback_data == "decompose_create_original":
            await self._handle_decompose_create_original(query, context, user_id)
        elif callback_data == "menu_list_all":
            await self._handle_menu_list_all(query, context)
        elif callback_data == "menu_list_active":
            await self._handle_menu_list_active(query, context)
        elif callback_data == "menu_summary":
            await self._handle_menu_summary(query, context)
        elif callback_data == "menu_search":
            await self._handle_menu_search(query, context)
        elif callback_data == "menu_quick_complete":
            await self._handle_menu_quick_complete(query, context)
        elif callback_data == "menu_quick_delete":
            await self._handle_menu_quick_delete(query, context)
        elif callback_data == "menu_token_manage":
            await self._handle_menu_token_manage(query, context)
        elif callback_data == "menu_help":
            await self._handle_menu_help(query, context)
        elif callback_data.startswith("complete_") or callback_data.startswith("comp_"):
            await self._handle_complete_todo(query, context, callback_data)
        elif callback_data.startswith("delete_") or callback_data.startswith("del_"):
            await self._handle_delete_todo(query, context, callback_data)
        elif callback_data == "token_status":
            await self._handle_token_status_callback(query, context)
        elif callback_data == "token_refresh":
            await self._handle_token_refresh_callback(query, context)
        elif callback_data == "token_auth_link":
            await self._handle_token_auth_link_callback(query, context)

    async def _handle_decompose_confirm_all(self, query, context, user_id):
        """处理确认全部创建拆解任务"""
        try:
            decompose_result = self.pending_decompose.get(user_id)
            if not decompose_result:
                await query.edit_message_text("❌ 拆解会话已过期，请重新发送任务")
                return
            
            subtasks = decompose_result.get('subtasks', [])
            if not subtasks:
                await query.edit_message_text("❌ 没有找到子任务")
                return
            
            await query.edit_message_text("⏳ 正在创建子任务...")
            
            created_count = 0
            failed_count = 0
            
            for task in subtasks:
                result = await self.todo_client.create_todo(
                    title=task.get('title', '子任务'),
                    description=task.get('description', ''),
                    due_date=task.get('due_date'),
                    reminder_date=task.get('reminder_date'),
                    reminder_time=task.get('reminder_time'),
                )
                if 'error' not in result:
                    created_count += 1
                else:
                    failed_count += 1
            
            # 清理会话
            del self.pending_decompose[user_id]
            
            if failed_count == 0:
                await query.edit_message_text(
                    f"✅ 成功创建 {created_count} 个子任务！"
                )
            else:
                await query.edit_message_text(
                    f"⚠️ 创建完成：成功 {created_count} 个，失败 {failed_count} 个"
                )
                
        except Exception as e:
            logger.error(f"创建拆解任务失败: {e}")
            await query.edit_message_text(f"❌ 创建失败: {str(e)}")
    
    async def _handle_decompose_cancel(self, query, context, user_id):
        """处理取消拆解"""
        if user_id in self.pending_decompose:
            del self.pending_decompose[user_id]
        await query.edit_message_text("❌ 已取消任务创建")
    
    async def _handle_decompose_create_original(self, query, context, user_id):
        """处理不拆解，创建原任务"""
        try:
            decompose_result = self.pending_decompose.get(user_id)
            if not decompose_result:
                await query.edit_message_text("❌ 会话已过期，请重新发送任务")
                return
            
            original_task = decompose_result.get('original_task', '任务')
            
            # 创建原始任务
            result = await self.todo_client.create_todo(
                title=original_task[:50],
                description='',
            )
            
            # 清理会话
            del self.pending_decompose[user_id]
            
            if 'error' not in result:
                await query.edit_message_text(f"✅ 已创建任务「{original_task[:20]}」")
            else:
                await query.edit_message_text(f"❌ 创建失败: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"创建原任务失败: {e}")
            await query.edit_message_text(f"❌ 创建失败: {str(e)}")

    async def _handle_menu_list_all(self, query, context):
        try:
            todos = await self.todo_client.list_todos()

            if not todos:
                await query.edit_message_text(
                    "您还没有任何待办事项。发送消息创建第一个吧！"
                )
                return

            message = "**所有待办事项：**\n\n"
            for i, todo in enumerate(todos[:8], 1):
                status = "" if todo.get("completed", False) else ""
                title = todo.get("title", "N/A")
                display_title = title[:30] + "..." if len(title) > 30 else title
                message += f"{status} **{i}. {display_title}**\n"

            if len(todos) > 8:
                message += (
                    f"\n... 还有 {len(todos) - 8} 个任务\n使用 /list 查看完整列表"
                )

            await query.edit_message_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"菜单查看待办事项失败: {e}")
            await query.edit_message_text("获取待办事项时出现错误")

    async def _handle_menu_list_active(self, query, context):
        try:
            todos = await self.todo_client.list_active_todos()

            if not todos:
                await query.edit_message_text("太棒了！您没有未完成的待办事项。")
                return

            message = "**未完成的待办事项：**\n\n"
            keyboard = []

            for i, todo in enumerate(todos[:6], 1):
                title = todo.get("title", "N/A")
                todo_id = todo.get("id", "")
                display_title = title[:30] + "..." if len(title) > 30 else title
                message += f"**{i}. {display_title}**\n"

                if i <= 4:
                    short_id = todo_id[:20] if todo_id else str(i)
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                f"完成 {i}", callback_data=f"comp_{short_id}"
                            )
                        ]
                    )

            if len(todos) > 6:
                message += f"\n... 还有 {len(todos) - 6} 个任务"

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"菜单查看未完成任务失败: {e}")
            await query.edit_message_text("获取待办事项时出现错误")

    async def _handle_menu_summary(self, query, context):
        try:
            summary = await self.todo_client.summarize_active_todos()

            if not summary:
                await query.edit_message_text("暂无待办事项摘要。")
                return

            await query.edit_message_text(f"**待办事项摘要：**\n\n{summary}")

        except Exception as e:
            logger.error(f"菜单获取摘要失败: {e}")
            await query.edit_message_text("获取摘要时出现错误")

    async def _handle_menu_search(self, query, context):
        await query.edit_message_text(
            "**搜索任务**\n\n"
            "请发送您要搜索的关键词，例如：\n"
            '• "找一下关于会议的任务"\n'
            '• "搜索买菜相关的待办"\n'
            '• "查找明天的任务"'
        )

    async def _handle_menu_quick_complete(self, query, context):
        try:
            todos = await self.todo_client.list_active_todos()

            if not todos:
                await query.edit_message_text("太棒了！您没有未完成的待办事项。")
                return

            message = "**快速完成任务**\n\n选择要完成的任务："
            keyboard = []

            for i, todo in enumerate(todos[:10], 1):
                title = todo.get("title", "N/A")
                todo_id = todo.get("id", "")
                display_title = title[:20] + "..." if len(title) > 20 else title
                short_id = todo_id[:20] if todo_id else str(i)
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{display_title}", callback_data=f"comp_{short_id}"
                        )
                    ]
                )

            if len(todos) > 10:
                message += f"\n显示前10个任务，共{len(todos)}个未完成任务"

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"快速完成菜单失败: {e}")
            await query.edit_message_text("获取待办事项时出现错误")

    async def _handle_menu_quick_delete(self, query, context):
        try:
            todos = await self.todo_client.list_todos()

            if not todos:
                await query.edit_message_text("您还没有任何待办事项。")
                return

            message = "**快速删除任务**\n\n选择要删除的任务（此操作不可撤销）："
            keyboard = []

            for i, todo in enumerate(todos[:10], 1):
                title = todo.get("title", "N/A")
                todo_id = todo.get("id", "")
                status = "" if todo.get("completed", False) else ""
                display_title = title[:15] + "..." if len(title) > 15 else title
                short_id = todo_id[:20] if todo_id else str(i)
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{status} {display_title}", callback_data=f"del_{short_id}"
                        )
                    ]
                )

            if len(todos) > 10:
                message += f"\n显示前10个任务，共{len(todos)}个任务"

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"快速删除菜单失败: {e}")
            await query.edit_message_text("获取待办事项时出现错误")

    async def _handle_menu_help(self, query, context):
        help_message = """
**使用帮助**

**创建待办事项**
• "明天要开会讨论项目进度"
• "买牛奶、面包和鸡蛋"
• 发送图片（手写清单、白板等）

**标记完成**
• "完成了买牛奶的任务"
• "开会任务做完了"

**查看和搜索**
• 使用菜单按钮快速操作
• "找一下关于会议的任务"

**小贴士**
• 直接用自然语言描述即可
• 支持发送图片识别待办事项
• 使用 /menu 显示主菜单
        """
        await query.edit_message_text(help_message)

    async def _handle_complete_todo(self, query, context, callback_data):
        try:
            if callback_data.startswith("comp_"):
                short_id = callback_data.replace("comp_", "")
                todos = await self.todo_client.list_active_todos()
                todo_id = None
                for todo in todos:
                    if todo.get("id", "").startswith(short_id):
                        todo_id = todo.get("id")
                        break
            else:
                todo_id = callback_data.replace("complete_", "")

            if not todo_id:
                await query.edit_message_text("未找到对应的任务")
                return

            result = await self.todo_client.complete_todo(todo_id)

            if "error" in result:
                await query.edit_message_text(f"完成任务失败: {result['error']}")
            else:
                await query.edit_message_text("任务已标记为完成！")

        except Exception as e:
            logger.error(f"完成待办事项失败: {e}")
            await query.edit_message_text("完成任务时出现错误")

    async def _handle_delete_todo(self, query, context, callback_data):
        try:
            if callback_data.startswith("del_"):
                short_id = callback_data.replace("del_", "")
                todos = await self.todo_client.list_todos()
                todo_id = None
                for todo in todos:
                    if todo.get("id", "").startswith(short_id):
                        todo_id = todo.get("id")
                        break
            else:
                todo_id = callback_data.replace("delete_", "")

            if not todo_id:
                await query.edit_message_text("未找到对应的任务")
                return

            result = await self.todo_client.delete_todo(todo_id)

            if "error" in result:
                await query.edit_message_text(f"删除任务失败: {result['error']}")
            else:
                await query.edit_message_text("任务已删除！")

        except Exception as e:
            logger.error(f"删除待办事项失败: {e}")
            await query.edit_message_text("删除任务时出现错误")

    async def _handle_keyboard_button(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
    ) -> bool:
        if text == "📋 查看待办":
            await self.list_command(update, context)
            return True
        elif text == "⏳ 未完成任务":
            await self.active_command(update, context)
            return True
        elif text == "📊 任务摘要":
            await self.summary_command(update, context)
            return True
        elif text == "🔍 搜索任务":
            await update.message.reply_text(
                "**搜索任务**\n\n"
                "请发送您要搜索的关键词，例如：\n"
                '• "找一下关于会议的任务"\n'
                '• "搜索买菜相关的待办"\n'
                '• "查找明天的任务"',
                parse_mode="Markdown",
            )
            return True
        elif text == "🔐 令牌状态":
            await self.token_status_command(update, context)
            return True
        elif text == "🆘 帮助":
            await self.help_command(update, context)
            return True
        elif text == "📱 主菜单":
            await self.menu_command(update, context)
            return True

        return False
