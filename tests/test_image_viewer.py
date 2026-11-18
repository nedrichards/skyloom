"""Native image viewer layout and retry with invented pixel data."""

import unittest
from concurrent.futures import Future
from dataclasses import replace

from gtk_support import DISPLAY, settle
from startup_fixture import StartupFixture


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ImageViewerTests(StartupFixture, unittest.TestCase):
    def test_gallery_opens_clicked_image_and_ignores_superseded_completions(self):
        from gi.repository import Gdk, GLib

        from skyloom.domain import Media
        from skyloom.widgets import PostRow

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        first = Media("https://cdn.bsky.app/invented-first", "First description")
        second = Media("invented-second", "", local=True)
        third = Media("https://cdn.bsky.app/invented-third", "Third description")
        gallery = (first, second, third)
        texture = Gdk.MemoryTexture.new(
            120, 100, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(b"\x79" * (120 * 100 * 3)), 360
        )
        calls, pending = [], []
        original_get, original_submit = self.app.images.get, self.app.worker.submit

        async def controlled_image():
            return texture

        def get(url, local=False, *, explicit=False):
            if not explicit:
                return original_get(url, local)
            calls.append((url, local))
            return controlled_image()

        def submit(coro, *callbacks, **kwargs):
            if coro.cr_code is not controlled_image.__code__:
                return original_submit(coro, *callbacks, **kwargs)
            coro.close()
            future = Future()
            pending.append((future, *callbacks))
            return future

        self.app.images.get, self.app.worker.submit = get, submit
        row = PostRow(replace(self.app.service.posts[0], images=gallery), self.window)
        self.addCleanup(row.cancel)
        row.media_cells[1].viewer.emit("clicked")
        dialog = self.window.get_visible_dialog()
        self.addCleanup(dialog.force_close)
        self.assertEqual(calls, [(second.url, True)])
        self.assertEqual(dialog.gallery_title.get_subtitle(), "2 of 3")
        self.assertFalse(dialog.details.get_visible())
        self.assertFalse(dialog.browser.get_visible())
        dialog.next.emit("clicked")
        self.assertEqual(dialog.gallery_title.get_subtitle(), "3 of 3")
        self.assertFalse(dialog.next.get_sensitive())
        self.assertTrue(pending[0][0].cancelled())
        pending[0][1](texture)
        pending[0][2]("Invented stale failure")
        self.assertEqual(dialog.stage.get_visible_child_name(), "loading")
        self.assertEqual(dialog.description.get_text(), third.alt)
        self.assertTrue(dialog.details.get_visible())
        links = []
        self.window.open_uri = links.append
        dialog.browser.emit("clicked")
        self.assertEqual(links, [third.url])
        pending[1][1](texture)
        dialog.set_zoom(2)
        modifiers = Gdk.ModifierType(0)
        self.assertFalse(dialog.key_pressed(None, Gdk.KEY_Left, 0, modifiers))
        dialog.previous.emit("clicked")
        self.assertIsNone(dialog.canvas.zoom)
        self.assertIsNone(dialog.center_tick)
        self.assertIsNone(dialog.canvas.texture)
        self.assertTrue(dialog.key_pressed(None, Gdk.KEY_Left, 0, modifiers))
        self.assertEqual(dialog.gallery_title.get_subtitle(), "1 of 3")
        self.assertFalse(dialog.previous.get_sensitive())
        pending[2][1](texture)
        pending[3][2]("Invented current failure")
        self.assertEqual(dialog.stage.get_visible_child_name(), "error")
        self.assertEqual(
            calls, [(second.url, True), (third.url, False), (second.url, True), (first.url, False)]
        )

    def test_portrait_layout_falls_back_to_decoded_size_and_adapts_at_narrow_width(self):
        from gi.repository import Gdk, GLib, Gtk

        from skyloom.domain import Media
        from skyloom.errors import UserError

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        texture = Gdk.MemoryTexture.new(
            120, 240, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(b"\x79" * (120 * 240 * 3)), 360
        )
        attempts = []
        original_get = self.app.images.get

        async def get(url, local=False, *, explicit=False):
            if not explicit:
                return await original_get(url, local)
            attempts.append((url, local, explicit))
            if len(attempts) == 1:
                raise UserError("Invented image failure.")
            return texture

        self.app.images.get = get
        self.window.view_media(
            Media("invented-portrait", "Portrait description. " * 100, local=True)
        )
        dialog = self.window.get_visible_dialog()
        self.addCleanup(dialog.force_close)
        self.wait(lambda: dialog.stage.get_visible_child_name() == "error")
        self.assertIn("Invented image failure", dialog.error.get_text())
        dialog.stage.get_visible_child().get_last_child().emit("clicked")
        self.wait(lambda: dialog.stage.get_visible_child_name() == "image")
        self.assertEqual(attempts, [("invented-portrait", True, True)] * 2)
        self.assertTrue(settle(self.window))
        self.assertEqual(dialog.body.get_orientation(), Gtk.Orientation.HORIZONTAL)
        self.window.set_default_size(480, 820)
        self.assertTrue(
            settle(
                self.window, ready=lambda: dialog.body.get_orientation() == Gtk.Orientation.VERTICAL
            )
        )
        adjustment = dialog.description_scroll.get_vadjustment()
        self.assertGreater(adjustment.get_upper(), adjustment.get_page_size())
        self.assertGreater(dialog.canvas.get_height(), dialog.description_scroll.get_height())
        self.assertTrue(dialog.key_pressed(None, Gdk.KEY_1, 0, Gdk.ModifierType(0)))
        self.assertEqual(dialog.canvas.zoom, 1)
        self.assertTrue(dialog.key_pressed(None, Gdk.KEY_0, 0, Gdk.ModifierType(0)))
        self.assertIsNone(dialog.canvas.zoom)
        dialog.close()
        self.wait(lambda: dialog.closed)
        self.assertIsNone(dialog.canvas.texture)
