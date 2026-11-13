"""Real SDK post records and account-leased video preparation boundaries."""

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from atproto import AsyncClient, models
from atproto_client.client.session import Session
from atproto_client.request import AsyncRequest
from test_service import CID, DID, URI, jwt

from skyloom.domain import Author, Post
from skyloom.errors import UserError
from skyloom.service import Service
from skyloom.storage import Storage
from skyloom.video_upload import VideoAttachment


class VideoSend(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.requests = []
        client = AsyncClient(
            base_url="https://pds.invalid",
            request=AsyncRequest(transport=httpx.MockTransport(self.handle)),
        )
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
        client.me = models.AppBskyActorDefs.ProfileViewDetailed(did=DID, handle="invented.invalid")
        self.service = Service(client=client, storage=Storage(self.directory.name))
        self.service.account = Author(DID, "invented.invalid", "Invented")
        self.video = VideoAttachment("invented-prepared.mp4", "An invented blue square", 1, 160, 90)
        self.embed = models.AppBskyEmbedVideo.Main(
            video={"$type": "blob", "ref": {"$link": CID}, "mimeType": "video/mp4", "size": 100},
            alt=self.video.alt,
            aspect_ratio={"width": 160, "height": 90},
        )

    async def asyncTearDown(self):
        await self.service.close()
        self.directory.cleanup()

    def handle(self, request):
        self.assertTrue(request.url.path.endswith("com.atproto.repo.createRecord"))
        self.requests.append(json.loads(request.content))
        return httpx.Response(200, json={"uri": URI, "cid": CID})

    async def test_video_and_quote_wrap_real_sdk_create_record(self):
        quote = Post(URI, CID, self.service.account, "Invented quote", "2026-11-13T00:00:00Z")
        helper = AsyncMock(return_value=self.embed)
        with patch("skyloom.video_upload.upload_video", helper):
            await self.service.send(
                "Invented video caption",
                quote=quote,
                video=self.video,
                expected_account=self.service.account,
            )
        helper.assert_awaited_once_with(self.service, self.video)
        self.assertEqual(len(self.requests), 1)
        record = self.requests[0]["record"]
        self.assertEqual(record["embed"]["$type"], "app.bsky.embed.recordWithMedia")
        self.assertEqual(record["embed"]["record"]["record"]["uri"], URI)
        self.assertEqual(record["embed"]["media"]["$type"], "app.bsky.embed.video")
        self.assertEqual(record["embed"]["media"]["alt"], self.video.alt)

    async def test_account_replacement_rejects_before_video_upload(self):
        previous = self.service.account
        self.service.account = replace(previous)
        helper = AsyncMock(return_value=self.embed)
        with (
            patch("skyloom.video_upload.upload_video", helper),
            self.assertRaisesRegex(UserError, "account changed"),
        ):
            await self.service.send(
                "Invented video caption", video=self.video, expected_account=previous
            )
        helper.assert_not_awaited()
        self.assertEqual(self.requests, [])

    async def test_failed_preprocessing_never_creates_post(self):
        helper = AsyncMock(side_effect=UserError("Invented processing failure"))
        with (
            patch("skyloom.video_upload.upload_video", helper),
            self.assertRaisesRegex(UserError, "processing failure"),
        ):
            await self.service.send("Invented video caption", video=self.video)
        self.assertEqual(helper.await_count, 1)
        self.assertEqual(self.requests, [])


class VideoStorageLease(unittest.TestCase):
    def test_signout_waits_for_preparation_then_removes_video_and_rejects_stale_work(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            token = storage.activate(DID)
            entered, resume, cleared = threading.Event(), threading.Event(), threading.Event()
            errors = []

            def prepare(_source, target, **_kwargs):
                entered.set()
                if not resume.wait(3):
                    raise TimeoutError("Invented preparation gate was not released")
                target = Path(target)
                target.mkdir()
                result = target / "invented.mp4"
                result.write_bytes(b"invented prepared bytes")
                return VideoAttachment(str(result))

            def run():
                try:
                    storage.run(DID, token, "prepare_video", "invented-source.mp4")
                except (OSError, RuntimeError, ValueError) as exc:
                    errors.append(type(exc).__name__)

            def clear():
                storage.clear(DID)
                cleared.set()

            with patch("skyloom.video_upload.prepare_video", side_effect=prepare) as operation:
                worker = threading.Thread(target=run)
                worker.start()
                self.assertTrue(entered.wait(3))
                cleaner = threading.Thread(target=clear)
                cleaner.start()
                try:
                    self.assertFalse(cleared.wait(0.05))
                finally:
                    resume.set()
                    worker.join(3)
                    cleaner.join(3)
                self.assertFalse(worker.is_alive())
                self.assertFalse(cleaner.is_alive())
                self.assertEqual(errors, [])
                self.assertTrue(cleared.is_set())
                self.assertEqual(list(Path(directory).glob("*-videos")), [])
                self.assertIsNone(storage.run(DID, token, "prepare_video", "invented-source.mp4"))
                self.assertEqual(operation.call_count, 1)
