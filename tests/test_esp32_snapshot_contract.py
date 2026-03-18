from __future__ import annotations

import unittest


class TestEsp32SnapshotContract(unittest.TestCase):
    def test_snapshot_payload_matches_device_contract(self) -> None:
        from bridge.mstodo_bridge import snapshot as snapshot_mod

        sample_task = {
            "id": "AQMk-task-id",
            "list_id": "AQMk-list-id",
            "title": "测试",
            "status": "notStarted",
            "dueDateTime": {"dateTime": "2026-03-18T00:00:00+08:00"},
            "reminderDateTime": {"dateTime": "2026-03-18T03:00:00Z"},
            "body": {"content": "111"},
        }

        old_list_tasks = snapshot_mod._list_tasks_via_core
        old_now_iso = snapshot_mod._now_iso

        def _fake_list_tasks(limit: int, status: str):
            return [sample_task]

        snapshot_mod._list_tasks_via_core = _fake_list_tasks
        snapshot_mod._now_iso = lambda: "2026-03-18T17:55:39+08:00"
        try:
            data = snapshot_mod.build_snapshot(device_id="esp32-1", limit=6).to_dict()
        finally:
            snapshot_mod._list_tasks_via_core = old_list_tasks
            snapshot_mod._now_iso = old_now_iso

        self.assertEqual(data["device_id"], "esp32-1")
        self.assertEqual(data["timestamp"], "2026-03-18T17:55:39+08:00")
        self.assertEqual(len(data["tasks"]), 1)

        task = data["tasks"][0]
        expected = {
            "task_id": "AQMk-task-id",
            "list_id": "AQMk-list-id",
            "title": "测试",
            "status": "notStarted",
            "due": "2026-03-18",
            "reminder": "2026-03-18 11:00",
            "note": "111",
        }
        self.assertEqual(task, expected)
