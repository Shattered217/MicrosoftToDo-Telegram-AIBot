# mstodo (OpenClaw Skill)

在 OpenClaw 中使用 Microsoft To Do。

## 安装

1. 把本仓库克隆或复制到 OpenClaw workspace：

```bash
cp -a ./skills/mstodo ~/.openclaw/workspace/skills/mstodo
```

2. 安装依赖：

```bash
uv sync --project <项目路径>
```

3. 在 `~/.openclaw/openclaw.json` 中配置：

```json5
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

4. 首次使用：在对话里说"开始 ToDo 授权"，按提示复制/粘贴跳转 URL。

## Azure 应用注册要求

- **Redirect URI**: `http://localhost:3000/callback`
- **Delegated 权限**: `Tasks.ReadWrite`, `User.Read`, `offline_access`

更多交互规则见 `SKILL.md`。
