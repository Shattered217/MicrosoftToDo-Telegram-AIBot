from __future__ import annotations

import unittest


class TestMSTodoNormalize(unittest.TestCase):
    def test_normalize_due_date_only_defaults_to_2359(self) -> None:
        from zoneinfo import ZoneInfo

        from core.mstodo import _normalize_due_input

        tz = ZoneInfo("Asia/Shanghai")
        self.assertEqual(_normalize_due_input("2026-03-18", tz), "2026-03-18T23:59:00")

    def test_normalize_due_datetime_is_localized(self) -> None:
        from zoneinfo import ZoneInfo

        from core.mstodo import _normalize_due_input

        tz = ZoneInfo("Asia/Shanghai")
        self.assertEqual(
            _normalize_due_input("2026-03-18T09:00:00", tz),
            "2026-03-18T09:00:00",
        )

    def test_normalize_due_datetime_z_is_converted_to_local(self) -> None:
        from zoneinfo import ZoneInfo

        from core.mstodo import _normalize_due_input

        tz = ZoneInfo("Asia/Shanghai")
        self.assertEqual(
            _normalize_due_input("2026-03-18T01:00:00Z", tz),
            "2026-03-18T09:00:00",
        )

    def test_normalize_reminder_date_only_defaults_to_0900(self) -> None:
        from zoneinfo import ZoneInfo

        from core.mstodo import _normalize_reminder_input

        tz = ZoneInfo("Asia/Shanghai")
        self.assertEqual(
            _normalize_reminder_input("2026-03-18", tz),
            "2026-03-18T09:00:00",
        )

    def test_normalize_reminder_invalid_iso_raises(self) -> None:
        from zoneinfo import ZoneInfo

        from core.mstodo import _normalize_reminder_input

        tz = ZoneInfo("Asia/Shanghai")
        with self.assertRaises(ValueError):
            _normalize_reminder_input("not-a-datetime", tz)
