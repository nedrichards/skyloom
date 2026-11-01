import unittest

from skyloom.pagination import AutoPager


class AutoPagerTests(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        self.pager = AutoPager(self.load)

    def load(self):
        self.calls += 1

    def test_scroll_threshold_and_single_inflight_request(self):
        self.pager.complete("a", 30)
        self.assertFalse(self.pager.near_end(0, 3000, 600))
        self.assertTrue(self.pager.near_end(2100, 3000, 600))
        for _ in range(5):
            self.assertFalse(self.pager.near_end(2400, 3000, 600))
        self.assertEqual(self.calls, 1)
        self.pager.complete("b", 30)
        self.assertFalse(self.pager.near_end(2400, 6000, 600))
        self.assertTrue(self.pager.near_end(5200, 6000, 600))
        self.assertEqual(self.calls, 2)

    def test_error_pauses_auto_retry_but_manual_retry_works(self):
        self.pager.begin(reset=True)
        self.pager.fail("Offline")
        self.assertFalse(self.pager.near_end(0, 0, 600))
        self.assertTrue(self.pager.request())
        self.assertTrue(self.pager.busy)
        self.assertEqual(self.calls, 1)

    def test_duplicate_empty_and_repeated_cursor_pages_do_not_spin(self):
        self.pager.complete("a", 30)
        self.pager.near_end(0, 100, 600)
        self.pager.complete("a", 30)
        self.assertFalse(self.pager.near_end(0, 100, 600))
        self.pager.complete("b", 0)
        self.assertFalse(self.pager.near_end(0, 100, 600))
        self.assertTrue(self.pager.request())
        self.pager.complete(None, 0)
        self.assertFalse(self.pager.request())

    def test_short_pages_fill_viewport_and_hidden_or_zero_size_does_not_load(self):
        self.pager.complete("a", 1)
        self.assertFalse(self.pager.near_end(0, 200, 0))
        self.assertTrue(self.pager.near_end(0, 200, 600))

    def test_closed_page_cannot_load_and_refresh_resets_cursor_history(self):
        self.pager.complete("a", 30)
        self.pager.request()
        self.pager.begin(reset=True)
        self.pager.complete("a", 30)
        self.assertTrue(self.pager.near_end(0, 200, 600))
        self.pager.closed = True
        self.pager.complete("b", 30)
        self.assertFalse(self.pager.request())
