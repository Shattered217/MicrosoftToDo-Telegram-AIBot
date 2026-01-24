#!/usr/bin/env python3

import requests
import json
from config import Config

def refresh_access_token():
	if not Config.MS_TODO_REFRESH_TOKEN:
		print("缺少 MS_TODO_REFRESH_TOKEN")
		return None

	if not Config.MS_TODO_CLIENT_ID:
		print("缺少 MS_TODO_CLIENT_ID")
		return None

	if Config.MS_TODO_REFRESH_TOKEN == "client_credentials_flow":
		print("检测到客户端凭据流，重新获取访问令牌...")
		return get_client_credentials_token()

	if Config.MS_TODO_CLIENT_SECRET:
		token_url = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}/oauth2/v2.0/token"
		print("使用工作/学校账户刷新令牌")
	else:
		token_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
		print("使用个人账户刷新令牌")

	data = {
		"client_id": Config.MS_TODO_CLIENT_ID,
		"refresh_token": Config.MS_TODO_REFRESH_TOKEN,
		"grant_type": "refresh_token",
		"scope": "https://graph.microsoft.com/Tasks.ReadWrite https://graph.microsoft.com/User.Read offline_access",
	}

	if Config.MS_TODO_CLIENT_SECRET:
		data["client_secret"] = Config.MS_TODO_CLIENT_SECRET

	try:
		r = requests.post(token_url, data=data, verify=False)
		result = r.json()

		if "error" in result:
			print(f"刷新令牌失败: {result.get('error_description', result.get('error'))}")
			return None

		return result

	except Exception as e:
		print(f"刷新令牌时出错: {e}")
		return None

def get_client_credentials_token():
	if not Config.MS_TODO_CLIENT_SECRET:
		print("客户端凭据流需要client_secret")
		return None

	token_url = f"https://login.microsoftonline.com/{Config.MS_TODO_TENANT_ID}/oauth2/v2.0/token"

	data = {
		"client_id": Config.MS_TODO_CLIENT_ID,
		"client_secret": Config.MS_TODO_CLIENT_SECRET,
		"scope": "https://graph.microsoft.com/.default",
		"grant_type": "client_credentials",
	}

	try:
		r = requests.post(token_url, data=data, verify=False)
		result = r.json()

		if "error" in result:
			print(f"获取令牌失败: {result.get('error_description', result.get('error'))}")
			return None

		result["refresh_token"] = "client_credentials_flow"
		return result

	except Exception as e:
		print(f"获取令牌时出错: {e}")
		return None

def save_tokens_to_env(tokens):
	if "access_token" not in tokens:
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

		access_token_found = False
		refresh_token_found = False

		for i, line in enumerate(env_lines):
			if line.startswith('MS_TODO_ACCESS_TOKEN='):
				env_lines[i] = f'MS_TODO_ACCESS_TOKEN={tokens["access_token"]}\n'
				access_token_found = True
			elif line.startswith('MS_TODO_REFRESH_TOKEN=') and "refresh_token" in tokens:
				env_lines[i] = f'MS_TODO_REFRESH_TOKEN={tokens["refresh_token"]}\n'
				refresh_token_found = True

		if not access_token_found:
			env_lines.append(f'MS_TODO_ACCESS_TOKEN={tokens["access_token"]}\n')
		if not refresh_token_found and "refresh_token" in tokens:
			env_lines.append(f'MS_TODO_REFRESH_TOKEN={tokens["refresh_token"]}\n')

		with open('.env', 'w', encoding='utf-8') as f:
			f.writelines(env_lines)

		print(" 新令牌已保存到.env文件")
		return True

	except Exception as e:
		print(f"保存令牌失败: {e}")
		return False

def main():
	"""主函数"""
	print("Microsoft Todo 令牌刷新")
	print("=" * 40)

	if Config.MS_TODO_ACCESS_TOKEN:
		print(f"当前 ACCESS_TOKEN: {Config.MS_TODO_ACCESS_TOKEN[:20]}...")
	else:
		print("未找到 ACCESS_TOKEN")
		return False

	if Config.MS_TODO_REFRESH_TOKEN:
		if Config.MS_TODO_REFRESH_TOKEN == "client_credentials_flow":
			print("当前 REFRESH_TOKEN: 客户端凭据流")
		else:
			print(f"当前 REFRESH_TOKEN: {Config.MS_TODO_REFRESH_TOKEN[:20]}...")
	else:
		print("未找到 REFRESH_TOKEN")
		return False

	print("\n正在刷新访问令牌...")
	tokens = refresh_access_token()

	if not tokens:
		print("令牌刷新失败")
		return False

	print("令牌刷新成功！")
	print(f"新 ACCESS_TOKEN: {tokens['access_token'][:50]}...")

	if tokens.get('refresh_token') and tokens['refresh_token'] != 'client_credentials_flow':
		print(f"新 REFRESH_TOKEN: {tokens['refresh_token'][:50]}...")
	elif tokens.get('refresh_token') == 'client_credentials_flow':
		print("REFRESH_TOKEN: 客户端凭据流（无需刷新令牌）")

	print(f"过期时间: {tokens.get('expires_in', 'N/A')} 秒")

	if save_tokens_to_env(tokens):
		print("\n 令牌刷新完成！新令牌已保存到.env文件")
		return True
	else:
		print("\n 令牌刷新成功但保存失败，请手动更新.env文件")
		return False

if __name__ == "__main__":
	success = main()
	if not success:
		print("\n如果遇到问题，请检查:")
		print("- 刷新令牌是否有效")
		print("- Azure应用注册配置是否正确")
		print("- 网络连接是否正常")
