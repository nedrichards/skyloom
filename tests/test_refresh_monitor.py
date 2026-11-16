"""Production monitor and Window scheduling with invented service and clocks."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gtk_support import DISPLAY, settle
from startup_fixture import StartupFixture


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class MonitorIntegrationTests(StartupFixture, unittest.TestCase):
    def test_real_window_monitor_reuses_deadline_and_resumes_after_busy_and_cost_gates(self):
        from skyloom.refresh import Connection

        fixture = self
        fixture.open(fixture.restored_account)
        fixture.wait(lambda: fixture.window.stack.get_visible_child_name() == "shell")
        fixture.wait(lambda: not fixture.window.page_requests)
        window = fixture.window
        window.is_active = lambda: True
        self.assertTrue(settle(window, 200))
        monitor = window.refresh_monitor
        monitor.test_connection = Connection()
        now = time.time()
        view = window.interactions.current_view()
        self.assertIsNotNone(view)
        policy = window.interactions.policy(view.auto_key)
        policy.finished(now, True)
        with patch(
            "skyloom.refresh_monitor.time",
            SimpleNamespace(
                time=Mock(return_value=now),
                monotonic=time.monotonic,
                clock_gettime=time.clock_gettime,
                CLOCK_BOOTTIME=time.CLOCK_BOOTTIME,
            ),
        ):
            self.assertEqual(time.time.__module__, "time")
            window.settings.set_boolean("auto-refresh", True)
            monitor.changed()
            self.assertIsNotNone(monitor.source)
            source, key = monitor.source, monitor.timer_key
            monitor.changed()
            self.assertEqual((monitor.source, monitor.timer_key), (source, key))
            window.mutations.add(("invented-uri", "like"))
            monitor.changed()
            self.assertIsNone(monitor.source)
            window.mutations.clear()
            monitor.changed()
            self.assertIsNotNone(monitor.source)
            monitor.test_connection = Connection(metered=True)
            monitor.changed()
            self.assertIsNone(monitor.source)
            monitor.test_connection = Connection()
            monitor.changed()
            self.assertIsNotNone(monitor.source)
            monitor.clock.boot -= 3600
            monitor.clock.awake -= 1
            policy.finished(now, False)
            monitor.changed()
            self.assertEqual(policy.failures, 0)
        monitor.close()
        self.assertIsNone(monitor.source)
        self.assertIsNone(monitor.fd)


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class TimestampTests(unittest.TestCase):
    def test_shared_refresh_uses_one_now_and_skips_inactive_rows(self):
        from skyloom.refresh_monitor import RefreshMonitor

        visible = Mock(alive=True)
        visible.get_mapped.return_value = True
        hidden = Mock(alive=True)
        hidden.get_mapped.return_value = False
        cancelled = Mock(alive=False)
        monitor = SimpleNamespace(
            window=SimpleNamespace(timestamp_rows=[visible, hidden, cancelled])
        )
        RefreshMonitor.refresh_timestamps(monitor)
        visible.refresh_timestamp.assert_called_once()
        hidden.refresh_timestamp.assert_not_called()
        cancelled.refresh_timestamp.assert_not_called()

    def test_timestamp_changes_only_when_text_changes(self):
        from datetime import UTC, datetime

        from skyloom.widgets import PostRow

        row = SimpleNamespace(
            post=SimpleNamespace(created="2026-11-16T12:00:00Z"), timestamp=Mock()
        )
        row.timestamp.get_label.return_value = "2 min"
        PostRow.refresh_timestamp(row, datetime(2026, 11, 16, 12, 2, 30, tzinfo=UTC))
        row.timestamp.set_label.assert_not_called()
        PostRow.refresh_timestamp(row, datetime(2026, 11, 16, 13, 0, tzinfo=UTC))
        row.timestamp.set_label.assert_called_once_with("1 h")
