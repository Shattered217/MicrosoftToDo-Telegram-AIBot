"""
意图分析
包含文本分析和任务匹配功能
"""
import json
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
        
        intent_analysis = await self._analyze_intent(text)
        
        if intent_analysis.get('action') in ['CREATE', 'LIST', 'SEARCH'] or intent_analysis.get('todo_id'):
            return intent_analysis
        
        if intent_analysis.get('action') in ['UPDATE', 'COMPLETE', 'DELETE']:
            candidates = [t for t in (existing_todos or []) if not t.get('completed', False)]
            
            if not candidates:
                return intent_analysis
                
            resolved_result = await self._resolve_task_id_and_details(
                user_text=text,
                initial_analysis=intent_analysis,
                candidates=candidates
            )
            return resolved_result
            
        return intent_analysis

    async def _analyze_intent(self, text: str) -> Dict[str, Any]:
        """第一步：初步分析用户意图（使用Function Calling）"""
        import json
        from datetime import datetime
        from ai.function_tools import get_task_analysis_tools
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        tools = get_task_analysis_tools(current_time)
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": text}],
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=800
                )
                
                message = response.choices[0].message
                
                if message.tool_calls:
                    tool_call = message.tool_calls[0]
                    result = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"AI推断理由: {result.get('reasoning', 'N/A')}")
                    
                    from utils.datetime_helper import calculate_relative_time
                    from datetime import datetime
                    
                    now = datetime.now()
                    
                    if result.get('due_in_days') is not None:
                        date_str, _ = calculate_relative_time(now, days=result['due_in_days'])
                        result['due_date'] = date_str
                        logger.info(f"使用相对时间: due_in_days={result['due_in_days']} -> {date_str}")
                    
                    if (result.get('reminder_in_days') is not None or 
                        result.get('reminder_in_hours') is not None or 
                        result.get('reminder_in_minutes') is not None):
                        date_str, time_str = calculate_relative_time(
                            now,
                            days=result.get('reminder_in_days', 0),
                            hours=result.get('reminder_in_hours', 0),
                            minutes=result.get('reminder_in_minutes', 0)
                        )
                        result['reminder_date'] = date_str
                        result['reminder_time'] = time_str
                        logger.info(f"使用相对时间: {result.get('reminder_in_days', 0)}天"
                                  f"{result.get('reminder_in_hours', 0)}小时"
                                  f"{result.get('reminder_in_minutes', 0)}分钟 -> {date_str} {time_str}")
                    
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
            "confidence": 0.0,
            "reasoning": "意图分析失败，使用默认值"
        }

    async def _resolve_task_id_and_details(self, user_text: str, initial_analysis: Dict[str, Any], candidates: List[Dict]) -> Dict[str, Any]:
        """第二步：根据候选列表匹配确切任务（使用Function Calling）"""
        from ai.function_tools import get_task_match_tools
        
        tools = get_task_match_tools(
            candidates=candidates,
            user_text=user_text,
            initial_action=initial_analysis.get('action', 'UPDATE')
        )
        
        system_prompt = """你是一个智能任务匹配助手。
根据用户输入和候选任务列表，找到最匹配的任务并生成修改参数。

关键规则：
1. 仔细匹配任务ID
2. UPDATE时只输出需要修改的字段
3. 未修改的字段必须为null
4. 提供清晰的匹配理由"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}],
                tools=tools,
                tool_choice="auto",
                temperature=0.4,
                max_tokens=800
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                result = json.loads(tool_call.function.arguments)
                
                logger.info(f"任务匹配理由: {result.get('reasoning', 'N/A')}")
                
                final_result = initial_analysis.copy()
                final_result.update(result)
                
                from utils.datetime_helper import calculate_relative_time
                from datetime import datetime
                
                now = datetime.now()
                
                if final_result.get('due_in_days') is not None:
                    date_str, _ = calculate_relative_time(now, days=final_result['due_in_days'])
                    final_result['due_date'] = date_str
                    logger.info(f"使用相对时间: due_in_days={final_result['due_in_days']} -> {date_str}")
                
                if (final_result.get('reminder_in_days') is not None or
                    final_result.get('reminder_in_hours') is not None or
                    final_result.get('reminder_in_minutes') is not None):
                    date_str, time_str = calculate_relative_time(
                        now,
                        days=final_result.get('reminder_in_days', 0),
                        hours=final_result.get('reminder_in_hours', 0),
                        minutes=final_result.get('reminder_in_minutes', 0)
                    )
                    final_result['reminder_date'] = date_str
                    final_result['reminder_time'] = time_str
                    logger.info(f"使用相对时间: {final_result.get('reminder_in_days', 0)}天"
                              f"{final_result.get('reminder_in_hours', 0)}小时"
                              f"{final_result.get('reminder_in_minutes', 0)}分钟 -> {date_str} {time_str}")
                
                return final_result
            else:
                logger.warning("AI未调用function，使用初始分析结果")
                return initial_analysis
                
        except Exception as e:
            logger.error(f"任务匹配失败: {e}")
            return initial_analysis

