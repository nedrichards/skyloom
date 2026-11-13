"""Native post wrapping and selection across scripts, fonts and widths."""

import unittest
from dataclasses import replace
from pathlib import Path

from gtk_support import DISPLAY

if DISPLAY:
    from gi.repository import Adw, Gdk, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class PostWidthTests(unittest.TestCase):
    def test_posts_wrap_at_narrow_widths_and_keep_text_selectable(self):
        from content_fixture import ContentFixture

        from skyloom.widgets import PostRow

        fixture = ContentFixture()
        fixture.window.settings.set_boolean("load-images", False)
        texts = (
            "Readable invented text, with native selection. " * 5,
            "例の文章です。読みやすい文字と折り返しを確認します。" * 5,
            "هذه رسالة تجريبية للتحقق من التفاف النص. " * 5,
            "https://example.invalid/" + "unbroken" * 30,
        )
        settings = Gtk.Settings.get_default()
        original_font = settings.get_property("gtk-font-name")
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).resolve().parents[1] / "data/style.css"))
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        try:
            for font in ("Adwaita Sans 11", "Adwaita Sans 16", "Adwaita Sans 24"):
                settings.set_property("gtk-font-name", font)
                for text in texts:
                    for quoted in (False, True):
                        with self.subTest(font=font, text=text[:20], quoted=quoted):
                            post = replace(fixture.post, text=text, labels=(), images=())
                            if quoted:
                                post = replace(post, quote=replace(post, uri=post.uri + "quote"))
                            row = PostRow(post, fixture.window)
                            clamp = Adw.Clamp(maximum_size=760, tightening_threshold=600, child=row)
                            labels = [row.text, *(child.text for child in row.quoted_rows)]
                            try:
                                for label in labels:
                                    self.assertTrue(label.get_wrap())
                                    self.assertTrue(label.get_selectable())
                                heights = [
                                    clamp.measure(Gtk.Orientation.VERTICAL, width).natural
                                    for width in (320, 360, 480, 800)
                                ]
                                self.assertTrue(all(height > 0 for height in heights))
                                self.assertEqual(heights, sorted(heights, reverse=True))
                                self.assertEqual(row.text.get_text(), text)
                                row.text.select_region(0, 5)
                                self.assertTrue(row.text.get_selection_bounds()[0])
                            finally:
                                row.cancel()
                                clamp.set_child(None)
        finally:
            settings.set_property("gtk-font-name", original_font)
            Gtk.StyleContext.remove_provider_for_display(display, provider)
