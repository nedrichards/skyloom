"""Contracts through the actual pinned SDK and HTTPX transport; no live service calls."""

import asyncio
import base64
import json
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path

import httpx
from atproto import AsyncClient
from atproto_client.exceptions import AtProtocolError, RateLimitExceededError
from atproto_client.request import AsyncRequest

from skyloom.credentials import KeyringError
from skyloom.domain import Author
from skyloom.errors import UserError, message
from skyloom.network import Request
from skyloom.service import Attachment, Service
from skyloom.storage import Storage

DID = "did:plc:abcdefghijklmnopqrstuvwx"
URI = f"at://{DID}/app.bsky.feed.post/test"
CID = "bafyreie5nqv6mse23zlpqzboxxjxmkq74i4wvs4jkxpxqdqmjpoa7mc5vu"


def jwt(exp=None, scope="com.atproto.access"):
    # Deliberately unsigned test-only material, never a service-issued credential.
    def enc(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return (
        enc({"alg": "none"})
        + "."
        + enc(
            {
                "sub": DID,
                "aud": "did:web:pds.invalid",
                "exp": exp or int(time.time()) + 3600,
                "iat": int(time.time()),
                "scope": scope,
            }
        )
        + ".test"
    )


class Secrets:
    def __init__(self):
        self.value = None
        self.locked = False
        self.saves = 0

    def save(self, value):
        if self.locked:
            raise KeyringError("Unlock your keyring.")
        self.value = value
        self.saves += 1

    def load(self):
        if self.locked:
            raise KeyringError("Unlock your keyring.")
        return self.value

    def clear(self):
        if self.locked:
            raise KeyringError("Unlock your keyring.")
        self.value = None


class Contract(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.secrets = Secrets()
        self.requests = []
        self.fail = None
        self.refreshes = 0
        self.profile = {
            "did": DID,
            "handle": "alice.invalid",
            "displayName": "Alice",
            "followersCount": 4,
            "followsCount": 2,
            "postsCount": 3,
        }
        self.post = {
            "uri": URI,
            "cid": CID,
            "author": self.profile,
            "record": {
                "$type": "app.bsky.feed.post",
                "text": "Hi 🌤️",
                "createdAt": "2026-10-26T10:00:00Z",
            },
            "likeCount": 1,
            "repostCount": 2,
            "replyCount": 0,
            "indexedAt": "2026-10-26T10:00:00Z",
        }
        self.factory = lambda base_url="https://pds.invalid": AsyncClient(
            base_url=base_url, request=AsyncRequest(transport=httpx.MockTransport(self.handle))
        )
        self.service = Service(
            client=self.factory(),
            secrets=self.secrets,
            storage=Storage(self.tmp.name),
            client_factory=self.factory,
        )

    async def asyncTearDown(self):
        await self.service.client.request.close()
        self.tmp.cleanup()

    def session(self):
        return {
            "did": DID,
            "handle": "alice.invalid",
            "accessJwt": jwt(),
            "refreshJwt": jwt(scope="com.atproto.refresh"),
            "didDoc": {
                "id": DID,
                "service": [
                    {
                        "id": "#atproto_pds",
                        "type": "AtprotoPersonalDataServer",
                        "serviceEndpoint": "https://pds.invalid",
                    }
                ],
            },
        }

    def handle(self, req):
        method = req.url.path.rsplit("/", 1)[-1]
        body = (
            json.loads(req.content)
            if req.content and req.headers.get("content-type", "").startswith("application/json")
            else None
        )
        self.requests.append((method, body, dict(req.url.params), req.headers.get("Authorization")))
        if self.fail and method == self.fail[0]:
            return httpx.Response(
                self.fail[1],
                json={
                    "error": "TestFailure",
                    "message": "Sensitive exception body must not reach UI",
                },
                headers={"retry-after": "60"},
            )
        if method.endswith(("createSession", "refreshSession")):
            if method.endswith("refreshSession"):
                self.refreshes += 1
            value = self.session()
        elif method.endswith("getProfile"):
            value = self.profile
        elif method.endswith(("getTimeline", "getAuthorFeed", "getFeed")):
            value = {"feed": [{"post": self.post}], "cursor": "page-2"}
        elif method.endswith("getPostThread"):
            value = getattr(self, "thread_response", None) or {
                "thread": {
                    "$type": "app.bsky.feed.defs#threadViewPost",
                    "post": self.post,
                    "replies": [],
                }
            }
        elif method.endswith("createRecord"):
            value = {"uri": f"at://{DID}/{body['collection']}/own-record", "cid": CID}
        elif method.endswith("getPreferences"):
            value = {
                "preferences": [
                    {
                        "$type": "app.bsky.actor.defs#savedFeedsPrefV2",
                        "items": [
                            {
                                "id": "1",
                                "type": "feed",
                                "value": f"at://{DID}/app.bsky.feed.generator/custom",
                                "pinned": True,
                            }
                        ],
                    }
                ]
            }
        elif method.endswith("getFeedGenerators"):
            value = {"feeds": []}
        elif method.endswith("resolveHandle"):
            value = {"did": DID}
        elif method.endswith("listNotifications"):
            value = {
                "notifications": [
                    {
                        "uri": URI,
                        "cid": CID,
                        "author": self.profile,
                        "reason": "like",
                        "reasonSubject": URI,
                        "record": self.post["record"],
                        "isRead": False,
                        "indexedAt": "2026-10-26T10:00:00Z",
                    }
                ]
            }
        elif method.endswith("getUnreadCount"):
            value = {"count": 1}
        elif method.endswith("searchPosts"):
            value = {"posts": [self.post], "cursor": "more"}
        elif method.endswith("searchActors"):
            value = {"actors": [self.profile]}
        elif method.endswith("uploadBlob"):
            value = {
                "blob": {
                    "$type": "blob",
                    "ref": {"$link": CID},
                    "mimeType": "image/png",
                    "size": 50,
                }
            }
        else:
            value = {}
        return httpx.Response(200, json=value)

    async def login(self):
        return await self.service.sign_in(
            "alice.invalid", "test-only-never-valid", "https://pds.invalid"
        )

    async def test_login_restore_refresh_and_signout(self):
        a = await self.login()
        self.assertEqual(a.did, DID)
        self.assertIsNotNone(self.secrets.value)
        self.assertNotIn("test-only-never-valid", self.secrets.value)
        self.assertEqual(self.secrets.saves, 1)
        self.assertEqual((await self.service.restore()).did, DID)
        self.service.client._session.access_jwt = jwt(exp=int(time.time()) - 10)
        await asyncio.gather(self.service.feed(), self.service.profile(DID))
        self.assertEqual(self.refreshes, 1)
        self.assertGreaterEqual(self.secrets.saves, 3)
        self.service.storage.put(DID, "draft:new", {"text": "private draft"})
        refresh_jwt = self.service.client._session.refresh_jwt
        await self.service.sign_out()
        self.assertIsNone(self.secrets.value)
        self.assertIsNone(self.service.account)
        self.assertIsNone(self.service.storage.get(DID, "draft:new"))
        delete = next(r for r in self.requests if r[0].endswith("deleteSession"))
        self.assertEqual(delete[3], "Bearer " + refresh_jwt)

    async def test_locked_keyring_and_revoked_refresh(self):
        self.secrets.locked = True
        with self.assertRaises(KeyringError):
            await self.login()
        with self.assertRaises(KeyringError):
            await self.service.restore()
        self.secrets.locked = False
        await self.login()
        self.secrets.locked = True
        with self.assertRaises(KeyringError):
            await self.service.sign_out()
        self.assertIsNotNone(self.service.account)
        self.secrets.locked = False
        self.service.client._session.access_jwt = jwt(exp=int(time.time()) - 10)
        self.fail = ("com.atproto.server.refreshSession", 401)
        with self.assertRaises(AtProtocolError) as caught:
            await self.service.feed()
        self.assertIn("session", message(caught.exception))
        self.assertIsNotNone(self.secrets.value)

    async def test_feed_pagination_profile_and_thread(self):
        await self.login()
        page = await self.service.feed(cursor="cursor-value")
        self.assertEqual(page.posts[0].text, "Hi 🌤️")
        self.assertEqual(page.cursor, "page-2")
        self.assertEqual(self.requests[-1][2]["cursor"], "cursor-value")
        await self.service.feed()
        self.assertEqual((await self.service.cached("following")).posts[0].uri, URI)
        requests = len(self.requests)
        self.assertEqual((await self.service.cached_post(URI)).uri, URI)
        self.assertEqual(len(self.requests), requests)
        self.assertEqual((await self.service.thread(URI)).posts[0].context, "Selected post")
        self.assertEqual((await self.service.author_feed(DID)).posts[0].uri, URI)
        self.assertEqual((await self.service.profile(DID)).followers, 4)
        self.assertTrue(await self.service.feeds())
        await self.service.feed("at://custom/feed")
        self.assertEqual(self.requests[-1][2]["feed"], "at://custom/feed")

    async def test_conversation_context_incremental_requests_and_unavailable_posts(self):
        await self.login()
        parent = deepcopy(self.post)
        parent["uri"] = URI.rsplit("/", 1)[0] + "/parent"
        selected = deepcopy(self.post)
        selected["record"]["reply"] = {
            "root": {"uri": parent["uri"], "cid": CID},
            "parent": {"uri": parent["uri"], "cid": CID},
        }
        child = deepcopy(self.post)
        child["uri"] = URI.rsplit("/", 1)[0] + "/child"
        child["replyCount"] = 2
        child["record"]["reply"] = {
            "root": {"uri": parent["uri"], "cid": CID},
            "parent": {"uri": URI, "cid": CID},
        }
        self.thread_response = {
            "thread": {
                "$type": "app.bsky.feed.defs#threadViewPost",
                "post": selected,
                "parent": {"$type": "app.bsky.feed.defs#threadViewPost", "post": parent},
                "replies": [{"$type": "app.bsky.feed.defs#threadViewPost", "post": child}],
            }
        }
        page = await self.service.thread(URI)
        self.assertEqual([p.uri for p in page.posts], [parent["uri"], URI, child["uri"]])
        self.assertEqual(page.branches, (child["uri"],))
        self.assertEqual(page.posts[1].parent, (parent["uri"], CID))
        self.assertEqual(self.requests[-1][2]["depth"], "2")
        self.assertEqual(self.requests[-1][2]["parentHeight"], "20")
        await self.service.thread(child["uri"], replies_only=True)
        self.assertEqual(self.requests[-1][2]["parentHeight"], "0")
        await self.service.thread(parent["uri"], earlier=True)
        self.assertEqual(self.requests[-1][2]["depth"], "0")
        self.thread_response = {
            "thread": {
                "$type": "app.bsky.feed.defs#notFoundPost",
                "uri": URI,
                "notFound": True,
            }
        }
        with self.assertRaisesRegex(UserError, "deleted, blocked or unavailable"):
            await self.service.thread(URI)

    async def test_own_record_mutations_and_failure(self):
        await self.login()
        p = (await self.service.feed()).posts[0]
        liked = await self.service.mutate(p, "like")
        self.assertIn("app.bsky.feed.like/own-record", liked.like_uri)
        restored = await self.service.mutate(liked, "like")
        self.assertFalse(restored.like_uri)
        deletion = next(r for r in self.requests if r[0].endswith("deleteRecord"))
        self.assertEqual(deletion[1]["rkey"], "own-record")
        self.assertEqual(deletion[1]["collection"], "app.bsky.feed.like")
        reposted = await self.service.mutate(p, "repost")
        self.assertFalse((await self.service.mutate(reposted, "repost")).repost_uri)
        self.fail = ("com.atproto.repo.createRecord", 500)
        with self.assertRaises(AtProtocolError):
            await self.service.mutate(p, "like")
        self.assertFalse(p.like_uri)  # Immutable snapshot is rollback source.

    async def test_post_reply_quote_images_facets(self):
        await self.login()
        p = (await self.service.feed()).posts[0]
        from dataclasses import replace

        reply = replace(p, root=("at://root/post/1", CID))
        await self.service.send(
            "🌤️ https://example.invalid @alice.invalid #GNOME", reply=reply, quote=p
        )
        record = self.requests[-1][1]["record"]
        self.assertEqual(record["reply"]["root"]["uri"], "at://root/post/1")
        self.assertEqual(record["reply"]["parent"]["uri"], URI)
        self.assertEqual(record["embed"]["record"]["uri"], URI)
        self.assertEqual(len(record["facets"]), 3)
        path = Path(self.tmp.name) / "image.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-only-mocked-image")
        await self.service.send("Image", [Attachment(str(path), "A test image")], quote=p)
        record = self.requests[-1][1]["record"]
        self.assertEqual(record["embed"]["media"]["images"][0]["alt"], "A test image")
        self.assertEqual(record["embed"]["$type"], "app.bsky.embed.recordWithMedia")
        with self.assertRaises(UserError):
            await self.service.send("a" * 301)
        with self.assertRaises(UserError):
            await self.service.send("", [Attachment(str(path), "")])
        path.unlink()
        with self.assertRaisesRegex(UserError, "no longer available"):
            await self.service.send("Kept image post", [Attachment(str(path), "Description kept")])

    async def test_search_notifications_follow_moderation(self):
        await self.login()
        self.assertTrue((await self.service.search("hi")).posts)
        self.assertEqual((await self.service.search("Alice", True))[0][0].did, DID)
        notices, _cursor, timestamp = await self.service.notifications()
        self.assertEqual(notices[0].subject, URI)
        self.assertEqual(await self.service.unread(), 1)
        await self.service.mark_seen(timestamp)
        self.assertEqual(self.requests[-1][1]["seenAt"], timestamp)
        a = Author("did:example:other", "other.invalid", "Other")
        followed = await self.service.follow(a)
        self.assertTrue(followed.following)
        self.assertFalse((await self.service.follow(followed)).following)
        await self.service.moderate(a, "mute")
        self.assertTrue(any(r[0].endswith("muteActor") for r in self.requests))
        await self.service.moderate(a, "block")
        self.assertTrue(
            any(r[1] and r[1].get("collection") == "app.bsky.graph.block" for r in self.requests)
        )

    async def test_offline_restore_and_refresh_persistence_retry(self):
        await self.login()
        await self.service.feed()
        self.fail = ("app.bsky.actor.getProfile", 500)
        self.assertEqual((await self.service.restore()).did, DID)
        self.assertTrue((await self.service.cached("following")).posts)
        self.fail = None
        self.secrets.locked = True
        self.service.client._session.access_jwt = jwt(exp=int(time.time()) - 10)
        with self.assertRaises(KeyringError):
            await self.service.feed()
        with self.assertRaises(KeyringError):
            await self.service.feed()
        self.secrets.locked = False
        self.assertTrue((await self.service.feed()).posts)
        self.assertIsNone(self.service.persist_error)

    async def test_restart_restores_selected_feed_only_when_still_in_saved_choices(self):
        await self.login()
        selected = "at://did:example:feed/app.bsky.feed.generator/invented"
        self.service.storage.put(
            DID, "feed-options", [("following", "Following"), (selected, "Invented")]
        )
        await self.service.save_active_feed(selected, self.service.account)
        await self.service.restore()
        self.assertEqual(self.service.reading_feed, selected)
        self.assertEqual(self.service.reading_choices[1], (selected, "Invented"))
        self.service.storage.put(DID, "feed-options", [("following", "Following")])
        await self.service.restore()
        self.assertEqual(self.service.reading_feed, "following")

    async def test_old_account_checkpoint_cannot_recreate_data_after_sign_out(self):
        from skyloom.domain import Pager
        from skyloom.feed_state import Bookmark

        await self.login()
        old_account = self.service.account
        page = await self.service.feed(cursor="invented-cursor")
        self.assertEqual(
            (await self.service.cached_page("following", "invented-cursor")).posts, page.posts
        )
        pager = Pager(list(page.posts), page.cursor)
        bookmark = Bookmark(page.posts[0].uri, -12)
        await self.service.save_feed_state("following", pager, bookmark, old_account)
        self.assertEqual((await self.service.cached_state("following")).bookmark, bookmark)
        await self.service.sign_out()
        await self.service.save_feed_state("following", pager, bookmark, old_account)
        self.assertFalse(self.service.storage.cached_state(DID, "following").pager.posts)
        await self.login()
        await self.service.save_feed_state("following", pager, bookmark, old_account)
        self.assertFalse((await self.service.cached_state("following")).pager.posts)

    async def test_draft_serialization_and_discovery(self):
        await self.login()
        value = {"text": "Kept draft", "attachments": [], "reply": None, "quote": None}
        await asyncio.gather(
            *(self.service.draft_save("new", {**value, "text": str(i)}) for i in range(8))
        )
        self.assertEqual((await self.service.draft_get("new"))["text"], "7")
        self.assertEqual((await self.service.drafts())[0][0], "new")
        await self.service.draft_save("new", {})
        self.assertEqual(await self.service.drafts(), [])

    async def test_errors_are_safe_and_cancellable(self):
        await self.login()
        for status, word in [
            (401, "session"),
            (403, "permitted"),
            (429, "limiting"),
            (500, "connection"),
        ]:
            self.fail = ("app.bsky.feed.getTimeline", status)
            with self.assertRaises(AtProtocolError) as caught:
                await self.service.feed()
            text = message(caught.exception)
            self.assertIn(word, text)
            self.assertNotIn("Sensitive", text)
        self.assertNotIn("token", message(RuntimeError("token")))
        with self.assertRaises(UserError):
            await self.service.sign_in("x", "test", "http://insecure.invalid")


class CooldownTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_replacement_preserves_cooldown(self):
        calls = []

        def handler(req):
            calls.append(req)
            return httpx.Response(
                429, json={"error": "RateLimitExceeded"}, headers={"Retry-After": "90"}
            )

        def factory(base_url="https://pds.invalid"):
            return AsyncClient(
                base_url=base_url, request=Request(transport=httpx.MockTransport(handler))
            )

        service = Service(client=factory(), client_factory=factory, secrets=Secrets())
        try:
            with self.assertRaises(RateLimitExceededError):
                await service.sign_in(
                    "alice.invalid", "test-only-never-valid", "https://pds.invalid"
                )
            with self.assertRaises(UserError):
                await service.sign_in(
                    "alice.invalid", "test-only-never-valid", "https://pds.invalid"
                )
            self.assertEqual(len(calls), 1)
        finally:
            await service.close()

    async def test_retry_after_blocks_repeated_requests(self):
        calls = []

        def handler(req):
            calls.append(req)
            return httpx.Response(
                429, json={"error": "RateLimitExceeded"}, headers={"Retry-After": "90"}
            )

        r = Request(transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(RateLimitExceededError):
                await r.get("https://pds.invalid/xrpc/test")
            with self.assertRaises(UserError):
                await r.get("https://pds.invalid/xrpc/test")
            self.assertEqual(len(calls), 1)
        finally:
            await r.close()
