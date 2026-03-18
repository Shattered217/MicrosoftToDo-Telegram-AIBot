# Microsoft To Do for OpenClaw (mstodo)

把 **Microsoft To Do** 接入 OpenClaw：在对话里直接创建、查询、完成、删除待办，并提供更安全的交互（消歧、删除二次确认）。

- 适用：个人 Microsoft 账户（`consumers`）
- 特点：授权一次即可长期使用（refresh_token 本地保存）

---

## 你会得到什么

- 在 OpenClaw 里用自然语言管理 To Do：
  - "获取未完成任务"
  - "创建任务：… 截止后天，后天 18:00 提醒，简介：…"
  - "完成 XXX"
  - "删除 XXX"（会二次确认）
- 安全规则：
  - 多个任务匹配时必须让你选择（避免误操作）
  - 删除永远二次确认
  - 不在聊天中输出 token

---

## 架构

本仓库采用 **CLI 脚本** 方式，不使用 MCP 服务：

```
OpenClaw → bash → uv run scripts/run.py <command> → JSON stdout
```

所有 TODO 操作通过 `scripts/run.py` 这一个入口完成，OpenClaw 通过 Bash tool 调用。

---

## 安装

### 1) 复制 skill 到 OpenClaw workspace

```bash
cp -a ./skills/mstodo ~/.openclaw/workspace/skills/mstodo
```

### 2) 安装依赖

```bash
uv sync --project <项目路径>
```

### 3) 配置 OpenClaw

在 `~/.openclaw/openclaw.json` 中设置 skill 环境变量：

```json5
// ~/.openclaw/openclaw.json
{
  skills: {
    entries: {
      mstodo: {
        enabled: true,
        env: {
          MS_TODO_CLIENT_ID: "YOUR_CLIENT_ID",
          MS_TODO_TENANT_ID: "consumers",
          TIMEZONE: "Asia/Shanghai"
        }
      }
    }
  }
}
```

---

## 配置说明

你需要在 Azure 里创建一个应用注册（Microsoft Graph），并拿到 **Client ID**。

**必需的 Redirect URI：**

- `http://localhost:3000/callback`

**必需的 Delegated 权限：**

- `Tasks.ReadWrite`
- `User.Read`
- `offline_access`

---

## 第一次使用：授权（copy/paste）

在 OpenClaw 对话里对我说：

- "开始 ToDo 授权"

我会给你一个登录链接。你登录并同意授权后，浏览器会跳转到类似：

- `http://localhost:3000/callback?code=...&state=...`

把这个 **完整跳转 URL** 复制回聊天发给我即可完成授权。

> token 会保存到本机：`~/.openclaw/state/mstodo/tokens.json`

---

## 使用示例（对话）

- 获取未完成任务："获取未完成任务"
- 创建任务："创建任务：OpenClaw 测试；截止后天；后天 18:00 提醒；简介：验证链路"
- 完成任务："完成 OpenClaw 测试"
- 删除任务："删除 OpenClaw 测试"

---

## 时间策略（重要）

Microsoft To Do 的 due 往往更像"截止日期"而不是精确到分钟的时间点。

因此本 skill 的策略是：

- **due：只按日期处理**
- **reminder：承担精确时间**

---

## ESP32（可选）

本仓库在 `claw-next-esp32` 分支提供"设备桥接服务"（Bridge），用于把待办同步到 ESP32：

- **HTTP 模式（推荐同局域网）**：ESP32 主动拉取 `GET /api/snapshot`，点按后 `POST /api/cmd`
- **MQTT 模式（推荐异地/WAN）**：ESP32 订阅 tasks + 发布 cmd；Bridge 负责执行并回 ack

切换分支即可启用：

```bash
git checkout claw-next-esp32
```

---

## 故障排查

- 授权后提示拿不到 refresh_token：确认权限里有 `offline_access`。
- 授权跳转失败：确认 Redirect URI 设置为 `http://localhost:3000/callback`。
- 任务时间显示不对：确认 `TIMEZONE`（默认 Asia/Shanghai）。
