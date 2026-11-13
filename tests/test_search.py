"""Native search state allocation, scrolling and retry regressions."""

import unittest

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class SearchTests(unittest.TestCase):
    def setUp(self):
        from skyloom.search import SearchView

        self.window = Adw.Window(
            title="Skyloom search fixture", default_width=800, default_height=700
        )
        self.window.views = []
        self.view = SearchView(
            self.window, render=lambda value: Gtk.Label(label=str(value), height_request=60)
        )
        self.window.set_content(self.view)
        self.addCleanup(self.window.destroy)
        self.addCleanup(self.view.close)
        self.pump()

    def pump(self):
        self.assertTrue(
            settle(
                self.window,
                ready=lambda: (
                    self.view.position_tick is None
                    and self.view.header_fit_tick is None
                    and not self.view.check_pending
                ),
            ),
            "Search fixture did not settle",
        )

    def assert_status_readable(self):
        view = self.view
        self.assertTrue(view.status_box.get_mapped())
        self.assertGreater(view.content_header.get_height(), view.scroll.get_height() * 0.9)
        adjustment = view.scroll.get_vadjustment()
        self.assertAlmostEqual(adjustment.get_upper(), adjustment.get_page_size(), delta=2)
        for widget in (view.status_icon, view.status_title, view.status_description):
            if not widget.get_visible():
                continue
            valid, bounds = widget.compute_bounds(view.scroll)
            self.assertTrue(valid)
            self.assertGreaterEqual(bounds.origin.y, 0)
            self.assertLessEqual(bounds.origin.y + bounds.size.height, view.scroll.get_height())

    def test_initial_state_fills_viewport_and_tracks_taller_and_narrower_windows(self):
        self.assert_status_readable()
        self.window.set_default_size(480, 1000)
        self.pump()
        self.assert_status_readable()
        self.window.set_default_size(480, 550)
        self.pump()
        self.assert_status_readable()
        self.assertTrue(all(not footer.get_visible() for footer in self.view.footers))

    def test_loading_empty_error_and_retry_share_the_same_full_height_state(self):
        view = self.view
        view.search_started = True
        view.paging.begin("Searching…", reset=True)
        self.pump()
        self.assertEqual(view.status_title.get_text(), "Searching…")
        self.assertTrue(view.spinner.get_mapped())
        self.assertFalse(view.status_action.get_visible())
        view.paging.complete(None, 0)
        self.pump()
        self.assert_status_readable()
        self.assertEqual(view.status_title.get_text(), "No results found")
        view.paging.fail("Invented connection failure")
        self.pump()
        self.assert_status_readable()
        self.assertEqual(view.status_description.get_text(), "Invented connection failure")
        self.assertTrue(view.status_action.get_mapped())
        calls = []
        view.load_more = lambda: calls.append(True)
        view.status_action.emit("clicked")
        self.assertEqual(calls, [True])
        self.assertTrue(view.paging.busy)
        self.assertFalse(view.status_action.get_visible())
        view.paging.complete("next-page", 0)
        self.assertEqual(view.status_title.get_text(), "No results on this page")
        self.assertEqual(view.status_action.get_label(), "Load more")

    def test_results_release_viewport_height_and_restore_initial_state(self):
        view = self.view
        entry = view.entry
        entry.set_text("invented query")
        view.search_started = True
        view.set_items(list(range(40)), lambda value: value, reset=True)
        view.paging.complete(None, 40)
        self.pump()
        self.assertFalse(view.status_box.get_visible())
        self.assertLess(view.content_header.get_height(), 200)
        self.assertIs(view.scroll.get_child(), view.list)
        self.assertTrue(all(footer.get_visible() for footer in view.footers))
        adjustment = view.scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        self.pump()
        view.focus_header(entry)
        self.pump()
        self.assertLessEqual(adjustment.get_value(), 1)
        self.assertEqual(entry.get_text(), "invented query")
        self.assertTrue(self.window.get_focus().is_ancestor(entry))
        view.set_items([], lambda value: value, reset=True)
        view.search_started = False
        view.paging.complete(None, 0)
        view.focus_header(entry)
        self.pump()
        self.assert_status_readable()
        self.assertEqual(view.status_title.get_text(), "Search Bluesky")
