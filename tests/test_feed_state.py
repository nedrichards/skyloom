"""Invented archive, real-cursor and reading-window regression cases."""

import tempfile
import time
import unittest
from dataclasses import replace

from skyloom.domain import Author, Page, Pager, Post
from skyloom.feed_state import Bookmark, FeedGap
from skyloom.storage import Storage


def posts(start, end):
    return tuple(
        Post(
            f"at://did:example:cache/post/{i}",
            "cid",
            Author("did:example:cache", "cache.invalid", "Invented reader"),
            f"Invented post {i}",
            "2026-10-28T12:00:00Z",
        )
        for i in range(start, end)
    )


class FeedStateTests(unittest.TestCase):
    def test_live_order_and_manual_reorder_preserve_omitted_history_and_counters(self):
        old = list(posts(0, 8))
        pager = Pager(old, "oldest", page_starts={old[0].uri: None, old[4].uri: "middle"})
        head = Page((posts(8, 9)[0], replace(old[2], likes=9), old[0]), "head")
        live = pager.reconciled(head)
        self.assertEqual([p.uri for p in live.posts], [head.posts[0].uri, *[p.uri for p in old]])
        self.assertEqual(live.posts[3].likes, 9)
        manual = pager.reconciled(head, reorder=True)
        self.assertEqual(manual.posts[:3], list(head.posts))
        self.assertEqual(len(manual.posts), 9)
        self.assertEqual(manual.cursor, "oldest")
        self.assertEqual(pager.posts, old)

    def test_disjoint_head_keeps_anchor_and_exposes_bridge(self):
        old = posts(0, 20)
        pager = Pager(list(old), "tail")
        result = pager.reconciled(Page(posts(100, 105), "between"), anchor=old[8].uri)
        self.assertIn(old[8], result.posts)
        gap = next(item for item in result.projected() if isinstance(item, FeedGap))
        self.assertEqual((gap.before, gap.cursor), (old[0].uri, "between"))
        bridged = result.bridge(gap.before, Page((*posts(80, 83), old[0]), "unused"))
        self.assertFalse(bridged.gaps)
        self.assertEqual(bridged.cursor, "tail")
        self.assertEqual(len(bridged.posts), 28)

    def test_bridge_deduplicates_within_page_and_keeps_existing_order(self):
        old = posts(0, 3)
        new = posts(20, 21)[0]
        pager = Pager(list(old), "tail", gaps={old[1].uri: "between"})
        result = pager.bridge(old[1].uri, Page((new, new, old[1]), "next"))
        self.assertEqual(result.posts, [old[0], new, old[1], old[2]])
        self.assertEqual(len(result.posts), len({post.uri for post in result.posts}))
        self.assertFalse(result.gaps)
        self.assertEqual(result.cursor, "tail")

    def test_full_window_protects_anchors_and_real_continuations(self):
        old = posts(0, 250)
        for index in (0, 25, 125, 230, 249):
            pager = Pager(list(old), "tail")
            result = pager.reconciled(Page(posts(300, 330), "head-cursor"), anchor=old[index].uri)
            self.assertLessEqual(len(result.posts), 250)
            self.assertIn(old[index], result.posts)
            self.assertEqual(result.posts[:30], list(posts(300, 330)))
            self.assertIn(result.cursor, {"tail", "head-cursor"})
        pager = Pager(list(old), "tail", gaps={old[0].uri: "between"})
        self.assertIs(
            pager.bridge(old[0].uri, Page(posts(300, 330), "next"), anchor=old[-1].uri), pager
        )

    def test_pagination_retains_current_anchor_when_arrival_would_trim_it(self):
        old = posts(0, 250)
        pager = Pager(list(old), "real-older")
        for index in (0, 5, 240):
            result = pager.appended(Page(posts(250, 280), "real-next"), anchor=old[index].uri)
            self.assertIn(old[index], result.posts)
            self.assertEqual(len(result.posts), 250)
            self.assertEqual(result.cursor, "real-next" if index >= 30 else "real-older")

    def test_thousands_archived_all_pages_restorable_without_large_render_window(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            for start in range(0, 3300, 30):
                storage.cache(
                    "invented",
                    "following",
                    Page(posts(start, start + 30), f"c{start + 30}"),
                    None if start == 0 else f"c{start}",
                )
            with storage.connect("invented") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM feed_posts").fetchone()[0], 3300)
            saved = Pager(
                list(posts(2700, 2940)), "c2940", page_starts={posts(2700, 2701)[0].uri: "c2700"}
            )
            bookmark = Bookmark(
                saved.posts[180].uri, -47, saved.posts[183].uri, (saved.posts[181].uri,)
            )
            storage.checkpoint("invented", "following", saved, bookmark)
            # A later head fetch must not overwrite the older reading window.
            storage.cache("invented", "following", Page(posts(4000, 4030), "new-head"))
            restored = Storage(directory).cached_state("invented", "following")
            self.assertEqual(restored.pager.posts, saved.posts)
            self.assertEqual(restored.pager.cursor, "c2940")
            self.assertEqual(restored.bookmark, bookmark)
            cached = storage.cached_page("invented", "following", "c2940")
            self.assertTrue(cached.cached)
            self.assertEqual(cached.posts, posts(2940, 2970))
            self.assertEqual(cached.cursor, "c2970")
            self.assertIsNone(storage.cached_post("other", bookmark.uri))

    def test_automatic_cleanup_count_age_protection_and_missing_page_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.archive_feed_limit = 60
            storage.archive_limit = 80
            saved = Pager(list(posts(0, 10)), "next")
            storage.checkpoint("invented", "following", saved, Bookmark(saved.posts[5].uri))
            storage.cache("invented", "following", Page(posts(10, 40), "next"), "old")
            with storage.connect("invented") as db:
                db.execute("UPDATE feed_posts SET touched=?", (time.time() - 40 * 86400,))
            # Trigger automatic cleanup, without explicitly invoking cleanup().
            storage._last_cleanup.clear()
            storage.cache("invented", "following", Page(posts(40, 160), "end"), "recent")
            with storage.connect("invented") as db:
                count = db.execute("SELECT COUNT(*) FROM feed_posts").fetchone()[0]
                self.assertLessEqual(count, 70)  # protected 10 plus the newest 60
            self.assertEqual(storage.cached_state("invented", "following").pager.posts, saved.posts)
            self.assertIsNone(storage.cached_page("invented", "following", "old"))
            self.assertIsNone(storage.cached_page("invented", "following", "recent"))
            storage.put("invented", "draft:keep", {"text": "Invented draft"})
            storage.cleanup("invented")
            self.assertEqual(storage.get("invented", "draft:keep"), {"text": "Invented draft"})
            storage.clear("invented")
            self.assertFalse(storage.cached_state("invented", "following").pager.posts)

    def test_bookmark_validation_and_nearest_surviving_neighbour(self):
        old = posts(0, 4)
        bookmark = Bookmark(old[0].uri, -15, old[2].uri, (old[1].uri, old[3].uri))
        self.assertEqual(bookmark.resolve(old[2:]), Bookmark(old[3].uri, 0, old[2].uri))
        self.assertIsNone(bookmark.resolve(()))
        self.assertIsNone(Bookmark.parse({}))
        self.assertEqual(
            Bookmark.parse({"uri": "invented", "offset": float("nan"), "neighbours": 4}).offset, 0
        )
