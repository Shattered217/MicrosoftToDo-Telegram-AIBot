"""
意图分析
包含文本分析和任务匹配功能
"""
import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class IntentMixin:
    """意图分析混入类"""
    
    async def analyze_text_for_todos(self, text: str, existing_todos: List[Dict] = None) -> Dict[str, Any]:
        """分析文本并提取待办事项信息"""
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        intent_analysis = await self._analyze_intent(text, current_time)
        
        # 如果是查询或创建，或者明确包含ID，直接返回初步结果
        if intent_analysis.get('action') in ['CREATE', 'LIST', 'SEARCH'] or intent_analysis.get('todo_id'):
            return intent_analysis
        
        if intent_analysis.get('action') in ['UPDATE', 'COMPLETE', 'DELETE']:
            candidates = [t for t in (existing_todos or []) if not t.get('completed', False)]
            
            if not candidates:
                return intent_analysis  # 没有候选任务，无法匹配
                
            resolved_result = await self._resolve_task_id_and_details(
                user_text=text,
                initial_analysis=intent_analysis,
                candidates=candidates
            )
            return resolved_result
            
        return intent_analysis

    async def _analyze_intent(self, text: str, current_time: str) -> Dict[str, Any]:
        """第一步：分析用户意图"""
        system_prompt = f"""你是一个智能待办事项意图分析器。分析用户输入的操作类型和关键信息。

核心原则：
1. 识别操作类型 (action)
2. 提取用户提到的任务关键描述 (target_description)
3. 提取修改后的新信息 (modification_intent)
4. 提取时间信息

{self._get_action_rules()}

{self._get_common_time_rules(current_time)}

**输出格式：严格的JSON对象**

必需字段：
- action: CREATE/UPDATE/COMPLETE/DELETE/LIST/SEARCH
- title: 如果是CREATE，为任务标题；如果是UPDATE/COMPLETE/DELETE，为用于搜索的关键词（不是新标题！）
- description: 详细描述（仅CREATE）
- due_date, reminder_date, reminder_time: 仅CREATE时填写，UPDATE时留空
- search_query: 搜索关键词
- todo_id: 如果用户明确提供了ID（极少见），否则留空
- target_description: 用户用来指代目标任务的描述（如"把跑步时间改为下午2点" -> "跑步"）
- modification_intent: 如果是UPDATE，描述要修改什么（如"把跑步时间改为下午2点" -> "时间改为下午2点"）
- confidence: 0-1

UPDATE示例：
输入："把跑步时间修改为下午2点"
输出：{{"action": "UPDATE", "title": "跑步", "target_description": "跑步", "modification_intent": "时间改为下午2点", ...}}
"""

        user_prompt = f"用户输入：{text}"
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=800,
                    response_format={"type": "json_object"} if "gpt-4" in self.model.lower() else None
                )
                
                content = response.choices[0].message.content
                result = self._robust_json_parse(content)
                
                if result:
                    result = self._validate_and_fix_dates(result)
                    return result
                    
            except Exception as e:
                logger.warning(f"意图分析失败 (尝试 {attempt+1}): {e}")
                if attempt == max_retries:
                    break
                await asyncio.sleep(1)
        
        # Fallback
        return {
            "action": "CREATE",
            "title": text[:30],
            "confidence": 0.0
        }

    async def _resolve_task_id_and_details(self, user_text: str, initial_analysis: Dict[str, Any], candidates: List[Dict]) -> Dict[str, Any]:
        """第二步：根据候选列表匹配确切任务"""
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        candidates_str = "\n".join([
            f"- [ID: {t['id']}] {t.get('title', '无标题')} (创建于: {t.get('createdDateTime', '未知')})"
            for t in candidates
        ])
        
        system_prompt = f"""你是一个智能任务匹配助手。你的任务是根据用户输入和意图，从候选任务列表中找到最匹配的任务，并生成最终的操作参数。

当前时间：{current_time}

候选任务列表：
{candidates_str}

用户原始输入：{user_text}
初步意图分析：{initial_analysis.get('action')} - {initial_analysis.get('target_description')}

任务：
1. **匹配任务**：基于用户的描述（"{initial_analysis.get('target_description', '')}"），在候选列表中找到最匹配的任务ID。
2. **生成更新参数**：
    - 如果是UPDATE：
      * 分析修改意图："{initial_analysis.get('modification_intent', '')}"
      * 只输出需要修改的字段！
      * 如果只修改时间，title 必须为 null
      * 如果只修改标题，时间字段必须为 null
      * 例如："把跑步时间改为下午2点" -> {{"title": null, "reminder_time": "14:00"}}
      * 例如："把任务改名为跑步锻炼" -> {{"title": "跑步锻炼", "reminder_time": null}}
    - 如果是COMPLETE/DELETE：只需返回ID。

**输出格式：严格的JSON对象**

字段：
- todo_id: 匹配到的任务ID（必需，如果在列表中找到）
- action: 保持原操作类型（UPDATE/COMPLETE/DELETE），或者如果有歧义转为SEARCH
- title: 更新后的新标题（仅UPDATE且修改标题时），否则必须为 null
- due_date: 更新后的截止日期（仅UPDATE且修改截止日期时），格式 YYYY-MM-DD
- reminder_date: 更新后的提醒日期（仅UPDATE且修改提醒时），格式 YYYY-MM-DD
- reminder_time: 更新后的提醒时间（仅UPDATE且修改提醒时），格式 HH:MM
- confidence: 匹配置信度 (0-1)
- reasoning: 匹配理由

重要：不修改的字段必须设为 null，不要返回原值！
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}],
                temperature=0.4, # 稍微高一点以便模糊匹配
                max_tokens=800,
                response_format={"type": "json_object"} if "gpt-4" in self.model.lower() else None
            )
            
            content = response.choices[0].message.content
            logger.info(f"任务匹配结果: {content[:200]}...")
            
            result = self._robust_json_parse(content)
            if result:
                final_result = initial_analysis.copy()
                final_result.update(result)
                return self._validate_and_fix_dates(final_result)
                
        except Exception as e:
            logger.error(f"任务匹配失败: {e}")
            
        return initial_analysis
