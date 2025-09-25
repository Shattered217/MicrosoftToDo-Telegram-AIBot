import asyncio
import logging
from io import BytesIO
from typing import Optional
from telegram import Update, Bot, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from PIL import Image
import requests
from datetime import datetime, timedelta

from config import Config
from ai_service import AIService
from microsoft_todo_client import MicrosoftTodoDirectClient
import os
import uuid

logger = logging.getLogger(__name__)

class TodoTelegramBot:
    
    def __init__(self):
        self.config = Config()
        self.ai_service = AIService()
        self.todo_client = MicrosoftTodoDirectClient()
        self.application = None
        self.pending_auth = {}
        self.admin_ids = Config.TELEGRAM_ADMIN_IDS
        
    async def start(self):
        config_errors = Config.validate()
        if config_errors:
            raise ValueError(f"配置错误: {', '.join(config_errors)}")
        
        logger.info("使用直接Microsoft Graph API客户端")
        
        self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("list", self.list_command))
        self.application.add_handler(CommandHandler("active", self.active_command))
        self.application.add_handler(CommandHandler("summary", self.summary_command))
        self.application.add_handler(CommandHandler("refresh_token", self.refresh_token_command))
        self.application.add_handler(CommandHandler("get_auth_link", self.get_auth_link_command))
        self.application.add_handler(CommandHandler("token_status", self.token_status_command))
        
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Telegram Bot已启动")
    
    async def stop(self):
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        await self.todo_client.close()
        logger.info("Telegram Bot已停止")
    
    def _is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
    
    async def _check_admin_permission(self, update: Update) -> bool:
        user_id = update.effective_user.id
        username = update.effective_user.username or "未知用户"
        
        if not self._is_admin(user_id):
            logger.warning(f"未授权用户尝试访问: ID={user_id}, 用户名=@{username}")
            
            unauthorized_message = """
**访问被拒绝**

抱歉，您没有权限使用此机器人。

如果您认为这是错误，请联系管理员。

您的用户ID: `{user_id}`
            """.format(user_id=user_id)
            
            await update.message.reply_text(unauthorized_message, parse_mode='Markdown')
            return False
        
        return True
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        welcome_message = """
欢迎使用待办事项助手！

功能：
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
            ["📱 主菜单"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        help_message = """
使用帮助

1. 创建待办事项  
• "明天要开会讨论项目进度"
• "买牛奶、面包和鸡蛋"
• 发送图片（手写清单、白板等）

2. 标记完成  
• "完成了买牛奶的任务"
• "开会任务做完了"

3. 查看和搜索  
• /list - 查看所有待办事项
• /active - 查看未完成的待办事项
• /summary - 获取待办事项摘要
• "找一下关于会议的任务"

4. 令牌管理  
• /token_status - 查看当前令牌状态
• /get_auth_link - 获取授权链接更新令牌
• /refresh_token - 刷新访问令牌

5. 更新任务  
• "把买牛奶改成买酸奶"
• "更新会议时间为下午3点"

6.删除任务  
• "删除买牛奶的任务"

7. 小贴士
• 直接用自然语言描述即可，无需特殊格式
• 支持发送图片识别待办事项
• 我会智能理解您的意图并执行相应操作
        """
        await update.message.reply_text(help_message)
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        menu_message = "**主菜单**\n\n请选择您要执行的操作："
        
        keyboard = [
            [
                InlineKeyboardButton("📋 查看所有待办", callback_data="menu_list_all"),
                InlineKeyboardButton("⏳ 未完成任务", callback_data="menu_list_active")
            ],
            [
                InlineKeyboardButton("📊 任务摘要", callback_data="menu_summary"),
                InlineKeyboardButton("🔍 搜索任务", callback_data="menu_search")
            ],
            [
                InlineKeyboardButton("✅ 快速完成", callback_data="menu_quick_complete"),
                InlineKeyboardButton("🗑️ 快速删除", callback_data="menu_quick_delete")
            ],
            [
                InlineKeyboardButton("🔐 令牌管理", callback_data="menu_token_manage"),
                InlineKeyboardButton("🆘 帮助", callback_data="menu_help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(menu_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if not self._is_admin(user_id):
            username = query.from_user.username or "未知用户"
            logger.warning(f"未授权用户尝试使用回调功能: ID={user_id}, 用户名=@{username}")
            await query.edit_message_text("您没有权限执行此操作。")
            return
        
        callback_data = query.data
        
        if callback_data == "menu_list_all":
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
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        try:
            todos = await self.todo_client.list_todos()
            
            if not todos:
                await update.message.reply_text("您还没有任何待办事项。发送消息创建第一个吧！")
                return
            
            message = "**所有待办事项：**\n\n"
            
            display_todos = todos[:15]
            
            for i, todo in enumerate(display_todos, 1):
                status = "" if todo.get('completed', False) else ""
                title = todo.get('title', 'N/A')
                description = todo.get('description', '')
                todo_id = todo.get('id', 'N/A')
                
                display_title = title[:40] + "..." if len(title) > 40 else title
                message += f"{status} **{i}. {display_title}**\n"
                
                if description:
                    display_desc = description[:60] + "..." if len(description) > 60 else description
                    message += f"   {display_desc}\n"
                
                message += "\n"
                
                if len(message) > 3500:
                    remaining = len(todos) - i
                    if remaining > 0:
                        message += f"... 还有 {remaining} 个任务，使用具体命令查看更多"
                    break
            
            if len(todos) > 15:
                message += f"\n总共 {len(todos)} 个任务，显示前 {min(15, len(display_todos))} 个"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
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
                title = todo.get('title', 'N/A')
                description = todo.get('description', '')
                todo_id = todo.get('id', 'N/A')
                
                display_title = title[:40] + "..." if len(title) > 40 else title
                message += f"**{i}. {display_title}**\n"
                
                if description:
                    display_desc = description[:60] + "..." if len(description) > 60 else description
                    message += f"   {display_desc}\n"
                
                message += "\n"
                
                if len(message) > 3500:
                    remaining = len(todos) - i
                    if remaining > 0:
                        message += f"... 还有 {remaining} 个未完成任务"
                    break
            
            if len(todos) > 12:
                message += f"\n总共 {len(todos)} 个未完成任务，显示前 {min(12, len(display_todos))} 个"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
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
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        try:
            user_text = update.message.text
            user_id = update.effective_user.id
            logger.info(f"收到文本消息: {user_text}")
            
            if user_id in self.pending_auth and self.pending_auth[user_id].get('expecting_code'):
                await self._handle_auth_code(update, context, user_text)
                return
            
            if await self._handle_keyboard_button(update, context, user_text):
                return
            
            processing_message = await update.message.reply_text("正在分析您的消息...")
            
            existing_todos = await self.todo_client.list_todos()
            
            analysis = await self.ai_service.analyze_text_for_todos(user_text, existing_todos)
            
            result = await self.execute_action(analysis)
            
            response = await self.ai_service.generate_response(analysis, result)
            
            await processing_message.edit_text(response)
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            await update.message.reply_text("处理消息时出现错误，请稍后重试。")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        try:
            processing_message = await update.message.reply_text("正在分析图片内容...")
            
            photo = update.message.photo[-1]
            file = await photo.get_file()
            
            if file.file_size > Config.MAX_IMAGE_SIZE:
                await processing_message.edit_text("图片文件过大，请发送小于5MB的图片。")
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
                await processing_message.edit_text("不支持的图片格式。支持的格式：jpg, jpeg, png, gif, webp")
                return
            
            logger.info(f"收到图片消息，格式: {image_format}, 大小: {len(image_bytes)} bytes")
            
            existing_todos = await self.todo_client.list_todos()
            
            analysis = await self.ai_service.analyze_image_for_todos(image_bytes, image_format, existing_todos)
            
            result = await self.execute_action(analysis)
            
            response = await self.ai_service.generate_response(analysis, result)
            
            await processing_message.edit_text(response)
            
        except Exception as e:
            logger.error(f"处理图片消息失败: {e}")
            await update.message.reply_text("处理图片时出现错误，请稍后重试。")
    
    async def _handle_menu_list_all(self, query, context):
        try:
            todos = await self.todo_client.list_todos()
            
            if not todos:
                await query.edit_message_text("您还没有任何待办事项。发送消息创建第一个吧！")
                return
            
            message = "**所有待办事项：**\n\n"
            for i, todo in enumerate(todos[:8], 1):
                status = "" if todo.get('completed', False) else ""
                title = todo.get('title', 'N/A')
                display_title = title[:30] + "..." if len(title) > 30 else title
                message += f"{status} **{i}. {display_title}**\n"
            
            if len(todos) > 8:
                message += f"\n... 还有 {len(todos) - 8} 个任务\n使用 /list 查看完整列表"
            
            await query.edit_message_text(message, parse_mode='Markdown')
            
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
                title = todo.get('title', 'N/A')
                todo_id = todo.get('id', '')
                display_title = title[:30] + "..." if len(title) > 30 else title
                message += f"**{i}. {display_title}**\n"
                
                if i <= 4:
                    short_id = todo_id[:20] if todo_id else str(i)
                    keyboard.append([InlineKeyboardButton(f"完成 {i}", callback_data=f"comp_{short_id}")])
            
            if len(todos) > 6:
                message += f"\n... 还有 {len(todos) - 6} 个任务"
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
            
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
            "• \"找一下关于会议的任务\"\n"
            "• \"搜索买菜相关的待办\"\n"
            "• \"查找明天的任务\""
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
                title = todo.get('title', 'N/A')
                todo_id = todo.get('id', '')
                display_title = title[:20] + "..." if len(title) > 20 else title
                short_id = todo_id[:20] if todo_id else str(i)
                keyboard.append([InlineKeyboardButton(f"{display_title}", callback_data=f"comp_{short_id}")])
            
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
                title = todo.get('title', 'N/A')
                todo_id = todo.get('id', '')
                status = "" if todo.get('completed', False) else ""
                display_title = title[:15] + "..." if len(title) > 15 else title
                short_id = todo_id[:20] if todo_id else str(i)
                keyboard.append([InlineKeyboardButton(f"{status} {display_title}", callback_data=f"del_{short_id}")])
            
            if len(todos) > 10:
                message += f"\n显示前10个任务，共{len(todos)}个任务"
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"快速删除菜单失败: {e}")
            await query.edit_message_text("获取待办事项时出现错误")
    
    async def _handle_menu_token_manage(self, query, context):
        message = "**令牌管理**\n\n"
        keyboard = [
            [InlineKeyboardButton("📊 查看令牌状态", callback_data="token_status")],
            [InlineKeyboardButton("🔄 刷新令牌", callback_data="token_refresh")],
            [InlineKeyboardButton("🔗 获取授权链接", callback_data="token_auth_link")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup)
    
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
                    if todo.get('id', '').startswith(short_id):
                        todo_id = todo.get('id')
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
                    if todo.get('id', '').startswith(short_id):
                        todo_id = todo.get('id')
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
    
    async def _handle_keyboard_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
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
                "• \"找一下关于会议的任务\"\n"
                "• \"搜索买菜相关的待办\"\n"
                "• \"查找明天的任务\"",
                parse_mode='Markdown'
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
    
    async def _handle_token_status_callback(self, query, context):
        try:
            status_message = "**令牌状态**\n\n"
            
            if Config.MS_TODO_ACCESS_TOKEN:
                status_message += f"访问令牌: {Config.MS_TODO_ACCESS_TOKEN[:20]}...\n"
            else:
                status_message += "访问令牌: 未设置\n"
            
            if Config.MS_TODO_REFRESH_TOKEN:
                if Config.MS_TODO_REFRESH_TOKEN == "client_credentials_flow":
                    status_message += "刷新令牌: 客户端凭据流\n"
                else:
                    status_message += f"刷新令牌: {Config.MS_TODO_REFRESH_TOKEN[:20]}...\n"
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
                error_msg = str(test_result.get('error', '未知错误'))
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
                        f"新访问令牌: {new_access_token[:30]}...\n"
                        "已自动保存到配置文件"
                    )
                else:
                    await query.edit_message_text(
                        "**令牌刷新成功但保存失败**\n\n"
                        f"新访问令牌: {new_access_token[:30]}...\n"
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
                'session_id': session_id,
                'timestamp': datetime.now(),
                'expecting_code': True
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
            
        except Exception as e:
            logger.error(f"生成授权链接失败: {e}")
            await query.edit_message_text(f"生成授权链接失败: {str(e)}")
    
    async def execute_action(self, analysis: dict) -> any:
        action = analysis.get("action", "QUERY")
        
        try:
            if action == "CREATE":
                if "items" in analysis:
                    results = []
                    for item in analysis["items"]:
                        item_text = f"{item.get('title', '')} {item.get('description', '')}"
                        
                        existing_todos = await self.todo_client.list_todos()
                        
                        detailed_analysis = await self.ai_service.analyze_text_for_todos(item_text, existing_todos)
                        
                        result = await self.todo_client.create_todo(
                            title=detailed_analysis.get("title", item.get("title", "")),
                            description=detailed_analysis.get("description", item.get("description", "")),
                            due_date=detailed_analysis.get("due_date"),
                            reminder_date=detailed_analysis.get("reminder_date"),
                            reminder_time=detailed_analysis.get("reminder_time")
                        )
                        results.append(result)
                    return results
                else:
                    return await self.todo_client.create_todo(
                        title=analysis.get("title", ""),
                        description=analysis.get("description", ""),
                        due_date=analysis.get("due_date"),
                        reminder_date=analysis.get("reminder_date"),
                        reminder_time=analysis.get("reminder_time")
                    )
            
            elif action == "UPDATE":
                todo_id = analysis.get("todo_id", "")
                if not todo_id:
                    search_results = await self.todo_client.search_todos_by_title(analysis.get("title", ""))
                    if search_results:
                        todo_id = search_results[0].get("id", "")
                
                if todo_id:
                    return {"error": "更新功能需要指定任务列表ID，暂不支持通过搜索更新"}
                else:
                    return {"error": "未找到要更新的待办事项"}
            
            elif action == "COMPLETE":
                todo_id = analysis.get("todo_id", "")
                if not todo_id:
                    search_query = analysis.get("search_query", analysis.get("title", ""))
                    if search_query:
                        search_results = await self.todo_client.search_todos_by_title(search_query)
                        if search_results:
                            todo_id = search_results[0].get("id", "")
                
                if todo_id:
                    return await self.todo_client.complete_todo(todo_id)
                else:
                    return {"error": "未找到要完成的待办事项"}
            
            elif action == "DELETE":
                todo_id = analysis.get("todo_id", "")
                if not todo_id:
                    search_query = analysis.get("search_query", analysis.get("title", ""))
                    if search_query:
                        search_results = await self.todo_client.search_todos_by_title(search_query)
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
                return {"message": "我理解了您的消息，但不确定需要执行什么具体操作。您可以更明确地告诉我您想要做什么。"}
        
        except Exception as e:
            logger.error(f"执行操作失败: {e}")
            return {"error": f"操作执行失败: {str(e)}"}
    
    async def token_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        try:
            status_message = "令牌状态\n\n"
            
            if Config.MS_TODO_ACCESS_TOKEN:
                status_message += f"访问令牌: {Config.MS_TODO_ACCESS_TOKEN[:20]}...\n"
            else:
                status_message += "访问令牌: 未设置\n"
            
            if Config.MS_TODO_REFRESH_TOKEN:
                if Config.MS_TODO_REFRESH_TOKEN == "client_credentials_flow":
                    status_message += "刷新令牌: 客户端凭据流\n"
                else:
                    status_message += f"刷新令牌: {Config.MS_TODO_REFRESH_TOKEN[:20]}...\n"
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
                error_msg = str(test_result.get('error', '未知错误'))
                status_message += f"令牌可能已过期: {error_msg}\n"
                status_message += "\n使用 /refresh_token 刷新令牌或 /get_auth_link 重新授权"
            
            await update.message.reply_text(status_message)
            
        except Exception as e:
            logger.error(f"检查令牌状态失败: {e}")
            await update.message.reply_text(f"检查令牌状态失败: {str(e)}")
    
    async def refresh_token_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        try:
            await update.message.reply_text("正在刷新访问令牌...")
            
            success = await self.todo_client.refresh_token_manually()
            
            if success:
                new_access_token = self.todo_client.access_token
                new_refresh_token = self.todo_client.refresh_token
                
                if await self._save_tokens_to_env(new_access_token, new_refresh_token):
                    await update.message.reply_text(
                        "令牌刷新成功！\n\n"
                        f"新访问令牌: {new_access_token[:30]}...\n"
                        "已自动保存到配置文件"
                    )
                else:
                    await update.message.reply_text(
                        "令牌刷新成功但保存失败\n\n"
                        f"新访问令牌: {new_access_token[:30]}...\n"
                        "请联系管理员手动更新配置文件"
                    )
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
    
    async def get_auth_link_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return
            
        try:
            user_id = update.effective_user.id
            
            auth_url = self._generate_auth_url()
            
            session_id = str(uuid.uuid4())
            self.pending_auth[user_id] = {
                'session_id': session_id,
                'timestamp': datetime.now(),
                'expecting_code': True
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
            
            context.job_queue.run_once(
                self._cleanup_auth_session, 
                600,
                data=user_id,
                name=f"cleanup_auth_{user_id}"
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
                with open('.env', 'r', encoding='utf-8') as f:
                    env_lines = f.readlines()
            except FileNotFoundError:
                pass
            
            access_token_found = False
            refresh_token_found = False
            
            for i, line in enumerate(env_lines):
                if line.startswith('MS_TODO_ACCESS_TOKEN='):
                    env_lines[i] = f'MS_TODO_ACCESS_TOKEN={access_token}\n'
                    access_token_found = True
                elif line.startswith('MS_TODO_REFRESH_TOKEN='):
                    env_lines[i] = f'MS_TODO_REFRESH_TOKEN={refresh_token}\n'
                    refresh_token_found = True
            
            if not access_token_found:
                env_lines.append(f'MS_TODO_ACCESS_TOKEN={access_token}\n')
            if not refresh_token_found:
                env_lines.append(f'MS_TODO_REFRESH_TOKEN={refresh_token}\n')
            
            with open('.env', 'w', encoding='utf-8') as f:
                f.writelines(env_lines)
            
            Config.MS_TODO_ACCESS_TOKEN = access_token
            Config.MS_TODO_REFRESH_TOKEN = refresh_token
            
            return True
            
        except Exception as e:
            logger.error(f"保存令牌失败: {e}")
            return False
    
    async def _handle_auth_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, auth_code: str):
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
                authority = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}"
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
        user_id = context.job.data
        if user_id in self.pending_auth:
            del self.pending_auth[user_id]
            logger.info(f"清理过期的授权会话: {user_id}")
    
    async def run_forever(self):
        try:
            await self.start()
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
        finally:
            await self.stop()
