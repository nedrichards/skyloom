"""Native feedback, modern reduced motion and deadline-based refresh contracts."""

import gc
import time
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw, Gio, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class MotionTests(unittest.TestCase):
    def setUp(self):
        from skyloom.motion import Feedback
        from skyloom.refresh import Connection

        self.settings = Gtk.Settings.get_default()
        for name in ("gtk-enable-animations", "gtk-interface-reduced-motion"):
            self.addCleanup(self.settings.set_property, name, self.settings.get_property(name))
        self.settings.set_property("gtk-enable-animations", True)
        self.settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.NO_PREFERENCE)
        self.button = Gtk.Button(label="Invented reaction")
        self.window = Adw.Window(content=self.button, default_width=500, default_height=300)
        # Activity is a policy input; native mapped geometry/animations remain real.
        self.window.is_active = lambda: True
        self.window.views = []
        self.window.interactions = SimpleNamespace(connection=Connection())
        self.addCleanup(self.window.destroy)
        self.window.present()
        self.assertTrue(settle(self.window))
        self.motion = Feedback(self.window)
        self.addCleanup(self.motion.close)

    def test_feedback_changes_opacity_without_geometry_and_finishes(self):
        geometry = (self.button.get_width(), self.button.get_height())
        self.motion.fade(self.button, start=0.5)
        self.assertTrue(self.motion.active)
        animation_ref = weakref.ref(self.motion.active[self.button][0])
        self.assertAlmostEqual(self.button.get_opacity(), 0.5, delta=0.01)
        self.assertTrue(settle(self.window, 250, lambda: not self.motion.active))
        self.assertEqual(self.button.get_opacity(), 1)
        self.assertEqual((self.button.get_width(), self.button.get_height()), geometry)
        gc.collect()
        self.assertIsNone(animation_ref(), "Completed feedback must release its animation")

    def test_modern_reduce_legacy_disable_and_power_finish_at_the_correct_state(self):
        from skyloom.refresh import Connection

        self.motion.fade(self.button, 0)
        self.settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.REDUCE)
        self.assertFalse(self.motion.active)
        self.assertEqual(self.button.get_opacity(), 0)
        self.motion.fade(self.button, start=0.5)
        self.assertEqual(self.button.get_opacity(), 1)
        self.assertFalse(self.motion.active)
        self.settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.NO_PREFERENCE)
        self.motion.fade(self.button, start=0.5)
        self.settings.set_property("gtk-enable-animations", False)
        self.assertFalse(self.motion.active)
        self.assertEqual(self.button.get_opacity(), 1)
        self.settings.set_property("gtk-enable-animations", True)
        self.motion.fade(self.button, start=0.5)
        self.window.interactions.connection = Connection(power_saver=True)
        self.motion.changed()
        self.assertFalse(self.motion.active)
        self.assertEqual(self.button.get_opacity(), 1)

    def test_unmap_and_replacement_leave_no_animation_or_wrong_opacity(self):
        self.motion.fade(self.button, 0)
        self.motion.fade(self.button, start=0.5)
        self.assertEqual(len(self.motion.active), 1)
        self.button.set_visible(False)
        self.assertFalse(self.motion.active)
        self.assertEqual(self.button.get_opacity(), 1)
        self.motion.fade(self.button, 0)
        self.assertFalse(self.motion.active)
        self.assertEqual(self.button.get_opacity(), 0)

    def test_mapped_offscreen_controls_do_not_animate_and_scrolling_finishes_feedback(self):
        self.window.set_content(None)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.button)
        content.append(Gtk.Box(height_request=1200))
        below = Gtk.Button(label="Invented offscreen marker")
        content.append(below)
        scroll = Gtk.ScrolledWindow(child=content)
        self.window.set_content(scroll)
        self.assertTrue(settle(self.window))
        self.assertTrue(below.get_mapped())
        self.motion.fade(below, 0)
        self.assertFalse(self.motion.active)
        self.assertEqual(below.get_opacity(), 0)
        self.motion.fade(self.button, start=0.5)
        self.assertTrue(self.motion.active)
        self.motion.active[self.button][0].set_duration(1000)
        scroll.get_vadjustment().set_value(1000)
        self.assertTrue(settle(self.window))
        self.motion.finish_offscreen()
        self.assertFalse(self.motion.active)
        self.assertEqual(self.button.get_opacity(), 1)

    def test_refresh_deadline_is_one_shot_and_busy_focus_requires_no_polling(self):
        import os

        from skyloom import APP_ID
        from skyloom.interactions import Interactions
        from skyloom.refresh import Connection, RefreshPolicy
        from skyloom.refresh_monitor import RefreshMonitor

        window = self.window
        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        window.settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        window.demo = False
        window.service = SimpleNamespace(account=object())
        window.worker = SimpleNamespace(after_dispatch=lambda: None)
        window.page_requests, window.mutations = {}, set()
        window.is_active = lambda: True
        window.get_visible_dialog = lambda: None
        target = SimpleNamespace(auto_key="feed:invented", paging=SimpleNamespace(busy=False))
        policy = RefreshPolicy(last_finished=1000, last_success=1000)
        context = ["list"]
        window.interactions = Interactions(window)
        window.interactions.policies[target.auto_key] = policy
        window.interactions.auto_target = lambda: target
        window.interactions.context = lambda: context[0]
        window.automatic_target = lambda: target
        window.connection_changed = lambda connection: setattr(
            window.interactions, "connection", connection
        )

        def check(now):
            if policy.remaining(now) == 0:
                window.page_requests["invented"] = object()

        window.check_auto_refresh = check
        wall = Mock(return_value=1100)
        with patch(
            "skyloom.refresh_monitor.time",
            SimpleNamespace(
                time=wall,
                monotonic=time.monotonic,
                clock_gettime=time.clock_gettime,
                CLOCK_BOOTTIME=time.CLOCK_BOOTTIME,
            ),
        ):
            self.assertIsNot(time.time, wall)
            monitor = RefreshMonitor(window)
            self.addCleanup(monitor.close)
            monitor.test_connection = Connection()
            monitor.changed()
            fd, source = monitor.fd, monitor.source
            remaining, interval = os.timerfd_gettime(fd)
            self.assertEqual(interval, 0)
            self.assertGreater(remaining, 195)
            for _ in range(20):
                monitor.changed()
                window.worker.after_dispatch()
            self.assertTrue(settle(window))
            self.assertEqual(monitor.fd, fd)
            self.assertEqual(monitor.source, source)
            context[0] = "text"
            monitor.changed()
            self.assertIsNone(monitor.source)
            context[0] = "list"
            window.notify("focus-widget")
            self.assertTrue(settle(window))
            self.assertIsNotNone(monitor.source)
            wall.return_value = 1301
            monitor.changed()
            self.assertTrue(window.page_requests)
            self.assertIsNone(monitor.source)
            window.page_requests.clear()
            policy.finished(1301, True)
            window.worker.after_dispatch()
            self.assertTrue(settle(window))
            self.assertGreater(os.timerfd_gettime(monitor.fd)[0], 295)
            monitor.test_connection = Connection(power_saver=True)
            monitor.changed()
            self.assertIsNone(monitor.source)
            monitor.close()
            self.assertIsNone(monitor.queued)
            self.assertFalse(window.page_requests)
