"""Private bookmark contracts through the pinned SDK and invented HTTP records."""

import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
from atproto import AsyncClient
from atproto_client.request import AsyncRequest

from skyloom.bookmark_service import BookmarkService, UnavailableBookmark, bookmark_page
from skyloom.domain import Author, Post
from skyloom.errors import UserError

DID = "did:plc:abcdefghijklmnopqrstuvwx"
URI = f"at://{DID}/app.bsky.feed.post/saved"
CID = "bafyreie5nqv6mse23zlpqzboxxjxmkq74i4wvs4jkxpxqdqmjpoa7mc5vu"


class Adapter(BookmarkService):
    async def _io(self, operation, *args):
        self.cached = (operation, args)
        if operation == "reconcile_page":
            return args[0]
        return None

    @asynccontextmanager
    async def authenticated(self):
        yield


class BookmarkOverlayTests(unittest.TestCase):
    def test_confirmed_mutation_overlays_nested_quotes_until_expiry(self):
        from dataclasses import replace

        from skyloom.bookmark_service import reconcile_bookmarks

        post = Post(URI, CID, Author(DID, "invented.invalid", "Invented"), "Saved", "")
        quote = replace(post, uri=URI + "quote", quote=post)
        changes = {URI: (1, True, 120)}
        self.assertTrue(reconcile_bookmarks(quote, changes, now=119).quote.bookmarked)
        self.assertFalse(reconcile_bookmarks(quote, changes, now=120).quote.bookmarked)

    def test_deletion_strips_legacy_cached_records_and_bookmark_reconciliation(self):
        import tempfile
        from dataclasses import asdict

        from skyloom.domain import Page
        from skyloom.storage import Storage

        with tempfile.TemporaryDirectory() as directory:
            store = Storage(directory)
            post = Post(URI, CID, Author(DID, "invented.invalid", "Invented"), "Private post", "")
            store.put(DID, "feed:legacy", [asdict(post)])
            store.delete_post(DID, URI)
            self.assertEqual(store.cached_post(DID, URI).text, "")
            self.assertEqual(store.cached(DID, "legacy").posts[0].text, "")
            self.assertTrue(store.reconcile_page(DID, Page((post,))).posts[0].unavailable)

    def test_lagging_feed_and_queued_checkpoint_do_not_reverse_confirmed_save(self):
        import tempfile

        from skyloom.domain import Page, Pager
        from skyloom.storage import Storage

        with tempfile.TemporaryDirectory() as directory:
            store = Storage(directory)
            post = Post(URI, CID, Author(DID, "invented.invalid", "Invented"), "Saved", "")
            store.cache(DID, "following", Page((post,)))
            store.bookmark_post(DID, URI, True)
            store.cache(DID, "following", Page((post,)))
            store.checkpoint(DID, "following", Pager(posts=[post]), None)
            self.assertTrue(store.cached_post(DID, URI).bookmarked)
            store.clear(DID)
            self.assertEqual(store._bookmark_overrides(DID), {})


class BookmarkContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.response = {"bookmarks": []}

        def handle(request):
            self.calls.append(request)
            return httpx.Response(200, json=self.response)

        self.adapter = Adapter()
        self.adapter.client = AsyncClient(
            base_url="https://pds.invalid",
            request=AsyncRequest(transport=httpx.MockTransport(handle)),
        )
        self.addAsyncCleanup(self.adapter.client.request.close)
        self.post = Post(URI, CID, Author(DID, "invented.invalid", "Invented"), "Saved", "")

    async def test_bookmark_sdk_uses_uri_and_cid_and_remove_uses_only_uri(self):
        self.response = {}
        self.assertTrue((await self.adapter.bookmark(self.post, True)).bookmarked)
        self.assertEqual(self.calls[-1].url.path, "/xrpc/app.bsky.bookmark.createBookmark")
        self.assertEqual(json.loads(self.calls[-1].content), {"uri": URI, "cid": CID})
        self.assertEqual(self.adapter.cached, ("bookmark_post", (URI, True)))
        unavailable = UnavailableBookmark(URI, "Unavailable")
        self.assertEqual(await self.adapter.bookmark(unavailable, False), unavailable)
        self.assertEqual(self.calls[-1].url.path, "/xrpc/app.bsky.bookmark.deleteBookmark")
        self.assertEqual(json.loads(self.calls[-1].content), {"uri": URI})

    async def test_sdk_pagination_and_unavailable_items(self):
        self.response = {
            "cursor": "next",
            "bookmarks": [
                {
                    "subject": {"uri": URI, "cid": CID},
                    "item": {
                        "$type": "app.bsky.feed.defs#notFoundPost",
                        "uri": URI,
                        "notFound": True,
                    },
                }
            ],
        }
        page = await self.adapter.bookmarks("previous")
        self.assertEqual(page.cursor, "next")
        self.assertEqual(page.items, (UnavailableBookmark(URI, "This post is unavailable."),))
        self.assertEqual(dict(self.calls[-1].url.params), {"limit": "30", "cursor": "previous"})

    async def test_available_post_maps_viewer_state(self):
        self.response = {
            "bookmarks": [
                {
                    "subject": {"uri": URI, "cid": CID},
                    "item": {
                        "$type": "app.bsky.feed.defs#postView",
                        "uri": URI,
                        "cid": CID,
                        "author": {"did": DID, "handle": "invented.invalid"},
                        "record": {
                            "$type": "app.bsky.feed.post",
                            "text": "Saved",
                            "createdAt": "2026-11-13T12:00:00Z",
                        },
                        "indexedAt": "2026-11-13T12:00:00Z",
                    },
                }
            ]
        }
        page = await self.adapter.bookmarks()
        self.assertEqual(page.items[0].text, "Saved")
        self.assertTrue(page.items[0].bookmarked)
        self.assertNotIn("cursor", self.calls[-1].url.params)

    async def test_cannot_save_unavailable_or_non_post_record(self):
        with self.assertRaises(UserError):
            await self.adapter.bookmark(UnavailableBookmark(URI, "Unavailable"), True)
        with self.assertRaises(UserError):
            await self.adapter.bookmark(
                SimpleNamespace(uri=f"at://{DID}/app.bsky.feed.like/a"), False
            )
        self.assertFalse(self.calls)

    def test_blocked_unknown_and_mismatched_views_remain_removable(self):
        page = bookmark_page(
            {
                "bookmarks": [
                    {"subject": {"uri": URI}, "item": {"$type": "app.bsky.feed.defs#blockedPost"}},
                    {"subject": {"uri": URI + "2"}, "item": {"$type": "future#view"}},
                    {
                        "subject": {"uri": URI + "3"},
                        "item": {"$type": "app.bsky.feed.defs#postView", "uri": URI},
                    },
                ]
            }
        )
        self.assertEqual(len(page.items), 3)
        self.assertEqual(page.items[0].reason, "This post is blocked.")
        self.assertTrue(all(isinstance(item, UnavailableBookmark) for item in page.items))


class BookmarkCacheTests(unittest.TestCase):
    def test_success_updates_archived_head_and_quote_copies(self):
        import tempfile
        from dataclasses import replace
        from pathlib import Path

        from skyloom.domain import Page
        from skyloom.storage import Storage

        with tempfile.TemporaryDirectory() as directory:
            store = Storage(Path(directory))
            post = Post(URI, CID, Author(DID, "invented.invalid", "Invented"), "Saved", "")
            quote = replace(post, uri=URI + "quote", quote=post)
            store.cache(DID, "following", Page((post, quote), "next"))
            store.bookmark_post(DID, URI, True)
            page = store.cached(DID, "following")
            self.assertTrue(page.posts[0].bookmarked)
            self.assertTrue(page.posts[1].quote.bookmarked)
            self.assertTrue(store.cached_page(DID, "following", None).posts[0].bookmarked)
            store.bookmark_post(DID, URI, False)
            self.assertFalse(store.cached_post(DID, URI).bookmarked)
