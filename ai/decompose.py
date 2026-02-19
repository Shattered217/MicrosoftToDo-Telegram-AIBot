"""
任务拆解模块
将复杂任务智能拆解为多个可执行的子任务
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


COMPLEX_TASK_PATTERNS = [
    "准备", "筹备", "组织", "策划", "规划",
    "完成", "搞定", "处理",
    "项目", "活动", "会议", "汇报", "报告",
    "出差", "旅行", "搬家", "装修",
    "学习", "考试", "面试",
]


class DecomposeMixin:
    """任务拆解混入类"""
    
    def _should_suggest_decompose(self, text: str, analysis: Dict[str, Any]) -> bool:
        """判断是否应该建议拆解任务"""
        if analysis.get('action') != 'CREATE':
            return False
        
        text_lower = text.lower()
        has_complex_pattern = any(pattern in text_lower for pattern in COMPLEX_TASK_PATTERNS)
        
        title = analysis.get('title', '')
        is_long_title = len(title) > 15
        
        low_confidence = analysis.get('confidence', 1.0) < 0.7
        
        return has_complex_pattern or (is_long_title and low_confidence)
    
    async def decompose_task(self, task_description: str, total_days: int = None) -> Dict[str, Any]:
        """将复杂任务拆解为子任务列表（使用Function Calling）"""
        import json
        from utils.datetime_helper import now_local
        current_time = now_local().strftime("%Y-%m-%d %H:%M")
        
        tools = get_decompose_tools(current_time, total_days)
        
        system_prompt = """你是一个智能任务拆解助手。
将复杂任务拆解为多个可执行的子任务。

拆解原则：
1. 子任务按逻辑顺序排列
2. 每个子任务都应具体可执行
3. 合理设置优先级和截止日期
4. 提供拆解思路说明
5. **重要**：所有子任务的累计时间不能超过原始任务的总时长！"""

        if total_days:
            user_prompt = f"请拆解以下任务：{task_description}\n\n原始任务总时长：{total_days}天。请确保所有子任务的累计时间不超过{total_days}天！"
        else:
            user_prompt = f"请拆解以下任务：{task_description}"
        
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.5,
                    max_tokens=1200
                )
                
                message = response.choices[0].message
                
                if message.tool_calls:
                    tool_call = message.tool_calls[0]
                    result = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"任务拆解成功，生成 {len(result['subtasks'])} 个子任务")
                    logger.info(f"拆解理由: {result.get('reasoning', 'N/A')}")
                    
                    from utils.datetime_helper import calculate_relative_time, now_local
                    now = now_local()
                    
                    # 累加天数
                    accumulated_days = 0
                    
                    for subtask in result['subtasks']:
                        if subtask.get('due_in_days') is not None:
                            days = subtask['due_in_days']
                            accumulated_days += days
                            
                            if accumulated_days > 0:
                                date_str, time_str = calculate_relative_time(now, days=accumulated_days, hours=9)
                            else:
                                date_str, time_str = calculate_relative_time(now, days=0)
                            
                            subtask['due_date'] = date_str
                            logger.info(f"子任务 '{subtask['title']}': 需要{days}天, 累计{accumulated_days}天 -> {date_str} {time_str}")
                    
                    return {
                        "action": "DECOMPOSE",
                        "original_task": result['original_task'],
                        "subtasks": result['subtasks'],
                        "estimated_total_days": result.get('estimated_total_days', 7),
                        "reasoning": result.get('reasoning', ''),
                        "confidence": 0.9
                    }
                else:
                    logger.warning("AI未调用function")
                    
            except Exception as e:
                logger.warning(f"任务拆解失败 (尝试 {attempt+1}): {e}")
                if attempt == max_retries:
                    break
                await asyncio.sleep(1)
        
        logger.warning("任务拆解失败，回退到普通创建")
        return {
            "action": "CREATE",
            "title": task_description[:30],
            "confidence": 0.3
        }

    
    def format_decompose_message(self, analysis: Dict[str, Any]) -> str:
        """格式化拆解结果为用户友好的消息"""
        subtasks = analysis.get('subtasks', [])
        original_task = analysis.get('original_task', '复杂任务')
        
        priority_emoji = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🔵"}
        
        message = f"🎯 **检测到复杂任务，建议拆解为以下子任务：**\n\n"
        message += f"📌 原始任务：{original_task}\n\n"
        
        for i, task in enumerate(subtasks, 1):
            priority = task.get('priority', 3)
            emoji = priority_emoji.get(priority, "⚪")
            title = task.get('title', f'子任务{i}')
            
            message += f"{emoji} **{i}. {title}**"
            
            if task.get('description'):
                message += f"\n   _{task['description']}_"
            
            if task.get('due_date'):
                message += f"\n   📅 截止: {task['due_date']}"
            
            message += "\n\n"
        
        if analysis.get('estimated_total_days'):
            message += f"⏱️ 预估总时长：{analysis['estimated_total_days']} 天\n"
        
        return message
