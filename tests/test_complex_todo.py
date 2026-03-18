from __future__ import annotations

import io
import json
import unittest
from argparse import Namespace
from contextlib import redirect_stdout


class TestComplexTodo(unittest.TestCase):
    def test_complex_todo_schema(self) -> None:
        import scripts.run as run

        buf = io.StringIO()
        with redirect_stdout(buf):
            run.cmd_complex_todo(Namespace(goal="Build robust sync", beats=6))
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["heartbeat_mode"], "openclaw-compatible")
        self.assertEqual(data["goal"], "Build robust sync")
        self.assertEqual(data["beats_requested"], 6)
        self.assertEqual(data["beats_applied"], 6)
        self.assertEqual(len(data["heartbeats"]), 6)
        self.assertGreaterEqual(len(data["todos"]), 5)
        for hb in data["heartbeats"]:
            self.assertIn("beat", hb)
            self.assertIn("phase", hb)
            self.assertIn("progress", hb)
            self.assertIn("pulse", hb)
            self.assertIn("message", hb)
        self.assertIn("next_action", data)
        self.assertIn("type", data["next_action"])
        self.assertIn("phase", data["next_action"])
        self.assertIn("hint", data["next_action"])

    def test_complex_todo_beats_are_clamped(self) -> None:
        import scripts.run as run

        buf = io.StringIO()
        with redirect_stdout(buf):
            run.cmd_complex_todo(Namespace(goal="Clamp test", beats=1))
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertEqual(data["beats_requested"], 1)
        self.assertEqual(data["beats_applied"], 3)
        self.assertEqual(len(data["heartbeats"]), 3)

    def test_complex_todo_invalid_beats(self) -> None:
        import scripts.run as run

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(buf):
                run.cmd_complex_todo(Namespace(goal="x", beats=0))
        self.assertEqual(cm.exception.code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_argument")
