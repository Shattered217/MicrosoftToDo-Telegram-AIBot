from functools import wraps
from flask import request, jsonify
from config import Config


def require_api_key(f):
    """API 密钥验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != Config.ESP32_API_KEY:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated_function
