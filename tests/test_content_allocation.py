"""Disclosure allocates warning controls only when the user needs them."""

import unittest
from types import SimpleNamespace
from weakref import WeakSet

from gtk_support import DISPLAY

if DISPLAY:
    from gi.repository import Gio, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class DisclosureAllocationTests(unittest.TestCase):
    def test_visible_content_builds_warning_once_on_first_hide(self):
        from skyloom import APP_ID
        from skyloom.content import LabelledContent

        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        self.assertIsNotNone(schema)
        settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        settings.set_boolean("warn-labelled-content", False)
        window = SimpleNamespace(settings=settings, content_gates=WeakSet(), revealed_labels={})
        builds = []

        def content():
            builds.append(True)
            return Gtk.Label(label="Invented readable content")

        gate = LabelledContent(window, ("post", "invented"), ("sexual",), content)
        self.assertTrue(gate.get_revealed())
        self.assertIsNone(gate.show_button)
        self.assertIsNone(gate.notice.get_first_child())
        self.assertEqual(len(builds), 1)
        gate.hide_button.emit("clicked")
        show = gate.show_button
        heading = gate.notice.get_first_child()
        self.assertIsNotNone(show)
        self.assertIsNotNone(heading)
        self.assertFalse(gate.get_revealed())
        self.assertTrue(gate.notice.get_visible())
        show.emit("clicked")
        self.assertTrue(gate.get_revealed())
        gate.hide_button.emit("clicked")
        self.assertIs(gate.show_button, show)
        self.assertIs(gate.notice.get_first_child(), heading)
        self.assertEqual(len(builds), 1)
