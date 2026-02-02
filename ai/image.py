"""
图片处理
包含图片压缩和图片分析功能
"""
import base64
import logging
import asyncio
from typing import Dict, Any, List, Optional

from config import Config

logger = logging.getLogger(__name__)


class ImageMixin:
    """图片处理混入类"""
    
    def _compress_image_if_needed(self, image_data: bytes, max_size: int = 1024*1024) -> bytes:
        """如果图片过大则压缩"""
        if len(image_data) <= max_size:
            return image_data
        
        try:
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(BytesIO(image_data))
            
            ratio = (max_size / len(image_data)) ** 0.5
            new_size = (int(img.width * ratio), int(img.height * ratio))
            
            img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
            
            output = BytesIO()
            img_resized.save(output, format='JPEG', quality=85, optimize=True)
            compressed = output.getvalue()
            
            logger.info(f"图片已压缩: {len(image_data)} -> {len(compressed)} bytes")
            return compressed
            
        except Exception as e:
            logger.warning(f"图片压缩失败，使用原图: {e}")
            return image_data
    
    async def analyze_image_for_todos(self, image_data: bytes, image_format: str, existing_todos: List[Dict] = None, caption: Optional[str] = None) -> Dict[str, Any]:
        """分析图片并提取待办事项（两步法：Vision提取 + FC分析）"""
        import json
        from datetime import datetime
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        image_data = self._compress_image_if_needed(image_data, max_size=512*1024)
        
        existing_context = ""
        if existing_todos and len(existing_todos) > 0:
            active_todos = [t for t in existing_todos if not t.get('completed', False)][:3]
            if active_todos:
                existing_context = "\n当前未完成任务：" + ", ".join([t.get('title', '')[:15] for t in active_todos])
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        vision_prompt = f"""请仔细分析这张图片，提取所有可能的待办事项信息。

当前时间：{current_time}
{existing_context}

请提取：
1. 图片中的所有文字内容
2. 识别出的任务或待办事项
3. 相关的时间、日期信息
4. 任务的优先级或重要性

请用中文详细描述你看到的内容。"""

        max_retries = 2
        image_description = None
        
        for attempt in range(max_retries + 1):
            try:
                user_parts = []
                if caption:
                    user_parts.append({"type": "text", "text": f"图片描述：{caption}\n\n{vision_prompt}"})
                else:
                    user_parts.append({"type": "text", "text": vision_prompt})
                    
                user_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{image_format};base64,{image_base64}"}
                })

                response = await self.client.chat.completions.create(
                    model=Config.OPENAI_VL_MODEL,
                    messages=[{"role": "user", "content": user_parts}],
                    temperature=0.3,
                    max_tokens=800
                )
                
                image_description = response.choices[0].message.content
                logger.info(f"图片内容提取成功: {image_description[:100]}...")
                break
                
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"图片内容提取失败（尝试 {attempt + 1}）: {e}")
                    await asyncio.sleep(1)
                    continue
                else:
                    logger.error(f"图片内容提取失败: {e}")
                    return {
                        "action": "CREATE",
                        "items": [{"title": "图片待办事项", "description": caption or "图片内容"}],
                        "confidence": 0.0,
                        "reasoning": "图片分析失败"
                    }
        
        if not image_description:
            return {
                "action": "CREATE",
                "items": [{"title": "图片待办事项"}],
                "confidence": 0.0
            }
        
        from ai.function_tools import get_image_analysis_tools
        
        tools = get_image_analysis_tools(current_time)
        
        analysis_prompt = f"""基于以下图片内容分析，提取待办事项：

图片内容：
{image_description}

用户备注：{caption if caption else '无'}

当前时间：{current_time}
{existing_context}

请提取待办事项信息。"""
        
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": analysis_prompt}],
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.4,
                    max_tokens=1000
                )
                
                message = response.choices[0].message
                
                if message.tool_calls:
                    tool_call = message.tool_calls[0]
                    result = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"图片分析完成: {result.get('image_description', 'N/A')}")
                    
                    from utils.datetime_helper import normalize_reminder, normalize_due_date
                    from datetime import datetime
                    
                    now = datetime.now()
                    
                    if result.get('due_date'):
                        normalized_due = normalize_due_date(result['due_date'], now)
                        result['due_date'] = normalized_due if normalized_due else None
                    
                    if result.get('reminder_date'):
                        reminder_info = normalize_reminder(
                            result['reminder_date'], 
                            result.get('reminder_time', '09:00'), 
                            now
                        )
                        if reminder_info:
                            result['reminder_date'] = reminder_info.date
                            result['reminder_time'] = reminder_info.time
                        else:
                            result['reminder_date'] = None
                            result['reminder_time'] = None
                    
                    result['image_description'] = image_description[:200]
                    
                    return result
                else:
                    logger.warning("AI未调用function，使用fallback")
                    
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"图片分析失败（尝试 {attempt + 1}）: {e}")
                    await asyncio.sleep(1)
                    continue
                else:
                    logger.error(f"图片分析失败: {e}")
                    break
        
        # Fallback
        return {
            "action": "CREATE",
            "items": [{"title": "图片待办", "description": image_description[:100]}],
            "image_description": image_description[:200],
            "confidence": 0.5,
            "reasoning": "基于图片内容创建"
        }
