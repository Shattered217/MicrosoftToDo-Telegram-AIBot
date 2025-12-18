# Microsoft Todo Telegram Bot

一个智能的 Telegram 机器人，通过 ChatGPT API 进行语义分析，自动管理 Microsoft To Do 待办事项。支持文本和图片输入，直接与 Microsoft Graph API 集成，支持个人和工作/学校账户。

## 功能特性

### 智能语义分析

- 使用 ChatGPT API 分析用户输入的自然语言
- 自动识别用户意图（创建、更新、完成、删除、查询待办事项）
- 支持模糊匹配和智能推理

### Telegram Bot 交互

- 友好的中文界面
- 支持文本消息处理
- 支持图片识别（手写清单、白板、便签等）
- 丰富的命令支持

### 完整的待办事项管理

- 创建新的待办事项
- 查看所有/活跃的待办事项
- 更新现有任务内容
- 标记任务为完成
- 删除不需要的任务
- 按标题或日期搜索
- 生成待办事项摘要

### Microsoft Todo 集成

- 直接与 Microsoft Graph API 集成
- 支持个人和工作/学校账户
- 实时与 Microsoft To Do 同步
- 支持任务列表管理
- 自动令牌刷新
- 完整的错误处理

## 快速开始

### 1. 环境要求

- Python 3.8+
- Telegram Bot Token
- OpenAI API Key
- Microsoft 账户（个人账户或工作/学校账户）
- Azure 应用注册（用于 Microsoft Graph API 访问）

### 2. 安装依赖

```bash
git clone https://github.com/Shattered217/MicrosoftToDo-Telegram-AIBot.git
cd MicrosoftToDo-Telegram-AIBot
pip install -r requirements.txt
```

### 3. Azure 应用注册设置

#### 创建 Azure 应用注册

1. 访问 [Azure Portal](https://portal.azure.com)
2. 搜索并进入"应用注册"
3. 点击"新注册"
4. 填写应用信息：
   - 名称：`Todo Telegram Bot`
   - 支持的账户类型：选择"任何组织目录中的账户和个人 Microsoft 账户"
   - 重定向 URI：`http://localhost:3000/callback`

#### 配置 API 权限

1. 在应用页面，点击"API 权限"
2. 点击"添加权限"
3. 选择"Microsoft Graph"
4. 选择"委托的权限"
5. 添加以下权限：
   - `Tasks.Read`
   - `Tasks.ReadWrite`
   - `User.Read`
   - `offline_access`
6. 点击"授予管理员同意"（如果可用）

### 4. 配置环境变量

复制 `env_example.txt` 为 `.env` 并填写配置：

```env
# Telegram Bot Token (从 @BotFather 获取)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_ADMIN_IDS=your_telegram_user_id_here
# 可选：自定义 Telegram Bot API Base URL（例如通过 EdgeOne/反向代理加速）
TELEGRAM_BASE_URL=https://your-edgeone-or-proxy.example.com/bot

# OpenAI配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
OPENAI_VL_MODEL=Qwen/Qwen3-VL-32B-Instruct

# Microsoft Todo 应用注册信息（从Azure获取）
MS_TODO_CLIENT_ID=your_client_id_here
#MS_TODO_CLIENT_SECRET=your_client_secret_here
#需要工作/学校账户才可使用密钥实现自动获取refresh_token，填入密钥即视为工作/学校账户

# 可选配置
DEBUG=True
TIMEZONE=Asia/Shanghai
```

### 5. 获取 Microsoft Todo 访问令牌

```bash
python3 get_tokens.py
```

### 6. 运行程序

```bash
python3 main.py
```

## 使用方法

### 基本命令

- `/start` - 开始使用 Bot
- `/help` - 获取帮助信息
- `/menu` - 显示主菜单
- `/list` - 查看所有待办事项
- `/active` - 查看未完成的待办事项
- `/summary` - 获取待办事项摘要

### 令牌管理命令

- `/token_status` - 查看当前令牌状态和连接测试
- `/refresh_token` - 刷新访问令牌
- `/get_auth_link` - 获取授权链接重新授权

### 自然语言交互

#### 创建待办事项

- "明天要开会讨论项目进度"
- "买牛奶、面包和鸡蛋"
- "提醒我下周五交报告"

#### 完成任务

- "完成了买牛奶的任务"
- "开会任务做完了"

#### 更新任务

- "把买牛奶改成买酸奶"
- "更新会议时间为下午 3 点"

#### 搜索和查询

- "找一下关于会议的任务"
- "显示所有购物相关的待办事项"

#### 删除任务

- "删除买牛奶的任务"

### 图片识别

支持识别以下类型的图片内容：

- 手写的待办清单
- 会议白板上的任务
- 购物清单
- 提醒便签
- 日程安排
- 工作计划

只需发送图片，Bot 会自动识别并创建相应的待办事项。

## 项目结构

```
ToDoMCP/
├── main.py                    # 主程序入口
├── config.py                  # 配置管理
├── telegram_bot.py            # Telegram Bot实现
├── ai_service.py              # ChatGPT API集成
├── microsoft_todo_client.py   # Microsoft Graph API客户端
├── get_tokens.py              # 自动化令牌获取脚本
├── refresh_tokens.py          # 令牌刷新脚本
├── test_tokens.py             # 令牌有效性测试脚本
├── requirements.txt           # Python依赖
├── env_example.txt            # 环境变量示例
├── README.md                  # 项目说明
├── .gitignore                 # Git忽略文件
└── .env                       # 环境变量配置（需要创建）
```

## 技术架构

1. **Telegram Bot** - 处理用户输入和交互
2. **AI Service** - 使用 ChatGPT 进行语义分析
3. **Microsoft Graph Client** - 直接与 Microsoft Graph API 通信
4. **Config Management** - 统一的配置管理
5. **OAuth Helper** - 自动化令牌获取和刷新

## 令牌管理

### 通过 Telegram Bot 管理令牌（推荐）

#### 1. 查看令牌状态：`/token_status`

- 显示当前访问令牌和刷新令牌状态
- 自动测试与 Microsoft To-Do 的连接
- 显示账户类型（个人/工作学校）

#### 2. 刷新过期令牌：`/refresh_token`

- 使用现有刷新令牌获取新的访问令牌
- 自动保存到服务器配置文件
- 适用于令牌未完全过期的情况

#### 3. 重新授权：`/get_auth_link`

- 获取 Microsoft 登录授权链接
- 登录后复制授权码发送给 Bot
- 自动获取新的访问令牌和刷新令牌

## 部署说明

### 本地部署

按照快速开始部分的步骤即可在本地运行。

### 服务器部署

1. 将项目上传到服务器
2. 安装 Python 依赖
3. 配置环境变量
4. 使用 `screen` 或 `tmux` 在后台运行：

```bash
screen -S todobot
python3 main.py
# Ctrl+A, D 分离会话
```

### Docker 部署（可选）

```bash
# 构建镜像
docker build -t todobot .

# 运行容器
docker run -d --name todobot --env-file .env todobot
```

### CI/CD 自动部署 (推荐)

本项目支持通过 GitHub Actions 进行自动部署。

1.  **工作流**: 代码推送到 `main` 分支 -> GitHub Actions 自动连接服务器 -> 拉取最新代码 -> 使用 `uv` 安装依赖 -> 重启 Systemd 服务。
2.  **配置方法**: 请查看 [SERVER_SETUP.md](SERVER_SETUP.md) 获取详细的服务器配置和密钥设置指南。

## 许可证

MIT License

## 相关链接

- [Microsoft Graph API](https://docs.microsoft.com/en-us/graph/api/resources/todo-overview)
- [Azure App Registration](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [OpenAI API](https://platform.openai.com/docs)
- [microsoft-todo-mcp-server](https://github.com/jordanburke/microsoft-todo-mcp-server)
