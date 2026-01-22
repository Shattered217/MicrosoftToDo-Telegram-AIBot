"""
Token刷新管理
处理OAuth令牌刷新和客户端凭据流
"""
import logging

logger = logging.getLogger(__name__)


class TokenManagerMixin:
    """Token刷新管理混入类"""
    
    async def _refresh_access_token(self) -> bool:
        """刷新访问令牌"""
        if not self.refresh_token:
            logger.error("没有刷新令牌，无法刷新访问令牌")
            return False
            
        # 检查是否是客户端凭据流
        if self.refresh_token == "client_credentials_flow":
            logger.info("检测到客户端凭据流，重新获取访问令牌")
            return await self._get_client_credentials_token()
        
        if not self.client_id:
            logger.error("缺少client_id，无法刷新令牌")
            logger.info("请在.env文件中设置 MS_TODO_CLIENT_ID")
            return False
        
        await self._ensure_session()
        
        # 根据是否有client_secret选择不同的authority和认证方式
        if self.client_secret:
            # 工作/学校账户
            token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            logger.info("使用工作/学校账户刷新令牌")
        else:
            # 个人账户
            token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
            logger.info("使用个人账户刷新令牌")
        
        data = {
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read offline_access"
        }
        
        # 只有工作/学校账户需要client_secret
        if self.client_secret:
            data["client_secret"] = self.client_secret
        
        try:
            async with self.session.post(token_url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data.get("access_token")
                    if "refresh_token" in token_data:
                        self.refresh_token = token_data["refresh_token"]
                    
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
        
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
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
                    logger.error(f"客户端凭据流令牌获取失败: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"客户端凭据流异常: {e}")
            return False

    async def refresh_token_manually(self) -> bool:
        """手动刷新访问令牌（公共方法）"""
        logger.info("手动刷新访问令牌")
        return await self._refresh_access_token()
