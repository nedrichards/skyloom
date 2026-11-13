"""Interaction gates through the pinned SDK, using invented records only."""

import json
import unittest
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import httpx
from atproto import AsyncClient
from atproto_client.exceptions import AtProtocolError
from atproto_client.request import AsyncRequest

from skyloom.errors import UserError
from skyloom.thread_service import DISABLE, POST, THREAD, ThreadService, reply_rules

DID = "did:plc:abcdefghijklmnopqrstuvwx"
OTHER = "did:plc:bcdefghijklmnopqrstuvwxy"
URI = f"at://{DID}/app.bsky.feed.post/root"
REPLY = f"at://{OTHER}/app.bsky.feed.post/reply"
QUOTE = f"at://{OTHER}/app.bsky.feed.post/quote"
CID = "bafyreie5nqv6mse23zlpqzboxxjxmkq74i4wvs4jkxpxqdqmjpoa7mc5vu"


class Adapter(ThreadService):
    @asynccontextmanager
    async def authenticated(self):
        yield


class ThreadContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.records = {}
        self.failure = None
        self.visible = {
            "$type": "app.bsky.feed.post",
            "text": "Invented",
            "createdAt": "2026-11-13T12:00:00Z",
        }
        self.root = dict(self.visible)
        self.adapter = Adapter()
        self.adapter.account = SimpleNamespace(did=DID)

        def handle(request):
            method = request.url.path.rsplit("/", 1)[-1]
            self.calls.append(request)
            if self.failure and method.endswith(self.failure):
                return httpx.Response(409, json={"error": "InvalidSwap"})
            params = dict(request.url.params)
            if method.endswith("getRecord"):
                collection = params["collection"]
                record = (
                    self.root
                    if collection == "app.bsky.feed.post"
                    else self.records.get(collection)
                )
                if record is None:
                    return httpx.Response(404, json={"error": "RecordNotFound"})
                value = {"uri": f"at://{DID}/{collection}/root", "cid": CID, "value": record}
            elif method.endswith("getPosts"):
                uri = params["uris"]
                value = {
                    "posts": [
                        {
                            "uri": uri,
                            "cid": CID,
                            "author": {"did": OTHER, "handle": "invented.invalid"},
                            "record": self.visible,
                            "indexedAt": "2026-11-13T12:00:00Z",
                        }
                    ]
                }
            else:
                body = json.loads(request.content)
                self.records[body["collection"]] = body["record"]
                value = {"uri": f"at://{DID}/{body['collection']}/root", "cid": CID}
            return httpx.Response(200, json=value)

        self.adapter.client = AsyncClient(
            base_url="https://pds.invalid",
            request=AsyncRequest(transport=httpx.MockTransport(handle)),
        )
        self.addAsyncCleanup(self.adapter.client.request.close)

    async def test_absent_gate_uses_fixed_key_create_and_existing_uses_swap(self):
        thread, post = await self.adapter.thread_controls(URI)
        thread = await self.adapter.save_reply_rules(
            thread, "groups", ["mention", "follower", "following"]
        )
        body = json.loads(self.calls[-1].content)
        self.assertTrue(self.calls[-1].url.path.endswith("createRecord"))
        self.assertEqual(body["rkey"], "root")
        self.assertNotIn("swapRecord", body)
        self.assertEqual(len(body["record"]["allow"]), 3)
        await self.adapter.save_reply_rules(thread, "nobody", [])
        self.assertTrue(self.calls[-1].url.path.endswith("putRecord"))
        self.assertEqual(json.loads(self.calls[-1].content)["swapRecord"], CID)
        await self.adapter.save_quote_rule(post, False)
        self.assertEqual(self.records[POST]["embeddingRules"], [{"$type": DISABLE}])

    async def test_updates_preserve_lists_unknown_rules_and_other_fields(self):
        self.records[THREAD] = {
            "$type": THREAD,
            "post": URI,
            "createdAt": "2026-11-13T12:00:00Z",
            "allow": [
                {"$type": THREAD + "#listRule", "list": f"at://{DID}/app.bsky.graph.list/list"},
                {"$type": "future.example#rule", "value": "kept"},
            ],
            "hiddenReplies": [REPLY],
            "future": "kept",
        }
        self.records[POST] = {
            "$type": POST,
            "post": URI,
            "createdAt": "2026-11-13T12:00:00Z",
            "embeddingRules": [{"$type": DISABLE}, {"$type": "future.example#rule"}],
            "detachedEmbeddingUris": [QUOTE],
            "future": "kept",
        }
        thread, post = await self.adapter.thread_controls(URI)
        updated = await self.adapter.save_reply_rules(thread, "groups", ["mention"])
        self.assertEqual(updated.record["allow"][:2], thread.record["allow"])
        self.assertEqual(updated.record["hiddenReplies"], [REPLY])
        self.assertEqual(updated.record["future"], "kept")
        updated = await self.adapter.save_quote_rule(post, True)
        self.assertEqual(updated.record["embeddingRules"], [{"$type": "future.example#rule"}])
        self.assertEqual(updated.record["detachedEmbeddingUris"], [QUOTE])
        self.assertEqual(updated.record["future"], "kept")
        self.assertNotIn("allow", reply_rules(thread, "everyone", []))

    async def test_successful_hide_overrides_stale_thread_until_appview_catches_up(self):
        from skyloom.conversation import ThreadPage
        from skyloom.domain import Author, Post

        self.visible["reply"] = {
            "root": {"uri": URI, "cid": CID},
            "parent": {"uri": URI, "cid": CID},
        }
        await self.adapter.hidden_reply(URI, REPLY, True)
        author = Author(DID, "invented.invalid", "Invented")
        root = Post(URI, CID, author, "Root", "", context="Selected post")
        child = Post(REPLY, CID, author, "Hidden", "", context="Reply")
        stale = ThreadPage((root, child), edges=((REPLY, URI),))
        reconciled = self.adapter.apply_gate_controls(stale)
        self.assertEqual(reconciled.posts, (root,))
        self.assertEqual(reconciled.gaps[0].kind, "hidden")
        direct = ThreadPage((replace(child, context="Selected post"),))
        self.assertEqual(self.adapter.apply_gate_controls(direct).posts, direct.posts)
        await self.adapter.hidden_reply(URI, REPLY, False)
        self.assertEqual(self.adapter.apply_gate_controls(stale).posts, stale.posts)

    async def test_same_did_new_session_cannot_use_previous_gate_snapshot(self):
        thread, _post = await self.adapter.thread_controls(URI)
        self.adapter.account = SimpleNamespace(did=DID)
        count = len(self.calls)
        with self.assertRaises(UserError):
            await self.adapter.save_reply_rules(thread, "nobody", [])
        self.assertEqual(len(self.calls), count)

    async def test_permissions_reject_other_accounts_reply_roots_and_conflicts(self):
        with self.assertRaises(UserError):
            await self.adapter.thread_controls(REPLY)
        self.root["reply"] = {"root": {"uri": URI, "cid": CID}}
        with self.assertRaises(UserError):
            await self.adapter.thread_controls(URI)
        self.root.pop("reply")
        thread, _post = await self.adapter.thread_controls(URI)
        with self.assertRaises(UserError):
            await self.adapter.save_reply_rules(replace(thread, owner=OTHER), "nobody", [])
        self.failure = "createRecord"
        count = len(self.calls)
        with self.assertRaises(AtProtocolError):
            await self.adapter.save_reply_rules(thread, "nobody", [])
        self.assertEqual(len(self.calls), count + 2)  # root verification + single write

    async def test_hide_unhide_and_detach_reattach_preserve_permission_fields(self):
        self.visible["reply"] = {
            "root": {"uri": URI, "cid": CID},
            "parent": {"uri": URI, "cid": CID},
        }
        gate = await self.adapter.hidden_reply(URI, REPLY, True)
        self.assertEqual(gate.record["hiddenReplies"], [REPLY])
        self.assertEqual(
            (await self.adapter.hidden_reply(URI, REPLY, False)).record["hiddenReplies"], []
        )
        self.visible.pop("reply")
        self.visible["embed"] = {
            "$type": "app.bsky.embed.recordWithMedia",
            "record": {"$type": "app.bsky.embed.record", "record": {"uri": URI, "cid": CID}},
        }
        self.assertEqual(
            (await self.adapter.detached_quote(URI, QUOTE, True)).record["detachedEmbeddingUris"],
            [QUOTE],
        )
        self.assertEqual(
            (await self.adapter.detached_quote(URI, QUOTE, False)).record["detachedEmbeddingUris"],
            [],
        )
        self.visible.pop("embed")
        with self.assertRaises(UserError):
            await self.adapter.detached_quote(URI, QUOTE, True)
        with self.assertRaises(UserError):
            await self.adapter.hidden_reply(URI, REPLY, True)
