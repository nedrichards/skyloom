"""Video service contracts use invented bytes, account data and service tokens."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from atproto import AsyncClient
from atproto_client.client.session import Session
from atproto_client.request import AsyncRequest
from test_service import CID, DID, jwt

from skyloom.errors import UserError
from skyloom.video_upload import (
    VIDEO_SERVICE,
    VideoAttachment,
    pds_audience,
    upload_video,
    validate_video,
)


class VideoUploadContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "private-original-name.mp4"
        path.write_bytes(b"invented prepared fixture" * 30_000)
        self.attachment = VideoAttachment(str(path), "An invented moving shape", 1, 320, 180)
        self.auth_requests = []
        self.video_requests = []
        self.limits = {
            "canUpload": True,
            "remainingDailyBytes": 300_000_000,
            "remainingDailyVideos": 2,
        }
        self.job = {"jobId": "invented-job", "did": DID, "state": "JOB_STATE_CREATED"}
        self.blob = {"$type": "blob", "ref": {"$link": CID}, "mimeType": "video/mp4", "size": 100}
        self.upload_status = 200
        self.polls = 0
        self.complete = True
        self.redirect = False
        self.timeout = False
        self.client = AsyncClient(
            base_url="https://pds.invalid",
            request=AsyncRequest(transport=httpx.MockTransport(self.auth)),
        )
        await self.client.login(
            session_string=Session(
                "invented.invalid",
                DID,
                jwt(),
                jwt(scope="com.atproto.refresh"),
                "https://pds.invalid",
            ).export(),
            fetch_bsky_profile=False,
        )
        self.service = SimpleNamespace(client=self.client, account=SimpleNamespace(did=DID))
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(self.video))
        self.inspection = patch("skyloom.video_upload.inspect_video", return_value=self.attachment)
        self.inspection.start()

    async def asyncTearDown(self):
        self.inspection.stop()
        await self.http.aclose()
        await self.client.request.close()
        self.directory.cleanup()

    def auth(self, request):
        self.assertTrue(request.url.path.endswith("com.atproto.server.getServiceAuth"))
        params = dict(request.url.params)
        self.auth_requests.append(params)
        return httpx.Response(
            200,
            json={
                "token": "fixture-limits"
                if params["lxm"].endswith("getUploadLimits")
                else "fixture-upload"
            },
        )

    async def video(self, request):
        self.video_requests.append(request)
        self.assertEqual(str(request.url).split("/xrpc/")[0], VIDEO_SERVICE)
        method = request.url.path.rsplit(".", 1)[-1]
        if method == "getUploadLimits":
            if self.redirect:
                return httpx.Response(307, headers={"Location": "https://other.invalid/private"})
            return httpx.Response(200, json=self.limits)
        if method == "uploadVideo":
            await request.aread()
            if self.timeout:
                raise httpx.ReadTimeout("invented timeout", request=request)
            return httpx.Response(self.upload_status, json=self.job)
        if method == "getJobStatus":
            self.polls += 1
            job = {**self.job, "blob": self.blob} if self.complete else self.job
            return httpx.Response(200, json={"jobStatus": job})
        raise AssertionError(method)

    async def upload(self, **kwargs):
        return await upload_video(
            self.service,
            self.attachment,
            http_client=self.http,
            poll_interval=0,
            poll_limit=2,
            **kwargs,
        )

    async def test_scoped_tokens_stream_once_poll_then_embed(self):
        embed = await self.upload()
        self.assertEqual(embed.alt, self.attachment.alt)
        self.assertEqual(embed.aspect_ratio.width, 320)
        self.assertEqual(embed.video.mime_type, "video/mp4")
        self.assertEqual(
            [request["lxm"] for request in self.auth_requests],
            ["app.bsky.video.getUploadLimits", "com.atproto.repo.uploadBlob"],
        )
        self.assertEqual(
            [request["aud"] for request in self.auth_requests],
            ["did:web:video.bsky.app", "did:web:pds.invalid"],
        )
        self.assertTrue(
            all(str(int(request["exp"])) == request["exp"] for request in self.auth_requests)
        )
        request = next(request for request in self.video_requests if request.method == "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer fixture-upload")
        self.assertEqual(request.headers["Content-Type"], "video/mp4")
        self.assertEqual(int(request.headers["Content-Length"]), len(request.content))
        self.assertEqual(request.url.params["did"], DID)
        self.assertNotIn("private-original", request.url.params["name"])
        self.assertEqual(self.polls, 1)

    async def test_quota_rejects_before_upload_auth_or_bytes(self):
        self.limits["remainingDailyVideos"] = 0
        with self.assertRaisesRegex(UserError, "daily video allowance"):
            await self.upload()
        self.assertEqual(len(self.video_requests), 1)
        self.assertEqual(len(self.auth_requests), 1)

    async def test_redirect_never_receives_service_token(self):
        self.redirect = True
        with self.assertRaises(UserError):
            await self.upload()
        self.assertEqual(len(self.video_requests), 1)

    async def test_already_processed_blob_is_usable_even_with_failed_state(self):
        self.upload_status = 409
        self.job.update(state="JOB_STATE_FAILED", error="already_exists", blob=self.blob)
        embed = await self.upload()
        self.assertEqual(embed.video.size, 100)
        self.assertEqual(self.polls, 0)

    async def test_wrong_owner_job_and_invalid_blob_fail_closed(self):
        self.job["did"] = "did:plc:otherinvented"
        with self.assertRaisesRegex(UserError, "invalid processing job"):
            await self.upload()
        self.job["did"] = DID
        self.job["blob"] = {**self.blob, "size": 300_000_001}
        with self.assertRaisesRegex(UserError, "invalid video blob"):
            await self.upload()

    async def test_already_exists_without_blob_waits_for_existing_job(self):
        self.upload_status = 409
        self.job.update(state="JOB_STATE_FAILED", error="already_exists")
        embed = await self.upload()
        self.assertEqual(embed.video.size, 100)
        self.assertEqual(self.polls, 1)

    async def test_upload_timeout_does_not_retry(self):
        self.timeout = True
        with self.assertRaises(httpx.ReadTimeout):
            await self.upload()
        self.assertEqual(sum(request.method == "POST" for request in self.video_requests), 1)

    async def test_processing_polling_is_bounded(self):
        self.complete = False
        with self.assertRaisesRegex(UserError, "processing took too long"):
            await self.upload()
        self.assertEqual(self.polls, 2)

    def test_description_limits_and_nonstandard_https_pds_port(self):
        self.assertTrue(validate_video(VideoAttachment("unused", "")))
        self.assertTrue(validate_video(VideoAttachment("unused", "x" * 1001)))
        self.client._session.pds_endpoint = "https://pds.invalid:8443"
        self.assertEqual(pds_audience(self.service), "did:web:pds.invalid%3A8443")
        self.client._session.pds_endpoint = "http://pds.invalid"
        with self.assertRaises(UserError):
            pds_audience(self.service)
