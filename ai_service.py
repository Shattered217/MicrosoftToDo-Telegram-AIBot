"""
AI服务主模块
提供统一的AI接口，整合了意图分析、图片处理和响应生成功能
"""
import logging
from openai import AsyncOpenAI
import json
import re
from typing import Dict, Any
from datetime import datetime, timedelta

from config import Config
from ai.intent import IntentMixin
from ai.image import ImageMixin
from ai.response import ResponseMixin
from ai.decompose import DecomposeMixin

logger = logging.getLogger(__name__)


class AIService(IntentMixin, ImageMixin, ResponseMixin, DecomposeMixin):
    """
    AI服务类
    
    混入类说明:
    - IntentMixin: 意图分析
    - ImageMixin: 图片分析
    - ResponseMixin: 响应生成
    - DecomposeMixin: 任务拆解
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.OPENAI_BASE_URL,
            timeout=60.0
        )
        self.model = Config.OPENAI_MODEL

