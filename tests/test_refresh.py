"""Refresh/data-cost rules with synthetic clocks; no host network or power changes."""

import unittest

from skyloom.list_state import PullRefresh
from skyloom.refresh import Connection, RefreshPolicy, ResumeClock


class RefreshTests(unittest.TestCase):
    def due(self, policy, now=1000, **kwargs):
        options = {"active": True, "ready": True, "enabled": True, "connection": Connection()}
        return policy.due(now, **(options | kwargs))

    def test_active_account_only_and_every_connectivity_gate(self):
        policy = RefreshPolicy()
        self.assertTrue(self.due(policy))
        for options in (
            {"active": False},
            {"ready": False},
            {"enabled": False},
            {"busy": True},
            {"connection": Connection(available=False)},
            {"connection": Connection(internet=False)},
            {"connection": Connection(metered=True)},
            {"connection": Connection(power_saver=True)},
        ):
            with self.subTest(options=options):
                self.assertFalse(self.due(policy, **options))
        self.assertTrue(self.due(policy, connection=Connection(metered=True), allow_metered=True))
        self.assertFalse(
            self.due(
                policy, connection=Connection(metered=True, power_saver=True), allow_metered=True
            )
        )

    def test_persisted_success_freshness_counts_suspend_and_clock_correction(self):
        policy = RefreshPolicy()
        policy.restore(1000)
        self.assertFalse(self.due(policy, 1299))
        self.assertTrue(self.due(policy, 1300))
        self.assertTrue(self.due(policy, 1000 + 8 * 3600))
        self.assertTrue(self.due(policy, 900))
        policy.finished(1400, True)
        policy.restore(1)
        self.assertEqual(policy.last_success, 1400)
        for invalid in (None, "bad", float("nan"), float("inf")):
            other = RefreshPolicy()
            other.restore(invalid)
            self.assertIsNone(other.last_finished)

    def test_failures_back_off_without_making_manual_success_wait(self):
        policy = RefreshPolicy()
        now = 1000
        for minutes in (5, 10, 20, 30, 30):
            policy.finished(now, False)
            self.assertFalse(self.due(policy, now + minutes * 60 - 1))
            self.assertTrue(self.due(policy, now + minutes * 60))
            now += minutes * 60
        policy.finished(now, True)
        self.assertEqual(policy.interval, 300)
        self.assertEqual(policy.failures, 0)

    def test_deadline_remaining_uses_freshness_backoff_and_clock_correction(self):
        policy = RefreshPolicy()
        self.assertEqual(policy.remaining(1000), 0)
        policy.finished(1000, True)
        self.assertEqual(policy.remaining(1100), 200)
        self.assertEqual(policy.remaining(1300), 0)
        self.assertEqual(policy.remaining(999), 0)
        policy.finished(1000, False)
        policy.finished(1000, False)
        self.assertEqual(policy.remaining(1100), 500)

    def test_resume_detector_uses_suspended_time_not_wall_clock_changes(self):
        clock = ResumeClock(100, 100)
        self.assertFalse(clock.update(160, 160))
        self.assertTrue(clock.update(7600, 200))
        self.assertFalse(clock.update(7660, 260))
        self.assertFalse(clock.update(10, 10))

    def test_metered_and_power_status_never_claims_a_physical_network_type(self):
        self.assertIn("Metered", Connection(metered=True).description)
        self.assertIn("Power saver", Connection(power_saver=True).description)
        self.assertIn("Offline", Connection(available=False).description)
        self.assertIn("limited", Connection(internet=False).pause_reason().lower())


class PullTests(unittest.TestCase):
    def test_only_deliberate_downward_pull_at_top_refreshes_once(self):
        pull = PullRefresh()
        pull.begin(True, True)
        self.assertEqual(pull.update(0, 71), "pulling")
        self.assertEqual(pull.update(0, 72), "armed")
        self.assertTrue(pull.finish(True, True))
        self.assertFalse(pull.finish(True, True))

    def test_taps_sideways_upward_busy_and_cancelled_drags_do_not_refresh(self):
        for x, y in ((0, 0), (0, 7), (0, 71), (0, -90), (90, 10), (90, 90), (float("nan"), 90)):
            pull = PullRefresh()
            pull.begin(True, True)
            pull.update(x, y)
            self.assertFalse(pull.finish(True, True))
        for at_top, enabled in ((False, True), (True, False)):
            pull = PullRefresh()
            pull.begin(at_top, enabled)
            pull.update(0, 100)
            self.assertFalse(pull.finish(True, True))
        pull = PullRefresh()
        pull.begin(True, True)
        pull.update(0, 100)
        self.assertFalse(pull.finish(False, True))
        pull.begin(True, True)
        pull.update(0, 100)
        self.assertFalse(pull.finish(True, False))

    def test_reversal_disarms_before_release(self):
        pull = PullRefresh()
        pull.begin(True, True)
        pull.update(0, 100)
        self.assertEqual(pull.update(100, 90), "pulling")
        self.assertFalse(pull.finish(True, True))


class RefreshDecisionTests(unittest.TestCase):
    def test_one_decision_carries_eligibility_due_and_deadline(self):
        policy = RefreshPolicy()
        options = {"active": True, "ready": True, "enabled": True, "connection": Connection()}
        decision = policy.decision(1000, **options)
        self.assertTrue(decision.eligible)
        self.assertTrue(decision.due)
        self.assertEqual(decision.delay, 0)
        policy.finished(1000, True)
        decision = policy.decision(1100, **options)
        self.assertTrue(decision.eligible)
        self.assertFalse(decision.due)
        self.assertEqual(decision.delay, 200)
        for gate in (
            {"active": False},
            {"busy": True},
            {"enabled": False},
            {"connection": Connection(metered=True)},
        ):
            decision = policy.decision(1400, **(options | gate))
            self.assertFalse(decision.eligible)
            self.assertFalse(decision.due)
            self.assertIsNone(decision.delay)
