"""Native action CSS coverage and geometry, using invented records only."""

import unittest
from dataclasses import replace
from pathlib import Path

from gtk_support import settle

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk

    DISPLAY = Gtk.init_check()
except ImportError, ValueError, AttributeError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ActionStyleTests(unittest.TestCase):
    def test_local_action_selectors_keep_native_button_and_popup_geometry(self):
        from test_content import ContentTests

        from skyloom.widgets import PostRow, list_children

        fixture = ContentTests()
        fixture.setUp()
        row = PostRow(replace(fixture.post, labels=(), images=()), fixture.window)
        row.create_post_menu(row.menu)
        choices = tuple(list_children(row.menu.get_popover().get_child()))
        self.assertEqual(len(choices), 3)
        self.assertTrue(all(button.has_css_class("post-action") for button in row.action_buttons))
        self.assertTrue(row.menu.has_css_class("post-action"))
        self.assertTrue(all(button.has_css_class("post-menu-item") for button in choices))
        native_menu_button = row.menu.get_first_child()
        self.assertIsInstance(native_menu_button, Gtk.Button)
        controls = (*row.action_buttons, native_menu_button, *choices)
        window = Gtk.Window(child=row, default_width=800, default_height=600)
        display = window.get_display()
        priority = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 100
        old = Gtk.CssProvider()
        old.load_from_string(
            ".post-actions button { min-height: 30px; padding: 3px 9px; font-weight: normal; }"
        )
        current = Gtk.CssProvider()
        current.load_from_path(str(Path(__file__).resolve().parents[1] / "data/style.css"))

        def geometry():
            return tuple(
                tuple(control.measure(orientation, -1))
                for control in controls
                for orientation in (Gtk.Orientation.HORIZONTAL, Gtk.Orientation.VERTICAL)
            )

        try:
            Gtk.StyleContext.add_provider_for_display(display, old, priority)
            window.present()
            self.assertTrue(settle(window))
            before = geometry()
            Gtk.StyleContext.remove_provider_for_display(display, old)
            Gtk.StyleContext.add_provider_for_display(display, current, priority)
            self.assertTrue(settle(window))
            self.assertEqual(geometry(), before)
        finally:
            Gtk.StyleContext.remove_provider_for_display(display, old)
            Gtk.StyleContext.remove_provider_for_display(display, current)
            row.cancel()
            window.destroy()
