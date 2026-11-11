"""Native content-measured header action priority with invented feed names."""

import unittest
from types import SimpleNamespace

from gtk_support import settle

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    DISPLAY = Gtk.init_check()
    if DISPLAY:
        Adw.init()
except ImportError, ValueError, AttributeError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class FeedSwitcherTests(unittest.TestCase):
    def test_names_win_then_compose_then_refresh_without_visibility_feedback(self):
        from skyloom.feed_switcher import FeedSwitcher

        picker = Gtk.DropDown.new_from_strings(["Following", "Invented feed"])
        compose = Gtk.Button(icon_name="list-add-symbolic")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        switcher = FeedSwitcher(picker, SimpleNamespace(), (compose, refresh))
        window = Adw.Window(content=switcher, default_height=80)
        self.addCleanup(window.destroy)
        window.present()

        def resize(width):
            window.set_default_size(width, 80)
            self.assertTrue(settle(window, ready=lambda: switcher.tick is None))

        horizontal = Gtk.Orientation.HORIZONTAL
        resize(900)
        names = switcher.strip.measure(horizontal, -1)[1]
        controls = sum(c.measure(horizontal, -1)[1] for c in (switcher.previous, switcher.next))
        compose_width = compose.measure(horizontal, -1)[1] + 6
        refresh_width = refresh.measure(horizontal, -1)[1] + 6
        base = names + controls + 4
        for width, expected in (
            (base, (False, False)),
            (base + 2 * compose_width, (True, False)),
            (base + compose_width + 2 * refresh_width, (True, True)),
            (base + 2 * compose_width, (True, False)),
            (base, (False, False)),
        ):
            resize(width)
            self.assertEqual((compose.get_child_visible(), refresh.get_child_visible()), expected)
            self.assertEqual(switcher.mode, "expanded")
            before = switcher.width
            for _ in range(4):
                switcher.queue_allocate()
                self.assertTrue(settle(window, ready=lambda: switcher.tick is None))
                self.assertEqual(switcher.width, before)
                self.assertEqual(
                    (compose.get_child_visible(), refresh.get_child_visible()), expected
                )
        resize(900)
        refresh.grab_focus()
        self.assertIs(window.get_focus(), refresh)
        resize(base)
        self.assertIs(window.get_focus(), switcher.buttons[picker.get_selected()])
        resize(900)
        picker.set_model(
            Gtk.StringList.new(["Following", "An invented feed with a much longer name"] * 4)
        )
        self.assertTrue(settle(window, ready=lambda: switcher.tick is None))
        self.assertFalse(compose.get_child_visible())
        self.assertFalse(refresh.get_child_visible())
        self.assertEqual(switcher.mode, "scrollable")
        self.assertTrue(switcher.previous.get_child_visible())
        self.assertTrue(switcher.next.get_child_visible())
