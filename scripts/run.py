#!/usr/bin/env python3
"""mstodo CLI — unified entry point for all To Do operations.

Usage:
  uv run scripts/run.py <command> [options]

Commands:
  auth_status                  Check token status
  auth_begin                   Start OAuth (returns auth URL)
  auth_finish  --redirect URL  Finish OAuth (paste redirect URL)
  lists                        List task lists
  tasks        [options]       List tasks
  search       --query TEXT    Search tasks by title
  create       --title TEXT    Create a task
  update       --task-id/--query Update a task
  complete     --task-id/--query Complete a task
  delete       --task-id/--query Delete a task
  complex_todo --goal TEXT     Build heartbeat-driven plan

All output is JSON to stdout. Logs go to stderr.
Exit code 0 = success, 1 = error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

# Ensure project root is on sys.path so core/todo/config imports work.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.mstodo import MSTodoCore
from core.oauth import (
    build_authorize_url,
    exchange_code_for_token,
    parse_code_from_redirect,
)
from core.token_store import TokenBundle, TokenStore

logging.basicConfig(
    level=logging.WARNING,
    format="[mstodo] %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _out(data: dict) -> None:
    """Print JSON result to stdout."""
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _ok(data: dict) -> None:
    _out({"success": True, "data": data})


def _err(msg: str, *, code: str = "cli_error") -> None:
    _out({"success": False, "error": msg, "error_code": code})
    sys.exit(1)


def _err_with_data(msg: str, *, code: str, data: dict) -> None:
    _out({"success": False, "error": msg, "error_code": code, "data": data})
    sys.exit(1)


def _require_nonempty(value: str | None, *, name: str) -> str:
    v = (value or "").strip()
    if not v:
        _err(f"{name} is required", code="invalid_argument")
    return v


def _require_positive(value: Any, *, name: str) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        _err(f"{name} must be an integer > 0", code="invalid_argument")
        return 1
    if v <= 0:
        _err(f"{name} must be > 0", code="invalid_argument")
    return v


async def _with_core(fn):
    """Run an async function with a MSTodoCore, then close."""
    core = MSTodoCore()
    try:
        return await fn(core)
    finally:
        await core.close()


async def _resolve_task_id_by_query(
    core: MSTodoCore,
    *,
    query: str,
    list_id: str | None,
    status: str,
) -> tuple[str | None, list[dict]]:
    q = _require_nonempty(query, name="--query")
    hits = await core.search_tasks(query=q, list_id=list_id, limit=10, status=status)
    candidates = [
        {
            "task_id": h.task_id,
            "list_id": h.list_id,
            "title": h.title,
            "status": h.status,
            "due": h.due,
            "score": h.score,
        }
        for h in hits
    ]

    # Prefer a single exact title match first (case-insensitive)
    q_norm = q.strip().lower()
    exact = [
        c
        for c in candidates
        if isinstance(c.get("title"), str) and c["title"].strip().lower() == q_norm
    ]
    if len(exact) == 1:
        return exact[0]["task_id"], exact
    if len(exact) > 1:
        return None, exact

    # If top candidate is clearly dominant, resolve directly to reduce noisy disambiguation.
    if len(candidates) >= 2:
        top = candidates[0]
        second = candidates[1]
        top_score = float(top.get("score", 0.0))
        second_score = float(second.get("score", 0.0))
        if top_score >= 0.85 and (top_score - second_score) >= 0.20:
            return top["task_id"], [top]

    if len(candidates) == 1:
        return candidates[0]["task_id"], candidates
    return None, candidates


def _heartbeat_phases() -> list[str]:
    return ["scan", "shape", "build", "verify", "ship"]


def _build_complex_todo(goal: str, beats: int) -> dict:
    phases = _heartbeat_phases()
    beat_count = max(3, min(12, int(beats)))
    words = [w for w in goal.replace("\n", " ").split(" ") if w.strip()]
    complexity = max(1, min(10, len(words) // 3 + 1))

    heartbeats = []
    for i in range(beat_count):
        progress = int(round(((i + 1) / beat_count) * 100))
        phase = phases[min(len(phases) - 1, (i * len(phases)) // beat_count)]
        pulse = "💓" if i % 2 == 0 else "💗"
        heartbeats.append(
            {
                "beat": i + 1,
                "phase": phase,
                "progress": progress,
                "pulse": pulse,
                "message": f"{pulse} {phase} {progress}%",
            }
        )

    where = "task execution"
    how = "Split work into milestones and verify each phase"
    why = f"deliver goal: {goal}"

    todos = [
        {
            "id": "T1",
            "title": f"[{where}] Gather constraints to {why} — expect clear success criteria",
            "phase": "scan",
            "risk": "scope drift",
        },
        {
            "id": "T2",
            "title": f"[{where}] Define milestones to {why} — expect ordered implementation plan",
            "phase": "shape",
            "risk": "missing dependency",
        },
        {
            "id": "T3",
            "title": f"[{where}] Execute core changes to {why} — expect feature-complete behavior",
            "phase": "build",
            "risk": "edge-case bug",
        },
        {
            "id": "T4",
            "title": f"[{where}] Run diagnostics/tests to {why} — expect green verification",
            "phase": "verify",
            "risk": "flaky checks",
        },
        {
            "id": "T5",
            "title": f"[{where}] Package and summarize to {why} — expect handoff-ready output",
            "phase": "ship",
            "risk": "unclear rollout",
        },
    ]

    return {
        "schema_version": 1,
        "goal": goal,
        "beats_requested": int(beats),
        "beats_applied": beat_count,
        "complexity": complexity,
        "heartbeat_mode": "openclaw-compatible",
        "heartbeats": heartbeats,
        "todos": todos,
        "next_action": {
            "type": "start_phase",
            "phase": "scan",
            "hint": how,
        },
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_auth_status(_args: argparse.Namespace) -> None:
    store = TokenStore()
    b = store.load()
    _ok(
        {
            "has_refresh_token": bool(b.refresh_token),
            "has_access_token": bool(b.access_token),
            "expires_at": b.expires_at,
            "store_path": store.path,
        }
    )


def cmd_auth_begin(args: argparse.Namespace) -> None:
    client_id = os.getenv("MS_TODO_CLIENT_ID") or ""
    if not client_id:
        _err("MS_TODO_CLIENT_ID is required in environment", code="missing_env")

    tenant_id = args.tenant_id or os.getenv("MS_TODO_TENANT_ID") or "consumers"
    redirect_uri = (
        args.redirect_uri
        or os.getenv("MS_TODO_REDIRECT_URI")
        or "http://localhost:3000/callback"
    )

    url, sess = build_authorize_url(
        client_id=client_id,
        tenant_id=tenant_id,
        redirect_uri=redirect_uri,
    )
    _ok(
        {
            "auth_url": url,
            "state": sess.state,
            "redirect_uri": sess.redirect_uri,
            "instructions": "Open auth_url in a browser, sign in, then paste the final redirected URL back into: uv run scripts/run.py auth_finish --redirect '<URL>'",
        }
    )


def cmd_auth_finish(args: argparse.Namespace) -> None:
    redirect = args.redirect
    if not redirect:
        _err(
            "--redirect is required (paste the full redirected URL or the code)",
            code="invalid_argument",
        )

    code, state, _params = parse_code_from_redirect(redirect)
    code = _require_nonempty(
        code,
        name="code (from redirect)",
    )

    client_id = os.getenv("MS_TODO_CLIENT_ID") or ""
    if not client_id:
        _err("MS_TODO_CLIENT_ID is required in environment", code="missing_env")

    tenant_id = os.getenv("MS_TODO_TENANT_ID") or "consumers"
    client_secret = os.getenv("MS_TODO_CLIENT_SECRET")
    redirect_uri = os.getenv("MS_TODO_REDIRECT_URI") or "http://localhost:3000/callback"

    tokens = asyncio.run(
        exchange_code_for_token(
            client_id=client_id,
            code=code,
            tenant_id=tenant_id,
            redirect_uri=redirect_uri,
            client_secret=client_secret,
        )
    )

    if isinstance(tokens, dict) and tokens.get("error"):
        msg = tokens.get("error_description") or tokens.get("error")
        if not isinstance(msg, str) or not msg:
            msg = "OAuth token exchange failed"
        _err(msg, code="oauth_exchange_failed")

    import time

    expires_in = float(tokens.get("expires_in") or 0)
    bundle = TokenBundle(
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        expires_at=(time.time() + expires_in) if expires_in else None,
        token_type=tokens.get("token_type"),
        scope=tokens.get("scope"),
    )
    if not bundle.refresh_token:
        _err(
            "No refresh_token returned. Ensure offline_access scope is granted.",
            code="oauth_missing_refresh_token",
        )

    store = TokenStore()
    store.save(bundle)
    _ok(
        {
            "saved": True,
            "store_path": store.path,
            "has_refresh_token": True,
            "note": "Tokens saved locally.",
        }
    )


def cmd_lists(_args: argparse.Namespace) -> None:
    async def _run(core: MSTodoCore):
        return await core.list_lists()

    lists = asyncio.run(_with_core(_run))
    _ok({"lists": lists})


def cmd_tasks(args: argparse.Namespace) -> None:
    async def _run(core: MSTodoCore):
        return await core.list_tasks(
            list_id=args.list_id,
            status=args.status,
            due_before=args.due_before,
            limit=args.limit,
        )

    args.limit = _require_positive(args.limit, name="--limit")
    tasks = asyncio.run(_with_core(_run))
    _ok({"tasks": tasks})


def cmd_search(args: argparse.Namespace) -> None:
    async def _run(core: MSTodoCore):
        hits = await core.search_tasks(
            query=args.query,
            list_id=args.list_id,
            limit=args.limit,
            status=args.status,
        )
        return [
            {
                "task_id": h.task_id,
                "list_id": h.list_id,
                "title": h.title,
                "status": h.status,
                "due": h.due,
                "score": h.score,
            }
            for h in hits
        ]

    args.query = _require_nonempty(args.query, name="--query")
    args.limit = _require_positive(args.limit, name="--limit")
    candidates = asyncio.run(_with_core(_run))
    _ok({"candidates": candidates})


def cmd_create(args: argparse.Namespace) -> None:
    async def _run(core: MSTodoCore):
        return await core.create_task(
            title=args.title,
            list_id=args.list_id,
            due=args.due,
            reminder=args.reminder,
            note=args.note,
        )

    args.title = _require_nonempty(args.title, name="--title")
    result = asyncio.run(_with_core(_run))
    _ok(result)


def cmd_update(args: argparse.Namespace) -> None:
    patch: dict = {}
    if args.title:
        patch["title"] = args.title
    if args.due:
        patch["due"] = args.due
    if args.reminder:
        patch["reminder"] = args.reminder
    if args.note:
        patch["note"] = args.note
    if args.status:
        patch["status"] = args.status

    if not patch:
        _err(
            "No fields to update. Provide at least one of: --title, --due, --reminder, --note, --status",
            code="invalid_argument",
        )

    if args.task_id and args.query:
        _err("Use only one of --task-id or --query", code="invalid_argument")

    async def _run(core: MSTodoCore):
        task_id = args.task_id
        if not task_id and args.query:
            resolved, candidates = await _resolve_task_id_by_query(
                core,
                query=args.query,
                list_id=args.list_id,
                status="all",
            )
            if not resolved:
                if not candidates:
                    _err_with_data(
                        "No task found for the given query",
                        code="task_not_found",
                        data={"query": args.query, "candidates": []},
                    )
                _err_with_data(
                    "Multiple task candidates found; please disambiguate",
                    code="ambiguous_task",
                    data={"query": args.query, "candidates": candidates},
                )
            task_id = resolved
        task_id = _require_nonempty(task_id, name="--task-id or --query")
        return await core.update_task(
            task_id=task_id,
            patch=patch,
            list_id=args.list_id,
        )

    result = asyncio.run(_with_core(_run))
    _ok(result)


def cmd_complete(args: argparse.Namespace) -> None:
    if args.task_id and args.query:
        _err("Use only one of --task-id or --query", code="invalid_argument")

    async def _run(core: MSTodoCore):
        task_id = args.task_id
        if not task_id and args.query:
            resolved, candidates = await _resolve_task_id_by_query(
                core,
                query=args.query,
                list_id=args.list_id,
                status="active",
            )
            if not resolved:
                if not candidates:
                    _err_with_data(
                        "No task found for the given query",
                        code="task_not_found",
                        data={"query": args.query, "candidates": []},
                    )
                _err_with_data(
                    "Multiple task candidates found; please disambiguate",
                    code="ambiguous_task",
                    data={"query": args.query, "candidates": candidates},
                )
            task_id = resolved
        task_id = _require_nonempty(task_id, name="--task-id or --query")
        return await core.complete_task(
            task_id=task_id,
            list_id=args.list_id,
        )

    result = asyncio.run(_with_core(_run))
    _ok(result)


def cmd_delete(args: argparse.Namespace) -> None:
    if args.task_id and args.query:
        _err("Use only one of --task-id or --query", code="invalid_argument")

    async def _run(core: MSTodoCore):
        task_id = args.task_id
        if not task_id and args.query:
            resolved, candidates = await _resolve_task_id_by_query(
                core,
                query=args.query,
                list_id=args.list_id,
                status="all",
            )
            if not resolved:
                if not candidates:
                    _err_with_data(
                        "No task found for the given query",
                        code="task_not_found",
                        data={"query": args.query, "candidates": []},
                    )
                _err_with_data(
                    "Multiple task candidates found; please disambiguate",
                    code="ambiguous_task",
                    data={"query": args.query, "candidates": candidates},
                )
            task_id = resolved
        task_id = _require_nonempty(task_id, name="--task-id or --query")
        return await core.delete_task(
            task_id=task_id,
            list_id=args.list_id,
        )

    result = asyncio.run(_with_core(_run))
    _ok(result)


def cmd_complex_todo(args: argparse.Namespace) -> None:
    goal = _require_nonempty(args.goal, name="--goal")
    beats = _require_positive(args.beats, name="--beats")
    _ok(_build_complex_todo(goal, beats))


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mstodo", description="Microsoft To Do CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    # auth_status
    sub.add_parser("auth_status", help="Check token status")

    # auth_begin
    p = sub.add_parser("auth_begin", help="Start OAuth")
    p.add_argument("--tenant-id", default=None)
    p.add_argument("--redirect-uri", default=None)

    # auth_finish
    p = sub.add_parser("auth_finish", help="Finish OAuth")
    p.add_argument("--redirect", required=True, help="Full redirect URL or code")

    # lists
    sub.add_parser("lists", help="List task lists")

    # tasks
    p = sub.add_parser("tasks", help="List tasks")
    p.add_argument("--list-id", default=None)
    p.add_argument("--status", default="active", choices=["active", "completed", "all"])
    p.add_argument("--due-before", default=None, help="ISO datetime")
    p.add_argument("--limit", type=int, default=50)

    # search
    p = sub.add_parser("search", help="Search tasks by title")
    p.add_argument("--query", required=True)
    p.add_argument("--list-id", default=None)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--status", default="active", choices=["active", "completed", "all"])

    # create
    p = sub.add_parser("create", help="Create a task")
    p.add_argument("--title", required=True)
    p.add_argument("--list-id", default=None)
    p.add_argument("--due", default=None, help="ISO date for due")
    p.add_argument("--reminder", default=None, help="ISO datetime for reminder")
    p.add_argument("--note", default=None)

    # update
    p = sub.add_parser("update", help="Update a task")
    p.add_argument("--task-id", default=None)
    p.add_argument("--query", default=None)
    p.add_argument("--list-id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--due", default=None)
    p.add_argument("--reminder", default=None)
    p.add_argument("--note", default=None)
    p.add_argument("--status", default=None)

    # complete
    p = sub.add_parser("complete", help="Complete a task")
    p.add_argument("--task-id", default=None)
    p.add_argument("--query", default=None)
    p.add_argument("--list-id", default=None)

    # delete
    p = sub.add_parser("delete", help="Delete a task")
    p.add_argument("--task-id", default=None)
    p.add_argument("--query", default=None)
    p.add_argument("--list-id", default=None)

    p = sub.add_parser(
        "complex_todo",
        help="Build heartbeat-driven complex task plan",
    )
    p.add_argument("--goal", required=True)
    p.add_argument("--beats", type=int, default=5)

    return ap


DISPATCH = {
    "auth_status": cmd_auth_status,
    "auth_begin": cmd_auth_begin,
    "auth_finish": cmd_auth_finish,
    "lists": cmd_lists,
    "tasks": cmd_tasks,
    "search": cmd_search,
    "create": cmd_create,
    "update": cmd_update,
    "complete": cmd_complete,
    "delete": cmd_delete,
    "complex_todo": cmd_complex_todo,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handler = DISPATCH.get(args.command)
    if handler is None:
        _err(f"Unknown command: {args.command}", code="unknown_command")
        return

    try:
        handler(args)
    except SystemExit:
        raise
    except Exception as e:
        _err(str(e), code="runtime_error")


if __name__ == "__main__":
    main()
