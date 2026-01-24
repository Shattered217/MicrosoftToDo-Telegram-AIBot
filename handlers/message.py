"""
消息处理器
处理文本消息、图片消息和操作执行
"""
import logging
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes
from PIL import Image

from config import Config

logger = logging.getLogger(__name__)


class MessageHandlers:
    """消息处理器混入类"""

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

            # 对消息进行表态（reaction）
            await self._react(
                context, update.effective_chat.id, update.message.message_id, "🤖"
            )

            existing_todos = await self.todo_client.list_todos()

            analysis = await self.ai_service.analyze_text_for_todos(
                user_text, existing_todos
            )

            # 检测是否应该建议拆解任务
            if (analysis.get('action') == 'CREATE' and 
                self.ai_service._should_suggest_decompose(user_text, analysis)):
                # 调用AI拆解任务
                decompose_result = await self.ai_service.decompose_task(user_text)
                
                if decompose_result.get('action') == 'DECOMPOSE':
                    # 保存待确认的拆解结果
                    self.pending_decompose[user_id] = decompose_result
                    
                    # 发送交互式确认消息
                    message = self.ai_service.format_decompose_message(decompose_result)
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ 全部创建", callback_data="decompose_confirm_all"),
                            InlineKeyboardButton("❌ 取消", callback_data="decompose_cancel"),
                        ],
                        [
                            InlineKeyboardButton("📝 不拆解，创建原任务", callback_data="decompose_create_original"),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")
                    return

            result = await self.execute_action(analysis)

            response = await self.ai_service.generate_response(analysis, result)

            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            await update.message.reply_text("处理消息时出现错误，请稍后重试。")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin_permission(update):
            return

        try:
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

            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"处理图片消息失败: {e}")
            await update.message.reply_text("处理图片时出现错误，请稍后重试。")

    async def execute_action(self, analysis: dict) -> any:
        """执行分析结果对应的操作"""
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
