import unittest
from datetime import datetime, timedelta

from app.history_filters import HISTORY_PERIODS, period_bounds


class TestHistoryPeriods(unittest.TestCase):
    def test_quick_ranges(self):
        now = datetime(2026, 10, 22, 12, 0).astimezone()
        for label, duration in HISTORY_PERIODS.items():
            start, end = period_bounds(label, now)
            self.assertAlmostEqual(end - start, duration.total_seconds())

    def test_includes_requested_examples(self):
        self.assertIn("Últimos 15 minutos", HISTORY_PERIODS)
        self.assertIn("Últimas 3 horas", HISTORY_PERIODS)

    def test_unknown_period_rejected(self):
        with self.assertRaises(ValueError):
            period_bounds("período desconhecido")


if __name__ == "__main__":
    unittest.main()
