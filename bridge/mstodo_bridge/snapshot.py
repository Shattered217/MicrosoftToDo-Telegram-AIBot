"""Build task snapshot by calling scripts/run.py via subprocess."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from .models import TaskItem, TaskSnapshot
from .formatting import iso_to_date, iso_to_shanghai_minute

logger = logging.getLogger(__name__)

_SHANGHAI_TZ = timezone(timedelta(hours=8))

# Path to the project root (two levels up from this file)
_BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_BRIDGE_DIR))
_RUN_PY = os.path.join(_PROJECT_ROOT, "scripts", "run.py")


def _call_run_py(args: List[str], env: Optional[dict] = None) -> dict:
    """Call scripts/run.py with given args, return parsed JSON result."""
    cmd = [sys.executable, _RUN_PY] + args

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    start = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=_PROJECT_ROOT,
        env=run_env,
    )
    cost_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "run.py %s finished in %dms (rc=%d)", " ".join(args), cost_ms, result.returncode
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Try to parse stdout as JSON error
        try:
            data = json.loads(result.stdout)
            if not data.get("success"):
                raise RuntimeError(data.get("error", f"run.py failed: {stderr}"))
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"run.py exited {result.returncode}: {stderr}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"run.py returned invalid JSON: {e}")

    if not data.get("success"):
        raise RuntimeError(data.get("error", "Unknown error"))

    return data.get("data", {})


def build_snapshot(
    device_id: str, limit: int = 6, status: str = "active"
) -> TaskSnapshot:
    start = time.perf_counter()
    try:
        data = {"tasks": _list_tasks_via_core(limit=limit, status=status)}
    except Exception as e:
        logger.warning("Core path failed, fallback to run.py: %s", e)
        args = ["tasks", "--status", status, "--limit", str(limit)]
        try:
            data = _call_run_py(args)
        except Exception as fallback_error:
            logger.error("Failed to fetch tasks: %s", fallback_error)
            return TaskSnapshot(
                device_id=device_id,
                tasks=[],
                timestamp=_now_iso(),
            )

    raw_tasks = data.get("tasks", [])
    items: List[TaskItem] = []

    for t in raw_tasks[:limit]:
        due_raw = None
        due_dt = t.get("dueDateTime")
        if isinstance(due_dt, dict):
            due_raw = due_dt.get("dateTime")
        elif isinstance(due_dt, str):
            due_raw = due_dt
        if not due_raw:
            due = t.get("due")
            if isinstance(due, str):
                due_raw = due

        # Extract reminder
        reminder_raw = None
        reminder_dt = t.get("reminderDateTime")
        if isinstance(reminder_dt, dict):
            reminder_raw = reminder_dt.get("dateTime")
        elif isinstance(reminder_dt, str):
            reminder_raw = reminder_dt
        if not reminder_raw:
            reminder = t.get("reminder")
            if isinstance(reminder, str):
                reminder_raw = reminder

        # Extract note (body content)
        note = None
        body = t.get("body")
        if isinstance(body, dict):
            content = body.get("content", "")
            if content and content.strip():
                note = content.strip()

        items.append(
            TaskItem(
                task_id=t.get("id", ""),
                list_id=t.get("list_id", ""),
                title=t.get("title", ""),
                status=t.get("status", "notStarted"),
                due=iso_to_date(due_raw),
                reminder=iso_to_shanghai_minute(reminder_raw),
                note=note,
            )
        )

    snapshot = TaskSnapshot(
        device_id=device_id,
        tasks=items,
        timestamp=_now_iso(),
    )
    cost_ms = int((time.perf_counter() - start) * 1000)
    logger.info("build_snapshot finished in %dms with %d tasks", cost_ms, len(items))
    return snapshot


def execute_command(
    op: str, task_id: str | None = None, list_id: str | None = None, **kwargs
) -> dict:
    """Execute a command (complete/delete/create/update) via run.py."""
    if op in ("set_completed", "set-completed", "setComplete"):
        completed = kwargs.pop("completed", None)
        if isinstance(completed, bool) and not completed:
            op = "update"
            kwargs.setdefault("status", "notStarted")
        else:
            op = "complete"

    args = [op]

    if op in ("complete", "delete", "update"):
        args += ["--task-id", task_id]
        if list_id:
            args += ["--list-id", list_id]
        if op == "update":
            for k, v in kwargs.items():
                if v is not None:
                    args += [f"--{k.replace('_', '-')}", str(v)]
    elif op == "create":
        # For create, handle list_id and other params
        if list_id:
            args += ["--list-id", list_id]
        # Pass extra kwargs as --key value
        for k, v in kwargs.items():
            if v is not None:
                args += [f"--{k.replace('_', '-')}", str(v)]
    else:
        # For other operations, pass kwargs
        for k, v in kwargs.items():
            if v is not None:
                args += [f"--{k.replace('_', '-')}", str(v)]

    return _call_run_py(args)


def _now_iso() -> str:
    return datetime.now(_SHANGHAI_TZ).isoformat(timespec="seconds")


def _list_tasks_via_core(limit: int, status: str) -> List[dict]:
    async def _run() -> List[dict]:
        from core.mstodo import MSTodoCore

        core = MSTodoCore()
        try:
            return await core.list_tasks(status=status, limit=limit)
        finally:
            await core.close()

    return asyncio.run(_run())
