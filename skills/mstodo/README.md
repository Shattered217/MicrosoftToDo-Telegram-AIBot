# mstodo (OpenClaw Skill)

在 OpenClaw 中使用 Microsoft To Do。

## 安装

### 一键安装（推荐）

在项目根目录执行：

```bash
./scripts/install-mstodo.sh
```

这个脚本会自动：

- 部署 skill 到 `~/.openclaw/workspace/skills/mstodo`
- 安装依赖（自动寻找 `uv`）
- 创建 `~/.openclaw/state/mstodo`

### 配置

在 `~/.openclaw/openclaw.json` 中配置：

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

首次使用：在对话里说"开始 ToDo 授权"，按提示复制/粘贴跳转 URL。

### 手动安装（仅排障）

如果你不想用脚本，才需要：

```bash
cp -a ./skills/mstodo ~/.openclaw/workspace/skills/mstodo
uv sync --project <项目路径>
mkdir -p ~/.openclaw/state/mstodo
```

## Azure 应用注册要求

- **Redirect URI**: `http://localhost:3000/callback`
- **Delegated 权限**: `Tasks.ReadWrite`, `User.Read`, `offline_access`

更多交互规则见 `SKILL.md`。
