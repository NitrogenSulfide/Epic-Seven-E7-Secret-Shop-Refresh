import unittest
from e7_session_estimate import SessionEstimate


class SessionEstimateTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.estimate = SessionEstimate(clock=lambda: self.now)
        self.estimate.reset(30, enabled=True)

    def refresh(self, count, at):
        self.now = at
        self.estimate.observe(count)

    def test_startup_and_duplicate_purchase_stats_do_not_change_cycle_samples(self):
        self.refresh(0, 100)
        self.refresh(1, 120)  # First scan and shop entry are excluded.
        self.refresh(2, 130)
        self.refresh(2, 139)  # A purchase updates counters before the next refresh.
        self.refresh(3, 140)
        self.assertIsNone(self.estimate.remaining())
        self.refresh(4, 150)
        self.assertEqual(self.estimate.remaining(), 60)
        self.now += 4
        self.assertEqual(self.estimate.remaining(), 56)

    def test_paused_countdown_and_next_sample_exclude_focus_pause(self):
        for count in range(1, 5):
            self.refresh(count, count*10)
        self.now = 45
        self.estimate.pause()
        self.now = 145
        self.assertEqual(self.estimate.remaining(), 55)
        self.estimate.resume()
        self.refresh(5, 150)
        self.assertEqual(self.estimate.remaining(), 50)

    def test_rounds_budget_to_whole_refreshes_and_finishes_without_enough_samples(self):
        self.estimate.reset(4, enabled=True)
        self.refresh(1, 30)
        self.assertTrue(self.estimate.finishing)
        self.assertIsNone(self.estimate.remaining())
        self.estimate.reset(400, enabled=True)
        self.refresh(133, 60)
        self.assertTrue(self.estimate.finishing)

    def test_slower_purchases_change_estimate_then_age_out(self):
        for count in range(1, 5):
            self.refresh(count, count*10)
        self.refresh(5, 60)
        self.assertEqual(self.estimate.remaining(), 62.5)
        self.estimate.total = 20
        for count in range(6, 14):
            self.refresh(count, 60+(count-5)*10)
        self.assertEqual(self.estimate.remaining(), 70)

    def test_reader_timestamps_work_when_gui_processes_delayed_batch(self):
        self.now = 1000
        for count in range(1, 5):
            self.estimate.observe(count, count*10)
        self.assertEqual(self.estimate.remaining(40), 60)
        self.assertEqual(self.estimate.remaining(42), 58)

    def test_reset_and_calibration_do_not_reuse_previous_run(self):
        for count in range(1, 5):
            self.refresh(count, count*10)
        self.estimate.reset(300, enabled=False)
        self.refresh(30, 100)
        self.assertIsNone(self.estimate.remaining())
        self.assertFalse(self.estimate.finishing)
        self.estimate.reset(300, enabled=True)
        self.refresh(1, 110)
        self.assertIsNone(self.estimate.remaining())

    def test_duplicate_regressed_and_instant_counts_do_not_add_samples(self):
        self.refresh(1, 10)
        self.refresh(1, 20)
        self.refresh(0, 25)
        self.refresh(2, 10)
        self.assertEqual(len(self.estimate.samples), 0)
        self.assertIsNone(self.estimate.remaining())

    def test_batched_refresh_count_is_weighted_by_refreshes(self):
        self.refresh(1, 10)
        self.refresh(4, 40)
        self.assertEqual(self.estimate.remaining(), 60)


if __name__ == '__main__':
    unittest.main()
