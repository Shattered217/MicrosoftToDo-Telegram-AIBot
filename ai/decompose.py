"""
任务拆解模块
将复杂任务智能拆解为多个可执行的子任务
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# 复杂任务关键词模式
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
        # 只对 CREATE 操作建议拆解
        if analysis.get('action') != 'CREATE':
            return False
        
        # 检查是否包含复杂任务关键词
        text_lower = text.lower()
        has_complex_pattern = any(pattern in text_lower for pattern in COMPLEX_TASK_PATTERNS)
        
        # 检查任务标题长度（较长的标题可能是复杂任务）
        title = analysis.get('title', '')
        is_long_title = len(title) > 15
        
        # 检查置信度（低置信度可能意味着任务描述模糊）
        low_confidence = analysis.get('confidence', 1.0) < 0.7
        
        # 满足任意条件就建议拆解
        return has_complex_pattern or (is_long_title and low_confidence)
    
    async def decompose_task(self, task_description: str) -> Dict[str, Any]:
        """将复杂任务拆解为子任务列表"""
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        system_prompt = f"""你是一个智能任务拆解助手。将用户的复杂任务拆解为3-7个具体可执行的子任务。

当前时间：{current_time}

拆解原则：
1. 每个子任务应该是具体、可执行的动作
2. 子任务按逻辑顺序排列
3. 子任务标题简洁（10字以内）
4. **重要：第一个子任务的截止日期应从明天或后天开始**
5. 后续任务根据工作量合理递增，不要均匀分布
6. 紧急任务的日期应该更紧凑

**日期设置规则：**
- 第一个任务：明天或后天（{current_time[:10]} + 1~2天）
- 后续任务：根据前序任务的工作量递增
- 如果用户提到"一个月内"，最后一个任务应在约30天后
- 如果用户提到"一周内"，所有任务应在7天内完成

{self._get_common_time_rules(current_time)}

**输出格式：严格的JSON对象**

字段：
- original_task: 原始任务描述
- subtasks: 子任务数组，每个子任务包含：
  - title: 子任务标题（必需，10字以内）
  - description: 详细描述（可选）
  - due_date: 建议截止日期（格式 YYYY-MM-DD，第一个任务从明天开始！）
  - reminder_date: 建议提醒日期（可选，格式 YYYY-MM-DD）
  - reminder_time: 建议提醒时间（可选，格式 HH:MM）
  - priority: 优先级 1-5（1最高）
- estimated_total_days: 预估完成总天数
- reasoning: 拆解理由

示例（假设今天是2026-01-24）：
输入："一周内完成年终汇报"
输出：
{{
  "original_task": "一周内完成年终汇报",
  "subtasks": [
    {{"title": "收集年度数据", "due_date": "2026-01-25", "priority": 1}},
    {{"title": "梳理项目成果", "due_date": "2026-01-26", "priority": 2}},
    {{"title": "制作PPT", "due_date": "2026-01-28", "priority": 3}},
    {{"title": "准备演讲稿", "due_date": "2026-01-29", "priority": 4}},
    {{"title": "排练演示", "due_date": "2026-01-30", "priority": 5}}
  ],
  "estimated_total_days": 7,
  "reasoning": "紧急任务，第一步从明天开始"
}}
"""

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
                    temperature=0.5,
                    max_tokens=1200,
                    response_format={"type": "json_object"} if "gpt-4" in self.model.lower() else None
                )
                
                content = response.choices[0].message.content
                result = self._robust_json_parse(content)
                
                if result and 'subtasks' in result and len(result['subtasks']) > 0:
                    logger.info(f"任务拆解成功，生成 {len(result['subtasks'])} 个子任务")
                    return {
                        "action": "DECOMPOSE",
                        "original_task": task_description,
                        "subtasks": result['subtasks'],
                        "estimated_total_days": result.get('estimated_total_days', 7),
                        "reasoning": result.get('reasoning', ''),
                        "confidence": 0.9
                    }
                    
            except Exception as e:
                logger.warning(f"任务拆解失败 (尝试 {attempt+1}): {e}")
                if attempt == max_retries:
                    break
                await asyncio.sleep(1)
        
        # Fallback: 返回原始创建任务
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
        
        # 表情符号映射
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
