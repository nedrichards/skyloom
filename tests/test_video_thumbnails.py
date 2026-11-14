"""Invented video thumbnails exercise the real download, redirect and decoder path."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from gtk_support import DISPLAY

if DISPLAY:
    from gi.repository import GdkPixbuf

WATCH = "https://video.bsky.app/watch/did%3Aplc%3Ainvented/invented-cid/thumbnail.jpg"
CDN = "https://video.cdn.bsky.app/hls/did:plc:invented/invented-cid/thumbnail.jpg"


def transport(handler):
    client = httpx.AsyncClient
    return patch(
        "skyloom.media.httpx.AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class VideoThumbnailDownloads(unittest.IsolatedAsyncioTestCase):
    async def test_redirected_thumbnail_decodes_and_caches_under_original_url(self):
        from skyloom.image_cache import ImageCache
        from skyloom.media import Images

        pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 8, 8)
        pix.fill(0x3584E4FF)
        _ok, payload = pix.save_to_bufferv("png", [], [])
        calls = []

        def response(request):
            calls.append(request)
            if request.url.host == "video.bsky.app":
                return httpx.Response(302, headers={"Location": CDN})
            return httpx.Response(200, content=payload)

        with tempfile.TemporaryDirectory() as directory, transport(response):
            disk = ImageCache(Path(directory) / "cache")
            images = Images(directory, disk)
            images.use_account("invented-account")
            texture = await images.get(WATCH)
            self.assertEqual((texture.get_width(), texture.get_height()), (8, 8))
            self.assertIs(await images.get(WATCH), texture)
            restored = Images(directory, ImageCache(disk.root))
            restored.use_account("invented-account")
            restored.auto_download_allowed = lambda: False
            await restored.catalog()
            self.assertTrue(restored.has_cached(WATCH))
            self.assertEqual((await restored.get(WATCH)).get_width(), 8)
        self.assertEqual(
            [request.url.host for request in calls], ["video.bsky.app", "video.cdn.bsky.app"]
        )
        self.assertTrue(all("Authorization" not in request.headers for request in calls))

    async def test_unsupported_initial_sources_never_make_a_request(self):
        from skyloom.errors import UserError
        from skyloom.media import image_bytes

        calls = []

        def response(request):
            calls.append(request)
            return httpx.Response(200, content=b"unused")

        with transport(response):
            for url in (
                WATCH.replace("https:", "http:"),
                WATCH.replace("video.bsky.app", "video.bsky.app.evil.invalid"),
                WATCH.replace("video.bsky.app", "127.0.0.1"),
                WATCH.replace("video.bsky.app", "name@video.bsky.app"),
                WATCH.replace("video.bsky.app", "video.bsky.app:444"),
                WATCH.replace("video.bsky.app", "video.bsky.app:invalid"),
                WATCH.replace("thumbnail.jpg", "playlist.m3u8"),
                WATCH.replace("/watch/", "/other/"),
            ):
                with self.subTest(url=url), self.assertRaises(UserError):
                    await image_bytes(url)
        self.assertFalse(calls)

    async def test_video_redirects_cannot_escape_the_thumbnail_allowlist(self):
        from skyloom.errors import UserError
        from skyloom.media import image_bytes

        for target in (
            "https://127.0.0.1/private.jpg",
            "http://video.cdn.bsky.app/hls/a/b/thumbnail.jpg",
            CDN.replace("video.cdn.bsky.app", "video.cdn.bsky.app.evil.invalid"),
            CDN.replace("video.cdn.bsky.app", "name@video.cdn.bsky.app"),
            CDN.replace("video.cdn.bsky.app", "video.cdn.bsky.app:444"),
            CDN.replace("thumbnail.jpg", "playlist.m3u8"),
        ):
            calls = []

            def response(request, calls=calls, target=target):
                calls.append(request)
                return httpx.Response(302, headers={"Location": target})

            with self.subTest(target=target), transport(response), self.assertRaises(UserError):
                await image_bytes(WATCH)
            self.assertEqual(len(calls), 1)

    async def test_redirect_loops_stop_after_two_hops(self):
        from skyloom.errors import UserError
        from skyloom.media import image_bytes

        calls = []

        def response(request):
            calls.append(request)
            return httpx.Response(302, headers={"Location": WATCH})

        with transport(response), self.assertRaises(UserError):
            await image_bytes(WATCH)
        self.assertEqual(len(calls), 3)

    async def test_photo_redirects_remain_disabled(self):
        from skyloom.media import image_bytes

        calls = []

        def response(request):
            calls.append(request)
            return httpx.Response(302, headers={"Location": CDN})

        with transport(response), self.assertRaises(httpx.HTTPStatusError):
            await image_bytes("https://cdn.bsky.app/img/invented.jpg")
        self.assertEqual(len(calls), 1)

    async def test_redirected_body_still_obeys_the_image_byte_limit(self):
        from skyloom.errors import UserError
        from skyloom.media import image_bytes

        def response(request):
            if request.url.host == "video.bsky.app":
                return httpx.Response(302, headers={"Location": CDN})
            return httpx.Response(200, content=b"x" * 8_000_001)

        with transport(response), self.assertRaisesRegex(UserError, "too large"):
            await image_bytes(WATCH)
