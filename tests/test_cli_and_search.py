from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout


class TestCLIValidation(unittest.TestCase):
    def test_require_positive_accepts_positive(self) -> None:
        from scripts.run import _require_positive

        self.assertEqual(_require_positive(3, name="--limit"), 3)

    def test_require_positive_rejects_zero_with_error_code(self) -> None:
        from scripts.run import _require_positive

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                _require_positive(0, name="--limit")
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_argument")

    def test_require_positive_rejects_non_integer_with_error_code(self) -> None:
        from scripts.run import _require_positive

        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                _require_positive("abc", name="--limit")
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_argument")


class TestSearchDeterministicOrdering(unittest.IsolatedAsyncioTestCase):
    async def test_search_tie_breaker_is_stable(self) -> None:
        from core.mstodo import MSTodoCore

        class _Core(MSTodoCore):
            async def list_tasks(self, *args, **kwargs):
                return [
                    {
                        "id": "b-id",
                        "list_id": "l1",
                        "title": "x-ab",
                        "status": "notStarted",
                        "due": None,
                    },
                    {
                        "id": "a-id",
                        "list_id": "l1",
                        "title": "x-cd",
                        "status": "notStarted",
                        "due": None,
                    },
                ]

            async def close(self):
                return None

        core = _Core()
        hits = await core.search_tasks(query="x", limit=10, status="all")
        self.assertEqual([h.title for h in hits], ["x-ab", "x-cd"])

    async def test_search_tie_breaker_falls_back_to_task_id(self) -> None:
        from core.mstodo import MSTodoCore

        class _Core(MSTodoCore):
            async def list_tasks(self, *args, **kwargs):
                return [
                    {
                        "id": "b-id",
                        "list_id": "l1",
                        "title": "x-same",
                        "status": "notStarted",
                        "due": None,
                    },
                    {
                        "id": "a-id",
                        "list_id": "l1",
                        "title": "x-same",
                        "status": "notStarted",
                        "due": None,
                    },
                ]

            async def close(self):
                return None

        core = _Core()
        hits = await core.search_tasks(query="x", limit=10, status="all")
        self.assertEqual([h.task_id for h in hits], ["a-id", "b-id"])
