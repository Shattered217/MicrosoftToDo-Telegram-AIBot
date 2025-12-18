# 服务器部署与配置指南

本指南将帮助您配置服务器以支持自动部署和使用 `uv` 管理环境。

## 1. 服务器环境准备

### 安装 `uv`

在您的服务器上运行以下命令安装 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 克隆项目 (如果您还没有)

```bash
# 假设您将项目放在 /root/MicrosoftToDo-Telegram-AIBot
cd /root
git clone https://github.com/Shattered217/MicrosoftToDo-Telegram-AIBot.git
cd MicrosoftToDo-Telegram-AIBot
```

_请记住您的项目路径，并在 `.github/workflows/deploy.yml` 和 `service/telegram-bot.service` 中更新它。_

## 2. 配置 Systemd 服务

Systemd 可以让您的 Python 程序在后台运行，并在崩溃或服务器重启后自动启动。

1.  **修改服务文件**
    在您上传代码后，`service/telegram-bot.service` 文件会出现在服务器上。
    使用 `vim` 或 `nano` 修改它，确保 `WorkingDirectory` 和 `ExecStart` 指向正确的路径。

    ```bash
    nano service/telegram-bot.service
    ```

    _确保 User, WorkingDirectory, ExecStart (指向 .venv/bin/python) 都是正确的。_

2.  **链接并启动服务**

    ```bash
    # 复制或链接到 systemd 目录
    sudo cp service/telegram-bot.service /etc/systemd/system/

    # 重新加载配置
    sudo systemctl daemon-reload

    # 启动服务
    sudo systemctl start telegram-bot

    # 设置开机自启
    sudo systemctl enable telegram-bot

    # 查看状态
    sudo systemctl status telegram-bot
    ```

## 3. GitHub Secrets 配置

为了让 GitHub 能连接到您的服务器，您需要配置 Secrets。

1.  **生成 SSH 密钥对 (在服务器上)**
    如果您还没有密钥对：

    ```bash
    ssh-keygen -t rsa -b 4096 -C "github-actions"
    # 一路回车，默认不设置密码
    ```

    将公钥添加到 `authorized_keys` 以允许登录：

    ```bash
    cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
    ```

2.  **获取私钥**
    查看私钥内容：

    ```bash
    cat ~/.ssh/id_rsa
    ```

    _复制所有内容，包括 `-----BEGIN ...` 和 `-----END ...`。_

3.  **添加到 GitHub**
    进入 GitHub 仓库 -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**。

    添加以下四个 Secrets：

    - `HOST`: 服务器 IP 地址
    - `USERNAME`: 登录用户名 (例如 root)
    - `KEY`: 刚才复制的私钥内容
    - `PROJECT_PATH`: 服务器上的项目绝对路径 (例如 `/root/MicrosoftToDo-Telegram-AIBot`)

## 4. 完成

现在，每当您将代码推送到 `main` 分支时，GitHub Actions 就会自动登录您的服务器，拉取代码，使用 `uv` 更新依赖，并重启服务。
