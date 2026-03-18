import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Microsoft To Do (core)
    MS_TODO_ACCESS_TOKEN = os.getenv("MS_TODO_ACCESS_TOKEN")
    MS_TODO_REFRESH_TOKEN = os.getenv("MS_TODO_REFRESH_TOKEN")
    MS_TODO_CLIENT_ID = os.getenv("MS_TODO_CLIENT_ID")
    MS_TODO_CLIENT_SECRET = os.getenv("MS_TODO_CLIENT_SECRET")

    _default_tenant = (
        "consumers" if not os.getenv("MS_TODO_CLIENT_SECRET") else "organizations"
    )
    MS_TODO_TENANT_ID = os.getenv("MS_TODO_TENANT_ID", _default_tenant)

    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Shanghai")

    @classmethod
    def validate(cls) -> List[str]:
        errors = []

        if not cls.MS_TODO_CLIENT_ID:
            errors.append("MS_TODO_CLIENT_ID 未设置")

        return errors
