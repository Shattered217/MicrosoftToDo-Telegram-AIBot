"""
Token刷新管理
处理OAuth令牌刷新和客户端凭据流
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TokenManagerMixin:
    """Token刷新管理混入类"""

    access_token: Optional[str]
    refresh_token: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    tenant_id: str
    session: Any
    expires_at: Optional[float]
    token_type: Optional[str]
    scope: Optional[str]

    async def _ensure_session(self) -> None:
        raise NotImplementedError

    def _update_token_cache(self) -> None:
        raise NotImplementedError

    def _save_tokens_to_env(
        self, access_token: str, refresh_token: Optional[str] = None
    ) -> bool:
        """将token保存到.env文件"""
        try:
            env_lines = []
            try:
                with open(".env", "r", encoding="utf-8") as f:
                    env_lines = f.readlines()
            except FileNotFoundError:
                logger.warning(".env文件不存在，将创建新文件")

            access_token_found = False
            refresh_token_found = False

            for i, line in enumerate(env_lines):
                if line.startswith("MS_TODO_ACCESS_TOKEN="):
                    env_lines[i] = f"MS_TODO_ACCESS_TOKEN={access_token}\n"
                    access_token_found = True
                elif line.startswith("MS_TODO_REFRESH_TOKEN=") and refresh_token:
                    env_lines[i] = f"MS_TODO_REFRESH_TOKEN={refresh_token}\n"
                    refresh_token_found = True

            if not access_token_found:
                env_lines.append(f"MS_TODO_ACCESS_TOKEN={access_token}\n")
            if not refresh_token_found and refresh_token:
                env_lines.append(f"MS_TODO_REFRESH_TOKEN={refresh_token}\n")

            with open(".env", "w", encoding="utf-8") as f:
                f.writelines(env_lines)

            return True

        except Exception as e:
            logger.error(f"保存Token到.env失败: {e}")
            return False

    async def _refresh_access_token(self) -> bool:
        """刷新访问令牌"""
        if not self.refresh_token:
            logger.error("没有刷新令牌，无法刷新访问令牌")
            return False

        if self.refresh_token == "client_credentials_flow":
            logger.info("检测到客户端凭据流，重新获取访问令牌")
            return await self._get_client_credentials_token()

        if not self.client_id:
            logger.error("缺少client_id，无法刷新令牌")
            logger.info("请在.env文件中设置 MS_TODO_CLIENT_ID")
            return False

        await self._ensure_session()

        if self.client_secret:
            token_url = (
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            )
            logger.info("使用工作/学校账户刷新令牌")
        else:
            token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
            logger.info("使用个人账户刷新令牌")

        data = {
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read offline_access",
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        try:
            async with self.session.post(token_url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    access_token = token_data.get("access_token")
                    if not isinstance(access_token, str) or not access_token:
                        logger.error("令牌刷新成功但返回access_token为空")
                        return False
                    access_token_str: str = access_token

                    self.access_token = access_token_str
                    new_refresh_token = token_data.get("refresh_token")
                    expires_in = token_data.get("expires_in")
                    token_type = token_data.get("token_type")
                    scope = token_data.get("scope")

                    if new_refresh_token:
                        self.refresh_token = new_refresh_token
                    elif token_data.get("refresh_token"):
                        self.refresh_token = token_data.get("refresh_token")

                    try:
                        expires_in_value = (
                            float(expires_in) if expires_in is not None else 0.0
                        )
                    except (TypeError, ValueError):
                        expires_in_value = 0.0
                    self.expires_at = (
                        (time.time() + expires_in_value)
                        if expires_in_value > 0
                        else None
                    )
                    self.token_type = (
                        token_type if isinstance(token_type, str) else None
                    )
                    self.scope = scope if isinstance(scope, str) else None

                    if hasattr(self, "_update_token_cache"):
                        self._update_token_cache()

                    self._save_tokens_to_env(
                        access_token_str,
                        self.refresh_token if new_refresh_token else None,
                    )

                    logger.info("访问令牌刷新成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"令牌刷新失败: {response.status} - {error_text}")
                    return False

        except Exception as e:
            logger.error(f"令牌刷新异常: {e}")
            return False

    async def _get_client_credentials_token(self) -> bool:
        """使用客户端凭据流获取访问令牌"""
        if not self.client_secret:
            logger.error("客户端凭据流需要client_secret")
            return False

        await self._ensure_session()

        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }

        try:
            async with self.session.post(token_url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data.get("access_token")
                    logger.info("客户端凭据流令牌获取成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(
                        f"客户端凭据流令牌获取失败: {response.status} - {error_text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"客户端凭据流异常: {e}")
            return False

    async def refresh_token_manually(self) -> bool:
        """手动刷新访问令牌（公共方法）"""
        logger.info("手动刷新访问令牌")
        return await self._refresh_access_token()
