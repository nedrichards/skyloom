"""Native unavailable bookmarks remain removable within the shared list."""

import unittest

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class BookmarkViewTests(unittest.TestCase):
    def test_unavailable_entry_and_successful_removal_use_one_scroller(self):
        from skyloom.bookmark_service import UnavailableBookmark
        from skyloom.bookmark_view import BookmarkView

        window = Adw.Window(title="Invented bookmarks", default_width=600, default_height=600)
        window.views = []
        window.online_control = lambda control: control.set_sensitive(True)
        view = BookmarkView(window, None)
        window.set_content(view)
        self.addCleanup(window.destroy)
        self.addCleanup(view.close)
        item = UnavailableBookmark(
            "at://did:plc:invented/app.bsky.feed.post/missing", "This post is unavailable."
        )
        view.records.merge((item,), None, reset=True)
        view.set_items(view.records.items, lambda value: value.uri)
        view.paging.complete(None, 1)
        self.assertTrue(settle(window))
        rows = [row for row in view.rows if getattr(row, "_value", None) == item]
        self.assertEqual(len(rows), 1)
        remove = rows[0].get_last_child()
        self.assertIsInstance(remove, Gtk.Button)
        self.assertEqual(remove.get_label(), "Remove bookmark")
        view.changed_bookmark(item, False)
        self.assertEqual(view.model.get_n_items(), 0)
        self.assertEqual(view.paging.message, "No saved posts.")
