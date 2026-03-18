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
  update       --task-id ID    Update a task
  complete     --task-id ID    Complete a task
  delete       --task-id ID    Delete a task

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


def _err(msg: str) -> None:
    _out({"success": False, "error": msg})
    sys.exit(1)


async def _with_core(fn):
    """Run an async function with a MSTodoCore, then close."""
    core = MSTodoCore()
    try:
        return await fn(core)
    finally:
        await core.close()


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
        _err("MS_TODO_CLIENT_ID is required in environment")

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
        _err("--redirect is required (paste the full redirected URL or the code)")

    code, state, _params = parse_code_from_redirect(redirect)
    if not code:
        _err(
            "Could not parse code from redirect. Paste the full redirected URL or the code value."
        )

    client_id = os.getenv("MS_TODO_CLIENT_ID") or ""
    if not client_id:
        _err("MS_TODO_CLIENT_ID is required in environment")

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
        _err(tokens.get("error_description") or tokens.get("error"))

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
        _err("No refresh_token returned. Ensure offline_access scope is granted.")

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

    async def _run(core: MSTodoCore):
        return await core.update_task(
            task_id=args.task_id,
            patch=patch,
            list_id=args.list_id,
        )

    result = asyncio.run(_with_core(_run))
    _ok(result)


def cmd_complete(args: argparse.Namespace) -> None:
    async def _run(core: MSTodoCore):
        return await core.complete_task(
            task_id=args.task_id,
            list_id=args.list_id,
        )

    result = asyncio.run(_with_core(_run))
    _ok(result)


def cmd_delete(args: argparse.Namespace) -> None:
    async def _run(core: MSTodoCore):
        return await core.delete_task(
            task_id=args.task_id,
            list_id=args.list_id,
        )

    result = asyncio.run(_with_core(_run))
    _ok(result)


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
    p.add_argument("--task-id", required=True)
    p.add_argument("--list-id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--due", default=None)
    p.add_argument("--reminder", default=None)
    p.add_argument("--note", default=None)
    p.add_argument("--status", default=None)

    # complete
    p = sub.add_parser("complete", help="Complete a task")
    p.add_argument("--task-id", required=True)
    p.add_argument("--list-id", default=None)

    # delete
    p = sub.add_parser("delete", help="Delete a task")
    p.add_argument("--task-id", required=True)
    p.add_argument("--list-id", default=None)

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
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handler = DISPATCH.get(args.command)
    if not handler:
        _err(f"Unknown command: {args.command}")

    try:
        handler(args)
    except SystemExit:
        raise
    except Exception as e:
        _err(str(e))


if __name__ == "__main__":
    main()
