"""
ESP32 Flask 服务器模块
提供 REST API 供 ESP32 设备访问 Microsoft TODO 数据
"""

from flask import Flask
from flask_cors import CORS


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__)
    CORS(app) 
    
    from esp32_server.routes import api_bp
    app.register_blueprint(api_bp)
    
    return app
