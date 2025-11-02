import base64
import logging
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from config import Config

logger = logging.getLogger(__name__)

class AIService:
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.OPENAI_BASE_URL,
            timeout=60.0  # 60秒超时
        )
        self.model = Config.OPENAI_MODEL
    
    async def analyze_text_for_todos(self, text: str, existing_todos: List[Dict] = None) -> Dict[str, Any]:
        
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        existing_context = f"\n\n当前时间：{current_time}"
        if existing_todos:
            existing_context += f"\n\n当前已有的待办事项：\n" + "\n".join([
                f"- {todo.get('title', 'N/A')} (ID: {todo.get('id', 'N/A')}, 状态: {'已完成' if todo.get('completed', False) else '未完成'})"
                for todo in existing_todos[:10]  # 限制数量避免token过多
            ])
        
        system_prompt = f"""你是一个智能待办事项提取器。你的任务是将用户的任何文本消息都转换为具体的待办事项。

核心原则：
1. 每条消息都应该被解析为至少一个待办事项（除非是明确的操作指令）
2. 自动识别和提取时间信息（日期、时间、截止时间等）
3. 提取任务的核心内容作为标题
4. 将详细信息作为描述

操作类型判断：
- 如果包含"完成了"、"做完了"、"标记完成"等词语 → COMPLETE
- 如果包含"删除"、"取消"、"移除"等词语 → DELETE  
- 如果包含"修改"、"更新"、"改成"等词语 → UPDATE
- 如果包含"查看"、"显示"、"列表"等词语 → LIST
- 如果包含"搜索"、"找"、"查找"等词语 → SEARCH
- 其他所有情况 → CREATE（默认创建任务）

时间识别规则：
- 尽量从用户输入中提取任何可能的日期信息作为截止日期
- 提醒时间规则：
  * 如果任务提到具体时间（如"下午3点开会"），提取该时间作为提醒时间
  * 如果只有日期没有时间，根据任务重要性设置合适的提醒时间
  * 重要任务（会议、约会等）：提前1天提醒，时间为09:00
  * 普通任务：当天提醒，时间为09:00

请以JSON格式返回，包含：
- action: 操作类型（CREATE/UPDATE/COMPLETE/DELETE/LIST/SEARCH）
- title: 任务标题（简洁明了）
- description: 详细描述（包含所有相关信息）
- due_date: 截止日期（YYYY-MM-DD格式，尽量提取任何可能的日期信息）
- reminder_date: 提醒日期（YYYY-MM-DD格式，根据任务重要性设置）
- reminder_time: 提醒时间（HH:MM格式，根据任务具体时间或重要性设置）
- search_query: 搜索关键词（仅SEARCH操作）
- todo_id: 待办事项ID（仅UPDATE/COMPLETE/DELETE操作，如果提到具体ID）
- confidence: 置信度（0-1）

{existing_context}"""

        user_prompt = f"用户输入：{text}"
        
        try:
            logger.info(f"开始AI分析，模型: {self.model}")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1.0,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            logger.info(f"AI原始响应: {content}")
            
            import json
            import re
            
            # 清理可能的 markdown 代码块标记
            content_cleaned = content.strip()
            if content_cleaned.startswith("```"):
                # 移除开头的 ```json 或 ```
                content_cleaned = re.sub(r'^```(?:json)?\s*\n?', '', content_cleaned)
                # 移除结尾的 ```
                content_cleaned = re.sub(r'\n?```\s*$', '', content_cleaned)
                logger.info(f"清理后的内容: {content_cleaned}")
            
            try:
                result = json.loads(content_cleaned)
                logger.info(f"JSON解析成功，action={result.get('action')}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}, 清理后内容: {content_cleaned}")
                return {
                    "action": "CREATE",
                    "title": text[:50] + "..." if len(text) > 50 else text,
                    "description": text,
                    "due_date": None,
                    "reminder_date": None,
                    "reminder_time": None,
                    "search_query": "",
                    "todo_id": "",
                    "confidence": 0.5
                }
                
        except Exception as e:
            logger.error(f"AI分析失败: {type(e).__name__}: {e}", exc_info=True)
            return {
                "action": "CREATE",
                "title": text[:50] + "..." if len(text) > 50 else text,
                "description": text,
                "due_date": None,
                "reminder_date": None,
                "reminder_time": None,
                "search_query": "",
                "todo_id": "",
                "confidence": 0.0
            }
    
    async def analyze_image_for_todos(self, image_data: bytes, image_format: str, existing_todos: List[Dict] = None, caption: Optional[str] = None) -> Dict[str, Any]:
        
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        existing_context = f"\n\n当前时间：{current_time}"
        if existing_todos:
            existing_context += f"\n\n当前已有的待办事项：\n" + "\n".join([
                f"- {todo.get('title', 'N/A')} (ID: {todo.get('id', 'N/A')}, 状态: {'已完成' if todo.get('completed', False) else '未完成'})"
                for todo in existing_todos[:10]
            ])
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        system_prompt = f"""你是一个智能待办事项提取器。用户会发送图片，你需要识别图片中的文字与场景，将其等价视为用户文本输入，并按与文本分析相同的规则抽取待办事项。若提供了图片描述（caption），请将其视为主要参考之一。

核心原则：
1. 每条图片信息都应该被解析为至少一个待办事项（除非是明确的操作指令）
2. 自动识别并提取时间信息（日期、时间、截止时间等）
3. 提取任务的核心内容作为标题
4. 将详细信息作为描述

操作类型判断：
- 如果包含"完成了"、"做完了"、"标记完成"等词语 → COMPLETE
- 如果包含"删除"、"取消"、"移除"等词语 → DELETE  
- 如果包含"修改"、"更新"、"改成"等词语 → UPDATE
- 如果包含"查看"、"显示"、"列表"等词语 → LIST
- 如果包含"搜索"、"找"、"查找"等词语 → SEARCH
- 其他所有情况 → CREATE（默认创建任务）

时间识别规则：
- 尽量从识别到的内容中提取任何可能的日期信息作为截止日期
- 提醒时间规则：
  * 如果任务提到具体时间（如"下午3点开会"），提取该时间作为提醒时间
  * 如果只有日期没有时间，根据任务重要性设置合适的提醒时间
  * 重要任务（会议、约会等）：提前1天提醒，时间为09:00
  * 普通任务：当天提醒，时间为09:00

请以严格的JSON格式返回，字段要求与文本分析完全对齐：
- action: 操作类型（CREATE/UPDATE/COMPLETE/DELETE/LIST/SEARCH）
- title: 任务标题（简洁明了）
- description: 详细描述（包含所有相关信息，来源于图片识别）
- due_date: 截止日期（YYYY-MM-DD格式，尽量提取任何可能的日期信息）
- reminder_date: 提醒日期（YYYY-MM-DD格式，根据任务重要性设置）
- reminder_time: 提醒时间（HH:MM格式，根据任务具体时间或重要性设置）
- search_query: 搜索关键词（仅SEARCH操作）
- todo_id: 待办事项ID（仅UPDATE/COMPLETE/DELETE操作，如果提到具体ID）
- confidence: 置信度（0-1）

可选扩展字段（如果从图片中提取到多个事项）：
- items: 待办事项数组，元素包含 title、description、due_date、reminder_date、reminder_time
- image_description: 图片内容简要描述
- reasoning: 关键识别依据（简要说明）

只返回JSON，不要包含任何解释性文本或前后缀。

{existing_context}"""
        
        try:
            user_parts = []
            if caption:
                user_parts.append({
                    "type": "text",
                    "text": f"图片描述：{caption}"
                })
            user_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image_format};base64,{image_base64}"
                }
            })

            response = await self.client.chat.completions.create(
                model=Config.OPENAI_VL_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": user_parts
                    }
                ],
                temperature=1.0,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            logger.info(f"图片AI分析结果: {content}")
            
            import json
            import re
            
            # 清理可能的 markdown 代码块标记
            content_cleaned = content.strip()
            if content_cleaned.startswith("```"):
                # 移除开头的 ```json 或 ```
                content_cleaned = re.sub(r'^```(?:json)?\s*\n?', '', content_cleaned)
                # 移除结尾的 ```
                content_cleaned = re.sub(r'\n?```\s*$', '', content_cleaned)
                logger.info(f"清理后的图片分析内容: {content_cleaned}")
            
            try:
                result = json.loads(content_cleaned)
                return result
            except json.JSONDecodeError as e:
                logger.error(f"图片JSON解析失败: {e}, 清理后内容: {content_cleaned}")
                return {
                    "action": "CREATE",
                    "items": [{"title": "图片待办事项", "description": content_cleaned}],
                    "confidence": 0.5,
                    "reasoning": "无法解析AI响应为JSON格式",
                    "image_description": content_cleaned
                }
                
        except Exception as e:
            logger.error(f"图片AI分析失败: {e}")
            return {
                "action": "CREATE",
                "items": [{"title": "图片待办事项", "description": "无法分析图片内容"}],
                "confidence": 0.0,
                "reasoning": f"AI服务错误: {str(e)}",
                "image_description": "分析失败"
            }
    
    async def generate_response(self, analysis_result: Dict[str, Any], operation_result: Any) -> str:
        
        action = analysis_result.get("action", "QUERY")
        confidence = analysis_result.get("confidence", 0.0)
        
        try:
            system_prompt = """你是一个友好的待办事项助手。根据用户的操作结果，生成简洁、友好的中文回复。

回复要求：
- 简洁明了，不超过100字
- 语气友好自然
- 确认用户的操作结果
- 如果操作失败，提供简单的建议
- 必须与提供的结构化字段保持一致，特别是日期/时间/任务标题等关键信息，不要编造未提供的信息
- 如果存在提醒或截止日期，请在回复中自然体现
"""

            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

            # 提取关键字段，便于模型对齐生成
            title = analysis_result.get("title")
            description = analysis_result.get("description")
            due_date = analysis_result.get("due_date")
            reminder_date = analysis_result.get("reminder_date")
            reminder_time = analysis_result.get("reminder_time")
            search_query = analysis_result.get("search_query")
            todo_id = analysis_result.get("todo_id")
            items = analysis_result.get("items")
            items_count = len(items) if isinstance(items, list) else 0

            field_lines = [
                f"- title: {title}",
                f"- description: {description}",
                f"- due_date: {due_date}",
                f"- reminder_date: {reminder_date}",
                f"- reminder_time: {reminder_time}",
                f"- search_query: {search_query}",
                f"- todo_id: {todo_id}",
                f"- items_count: {items_count}",
            ]
            fields_block = "\n".join(field_lines)

            user_prompt = f"""
当前时间: {current_time}
操作类型: {action}
分析置信度: {confidence}

结构化字段（请严格对齐生成，不要编造）：
{fields_block}

操作结果对象（字符串化）：
{str(operation_result)}

分析推理:
{analysis_result.get('reasoning', '')}

请基于上述字段生成一个友好的、与字段一致的中文回复（不超过100字）。"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1.0,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"生成回复失败: {e}")
            if action == "CREATE":
                return "待办事项已创建成功！"
            elif action == "COMPLETE":
                return "待办事项已标记为完成！"
            elif action == "UPDATE":
                return "待办事项已更新！"
            elif action == "DELETE":
                return "待办事项已删除！"
            elif action == "LIST":
                return "这是您的待办事项列表："
            else:
                return "收到您的消息，正在处理中..."
