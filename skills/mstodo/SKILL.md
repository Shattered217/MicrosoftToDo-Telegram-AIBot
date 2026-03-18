---
name: mstodo
description: Microsoft To Do management via CLI — create, query, complete, delete tasks in chat
metadata: {"openclaw":{"emoji":"✅","requires":{"bins":["uv"],"env":["MS_TODO_CLIENT_ID"]}}}
---

# mstodo (OpenClaw Skill)

## What this skill does

- Provides a safe, chat-first UX for Microsoft To Do.
- All operations go through a local CLI script:
  `uv run {baseDir}/scripts/run.py <command> [options]`
- Output is always JSON to stdout; logs go to stderr.

## Security / safety rules (must follow)

1. **Two-phase execution for writes**
   - For create/update/complete: if there is ambiguity or low confidence, ask a clarification question first.
2. **Disambiguation**
   - If a search returns multiple candidate tasks, present options and ask the user to pick.
3. **Delete is always double-confirmed**
   - Never delete without an explicit confirmation in the same chat.
4. **Never echo tokens**
   - Do not print access_token / refresh_token in chat logs.

## First-time setup

### 1) Install dependencies

```bash
uv sync --project {baseDir}
```

### 2) Authentication (interactive OAuth)

Step 1 — begin auth:

```bash
uv run {baseDir}/scripts/run.py auth_begin
```

Returns JSON with `auth_url`. Tell the user to open that URL in a browser, sign in with their Microsoft account, and paste the full redirected URL back.

Step 2 — finish auth (user pastes redirected URL):

```bash
uv run {baseDir}/scripts/run.py auth_finish --redirect '<PASTED_URL>'
```

Tokens are saved locally: `~/.openclaw/state/mstodo/tokens.json`

### 3) Verify

```bash
uv run {baseDir}/scripts/run.py auth_status
```

Should show `has_refresh_token: true`.

## Available commands

### Check auth status

```bash
uv run {baseDir}/scripts/run.py auth_status
```

### List all task lists

```bash
uv run {baseDir}/scripts/run.py lists
```

### List tasks

```bash
uv run {baseDir}/scripts/run.py tasks --status active --limit 50
```

Options: `--list-id <ID>`, `--status active|completed|all`, `--due-before <ISO_DATE>`, `--limit <N>`

### Search tasks by title

```bash
uv run {baseDir}/scripts/run.py search --query "meeting"
```

Options: `--list-id <ID>`, `--limit <N>`, `--status active|completed|all`

### Create a task

```bash
uv run {baseDir}/scripts/run.py create --title "Buy groceries" --due "2025-03-20" --reminder "2025-03-20T09:00:00" --note "Milk, eggs, bread"
```

Options: `--list-id <ID>`, `--due <ISO_DATE>`, `--reminder <ISO_DATETIME>`, `--note <TEXT>`

### Update a task

```bash
uv run {baseDir}/scripts/run.py update --task-id <ID> --title "New title" --due "2025-03-25"
```

Options: `--list-id <ID>`, `--title`, `--due`, `--reminder`, `--note`, `--status`

### Complete a task

```bash
uv run {baseDir}/scripts/run.py complete --task-id <ID>
```

Options: `--list-id <ID>`

### Delete a task

```bash
uv run {baseDir}/scripts/run.py delete --task-id <ID>
```

Options: `--list-id <ID>`

## Output format

Every command returns JSON to stdout:

```json
{"success": true, "data": { ... }}
```

On error:

```json
{"success": false, "error": "description of what went wrong"}
```

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
