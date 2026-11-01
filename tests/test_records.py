import unittest

from skyloom.records import RecordPager


class RecordPagerTests(unittest.TestCase):
    def test_unique_records_bounds_cursor_repeats_and_reset(self):
        pager = RecordPager(lambda value: value, limit=3)
        self.assertEqual(pager.merge([1, 1, 2], "next"), 2)
        self.assertEqual(pager.merge([2, 3, 4], "next"), 2)
        self.assertEqual(pager.items, [2, 3, 4])
        self.assertIsNone(pager.cursor)
        pager.merge([5], "next", reset=True)
        self.assertEqual(pager.items, [5])
        self.assertEqual(pager.cursor, "next")

    def test_empty_intermediate_pages_keep_a_real_continuation(self):
        pager = RecordPager(lambda value: value)
        self.assertEqual(pager.merge([], "later"), 0)
        self.assertEqual(pager.cursor, "later")
        pager.merge([1], None)
        self.assertIsNone(pager.cursor)
        self.assertEqual(pager.items, [1])
