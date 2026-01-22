"""
AI Service - 智能待办事项分析服务
通过混入类组合各功能模块
"""
import json
import re
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
from openai import AsyncOpenAI
from config import Config

# 导入功能混入类
from ai.prompts import PromptsMixin
from ai.intent import IntentMixin
from ai.image import ImageMixin
from ai.response import ResponseMixin

logger = logging.getLogger(__name__)


class AIService(PromptsMixin, IntentMixin, ImageMixin, ResponseMixin):
    """
    AI服务类
    
    通过多重继承组合所有功能：
    - PromptsMixin: 提示词和规则
    - IntentMixin: 意图分析
    - ImageMixin: 图片处理
    - ResponseMixin: 响应生成
    """
    
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
    
    def _robust_json_parse(self, content: str) -> Dict[str, Any]:
        """健壮的JSON解析，支持多种格式"""
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
