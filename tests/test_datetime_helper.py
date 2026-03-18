from __future__ import annotations

import unittest


class TestDatetimeHelper(unittest.TestCase):
    def test_to_utc_iso_returns_iso_seconds(self) -> None:
        from utils.datetime_helper import to_utc_iso

        out = to_utc_iso("2026-03-18", "09:05", "Asia/Shanghai")
        self.assertEqual(out, "2026-03-18T01:05:00+00:00")

    def test_to_utc_iso_converts_timezone_correctly(self) -> None:
        """Verify Asia/Shanghai 18:00 converts to UTC 10:00 (8 hour difference)"""
        from utils.datetime_helper import to_utc_iso

        out = to_utc_iso("2026-03-18", "18:00", "Asia/Shanghai")
        self.assertEqual(out, "2026-03-18T10:00:00+00:00")

    def test_to_utc_iso_invalid_time_raises(self) -> None:
        from utils.datetime_helper import to_utc_iso

        with self.assertRaises(ValueError):
            to_utc_iso("2026-03-18", "25:00", "Asia/Shanghai")

    def test_to_utc_iso_invalid_timezone_raises(self) -> None:
        from utils.datetime_helper import to_utc_iso

        with self.assertRaises(ValueError):
            to_utc_iso("2026-03-18", "09:00", "Not/AZone")

    def test_calculate_relative_time_future(self) -> None:
        from datetime import datetime

        from utils.datetime_helper import calculate_relative_time

        now = datetime.fromisoformat("2026-03-18T00:00:00+00:00")
        self.assertEqual(
            calculate_relative_time("2026-03-18T00:00:30Z", now=now),
            "in 30s",
        )
