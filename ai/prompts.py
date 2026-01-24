"""
AI提示词和规则
提供时间识别规则和操作类型判断规则
"""
from datetime import datetime, timedelta


class PromptsMixin:
    """提示词和规则混入类"""
    
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
    
    def _get_decompose_prompt(self) -> str:
        """获取任务拆解提示词"""
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        day_2 = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        day_3 = (now + timedelta(days=3)).strftime("%Y-%m-%d")
        day_7 = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        
        return f"""你是一个智能任务拆解助手。将用户的复杂任务拆解为3-7个具体可执行的子任务。

**今天的日期是：{current_date}**
**明天的日期是：{tomorrow}**

拆解原则：
1. 每个子任务应该是具体、可执行的动作
2. 子任务按逻辑顺序排列
3. 子任务标题简洁（10字以内）

**日期计算规则（必须严格遵守！）：**
- 第一个子任务从明天 ({tomorrow}) 开始
- **最后一个子任务的截止日期必须 ≤ 今天 + 用户指定的天数**
- 计算公式：如果用户说"N天内"，最后任务日期 ≤ {current_date} + N天

具体示例（今天是 {current_date}）：
- "三天内" → 最后任务必须 ≤ {day_3}
- "一周内" → 最后任务必须 ≤ {day_7}
- "一个月内" → 最后任务必须 ≤ 今天+30天

**输出格式：严格的JSON对象**

字段：
- original_task: 原始任务描述
- subtasks: 子任务数组，每个子任务包含：
  - title: 子任务标题（必需，10字以内）
  - description: 详细描述（可选）
  - due_date: 截止日期（格式 YYYY-MM-DD）
  - priority: 优先级 1-5（1最高）
- estimated_total_days: 用户指定的天数（如"三天内"则为3）
- reasoning: 拆解理由

示例（今天是 {current_date}）：
输入："三天内完成PPT制作"
正确输出（注意最后任务日期不超过 {day_3}）：
{{
  "original_task": "三天内完成PPT制作",
  "subtasks": [
    {{"title": "确定PPT主题", "due_date": "{tomorrow}", "priority": 1}},
    {{"title": "收集素材内容", "due_date": "{day_2}", "priority": 2}},
    {{"title": "制作PPT", "due_date": "{day_3}", "priority": 3}}
  ],
  "estimated_total_days": 3,
  "reasoning": "三天内完成，任务日期从明天到第三天"
}}"""
