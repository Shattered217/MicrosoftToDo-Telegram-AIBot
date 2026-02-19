"""
响应生成
包含响应生成和模板响应功能
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ResponseMixin:
    """响应生成混入类"""
    
    async def generate_response(self, analysis_result: Dict[str, Any], operation_result: Any) -> str:
        """生成用户友好的响应文本（优先使用模板，复杂场景才用AI）"""
        action = analysis_result.get("action", "QUERY")
        confidence = analysis_result.get("confidence", 0.0)
        
        template_response = self._generate_template_response(action, analysis_result, operation_result)
        if template_response:
            return template_response
        
        try:
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
