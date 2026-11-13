"""Native action CSS coverage and geometry, using invented records only."""

import unittest
from dataclasses import replace
from pathlib import Path

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ActionStyleTests(unittest.TestCase):
    def test_action_buttons_and_popup_choices_have_compact_native_targets(self):
        from content_fixture import ContentFixture

        from skyloom.widgets import PostRow, list_children

        fixture = ContentFixture()
        row = PostRow(replace(fixture.post, labels=(), images=()), fixture.window)
        row.create_post_menu(row.menu)
        choices = tuple(list_children(row.menu.get_popover().get_child()))
        self.assertEqual(
            [choice.get_label() for choice in choices],
            ["Quote post", "Copy link", "Open in Bluesky / report", "Bookmark post"],
        )
        self.assertTrue(all(button.has_css_class("post-action") for button in row.action_buttons))
        self.assertTrue(row.menu.has_css_class("post-action"))
        self.assertTrue(all(button.has_css_class("post-menu-item") for button in choices))
        native_menu_button = row.menu.get_first_child()
        self.assertIsInstance(native_menu_button, Gtk.Button)
        controls = (*row.action_buttons, native_menu_button, *choices)
        window = Gtk.Window(child=row, default_width=800, default_height=600)
        display = window.get_display()
        priority = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 100
        current = Gtk.CssProvider()
        current.load_from_path(str(Path(__file__).resolve().parents[1] / "data/style.css"))

        try:
            Gtk.StyleContext.add_provider_for_display(display, current, priority)
            window.present()
            self.assertTrue(settle(window))
            for control in controls:
                with self.subTest(control=control):
                    minimum, natural, *_ = control.measure(Gtk.Orientation.VERTICAL, -1)
                    self.assertGreaterEqual(minimum, 30)
                    self.assertLessEqual(natural, 48)
                    self.assertTrue(control.get_sensitive())
        finally:
            Gtk.StyleContext.remove_provider_for_display(display, current)
            row.cancel()
            window.destroy()
