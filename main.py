import asyncio
import logging
import sys
from pathlib import Path

from config import Config
from telegram_bot import TodoTelegramBot

logging.basicConfig(
    level=logging.INFO if Config.DEBUG else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)

# 抑制 Telegram 轮询的网络错误日志（这些错误通常是暂时性的，不影响功能）
logging.getLogger('telegram.ext.Updater').setLevel(logging.CRITICAL)
logging.getLogger('httpx').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def main():
    try:
        logger.info("启动Bot...")
        
        config_errors = Config.validate()
        if config_errors:
            logger.error(f"配置验证失败: {', '.join(config_errors)}")
            print("\n配置错误:")
            for error in config_errors:
                print(f"  - {error}")
            print(f"\n请检查您的 .env 文件，参考 env_example.txt 进行配置。")
            return
        
        if not (Config.MS_TODO_ACCESS_TOKEN and Config.MS_TODO_REFRESH_TOKEN):
            logger.info("检测到缺少访问令牌")
            print("\n检测到缺少Microsoft Todo访问令牌")
            
            if Config.MS_TODO_CLIENT_SECRET:
                print("工作/学校账户模式：请运行以下命令获取令牌")
            else:
                print("个人账户模式：请运行以下命令获取令牌")
                
            print("python3 get_tokens.py")
            print("\n令牌获取成功后会自动保存到.env文件中")
            return
        
        logger.info("配置验证通过，启动Bot...")
        print("Microsoft Todo Telegram Bot 正在启动...")
        print("使用直接Microsoft Graph API连接")
        print(f"调试模式: {'开启' if Config.DEBUG else '关闭'}")
        
        bot = TodoTelegramBot()
        await bot.run_forever()
        
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")
        print("\nBot已停止运行")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        print(f"\n程序运行出错: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
