#!/usr/bin/env python3
"""
基于用户成功测试的令牌获取脚本
"""
import requests
import json
from config import Config

def get_auth_url():
 """获取授权URL"""
 client_id = Config.MS_TODO_CLIENT_ID
 redirect_uri = "http://localhost:3000/callback"
 
 # 检测是否有client_secret来判断账户类型
 if Config.MS_TODO_CLIENT_SECRET:
 # 工作/学校账户使用organizations或specific tenant
 authority = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}"
 print("检测到工作/学校账户模式（有client_secret）")
 else:
 # 个人账户使用consumers
 authority = "https://login.microsoftonline.com/consumers"
 print("检测到个人账户模式（无client_secret）")
 
 scopes = "offline_access https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read"
 
 return (
 f"{authority}/oauth2/v2.0/authorize"
 f"?client_id={client_id}"
 f"&response_type=code"
 f"&redirect_uri={redirect_uri}"
 f"&response_mode=query"
 f"&scope={scopes}"
 f"&state=12345"
 )

def get_client_credentials_token():
 """使用客户端凭据流获取令牌（工作/学校账户）"""
 if not Config.MS_TODO_CLIENT_SECRET:
 print("客户端凭据流需要client_secret")
 return None
 
 token_url = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}/oauth2/v2.0/token"
 
 data = {
 "client_id": Config.MS_TODO_CLIENT_ID,
 "client_secret": Config.MS_TODO_CLIENT_SECRET,
 "scope": "https://graph.microsoft.com/.default",
 "grant_type": "client_credentials"
 }
 
 try:
 print("使用客户端凭据流获取令牌...")
 r = requests.post(token_url, data=data, verify=False)
 result = r.json()
 
 if "error" in result:
 error_desc = result.get('error_description', result.get('error'))
 print(f"获取令牌失败: {error_desc}")
 
 # 检查是否是条件访问策略问题
 if "AADSTS53003" in str(error_desc) or "Conditional Access" in str(error_desc):
 print("这通常是由于组织的条件访问策略限制了应用程序访问")
 print(" 建议联系IT管理员或使用授权码流（浏览器登录）")
 
 return None
 
 # 客户端凭据流不返回refresh_token，我们使用access_token作为refresh_token的占位符
 result["refresh_token"] = "client_credentials_flow"
 return result
 
 except Exception as e:
 print(f"获取令牌时出错: {e}")
 return None

def exchange_code_for_token(code):
 """用授权码交换令牌"""
 client_id = Config.MS_TODO_CLIENT_ID
 redirect_uri = "http://localhost:3000/callback"
 
 # 根据是否有client_secret选择不同的authority
 if Config.MS_TODO_CLIENT_SECRET:
 authority = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}"
 else:
 authority = "https://login.microsoftonline.com/consumers"
 
 scopes = "offline_access https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read"
 
 token_url = f"{authority}/oauth2/v2.0/token"
 data = {
 "client_id": client_id,
 "grant_type": "authorization_code",
 "code": code,
 "redirect_uri": redirect_uri,
 "scope": scopes,
 }
 
 # 如果有client_secret，添加到请求中（工作/学校账户需要）
 if Config.MS_TODO_CLIENT_SECRET:
 data["client_secret"] = Config.MS_TODO_CLIENT_SECRET
 print("使用密钥认证（工作/学校账户）")
 else:
 print("🔓 使用公共客户端认证（个人账户）")
 
 r = requests.post(token_url, data=data, verify=False)
 return r.json()

def save_tokens_to_env(tokens):
 """保存令牌到.env文件"""
 if "access_token" not in tokens or "refresh_token" not in tokens:
 print("令牌数据不完整")
 return False
 
 try:
 # 读取现有的.env文件
 env_lines = []
 try:
 with open('.env', 'r', encoding='utf-8') as f:
 env_lines = f.readlines()
 except FileNotFoundError:
 pass
 
 # 更新或添加令牌
 access_token_found = False
 refresh_token_found = False
 
 for i, line in enumerate(env_lines):
 if line.startswith('MS_TODO_ACCESS_TOKEN='):
 env_lines[i] = f'MS_TODO_ACCESS_TOKEN={tokens["access_token"]}\n'
 access_token_found = True
 elif line.startswith('MS_TODO_REFRESH_TOKEN='):
 env_lines[i] = f'MS_TODO_REFRESH_TOKEN={tokens["refresh_token"]}\n'
 refresh_token_found = True
 
 # 如果没有找到，则添加
 if not access_token_found:
 env_lines.append(f'MS_TODO_ACCESS_TOKEN={tokens["access_token"]}\n')
 if not refresh_token_found:
 env_lines.append(f'MS_TODO_REFRESH_TOKEN={tokens["refresh_token"]}\n')
 
 # 写回文件
 with open('.env', 'w', encoding='utf-8') as f:
 f.writelines(env_lines)
 
 print(" 令牌已保存到.env文件")
 return True
 
 except Exception as e:
 print(f"保存令牌失败: {e}")
 return False

def main():
 """主函数"""
 print("Microsoft Todo 令牌获取")
 print("=" * 40)
 
 # 检查配置
 if not Config.MS_TODO_CLIENT_ID:
 print("缺少 MS_TODO_CLIENT_ID")
 print("请在.env文件中设置您的Azure应用程序ID")
 return False
 
 # 根据是否有client_secret选择不同的认证方式
 if Config.MS_TODO_CLIENT_SECRET:
 print("检测到工作/学校账户配置（有client_secret）")
 print(f" Tenant ID: {Config.MS_TODO_TENANT_ID}")
 
 print("配置检查通过")
 print(f"Client ID: {Config.MS_TODO_CLIENT_ID}")
 
 print("\n尝试客户端凭据流（无需浏览器登录）...")
 # 首先尝试客户端凭据流
 tokens = get_client_credentials_token()
 
 if not tokens:
 print("\n 客户端凭据流失败，可能是由于条件访问策略限制")
 print("🌐 切换到授权码流（需要浏览器登录）")
 
 # 如果客户端凭据流失败，使用授权码流
 print("\n请打开下面的链接登录并授权：")
 auth_url = get_auth_url()
 print(auth_url)
 
 print("\n授权步骤：")
 print("1. 点击上面的链接")
 print("2. 使用您的Microsoft工作/学校账户登录")
 print("3. 同意授权请求")
 print("4. 浏览器会跳转到localhost:3000/callback?code=...")
 print("5. 复制地址栏中 code= 后面的所有内容（到&之前）")
 
 code = input("\n📥 请粘贴授权码（code参数的值）：\n> ").strip()
 
 if not code:
 print("授权码不能为空")
 return False
 
 print("正在交换令牌...")
 try:
 tokens = exchange_code_for_token(code)
 
 if "error" in tokens:
 print(f"获取令牌失败: {tokens.get('error_description', tokens.get('error'))}")
 return False
 
 except Exception as e:
 print(f"获取令牌时出错: {e}")
 return False
 
 else:
 print("检测到个人账户配置（无client_secret）")
 print("个人账户使用公共客户端模式（需要浏览器登录）")
 
 print("配置检查通过")
 print(f"Client ID: {Config.MS_TODO_CLIENT_ID}")
 
 print("\n🌐 请打开下面的链接登录并授权：")
 auth_url = get_auth_url()
 print(auth_url)
 
 print("\n授权步骤：")
 print("1. 点击上面的链接")
 print("2. 使用您的Microsoft个人账户登录")
 print("3. 同意授权请求")
 print("4. 浏览器会跳转到localhost:3000/callback?code=...")
 print("5. 复制地址栏中 code= 后面的所有内容（到&之前）")
 
 code = input("\n📥 请粘贴授权码（code参数的值）：\n> ").strip()
 
 if not code:
 print("授权码不能为空")
 return False
 
 print("正在交换令牌...")
 try:
 tokens = exchange_code_for_token(code)
 
 if "error" in tokens:
 print(f"获取令牌失败: {tokens.get('error_description', tokens.get('error'))}")
 return False
 
 except Exception as e:
 print(f"获取令牌时出错: {e}")
 return False
 
 # 公共的令牌处理逻辑
 print("成功获取令牌！")
 print(f"Access Token: {tokens['access_token'][:50]}...")
 if tokens.get('refresh_token') != 'client_credentials_flow':
 print(f"Refresh Token: {tokens['refresh_token'][:50]}...")
 else:
 print("Refresh Token: 客户端凭据流（无需刷新令牌）")
 print(f"过期时间: {tokens.get('expires_in', 'N/A')} 秒")
 
 # 保存到.env文件
 if save_tokens_to_env(tokens):
 print("\n 令牌获取完成！您现在可以运行 'python3 main.py' 启动Telegram Bot")
 return True
 else:
 print("\n 令牌获取成功但保存失败，请手动添加到.env文件")
 return False

if __name__ == "__main__":
 success = main()
 if not success:
 print("\n如果遇到问题，请检查:")
 print("- Azure应用注册配置是否正确")
 print("- 重定向URI是否设置为 http://localhost:3000/callback")
 print("- 是否添加了正确的API权限并同意授权")
