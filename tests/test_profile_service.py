"""Profile preservation and pagination contracts through the pinned SDK."""

import json
import tempfile
import unittest

import httpx
from atproto import AsyncClient
from atproto_client.client.session import Session
from atproto_client.request import AsyncRequest
from test_service import CID, DID, jwt

from skyloom.domain import Author
from skyloom.errors import UserError
from skyloom.profile_service import COLLECTION, EditableProfile, validate_profile
from skyloom.service import Service
from skyloom.storage import Storage


class ProfileContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.record = {
            "$type": COLLECTION,
            "displayName": "Invented",
            "description": "Before",
            "futureField": {"preserve": [1, 2]},
            "pinnedPost": {
                "$type": "com.atproto.repo.strongRef",
                "uri": f"at://{DID}/app.bsky.feed.post/test",
                "cid": CID,
            },
            "labels": {
                "$type": "com.atproto.label.defs#selfLabels",
                "values": [
                    {"$type": "com.atproto.label.defs#selfLabel", "val": "!no-unauthenticated"}
                ],
            },
        }
        self.requests = []
        self.missing = False
        self.conflict = False
        self.profile_unavailable = False
        client = AsyncClient(
            base_url="https://pds.invalid",
            request=AsyncRequest(transport=httpx.MockTransport(self.handle)),
        )
        # Invented unsigned fixture credentials, never a real session.
        await client.login(
            session_string=Session(
                "invented.invalid",
                DID,
                jwt(),
                jwt(scope="com.atproto.refresh"),
                "https://pds.invalid",
            ).export(),
            fetch_bsky_profile=False,
        )
        self.service = Service(client=client, storage=Storage(self.directory.name))
        self.service.account = Author(DID, "invented.invalid", "Invented")

    async def asyncTearDown(self):
        await self.service.close()
        self.directory.cleanup()

    def handle(self, request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = (
            json.loads(request.content)
            if request.content
            and request.headers.get("content-type", "").startswith("application/json")
            else None
        )
        self.requests.append((method, body, dict(request.url.params)))
        if method.endswith("getRecord"):
            if self.missing:
                return httpx.Response(404, json={"error": "RecordNotFound"})
            value = {"uri": f"at://{DID}/{COLLECTION}/self", "cid": CID, "value": self.record}
        elif method.endswith(("putRecord", "createRecord")):
            if self.conflict:
                return httpx.Response(400, json={"error": "InvalidSwap"})
            value = {"uri": f"at://{DID}/{COLLECTION}/self", "cid": CID}
        elif method.endswith("uploadBlob"):
            value = {
                "blob": {
                    "$type": "blob",
                    "ref": {"$link": CID},
                    "mimeType": "image/png",
                    "size": 20,
                }
            }
        elif method.endswith("getProfile"):
            if self.profile_unavailable:
                return httpx.Response(503, json={"error": "Unavailable"})
            value = {"did": DID, "handle": "invented.invalid", "displayName": "Invented"}
        elif method.endswith(("getFollowers", "getFollows")):
            field = "followers" if method.endswith("getFollowers") else "follows"
            value = {
                "subject": {"did": DID, "handle": "invented.invalid"},
                field: [
                    {
                        "did": "did:plc:otherinvented",
                        "handle": "other.invalid",
                        "displayName": "Other",
                        "viewer": {"muted": True},
                    }
                ],
                "cursor": "next",
            }
        else:
            raise AssertionError(method)
        return httpx.Response(200, json=value)

    async def test_preserves_unknown_fields_and_uses_original_cid(self):
        original = await self.service.editable_profile()
        result = await self.service.update_profile(original, "After", "Updated")
        _, body, _ = next(item for item in self.requests if item[0].endswith("putRecord"))
        self.assertEqual(body["swapRecord"], CID)
        self.assertEqual(body["repo"], DID)
        self.assertEqual(body["rkey"], "self")
        expected = {**self.record, "displayName": "After", "description": "Updated"}
        self.assertEqual(body["record"], expected)
        self.assertEqual(result.bio, "Updated")
        self.assertEqual(original.record, self.record)

    async def test_missing_profile_creates_literal_self_record(self):
        self.missing = True
        original = await self.service.editable_profile()
        await self.service.update_profile(original, "New", "")
        created = next(item for item in self.requests if item[0].endswith("createRecord"))
        self.assertEqual(created[1]["rkey"], "self")

    async def test_conflict_is_not_retried(self):
        original = await self.service.editable_profile()
        self.conflict = True
        with self.assertRaisesRegex(UserError, "changed in another client"):
            await self.service.update_profile(original, "After", "Updated")
        self.assertEqual(sum(method.endswith("putRecord") for method, _, _ in self.requests), 1)

    async def test_queued_save_rejects_same_did_in_a_new_account_session(self):
        import asyncio
        from dataclasses import replace

        original = await self.service.editable_profile()
        count = len(self.requests)
        await self.service.lock.acquire()
        save = asyncio.create_task(self.service.update_profile(original, "After", "Updated"))
        await asyncio.sleep(0)
        # Same profile values and DID still represent a distinct signed-in session.
        self.service.account = replace(self.service.account)
        self.service.lock.release()
        with self.assertRaisesRegex(UserError, "signed-in account changed"):
            await save
        self.assertEqual(len(self.requests), count)

    async def test_other_account_snapshot_cannot_write(self):
        with self.assertRaises(UserError):
            await self.service.update_profile(
                EditableProfile("did:plc:other", CID, json.dumps(self.record)), "Name", ""
            )
        self.assertEqual(self.requests, [])

    async def test_image_removal_preserves_other_blob_and_write_success_survives_read_failure(self):
        blob = {"$type": "blob", "ref": {"$link": CID}, "mimeType": "image/png", "size": 20}
        self.record.update(avatar=blob, banner=blob)
        original = await self.service.editable_profile()
        self.profile_unavailable = True
        result = await self.service.update_profile(original, "Saved", "Saved bio", avatar="")
        _, body, _ = next(item for item in self.requests if item[0].endswith("putRecord"))
        self.assertNotIn("avatar", body["record"])
        self.assertEqual(body["record"]["banner"], blob)
        self.assertEqual(result.bio, "Saved bio")

    async def test_invalid_image_rejected_before_write(self):
        original = await self.service.editable_profile()
        from pathlib import Path

        path = Path(self.directory.name) / "invalid.png"
        path.write_bytes(b"not an image")
        with self.assertRaises(UserError):
            await self.service.update_profile(original, "Name", "", avatar=str(path))
        self.assertFalse(any(method.endswith("putRecord") for method, _, _ in self.requests))

    async def test_follow_lists_preserve_viewer_and_cursor(self):
        for kind, suffix in (("followers", "getFollowers"), ("following", "getFollows")):
            authors, cursor = await self.service.follow_people(DID, kind, "before")
            self.assertEqual(cursor, "next")
            self.assertTrue(authors[0].muted)
            method, _, params = self.requests[-1]
            self.assertTrue(method.endswith(suffix))
            self.assertEqual(params, {"actor": DID, "limit": "30", "cursor": "before"})

    def test_grapheme_and_byte_limits(self):
        self.assertFalse(validate_profile("👨‍👩‍👧‍👦" * 20, ""))
        self.assertTrue(validate_profile("x" * 65, ""))
        self.assertTrue(validate_profile("", "x" * 257))
        self.assertTrue(validate_profile("a" + "\u0301" * 400, ""))

    async def test_uploaded_images_and_text_survive_stale_profile_and_reopen(self):
        from pathlib import Path

        path = Path(self.directory.name) / "prepared.png"
        path.write_bytes(b"\x89PNG" + b"invented prepared fixture")
        account = self.service.account
        original = await self.service.editable_profile()
        result = await self.service.update_profile(
            original, "Saved", "New bio", avatar=str(path), banner=str(path)
        )
        self.assertEqual((result.avatar, result.banner), (str(path), str(path)))
        self.assertTrue(result.avatar_local and result.banner_local)
        self.assertFalse(any(method.endswith("getProfile") for method, _, _ in self.requests))
        self.assertIs(self.service.account, account)
        stale = await self.service.profile(DID)
        self.assertEqual((stale.name, stale.bio), ("Saved", "New bio"))
        self.assertEqual(stale.avatar, str(path))
        self.assertTrue(stale.avatar_local)
        await self.service.update_profile(original, "Saved", "New bio", avatar="", banner="")
        removed = await self.service.profile(DID)
        self.assertFalse(
            removed.avatar or removed.banner or removed.avatar_local or removed.banner_local
        )

    async def test_text_only_edit_keeps_the_displayed_images_without_a_dependent_read(self):
        from dataclasses import replace

        current = replace(
            self.service.account,
            avatar="https://cdn.bsky.app/avatar/new-before-editor.png",
            banner="https://cdn.bsky.app/banner/new-before-editor.png",
        )
        original = await self.service.editable_profile()
        result = await self.service.update_profile(original, "Saved", "Updated", current=current)
        self.assertEqual((result.avatar, result.banner), (current.avatar, current.banner))
        self.assertFalse(result.avatar_local or result.banner_local)
