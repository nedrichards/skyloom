"""Production monitor and Window scheduling with invented service and clocks."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_startup
from gtk_support import settle


@unittest.skipUnless(test_startup.DISPLAY, "GNOME GTK display required")
class MonitorIntegrationTests(unittest.TestCase):
    def test_real_window_monitor_reuses_deadline_and_resumes_after_busy_and_cost_gates(self):
        from skyloom.refresh import Connection

        fixture = test_startup.StartupTests()
        fixture.setUp()
        self.addCleanup(fixture.cleanup)
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
