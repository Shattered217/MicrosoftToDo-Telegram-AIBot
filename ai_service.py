import base64
import logging
import asyncio
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
        self._last_todos_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 30  # 缓存30秒
    
    def _get_common_time_rules(self, current_time: str) -> str:
        """获取通用时间识别规则"""
        return f"""时间识别规则：
- 尽量提取任何可能的日期信息作为截止日期
- **重要约束：所有日期时间必须在当前时间（{current_time}）之后，不得设置过去的日期**

提醒时间智能设置规则：
1. **如果任务提到具体时间**（如"下午3点开会"、"明天9点"）：
   - 提醒时间 = 任务时间提前30-60分钟
   - 例如："明天下午3点开会" → 提醒时间为明天14:00或14:30
   
2. **如果任务在今天且未指定具体时间**：
   - 立即提醒（设置为当前时间后1小时）
   - 例如：当前15:00，提醒设为16:00
   
3. **如果任务在明天且未指定时间**：
   - 重要任务（会议、约会等）：今天晚上20:00提醒，或明天早上08:00
   - 普通任务：明天早上09:00提醒
   
4. **如果任务在未来几天**：
   - 提前1天的早上09:00提醒
   
5. **智能判断**：
   - 如果计算出的提醒时间已经过去，自动调整为当前时间后30分钟
   - 避免设置已经过去的提醒时间
   - 考虑任务的紧急程度动态调整提醒时间

**关键原则：提醒时间必须在当前时间之后，且在任务时间之前**"""
    
    def _get_action_rules(self) -> str:
        """获取操作类型判断规则"""
        return """操作类型判断：
- 如果包含"完成了"、"做完了"、"标记完成"等词语 → COMPLETE
- 如果包含"删除"、"取消"、"移除"等词语 → DELETE  
- 如果包含"修改"、"更新"、"改成"等词语 → UPDATE
- 如果包含"查看"、"显示"、"列表"等词语 → LIST
- 如果包含"搜索"、"找"、"查找"等词语 → SEARCH
- 其他所有情况 → CREATE（默认创建任务）"""
    
    def _robust_json_parse(self, content: str) -> Dict[str, Any]:
        """健壮的JSON解析，支持多种格式"""
        import json
        import re
        
        # 清理markdown代码块
        content_cleaned = content.strip()
        if content_cleaned.startswith("```"):
            content_cleaned = re.sub(r'^```(?:json)?\s*\n?', '', content_cleaned)
            content_cleaned = re.sub(r'\n?```\s*$', '', content_cleaned)
        
        # 尝试直接解析
        try:
            return json.loads(content_cleaned)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON对象
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content_cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # 尝试修复常见错误
        try:
            # 修复单引号
            fixed = content_cleaned.replace("'", '"')
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        
        # 最后的fallback
        logger.error(f"所有JSON解析方法失败，原始内容: {content_cleaned[:200]}")
        return None
    
    def _validate_and_fix_dates(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """验证并修正日期时间，确保在当前时间之后"""
        from datetime import datetime, timedelta
        
        now = datetime.now()
        
        # 验证截止日期
        if result.get('due_date'):
            try:
                due = datetime.strptime(result['due_date'], '%Y-%m-%d')
                if due.date() < now.date():
                    # 自动调整到明天
                    result['due_date'] = (now + timedelta(days=1)).strftime('%Y-%m-%d')
                    logger.warning(f"截止日期在过去，已自动调整为明天: {result['due_date']}")
            except ValueError:
                logger.warning(f"无效的截止日期格式: {result['due_date']}")
                result['due_date'] = None
        
        # 验证提醒日期和时间（组合验证）
        if result.get('reminder_date'):
            try:
                reminder_date_obj = datetime.strptime(result['reminder_date'], '%Y-%m-%d')
                reminder_time = result.get('reminder_time', '09:00')
                
                # 组合日期和时间进行完整验证
                try:
                    reminder_datetime = datetime.strptime(
                        f"{result['reminder_date']} {reminder_time}",
                        '%Y-%m-%d %H:%M'
                    )
                    
                    # 如果提醒时间已经过去
                    if reminder_datetime <= now:
                        # 调整为当前时间后30分钟
                        new_reminder = now + timedelta(minutes=30)
                        result['reminder_date'] = new_reminder.strftime('%Y-%m-%d')
                        result['reminder_time'] = new_reminder.strftime('%H:%M')
                        logger.warning(
                            f"提醒时间已过去，已调整为30分钟后: "
                            f"{result['reminder_date']} {result['reminder_time']}"
                        )
                except ValueError:
                    # 时间格式错误，使用保守策略
                    if reminder_date_obj.date() < now.date():
                        result['reminder_date'] = now.strftime('%Y-%m-%d')
                        result['reminder_time'] = (now + timedelta(hours=1)).strftime('%H:%M')
                        logger.warning(f"提醒日期在过去，已调整为1小时后")
                    elif reminder_date_obj.date() == now.date():
                        # 今天的任务，检查时间是否合理
                        result['reminder_time'] = (now + timedelta(minutes=30)).strftime('%H:%M')
                        logger.info(f"今天的任务，提醒时间设为30分钟后: {result['reminder_time']}")
                        
            except ValueError:
                logger.warning(f"无效的提醒日期格式: {result['reminder_date']}")
                result['reminder_date'] = None
                result['reminder_time'] = None
        
        return result
    
    async def analyze_text_for_todos(self, text: str, existing_todos: List[Dict] = None) -> Dict[str, Any]:
        """分析文本并提取待办事项信息"""
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 构建上下文（使用缓存避免重复传输）
        existing_context = f"\n\n当前时间：{current_time}"
        if existing_todos and len(existing_todos) > 0:
            # 只传最近的5个未完成任务，减少token消耗
            active_todos = [t for t in existing_todos if not t.get('completed', False)][:5]
            if active_todos:
                existing_context += f"\n\n当前未完成的待办事项（供参考，避免重复）：\n" + "\n".join([
                    f"- {todo.get('title', 'N/A')}"
                    for todo in active_todos
                ])
        
        system_prompt = f"""你是一个智能待办事项提取器。将用户文本转换为结构化的待办事项数据。

核心原则：
1. 每条消息解析为至少一个待办事项（除非是明确的操作指令）
2. 自动识别和提取时间信息
3. 提取任务核心内容作为标题（简洁，10字以内）
4. 详细信息作为描述

{self._get_action_rules()}

{self._get_common_time_rules(current_time)}

**输出格式：严格的JSON对象，不包含任何markdown标记或解释文本**

必需字段：
- action: CREATE/UPDATE/COMPLETE/DELETE/LIST/SEARCH
- title: 任务标题（简洁明了，10字内）
- description: 详细描述
- due_date: YYYY-MM-DD格式或null
- reminder_date: YYYY-MM-DD格式或null
- reminder_time: HH:MM格式或null
- search_query: 搜索关键词（仅SEARCH）或空字符串
- todo_id: 任务ID（仅UPDATE/COMPLETE/DELETE）或空字符串
- confidence: 0-1之间的数字

{existing_context}"""

        user_prompt = f"用户输入：{text}"
        
        # 带重试的API调用
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"AI分析（尝试 {attempt + 1}/{max_retries + 1}），模型: {self.model}")
                
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,  # 降低temperature以获得更稳定的结构化输出
                    max_tokens=800,
                    response_format={"type": "json_object"} if "gpt-4" in self.model.lower() else None
                )
                
                content = response.choices[0].message.content
                logger.info(f"AI原始响应: {content[:200]}...")
                
                # 健壮的JSON解析
                result = self._robust_json_parse(content)
                
                if result:
                    # 验证并修正日期
                    result = self._validate_and_fix_dates(result)
                    logger.info(f"JSON解析成功，action={result.get('action')}, title={result.get('title')}")
                    return result
                else:
                    if attempt < max_retries:
                        logger.warning(f"JSON解析失败，将重试...")
                        continue
                    else:
                        raise ValueError("无法解析AI响应为有效JSON")
                        
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"AI调用失败（尝试 {attempt + 1}），将重试: {e}")
                    await asyncio.sleep(1)  # 短暂延迟后重试
                    continue
                else:
                    logger.error(f"AI分析失败（所有重试已用尽）: {type(e).__name__}: {e}", exc_info=True)
                    break
        
        # 所有尝试失败，返回fallback
        return {
            "action": "CREATE",
            "title": text[:30] + "..." if len(text) > 30 else text,
            "description": text,
            "due_date": None,
            "reminder_date": None,
            "reminder_time": None,
            "search_query": "",
            "todo_id": "",
            "confidence": 0.0,
            "reasoning": "AI服务暂时不可用，已创建基础任务"
        }
    
    def _compress_image_if_needed(self, image_data: bytes, max_size: int = 1024*1024) -> bytes:
        """如果图片过大则压缩"""
        if len(image_data) <= max_size:
            return image_data
        
        try:
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(BytesIO(image_data))
            
            # 计算缩放比例
            ratio = (max_size / len(image_data)) ** 0.5
            new_size = (int(img.width * ratio), int(img.height * ratio))
            
            # 缩放图片
            img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 保存为JPEG以进一步压缩
            output = BytesIO()
            img_resized.save(output, format='JPEG', quality=85, optimize=True)
            compressed = output.getvalue()
            
            logger.info(f"图片已压缩: {len(image_data)} -> {len(compressed)} bytes")
            return compressed
            
        except Exception as e:
            logger.warning(f"图片压缩失败，使用原图: {e}")
            return image_data
    
    async def analyze_image_for_todos(self, image_data: bytes, image_format: str, existing_todos: List[Dict] = None, caption: Optional[str] = None) -> Dict[str, Any]:
        """分析图片并提取待办事项"""
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 压缩图片以减少token消耗
        image_data = self._compress_image_if_needed(image_data, max_size=512*1024)
        
        # 构建简化的上下文
        existing_context = f"\n\n当前时间：{current_time}"
        if existing_todos and len(existing_todos) > 0:
            active_todos = [t for t in existing_todos if not t.get('completed', False)][:3]
            if active_todos:
                existing_context += "\n\n当前未完成任务：" + ", ".join([t.get('title', '')[:15] for t in active_todos])
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        system_prompt = f"""你是智能待办事项识别器。从图片中识别文字和场景，提取待办事项。

{self._get_action_rules()}
{self._get_common_time_rules(current_time)}

**输出：严格的JSON，不包含markdown标记**

字段：
- action: CREATE/UPDATE/COMPLETE/DELETE/LIST/SEARCH
- title: 任务标题（10字内）
- description: 详细描述
- due_date, reminder_date, reminder_time: 日期时间字段
- confidence: 0-1

如果识别到多个任务，添加items数组。

{existing_context}"""
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                user_parts = []
                if caption:
                    user_parts.append({"type": "text", "text": f"图片描述：{caption}"})
                user_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{image_format};base64,{image_base64}"}
                })

                response = await self.client.chat.completions.create(
                    model=Config.OPENAI_VL_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_parts}
                    ],
                    temperature=0.4,
                    max_tokens=1200
                )
                
                content = response.choices[0].message.content
                logger.info(f"图片AI分析（尝试 {attempt + 1}）: {content[:150]}...")
                
                result = self._robust_json_parse(content)
                if result:
                    result = self._validate_and_fix_dates(result)
                    return result
                elif attempt < max_retries:
                    continue
                else:
                    raise ValueError("无法解析图片分析结果")
                    
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"图片分析失败（尝试 {attempt + 1}）: {e}")
                    await asyncio.sleep(1)
                    continue
                else:
                    logger.error(f"图片AI分析失败: {e}")
                    break
        
        # Fallback
        return {
            "action": "CREATE",
            "items": [{"title": "图片待办事项", "description": caption or "图片内容"}],
            "confidence": 0.0,
            "reasoning": "AI服务不可用"
        }
    
    async def generate_response(self, analysis_result: Dict[str, Any], operation_result: Any) -> str:
        """生成用户友好的响应文本（优先使用模板，复杂场景才用AI）"""
        action = analysis_result.get("action", "QUERY")
        confidence = analysis_result.get("confidence", 0.0)
        
        # 先尝试使用模板生成（快速、省成本）
        template_response = self._generate_template_response(action, analysis_result, operation_result)
        if template_response:
            return template_response
        
        # 复杂场景才调用AI
        try:
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            system_prompt = """生成简洁友好的中文回复，确认操作结果。

要求：
- 不超过50字
- 语气自然
- 如有日期/时间，自然体现
- 失败时给出简单建议"""
            
            title = analysis_result.get("title", "")[:30]
            due_date = analysis_result.get("due_date")
            reminder_date = analysis_result.get("reminder_date")
            reminder_time = analysis_result.get("reminder_time")
            
            user_prompt = f"""操作: {action}
任务: {title}
截止: {due_date or '无'}
提醒: {reminder_date or '无'} {reminder_time or ''}
结果: {str(operation_result)[:100]}

生成简洁回复："""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=100
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"生成回复失败: {e}")
            return self._get_fallback_response(action)
    
    def _generate_template_response(self, action: str, analysis: Dict[str, Any], result: Any) -> Optional[str]:
        """使用模板生成响应（大部分场景）"""
        title = analysis.get("title", "")
        due_date = analysis.get("due_date")
        reminder_date = analysis.get("reminder_date")
        reminder_time = analysis.get("reminder_time")
        
        # 检查是否有错误
        has_error = isinstance(result, dict) and "error" in result
        
        if action == "CREATE":
            if has_error:
                return f"创建失败：{result.get('error', '未知错误')}"
            
            title_short = title[:20] if title else "任务"
            response = f"✅ 已创建任务「{title_short}」"
            
            if due_date:
                response += f"\n📅 截止: {due_date}"
            if reminder_date:
                time_part = f" {reminder_time}" if reminder_time else ""
                response += f"\n⏰ 提醒: {reminder_date}{time_part}"
            
            return response
        
        elif action == "COMPLETE":
            if has_error:
                return f"标记完成失败：{result.get('error', '未找到任务')}"
            return f"✅ 已完成任务！"
        
        elif action == "DELETE":
            if has_error:
                return f"删除失败：{result.get('error', '未找到任务')}"
            return f"🗑️ 任务已删除"
        
        elif action == "UPDATE":
            if has_error:
                return f"更新失败：{result.get('error', '未找到任务')}"
            return f"✏️ 任务已更新"
        
        elif action == "LIST":
            if isinstance(result, list):
                count = len(result)
                return f"📋 您有 {count} 个待办事项"
            return None
        
        elif action == "SEARCH":
            if isinstance(result, list):
                count = len(result)
                query = analysis.get("search_query", "")
                return f"🔍 找到 {count} 个与「{query}」相关的任务"
            return None
        
        return None  # 复杂场景返回None，由AI生成
    
    def _get_fallback_response(self, action: str) -> str:
        """获取默认响应"""
        fallbacks = {
            "CREATE": "待办事项已创建成功！",
            "COMPLETE": "待办事项已标记为完成！",
            "UPDATE": "待办事项已更新！",
            "DELETE": "待办事项已删除！",
            "LIST": "这是您的待办事项列表：",
            "SEARCH": "搜索结果："
        }
        return fallbacks.get(action, "收到您的消息，正在处理中...")
