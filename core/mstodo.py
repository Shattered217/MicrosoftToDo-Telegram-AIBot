"""core.mstodo

Core (non-UI) wrapper around Microsoft Graph To Do.

Design goals:
- No Telegram/OpenClaw dependencies.
- Token refresh handled transparently by the underlying client.
- Return normalized Python dicts that the MCP layer can serialize.

NOTE: This module currently adapts the existing MicrosoftTodoDirectClient implementation
from the repo. Later we can further decouple Config/env parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import difflib
import logging

from config import Config
from microsoft_todo_client import MicrosoftTodoDirectClient
from core.token_store import TokenBundle, TokenStore

logger = logging.getLogger(__name__)

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")
_WINDOWS_TZ_MAP = {
    "China Standard Time": "Asia/Shanghai",
    "UTC": "UTC",
}


@dataclass
class SearchHit:
    task_id: str
    list_id: str
    title: str
    status: Optional[str]
    score: float
    due: Optional[str] = None


def _iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _resolve_zone(tz_name: Optional[str]) -> ZoneInfo:
    if not tz_name:
        return _DEFAULT_TZ
    mapped = _WINDOWS_TZ_MAP.get(tz_name, tz_name)
    try:
        return ZoneInfo(mapped)
    except Exception:
        return _DEFAULT_TZ


def _to_shanghai_iso(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        date_str = value.get("dateTime")
        source_tz = value.get("timeZone")
    elif isinstance(value, str):
        date_str = value
        source_tz = None
    else:
        return None

    if not isinstance(date_str, str) or not date_str:
        return None

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return date_str

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_resolve_zone(source_tz))

    return dt.astimezone(_DEFAULT_TZ).isoformat(timespec="seconds")


class MSTodoCore:
    def __init__(self, token_store: TokenStore | None = None):
        self.store = token_store or TokenStore()
        self.client = MicrosoftTodoDirectClient()

        bundle = self.store.load()
        if bundle.access_token:
            self.client.access_token = bundle.access_token
        if bundle.refresh_token:
            self.client.refresh_token = bundle.refresh_token
        if bundle.expires_at is not None:
            self.client.expires_at = bundle.expires_at

        def _save_tokens_to_store(
            access_token: str, refresh_token: str | None = None
        ) -> bool:
            b = self.store.load()
            b.access_token = access_token
            if refresh_token:
                b.refresh_token = refresh_token
            expires_at = getattr(self.client, "expires_at", None)
            if isinstance(expires_at, (int, float)):
                b.expires_at = float(expires_at)
            token_type = getattr(self.client, "token_type", None)
            if isinstance(token_type, str) and token_type:
                b.token_type = token_type
            scope = getattr(self.client, "scope", None)
            if isinstance(scope, str) and scope:
                b.scope = scope
            self.store.save(b)
            return True

        try:
            self.client._save_tokens_to_env = _save_tokens_to_store  # type: ignore[attr-defined]
        except Exception:
            pass

    async def close(self):
        await self.client.close()

    async def list_lists(self) -> List[Dict[str, Any]]:
        res = await self.client.get_task_lists()
        if "error" in res:
            raise RuntimeError(res["error"])
        out = []
        for item in res.get("value", []) or []:
            out.append(
                {
                    "id": item.get("id"),
                    "name": item.get("displayName"),
                    "wellknown": item.get("wellknownListName"),
                }
            )
        return out

    async def _default_list_id(self) -> str:
        lists = await self.list_lists()
        if not lists:
            raise RuntimeError("No task lists found")
        for l in lists:
            if l.get("wellknown") == "defaultList":
                return l["id"]
        return lists[0]["id"]

    async def list_tasks(
        self,
        list_id: Optional[str] = None,
        status: str = "active",
        due_before: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if not list_id:
            list_id = await self._default_list_id()

        filter_parts = []
        if status and status != "all":
            # Graph uses: notStarted, inProgress, completed, waitingOnOthers, deferred
            if status == "completed":
                filter_parts.append("status eq 'completed'")
            else:
                filter_parts.append("status ne 'completed'")
        if due_before:
            # dueDateTime/dateTime is an ISO string; filter requires datetimeoffset
            # We'll avoid server-side filtering complexity and filter client-side later.
            pass

        filter_query = None
        if filter_parts:
            filter_query = " and ".join(filter_parts)

        res = await self.client.get_tasks(list_id=list_id, filter_query=filter_query)
        if "error" in res:
            raise RuntimeError(res["error"])

        tasks = res.get("value", []) or []

        def extract_due(t: Dict[str, Any]) -> Optional[str]:
            d = (t.get("dueDateTime") or {}).get("dateTime")
            return d

        if due_before:
            try:
                due_before_dt = datetime.fromisoformat(
                    due_before.replace("Z", "+00:00")
                )
            except Exception:
                raise RuntimeError(
                    "due_before must be ISO 8601, e.g. 2026-03-09T00:00:00Z"
                )

            filtered = []
            for t in tasks:
                d = extract_due(t)
                if not d:
                    continue
                try:
                    d_dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
                except Exception:
                    continue
                if d_dt <= due_before_dt:
                    filtered.append(t)
            tasks = filtered

        tasks = tasks[: max(1, int(limit))]

        out = []
        for t in tasks:
            reminder_raw = t.get("reminderDateTime")
            out.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "created": t.get("createdDateTime"),
                    "lastModified": t.get("lastModifiedDateTime"),
                    "due": (t.get("dueDateTime") or {}).get("dateTime"),
                    "reminder": _to_shanghai_iso(reminder_raw),
                    # Include body for device/bridge note extraction.
                    "body": t.get("body"),
                    "list_id": list_id,
                }
            )
        return out

    async def search_tasks(
        self,
        query: str,
        list_id: Optional[str] = None,
        limit: int = 5,
        status: str = "active",
    ) -> List[SearchHit]:
        query = (query or "").strip()
        if not query:
            return []

        tasks = await self.list_tasks(list_id=list_id, status=status, limit=200)

        hits: List[SearchHit] = []
        q = query.lower()
        for t in tasks:
            title = t.get("title") or ""
            tl = title.lower()

            score = 0.0
            if q in tl:
                # substring hit, prefer shorter distance
                score = 0.7 + min(0.3, len(q) / max(1, len(tl)))
            else:
                score = difflib.SequenceMatcher(None, q, tl).ratio()

            if score < 0.35:
                continue

            hits.append(
                SearchHit(
                    task_id=t["id"],
                    list_id=t["list_id"],
                    title=title,
                    status=t.get("status"),
                    score=float(score),
                    due=t.get("due"),
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[: max(1, int(limit))]

    async def create_task(
        self,
        title: str,
        list_id: Optional[str] = None,
        due: Optional[str] = None,
        reminder: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        title = (title or "").strip()
        if not title:
            raise RuntimeError("title is required")

        if not list_id:
            list_id = await self._default_list_id()

        if reminder:
            res = await self.client.create_task_with_reminder(
                list_id=list_id,
                title=title,
                description=note,
                due_date=due,
                reminder_datetime=reminder,
            )
        else:
            res = await self.client.create_task(
                list_id=list_id,
                title=title,
                description=note,
                due_date=due,
            )

        if "error" in res:
            raise RuntimeError(res["error"])

        return {
            "operation_id": f"create:{res.get('id')}:{_iso_now()}",
            "task": {
                "id": res.get("id"),
                "title": res.get("title"),
                "status": res.get("status"),
                "due": (res.get("dueDateTime") or {}).get("dateTime"),
                "reminder": (res.get("reminderDateTime") or {}).get("dateTime"),
                "list_id": list_id,
            },
        }

    async def update_task(
        self,
        task_id: str,
        patch: Dict[str, Any],
        list_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_id = (task_id or "").strip()
        if not task_id:
            raise RuntimeError("task_id is required")

        if not list_id:
            # try infer by scanning default list only (fast path)
            list_id = await self._default_list_id()

        title = patch.get("title")
        note = patch.get("note")
        status = patch.get("status")
        due = patch.get("due")
        reminder = patch.get("reminder")

        res = await self.client.update_task(
            list_id=list_id,
            task_id=task_id,
            title=title,
            description=note,
            status=status,
            due_date=due,
            reminder_datetime=reminder,
        )
        if "error" in res:
            raise RuntimeError(res["error"])

        return {
            "operation_id": f"update:{task_id}:{_iso_now()}",
            "task": {
                "id": res.get("id", task_id),
                "title": res.get("title", title),
                "status": res.get("status", status),
                "due": (res.get("dueDateTime") or {}).get("dateTime", due),
                "reminder": (res.get("reminderDateTime") or {}).get(
                    "dateTime", reminder
                ),
                "list_id": list_id,
            },
        }

    async def complete_task(
        self, task_id: str, list_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.update_task(
            task_id=task_id, patch={"status": "completed"}, list_id=list_id
        )

    async def delete_task(
        self, task_id: str, list_id: Optional[str] = None
    ) -> Dict[str, Any]:
        task_id = (task_id or "").strip()
        if not task_id:
            raise RuntimeError("task_id is required")

        if not list_id:
            list_id = await self._default_list_id()

        res = await self.client.delete_task(list_id=list_id, task_id=task_id)
        if "error" in res:
            raise RuntimeError(res["error"])

        return {
            "operation_id": f"delete:{task_id}:{_iso_now()}",
            "deleted": True,
            "task_id": task_id,
            "list_id": list_id,
        }
