---
name: mstodo
description: Microsoft To Do management via CLI — create, query, complete, delete tasks in chat
metadata: {"openclaw":{"emoji":"✅","requires":{"bins":["uv"],"env":["MS_TODO_CLIENT_ID"]},"baseDir":"~/.openclaw/tools/mstodo"}}
---

# mstodo (OpenClaw Skill)

## What this skill does

- Provides a safe, chat-first UX for Microsoft To Do.
- All operations go through a local CLI script located at `~/.openclaw/tools/mstodo/scripts/run.py`
- Command format: `uv run ~/.openclaw/tools/mstodo/scripts/run.py <command> [options]`
- Output is always JSON to stdout; logs go to stderr.
- **Important**: The full project (including scripts/) must be deployed to `~/.openclaw/tools/mstodo` via `install-mstodo.sh`

## Security / safety rules (must follow)

1. **Two-phase execution for writes**
   - For create/update/complete: if there is ambiguity or low confidence, ask a clarification question first.
2. **Disambiguation**
   - If a search returns multiple candidate tasks, present options and ask the user to pick.
3. **Delete is always double-confirmed**
   - Never delete without an explicit confirmation in the same chat.
4. **Never echo tokens**
   - Do not print access_token / refresh_token in chat logs.
5. **Minimal execution for simple intents**
   - For straightforward requests like "创建一个吃饭任务，明天18:00提醒", execute in one direct command.
   - Do not run unrelated diagnostics (auth_status/lists/search) before a simple create/list unless the command fails.
   - On failure, run at most one targeted diagnosis, then retry once.
6. **Concise title + rich note**
   - Keep task title short and action-oriented (one line, core intent only).
   - Put contextual details into note as compact bullet-like lines (location, time window, participants, constraints, references).
   - Do not hardcode domain templates; extract detail fields from user input when available.
   - If key detail is missing and would change execution, ask one concise clarification question.

## Handling image inputs

When user sends an image with TODO request:

1. **Extract task details from image context**:
   - Analyze image content to understand what the TODO is about
   - Use image evidence as context, not as a hardcoded template
   - If OCR text is available, prefer explicit text signals over visual guesses

2. **Combine image analysis with user text**:
   - User text provides timing/priority ("明天", "下周")
   - Image provides the subject matter (what to do)
   - Keep title concise; put extracted supporting details into note

3. **Handle ambiguity**:
   - If image content is unclear, ask one concise clarification question
   - Offer 1-3 candidate interpretations only when confidence is low

4. **Time extraction**:
   - Parse relative time from user text ("明天" = tomorrow, "下周" = next week)
   - If user does not provide a concrete time, do not hardcode domain-specific defaults.
   - Prefer asking one clarification question for reminder time, or create without reminder when user intent is date-only.

## First-time setup

### 1) One-click install

Run the installation script to deploy the full project:

```bash
./scripts/install-mstodo.sh
```

This will:
- Deploy project to `~/.openclaw/tools/mstodo`
- Install dependencies via `uv sync`
- Copy skill to `~/.openclaw/workspace/skills/mstodo`

Manual copy/sync should be treated as troubleshooting only, not the default install flow.

### 2) Configure environment variables

**CRITICAL**: Set these in `~/.openclaw/openclaw.json` under `env`:

```json
{
  "env": {
    "MS_TODO_CLIENT_ID": "your-azure-app-client-id",
    "TIMEZONE": "Asia/Shanghai"
  }
}
```

**TIMEZONE is essential**:
- All task times are converted from local timezone to UTC
- Wrong timezone = wrong task times (e.g., 18:00 becomes 10:00)
- Common values: `Asia/Shanghai`, `America/New_York`, `Europe/London`
- Default if not set: `Asia/Shanghai`

**Runtime env source by mode**:
- OpenClaw chat skill mode: read env from `~/.openclaw/openclaw.json` (`env` section)
- ESP32 bridge service mode: read env from `~/.openclaw/state/mstodo/bridge.env` (systemd `EnvironmentFile`)
- `.env` in project directory is only a local token cache, not the authoritative service config source

### 3) Authentication (interactive OAuth)

Step 1 — begin auth:

```bash
# Using uv (if available)
uv run ~/.openclaw/tools/mstodo/scripts/run.py auth_begin

# OR using venv python directly
~/.openclaw/tools/mstodo/.venv/bin/python ~/.openclaw/tools/mstodo/scripts/run.py auth_begin
```

Returns JSON with `auth_url`. Tell the user to open that URL in a browser, sign in with their Microsoft account, and paste the full redirected URL back.

Step 2 — finish auth (user pastes redirected URL):

```bash
# Using uv (if available)
uv run ~/.openclaw/tools/mstodo/scripts/run.py auth_finish --redirect '<PASTED_URL>'

# OR using venv python directly
~/.openclaw/tools/mstodo/.venv/bin/python ~/.openclaw/tools/mstodo/scripts/run.py auth_finish --redirect '<PASTED_URL>'
```

Tokens are saved locally: `~/.openclaw/state/mstodo/tokens.json`

### 4) Verify

```bash
# Using uv (if available)
uv run ~/.openclaw/tools/mstodo/scripts/run.py auth_status

# OR using venv python directly
~/.openclaw/tools/mstodo/.venv/bin/python ~/.openclaw/tools/mstodo/scripts/run.py auth_status
```

Should show `has_refresh_token: true`.

**Note**: OpenClaw may use either execution method depending on environment. Both work identically.

## Available commands

All commands use the full path: `uv run ~/.openclaw/tools/mstodo/scripts/run.py <command> [options]`

### Check auth status

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py auth_status
```

### List all task lists

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py lists
```

### List tasks

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py tasks --status active --limit 50
```

Options: `--list-id <ID>`, `--status active|completed|all`, `--due-before <ISO_DATE>`, `--limit <N>`

### Search tasks by title

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py search --query "meeting"
```

Options: `--list-id <ID>`, `--limit <N>`, `--status active|completed|all`

### Create a task

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py create --title "Buy groceries" --due "2025-03-20" --reminder "2025-03-20T09:00:00" --note "Milk, eggs, bread"
```

Options: `--list-id <ID>`, `--due <ISO_DATE>`, `--reminder <ISO_DATETIME>`, `--note <TEXT>`

### Update a task

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py update --task-id <ID> --title "New title" --due "2025-03-25"
```

You can also resolve by title query:

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py update --query "meeting" --title "New title"
```

Options: `--task-id <ID>`, `--query <TEXT>`, `--list-id <ID>`, `--title`, `--due`, `--reminder`, `--note`, `--status`

Note: `--task-id` and `--query` are mutually exclusive.

### Complete a task

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py complete --task-id <ID>
```

You can also resolve by title query:

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py complete --query "meeting"
```

Options: `--task-id <ID>`, `--query <TEXT>`, `--list-id <ID>`

Note: `--task-id` and `--query` are mutually exclusive.

### Delete a task

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py delete --task-id <ID>
```

You can also resolve by title query:

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py delete --query "meeting"
```

Options: `--task-id <ID>`, `--query <TEXT>`, `--list-id <ID>`

Note: `--task-id` and `--query` are mutually exclusive.

### Complex heartbeat todo (fun mode)

```bash
uv run ~/.openclaw/tools/mstodo/scripts/run.py complex_todo --goal "Ship a resilient sync pipeline" --beats 6
```

Returns a structured plan with:
- `heartbeat_mode`: marker for OpenClaw-style heartbeat integration
- `heartbeats`: progress events (`beat`, `phase`, `progress`, `pulse`, `message`)
- `todos`: complex-task breakdown ready for orchestration

Contract details:
- `beats_requested`: user input
- `beats_applied`: internal clamp to `3..12`
- `schema_version`: currently `1`
- Heartbeat phases may be compressed when beat count is low; todo phases always cover `scan/shape/build/verify/ship`
- Existing keys are stable; new keys may be added in future

This command is read-only and does not call Microsoft Graph.

## Output format

Every command returns JSON to stdout:

```json
{"success": true, "data": { ... }}
```

On error:

```json
{"success": false, "error": "description of what went wrong", "error_code": "machine_readable_code"}
```

`error_code` is stable for programmatic handling. Typical values:
- `invalid_argument`
- `missing_env`
- `oauth_exchange_failed`
- `oauth_missing_refresh_token`
- `unknown_command`
- `runtime_error`

For query-based write commands, additional error codes may appear:
- `task_not_found` with `data: { query, candidates: [] }`
- `ambiguous_task` with `data: { query, candidates: [...] }`

Exit code 0 = success, 1 = error.

## Time strategy (important)

Microsoft To Do's `due` is a date (not datetime). This skill's strategy:

- **due**: date only (e.g. `2025-03-20`)
- **reminder**: carries the precise time (e.g. `2025-03-20T18:00:00`)

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MS_TODO_CLIENT_ID` | ✅ | — | Azure App Registration Client ID |
| `MS_TODO_TENANT_ID` | — | `consumers` | `consumers` for personal, `organizations` for work |
| `MS_TODO_CLIENT_SECRET` | — | — | Only for confidential apps |
| `MS_TODO_REDIRECT_URI` | — | `http://localhost:3000/callback` | OAuth redirect URI |
| `TIMEZONE` | — | `Asia/Shanghai` | Timezone for date display |
