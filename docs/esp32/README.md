# ESP32 Bridge 部署指南

把 Microsoft To Do 的待办同步到 ESP32 设备。

## 架构

```
ESP32  ←→  Bridge (HTTP/MQTT)  ←→  scripts/run.py  ←→  Microsoft Graph API
```

Bridge 通过 `subprocess` 调用 `scripts/run.py` 完成所有 TODO 操作，不使用 MCP。

> 当前桥接分支：`claw-next-esp32`（从 `claw-next` 派生）。

## 运行模式

### HTTP 模式（推荐同局域网）

ESP32 主动拉取快照 + 发送命令：

- `GET /api/snapshot?device_id=esp32-1&limit=6` — 获取任务快照
- `POST /api/cmd` — 发送命令（complete/delete/create/update/set_completed）
- `GET /healthz` — 健康检查

### MQTT 模式（推荐异地/WAN）

ESP32 订阅任务 + 发布命令：

- `mstodo/{device_id}/tasks` — Bridge 定期发布任务快照（retain）
- `mstodo/{device_id}/cmd` — ESP32 发布命令
- `mstodo/{device_id}/ack` — Bridge 回复命令结果

## 安装

### 前置条件

- 已完成 mstodo skill 的授权（`~/.openclaw/state/mstodo/tokens.json` 存在）
- Python ≥ 3.11 + uv

### 一键安装（推荐）

项目提供了**一键安装脚本**，自动完成所有配置和启动：

```bash
# HTTP 模式（推荐同局域网）
./scripts/install-bridge.sh --mode http --port 7070

# MQTT 模式（推荐异地/WAN）
./scripts/install-bridge.sh --mode mqtt \
    --mqtt-broker <VPS_IP> \
    --mqtt-port 1883 \
    --mqtt-username <user> \
    --mqtt-password <pass> \
    --device-id esp32-1

# 两者同时（同时提供 HTTP 和 MQTT）
./scripts/install-bridge.sh --mode both \
    --port 7070 \
    --mqtt-broker <VPS_IP>
```

**脚本会自动完成：**
- ✅ 部署项目到 `~/.openclaw/tools/mstodo`
- ✅ 安装 Python 依赖（`uv sync`）
- ✅ 生成配置文件（`bridge.env`）
- ✅ 安装并启用 systemd 服务
- ✅ **默认自动启动服务**（不需要 `--start` 参数）

**服务管理命令：**
```bash
# 查看状态
systemctl --user status mstodo-bridge

# 重启服务
systemctl --user restart mstodo-bridge

# 停止服务
systemctl --user stop mstodo-bridge

# 查看日志
journalctl --user -u mstodo-bridge -f
```

### 手动运行（调试）

如需手动运行（不通过 systemd），使用 venv python：

```bash
# 进入项目目录
cd ~/.openclaw/tools/mstodo

# HTTP 模式
.venv/bin/python -m bridge.mstodo_bridge.daemon http --host 0.0.0.0 --port 7070

# MQTT 模式
.venv/bin/python -m bridge.mstodo_bridge.daemon mqtt \
    --mqtt-broker <IP> --mqtt-port 1883 \
    --mqtt-username <user> --mqtt-password <pass> \
    --device-id esp32-1 --publish-interval 60 --limit 6

# 或使用 uv（如果在开发环境）
uv run python -m bridge.mstodo_bridge.daemon http --host 0.0.0.0 --port 7070
```

## HTTP API 详情

### GET /api/snapshot

获取任务快照。

**参数：**
- `device_id` — 设备 ID（默认 `esp32-1`）
- `limit` — 最多返回几条（默认 6）

**响应：**
```json
{
  "device_id": "esp32-1",
  "tasks": [
    {
      "task_id": "AAMk...",
      "list_id": "AAMk...",
      "title": "买菜",
      "status": "notStarted",
      "due": "2025-03-20",
      "reminder": "2025-03-20 18:00"
    }
  ],
  "timestamp": "2025-03-16T12:00:00+08:00"
}
```

### POST /api/cmd

执行命令。

**请求体：**
```json
{
  "op": "complete",
  "task_id": "AAMk...",
  "list_id": "AAMk..."
}
```

支持的 `op`：`complete`、`delete`、`create`、`update`、`set_completed`

**响应：**
```json
{
  "success": true,
  "data": { ... }
}
```

`set_completed` 请求示例：

```json
{
  "op": "set_completed",
  "task_id": "AAMk...",
  "list_id": "AAMk...",
  "completed": false
}
```

其中：
- `completed: true` -> 等价执行 `complete`
- `completed: false` -> 等价执行 `update --status notStarted`

### GET /healthz

健康检查，返回 `{"status": "ok"}`。

## MQTT Mosquitto 部署（VPS）

如果使用 MQTT 模式且需要在 VPS 上部署 Mosquitto：

### 安装

```bash
sudo apt install mosquitto mosquitto-clients
```

### 配置账号密码

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd bridge_user
# 输入密码

sudo mosquitto_passwd /etc/mosquitto/passwd esp32_user
# 输入密码
```

### 配置文件

编辑 `/etc/mosquitto/conf.d/mstodo.conf`：

```
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd

# ACL（可选）
# acl_file /etc/mosquitto/acl
```

### 重启

```bash
sudo systemctl restart mosquitto
```

## 故障排查

- Bridge 日志：`journalctl --user -u mstodo-bridge -f`
- 测试 HTTP：`curl http://localhost:7070/api/snapshot?device_id=esp32-1`
- 测试 MQTT：`mosquitto_sub -h <VPS_IP> -u <user> -P <pass> -t 'mstodo/#' -v`
- 确认授权：`uv run scripts/run.py auth_status`（需要 `has_refresh_token: true`）
