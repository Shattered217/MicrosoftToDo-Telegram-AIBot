from __future__ import annotations

import io
import json
import unittest
from argparse import Namespace
from contextlib import redirect_stdout


class TestQueryResolver(unittest.TestCase):
    def _run_with_stub_core(
        self,
        args: Namespace,
        hits: list[dict],
        mode: str,
    ) -> None:
        import scripts.run as run
        from core.mstodo import SearchHit

        class _Core:
            async def search_tasks(self, query, list_id=None, limit=10, status="all"):
                out = []
                for h in hits:
                    out.append(
                        SearchHit(
                            task_id=h["task_id"],
                            list_id=h["list_id"],
                            title=h["title"],
                            status=h.get("status"),
                            score=float(h.get("score", 0.9)),
                            due=h.get("due"),
                        )
                    )
                return out

            async def update_task(self, task_id, patch, list_id=None):
                return {"task": {"id": task_id}, "mode": mode}

            async def complete_task(self, task_id, list_id=None):
                return {"task": {"id": task_id}, "mode": mode}

            async def delete_task(self, task_id, list_id=None):
                return {"task_id": task_id, "deleted": True, "mode": mode}

            async def close(self):
                return None

        async def _with_core(fn):
            return await fn(_Core())

        old = run._with_core
        run._with_core = _with_core
        try:
            if mode == "update":
                run.cmd_update(args)
            elif mode == "complete":
                run.cmd_complete(args)
            else:
                run.cmd_delete(args)
        finally:
            run._with_core = old

    def test_update_query_unique_hit(self) -> None:
        args = Namespace(
            task_id=None,
            query="buy milk",
            list_id=None,
            title="x",
            due=None,
            reminder=None,
            note=None,
            status=None,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_with_stub_core(
                args,
                hits=[{"task_id": "t1", "list_id": "l1", "title": "buy milk"}],
                mode="update",
            )
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["task"]["id"], "t1")

    def test_complete_query_ambiguous_returns_candidates(self) -> None:
        args = Namespace(task_id=None, query="buy", list_id=None)
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(buf):
                self._run_with_stub_core(
                    args,
                    hits=[
                        {
                            "task_id": "t1",
                            "list_id": "l1",
                            "title": "buy milk",
                            "score": 0.9,
                        },
                        {
                            "task_id": "t2",
                            "list_id": "l1",
                            "title": "buy eggs",
                            "score": 0.85,
                        },
                    ],
                    mode="complete",
                )
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "ambiguous_task")
        self.assertEqual(len(payload["data"]["candidates"]), 2)
        for cand in payload["data"]["candidates"]:
            self.assertIn("task_id", cand)
            self.assertIn("list_id", cand)
            self.assertIn("title", cand)
            self.assertIn("status", cand)
            self.assertIn("due", cand)
            self.assertIn("score", cand)

    def test_delete_query_not_found_returns_empty_candidates(self) -> None:
        args = Namespace(task_id=None, query="missing", list_id=None)
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(buf):
                self._run_with_stub_core(args, hits=[], mode="delete")
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "task_not_found")
        self.assertEqual(payload["data"]["candidates"], [])

    def test_update_rejects_task_id_and_query_together(self) -> None:
        import scripts.run as run

        args = Namespace(
            task_id="t1",
            query="buy",
            list_id=None,
            title="x",
            due=None,
            reminder=None,
            note=None,
            status=None,
        )
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(buf):
                run.cmd_update(args)
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_argument")
