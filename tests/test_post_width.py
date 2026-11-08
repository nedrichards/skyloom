"""Body request hints preserve native row sizing and actual wrapping."""

import unittest
from dataclasses import replace
from pathlib import Path

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Adw, Gdk, Gtk

    DISPLAY = Gtk.init_check()
except ImportError, ValueError, AttributeError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class PostWidthTests(unittest.TestCase):
    def test_body_hint_preserves_row_minima_and_allocated_heights(self):
        from test_content import ContentTests

        from skyloom.widgets import PostRow

        fixture = ContentTests()
        fixture.setUp()
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
                            self.assertTrue(all(label.get_width_chars() == 8 for label in labels))

                            def geometry(clamp=clamp):
                                return (
                                    tuple(clamp.measure(Gtk.Orientation.HORIZONTAL, -1)),
                                    *(
                                        tuple(clamp.measure(Gtk.Orientation.VERTICAL, width))
                                        for width in (320, 360, 480, 800)
                                    ),
                                )

                            try:
                                for label in labels:
                                    label.set_width_chars(1)
                                before = geometry()
                                for label in labels:
                                    label.set_width_chars(8)
                                self.assertEqual(geometry(), before)
                                self.assertEqual(row.text.get_text(), text)
                                row.text.select_region(0, 5)
                                self.assertTrue(row.text.get_selection_bounds()[0])
                            finally:
                                row.cancel()
                                clamp.set_child(None)
        finally:
            settings.set_property("gtk-font-name", original_font)
            Gtk.StyleContext.remove_provider_for_display(display, provider)
