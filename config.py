import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Config:
    
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_BASE_URL = os.getenv('TELEGRAM_BASE_URL')  # 可选：自定义 Telegram Bot API Base URL（如经由反向代理）
    
    TELEGRAM_ADMIN_IDS = os.getenv('TELEGRAM_ADMIN_IDS', '').split(',') if os.getenv('TELEGRAM_ADMIN_IDS') else []
    TELEGRAM_ADMIN_IDS = [int(id.strip()) for id in TELEGRAM_ADMIN_IDS if id.strip().isdigit()]
    
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    
    OPENAI_VL_MODEL = os.getenv('OPENAI_VL_MODEL', 'gpt-4o')
    
    
    MS_TODO_ACCESS_TOKEN = os.getenv('MS_TODO_ACCESS_TOKEN')
    MS_TODO_REFRESH_TOKEN = os.getenv('MS_TODO_REFRESH_TOKEN')
    MS_TODO_CLIENT_ID = os.getenv('MS_TODO_CLIENT_ID')
    MS_TODO_CLIENT_SECRET = os.getenv('MS_TODO_CLIENT_SECRET')
    
    _default_tenant = 'consumers' if not os.getenv('MS_TODO_CLIENT_SECRET') else 'organizations'
    MS_TODO_TENANT_ID = os.getenv('MS_TODO_TENANT_ID', _default_tenant)
    
    
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    MAX_IMAGE_SIZE = int(os.getenv('MAX_IMAGE_SIZE', '5242880'))
    ALLOWED_IMAGE_FORMATS = os.getenv('ALLOWED_IMAGE_FORMATS', 'jpg,jpeg,png,gif,webp').split(',')
    
    TIMEZONE = os.getenv('TIMEZONE', 'Asia/Shanghai')
    
    @classmethod
    def validate(cls) -> List[str]:
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN 未设置")
        
        if not cls.TELEGRAM_ADMIN_IDS:
            errors.append("TELEGRAM_ADMIN_IDS 未设置 - 必须设置至少一个管理员ID")
        
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY 未设置")
            
        if not cls.MS_TODO_CLIENT_ID:
            errors.append("MS_TODO_CLIENT_ID 未设置")
            
            
        return errors
