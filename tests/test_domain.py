import asyncio
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

from skyloom.demo import DemoService
from skyloom.domain import (
    Author,
    Media,
    Page,
    Pager,
    Post,
    feed_from,
    post_from,
    relative_time,
    safe_url,
)
from skyloom.errors import UserError
from skyloom.richtext import counts, facets_for, markup, validate
from skyloom.service import Attachment
from skyloom.storage import Storage

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/demo-feed.json"


def sample():
    return Post(
        "at://did:example:alice/app.bsky.feed.post/1",
        "cid",
        Author("did:example:alice", "alice.invalid", "Alice"),
        "Hello 👩🏽‍💻",
        "2026-10-26T12:00:00Z",
    )


class RichTextTests(unittest.TestCase):
    def test_graphemes(self):
        for cluster in ["👩🏽‍💻", "e\u0301", "🇬🇧", "क्‍ष", "👨‍👩‍👧‍👦"]:
            self.assertEqual(counts(cluster)[0], 1)
            self.assertFalse(
                validate(cluster * 300) if len((cluster * 300).encode()) <= 3000 else ""
            )
            self.assertTrue(validate(cluster * 301))

    def test_independent_byte_limit(self):
        text = "a" + "\u0301" * 1499
        self.assertEqual(counts(text), (1, 2999))
        self.assertFalse(validate(text))
        self.assertTrue(validate(text + "\u0301"))
        self.assertFalse(validate("a" * 300))
        self.assertTrue(validate("a" * 301))
        self.assertTrue(validate("  \n"))
        self.assertFalse(validate("", [Attachment("image", "A hill")]))
        self.assertTrue(validate("", [Attachment("image", "")]))
        self.assertTrue(validate("hello", [Attachment("image", "alt")] * 5))

    def test_utf8_facets_and_escaping(self):
        text = "🌤️ <tag> https://example.invalid/?a=1&b=2 @alice.invalid #GNOME"

        async def resolve(handle):
            self.assertEqual(handle, "alice.invalid")
            return "did:example:alice"

        facets = asyncio.run(facets_for(text, resolve))
        self.assertEqual(len(facets), 3)
        for f in facets:
            part = text.encode()[f["index"]["byteStart"] : f["index"]["byteEnd"]].decode()
            self.assertStartsWith(part, ("https:", "@", "#"))
        rendered = markup(text, facets)
        self.assertIn("&lt;tag&gt;", rendered)
        self.assertIn("&amp;b=2", rendered)
        self.assertEqual(rendered.count("<a "), 3)

    def test_invalid_overlapping_facets(self):
        def facet(a, b, uri="https://example.invalid"):
            return {
                "index": {"byteStart": a, "byteEnd": b},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": uri}],
            }

        self.assertEqual(markup("éx", [facet(1, 2), facet(-1, 2), facet(0, 20)]), "éx")
        self.assertEqual(markup("abcd", [facet(0, 2), facet(1, 4)]).count("<a "), 1)
        self.assertNotIn("<a ", markup("abcd", [facet(0, 4, "javascript:alert(1)")]))
        self.assertNotIn(
            "<a ", markup("abcd", [{"index": {"byteStart": 0, "byteEnd": 4}, "features": []}])
        )

    def test_malformed_facet_types(self):
        malformed = [
            None,
            "bad",
            {},
            {"index": {"byteStart": "oops", "byteEnd": 1}},
            {"index": {"byteStart": 0, "byteEnd": 2}, "features": [None]},
        ]
        self.assertEqual(markup("hello", malformed), "hello")

    def test_urls(self):
        for url in [
            "javascript:foo",
            "file:///etc/passwd",
            "https://user:pass@example.invalid",
            "https://[malformed",
        ]:
            self.assertFalse(safe_url(url))
        self.assertEqual(safe_url("https://example.invalid/path"), "https://example.invalid/path")


class ModelTests(unittest.TestCase):
    def test_sparse_and_unknown_embed(self):
        p = post_from(
            {"uri": "at://x/y/z", "record": {"text": "hi"}, "embed": {"$type": "unknown"}}
        )
        self.assertEqual(p.author.name, "Unknown account")
        self.assertEqual(p.text, "hi")

    def test_reply_repost_labels_and_quotes(self):
        d = {
            "uri": "at://a/post/b",
            "cid": "cid",
            "author": {"did": "did:example:a", "handle": "a.invalid", "viewer": {"muted": True}},
            "record": {"text": "Hello", "reply": {"root": {"uri": "root", "cid": "root-cid"}}},
            "labels": [{"val": "porn"}],
            "embed": {
                "$type": "app.bsky.embed.record#view",
                "record": {"$type": "app.bsky.embed.record#viewBlocked"},
            },
        }
        p = post_from(d)
        self.assertEqual(p.root, ("root", "root-cid"))
        self.assertTrue(p.author.muted)
        self.assertEqual(p.labels, ("porn",))
        self.assertIn("unavailable", p.unavailable)
        f = feed_from(
            {"feed": [{"post": d, "reason": {"by": {"handle": "b.invalid"}}}], "cursor": "next"}
        )
        self.assertIn("Reposted by", f.posts[0].context)
        self.assertEqual(f.cursor, "next")

    def test_pagination(self):
        p = sample()
        pager = Pager()
        pager.merge(Page((p, p), "a"))
        self.assertEqual(len(pager.posts), 1)
        pager.merge(Page((p, replace(p, uri="2")), "a"))
        self.assertIsNone(pager.cursor)
        self.assertEqual(len(pager.posts), 2)
        pager.merge(Page(tuple(replace(p, uri=str(i)) for i in range(300)), None), True)
        self.assertEqual(len(pager.posts), 250)

    def test_refresh_preserves_omitted_history_and_leaves_previous_window_immutable(self):
        posts = [replace(sample(), uri=str(i)) for i in range(90)]
        pager = Pager()
        for start in range(0, 90, 30):
            pager.merge(Page(tuple(posts[start : start + 30]), str(start + 30)))
        updated = replace(posts[0], likes=8)
        arrival = replace(posts[0], uri="new")
        refreshed = pager.reconciled(
            Page((arrival, updated, *posts[1:29]), "new-head"), reorder=True
        )
        self.assertEqual(refreshed.posts, [arrival, updated, *posts[1:]])
        self.assertEqual(refreshed.cursor, "90")
        self.assertEqual(pager.posts, posts)
        self.assertEqual(pager.cursor, "90")
        self.assertIs(refreshed.posts[-1], posts[-1])
        removed = pager.reconciled(
            Page((arrival, *posts[1:30]), "head-with-omission"), reorder=True
        )
        self.assertEqual(removed.posts, [arrival, *posts[1:30], posts[0], *posts[30:]])
        self.assertIn(posts[0], removed.posts)
        self.assertEqual(removed.cursor, "90")
        disjoint = pager.reconciled(Page((arrival,), "disjoint"), reorder=True)
        self.assertEqual(disjoint.posts, [arrival, *posts])
        self.assertEqual(disjoint.cursor, "90")
        self.assertEqual(disjoint.gaps, {posts[0].uri: "disjoint"})

    def test_refresh_bound_rewinds_to_a_real_page_without_skipping_dropped_posts(self):
        posts = [replace(sample(), uri=str(i)) for i in range(250)]
        pager = Pager()
        for start in range(0, 250, 25):
            pager.merge(Page(tuple(posts[start : start + 25]), str(start + 25)))
        arrivals = [replace(sample(), uri=f"new-{i}") for i in range(10)]
        refreshed = pager.reconciled(Page((*arrivals, *posts[:15]), "head"), reorder=True)
        self.assertEqual(refreshed.posts, [*arrivals, *posts[:225]])
        self.assertEqual(refreshed.cursor, "225")
        refreshed.merge(Page(tuple(posts[225:]), "250"))
        self.assertEqual(refreshed.cursor, "250")
        self.assertEqual(refreshed.posts[-25:], posts[225:])
        self.assertEqual(len(refreshed.posts), 250)

    def test_time(self):
        now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
        self.assertEqual(relative_time("2026-10-26T11:58:00Z", now), "2 min")
        self.assertEqual(relative_time("2026-10-26T12:30:00Z", now), "Just now")
        self.assertEqual(relative_time("bad", now), "")
        self.assertTrue(relative_time("2026-10-25T01:30:00+01:00", now))
        self.assertEqual(relative_time("2026-10-26T11:58:00.000Z", now), "2 min")
        self.assertEqual(relative_time("2026-10-26T12:58:00+01:00", now), "2 min")
        self.assertEqual(relative_time("2026-10-26T11:58:00", now), "")

    def test_model_replacement_and_nested_cache_round_trip(self):
        post = replace(
            sample(),
            quote=sample(),
            images=(Media("https://example.invalid/image", "Invented image"),),
            labels=("sexual",),
            root=("at://invented/root", "root-cid"),
            parent=("at://invented/parent", "parent-cid"),
        )
        reacted = replace(post, likes=1, like_uri="at://invented/like")
        self.assertEqual(post.likes, 0)
        self.assertEqual(reacted.likes, 1)
        self.assertEqual(get_type_hints(Post)["quote"], Post | None)
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.cache("invented", "following", Page((reacted,)))
            self.assertEqual(storage.cached("invented", "following").posts, (reacted,))

    def test_corrupt_storage_preserves_original(self):
        import hashlib
        import sqlite3

        from skyloom.errors import message

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (hashlib.sha256(b"one").hexdigest() + ".db")
            path.write_bytes(b"corrupt but must be preserved")
            with self.assertRaises(sqlite3.DatabaseError) as caught:
                Storage(directory).get("one", "draft:new")
            self.assertEqual(path.read_bytes(), b"corrupt but must be preserved")
            self.assertIn("drafts have not been deleted", message(caught.exception))

    def test_cache_preserves_server_cursor_and_reads_legacy_records(self):
        from dataclasses import asdict

        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.cache("invented", "following", Page((sample(),), "server-cursor"))
            self.assertEqual(storage.cached("invented", "following").cursor, "server-cursor")
            storage.put("invented", "feed:old", [asdict(sample())])
            self.assertEqual(storage.cached("invented", "old").posts, (sample(),))
            self.assertIsNone(storage.cached("invented", "old").cursor)

    def test_account_cache_drafts_and_clear(self):
        with tempfile.TemporaryDirectory() as base:
            s = Storage(base)
            s.cache("one", "following", Page((sample(),)))
            self.assertEqual(s.cached("one", "following").posts[0], sample())
            self.assertFalse(s.cached("two", "following").posts)
            s.put("one", "draft:new", {"text": "hello"})
            self.assertEqual(s.get("one", "draft:new")["text"], "hello")
            for i in range(20):
                s.cache("one", str(i), Page((sample(),)))
            with s.connect("one") as db:
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM state WHERE key LIKE 'feed:%'").fetchone()[0],
                    12,
                )
            s.clear("one")
            self.assertIsNone(s.get("one", "draft:new"))
            self.assertEqual(s.get("two", "draft:new", "empty"), "empty")

    def test_legacy_empty_drafts_do_not_hide_saved_work_and_clear_removes_record(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.put("invented", "draft:kept", {"text": "Keep this draft"})
            with storage.connect("invented") as db:
                db.executemany(
                    "INSERT INTO state VALUES (?, ?)",
                    [(f"draft:old-{i}", "{}") for i in range(120)],
                )
            self.assertEqual(storage.drafts("invented"), [("kept", {"text": "Keep this draft"})])
            storage.put("invented", "draft:kept", {})
            self.assertEqual(storage.drafts("invented"), [])
            with storage.connect("invented") as db:
                self.assertIsNone(
                    db.execute("SELECT value FROM state WHERE key=?", ("draft:kept",)).fetchone()
                )

    def test_saved_post_lookup_restores_quotes_without_crossing_accounts(self):
        quoted = replace(sample(), uri="at://did:example:quoted/app.bsky.feed.post/saved")
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.cache("invented", "following", Page((replace(sample(), quote=quoted),)))
            self.assertEqual(storage.cached_post("invented", quoted.uri), quoted)
            self.assertIsNone(storage.cached_post("another-account", quoted.uri))
            self.assertIsNone(
                storage.cached_post("invented", "at://did:example:missing/post/missing")
            )


class DemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_sessions_have_isolated_drafts_and_cleanup(self):
        first, second = DemoService(FIXTURE), DemoService(FIXTURE)
        try:
            first.storage.put(first.account.did, "draft:new", {"text": "Invented draft"})
            self.assertIsNone(second.storage.get(second.account.did, "draft:new"))
            self.assertNotEqual(first.storage.base, second.storage.base)
        finally:
            await first.close()
            await second.close()
        self.assertFalse(first.storage.base.exists())
        self.assertFalse(second.storage.base.exists())

    async def test_shared_flow(self):
        service = DemoService(FIXTURE)
        self.addAsyncCleanup(service.close)
        page = await service.feed()
        self.assertEqual(len(page.posts), 6)
        p = page.posts[0]
        changed = await service.mutate(p, "like")
        self.assertTrue(changed.like_uri)
        self.assertEqual(changed.likes, p.likes + 1)
        self.assertFalse((await service.mutate(changed, "like")).like_uri)
        self.assertTrue((await service.thread(p.uri)).posts)
        self.assertEqual((await service.profile(p.author.did)).did, p.author.did)
        self.assertTrue((await service.follow(p.author)).following)
        result = await service.send("A demo reply", reply=p)
        self.assertEqual(service.posts[0].root, (p.uri, p.cid))
        self.assertEqual(result.uri, service.posts[0].uri)
        self.assertTrue((await service.search("software")).posts)
        notices, _, timestamp = await service.notifications()
        self.assertEqual(len(notices), 3)
        self.assertEqual(notices[0].author.handle, "ada.demo.invalid")
        await service.mark_seen(timestamp)
        self.assertEqual(await service.unread(), 0)
        self.assertTrue(all(n.read for n in (await service.notifications())[0]))
        service.offline = True
        with self.assertRaises(UserError):
            await service.mutate(p, "like")
        self.assertTrue((await service.cached("following")).posts)
