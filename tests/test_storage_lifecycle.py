"""Invented account IO ownership and bookmark-only persistence regressions."""

import asyncio
import hashlib
import tempfile
import threading
import unittest
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import skyloom.storage as storage_module
from skyloom.credentials import KeyringError
from skyloom.domain import Author, Page, Pager, Post
from skyloom.feed_state import Bookmark
from skyloom.service import Service
from skyloom.storage import Storage

ACCOUNT = Author("did:example:storage-review", "storage.invalid", "Invented reader")
POST = Post(
    "at://did:example:storage-review/post/0",
    "invented",
    ACCOUNT,
    "Invented post",
    "2026-10-28T12:00:00Z",
)


class CountStorage(Storage):
    @contextmanager
    def connect(self, account):
        with super().connect(account) as db:
            before = db.total_changes
            yield db
            self.changed = db.total_changes - before


class StorageWorkTests(unittest.TestCase):
    def test_position_only_checkpoint_writes_one_row_without_serializing_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = CountStorage(directory)
            pager = Pager([replace(POST, uri=f"{POST.uri}/{i}") for i in range(250)])
            storage.cache(ACCOUNT.did, "following", Page(tuple(pager.posts[:30]), "next"))
            storage.checkpoint(ACCOUNT.did, "following", pager, Bookmark(pager.posts[0].uri))
            with patch.object(storage_module, "asdict", wraps=asdict) as serialize:
                storage.checkpoint(ACCOUNT.did, "following", pager, Bookmark(pager.posts[100].uri))
                self.assertEqual(storage.changed, 1)
                self.assertTrue(
                    all(not isinstance(call.args[0], Post) for call in serialize.call_args_list)
                )
            storage.checkpoint(ACCOUNT.did, "following", pager, Bookmark(pager.posts[100].uri))
            self.assertEqual(storage.changed, 0)
            self.assertEqual(
                storage.cached_state(ACCOUNT.did, "following").bookmark.uri, pager.posts[100].uri
            )

    def test_uri_lookup_uses_its_covering_order_index(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.cache(ACCOUNT.did, "following", Page((POST,)))
            with storage.connect(ACCOUNT.did) as db:
                plan = db.execute(
                    "EXPLAIN QUERY PLAN SELECT value FROM feed_posts WHERE uri=? ORDER BY touched DESC LIMIT 1",
                    (POST.uri,),
                ).fetchall()
            details = " ".join(row[-1] for row in plan)
            self.assertIn("feed_posts_uri_age", details)
            self.assertNotIn("SCAN", details)
            self.assertNotIn("TEMP B-TREE", details)

    def test_fresh_fetch_migrating_a_legacy_head_cannot_restore_stale_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            storage.put(ACCOUNT.did, "feed:following", {"posts": [asdict(POST)], "cursor": "old"})
            updated = replace(POST, likes=17)
            storage.cache(ACCOUNT.did, "following", Page((updated,), "new"))
            self.assertEqual(storage.cached(ACCOUNT.did, "following").posts, (updated,))
            self.assertEqual(storage.cached_post(ACCOUNT.did, POST.uri), updated)

    def test_legacy_migration_keeps_updated_content_and_moves_bookmark(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            original = Bookmark(POST.uri, -17)
            storage.put(
                ACCOUNT.did,
                "feed:following",
                {
                    "posts": [asdict(POST)],
                    "cursor": "tail",
                    "refreshed": 123,
                    "bookmark": asdict(original),
                },
            )
            updated = replace(POST, likes=5)
            storage.checkpoint(ACCOUNT.did, "following", Pager([updated], "tail"), original)
            value = storage.get(ACCOUNT.did, "feed:following")
            self.assertNotIn("posts", value)
            self.assertNotIn("refreshed", value)
            self.assertNotIn("bookmark", value)
            self.assertEqual(storage.cached(ACCOUNT.did, "following").posts, (updated,))
            self.assertEqual(storage.cached_state(ACCOUNT.did, "following").bookmark, original)


class GatedStorage(Storage):
    def __init__(self, directory):
        super().__init__(directory)
        self.entered, self.resume, self.finished = (threading.Event() for _ in range(3))

    def run(self, *args):
        self.entered.set()
        try:
            if not self.resume.wait(5):
                raise TimeoutError("Invented IO gate was not released")
            return super().run(*args)
        finally:
            self.finished.set()


class StorageOwnershipTests(unittest.IsolatedAsyncioTestCase):
    def service(self, storage):
        service = Service.__new__(Service)
        service.storage, service.account = storage, ACCOUNT
        service.lock, service.draft_lock = asyncio.Lock(), asyncio.Lock()
        service._storage_lease = (ACCOUNT.did, storage.activate(ACCOUNT.did))
        return service

    async def test_cancelled_pending_account_writes_cannot_recreate_cleared_data(self):
        operations = (
            ("put", "identity", {"did": ACCOUNT.did}),
            ("put", "draft:invented", {"text": "Invented draft"}),
            ("cache", "following", Page((POST,)), None),
            ("checkpoint", "following", Pager([POST]), Bookmark(POST.uri)),
            ("prepare_image", "unused-invented-image.png"),
        )
        for operation in operations:
            with self.subTest(operation=operation[0]), tempfile.TemporaryDirectory() as directory:
                storage = GatedStorage(directory)
                service = self.service(storage)
                task = asyncio.create_task(service._io(*operation))
                self.assertTrue(await asyncio.to_thread(storage.entered.wait, 3))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.to_thread(storage.clear, ACCOUNT.did)
                service.account = None
                storage.resume.set()
                self.assertTrue(await asyncio.to_thread(storage.finished.wait, 3))
                path = Path(directory) / (hashlib.sha256(ACCOUNT.did.encode()).hexdigest() + ".db")
                self.assertFalse(path.exists())

    async def test_queued_draft_does_not_follow_the_next_account(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            service = self.service(storage)
            draft = service.draft_save("invented", {"text": "Invented old draft"})
            service.account = replace(ACCOUNT, did="did:example:another-reader")
            await draft
            self.assertIsNone(storage.get(service.account.did, "draft:invented"))
            await service.save_active_feed("following", None)
            self.assertIsNone(storage.get(service.account.did, "reading:feed"))

    async def test_secure_io_retains_sdk_lock_across_repeated_cancellation(self):
        entered, resume = threading.Event(), threading.Event()
        calls = []
        service = Service.__new__(Service)
        service.lock = asyncio.Lock()

        def save():
            entered.set()
            if not resume.wait(5):
                raise TimeoutError("Invented keyring gate was not released")
            calls.append("save")

        async def guarded_save():
            async with service.lock:
                await service._secure_io(save)

        async def clear():
            async with service.lock:
                calls.append("clear")

        saving = asyncio.create_task(guarded_save())
        self.assertTrue(await asyncio.to_thread(entered.wait, 3))
        saving.cancel()
        await asyncio.sleep(0)
        saving.cancel()
        clearing = asyncio.create_task(clear())
        await asyncio.sleep(0)
        self.assertTrue(service.lock.locked())
        self.assertFalse(clearing.done())
        resume.set()
        with self.assertRaises(asyncio.CancelledError):
            await saving
        await clearing
        self.assertEqual(calls, ["save", "clear"])

    async def test_cancelled_failed_session_save_keeps_persistence_recovery_required(self):
        entered, resume = threading.Event(), threading.Event()
        failure = KeyringError("Invented persistence failure")

        def save(_value):
            entered.set()
            if not resume.wait(5):
                raise TimeoutError("Invented secure IO gate was not released")
            raise failure

        service = Service.__new__(Service)
        service.lock = asyncio.Lock()
        service.secrets = SimpleNamespace(save=save)
        service.persist_error = None

        async def saving():
            async with service.lock:
                await service._session_changed(
                    None, SimpleNamespace(export=lambda: "invalid fixture")
                )

        task = asyncio.create_task(saving())
        self.assertTrue(await asyncio.to_thread(entered.wait, 3))
        task.cancel()
        await asyncio.sleep(0)
        resume.set()
        with self.assertRaises(KeyringError):
            await task
        self.assertIs(service.persist_error, failure)
