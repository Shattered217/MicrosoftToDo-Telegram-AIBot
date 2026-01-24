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
        """分析图片并提取待办事项"""
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        image_data = self._compress_image_if_needed(image_data, max_size=512*1024)
        
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
