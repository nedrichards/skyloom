"""Defensive native-video model mapping and cached round trips."""

import unittest
from dataclasses import asdict, replace

from skyloom.domain import Author, Post, Video, deleted_post, post_from
from skyloom.storage import post_restore


class VideoModels(unittest.TestCase):
    def post(self, embed):
        return post_from(
            {
                "uri": "at://did:plc:invented/app.bsky.feed.post/video",
                "cid": "invented",
                "author": {"did": "did:plc:invented", "handle": "invented.invalid"},
                "record": {"text": "Invented video"},
                "embed": embed,
            }
        )

    def test_https_video_and_record_with_media_map_alt_and_aspect(self):
        view = {
            "$type": "app.bsky.embed.video#view",
            "cid": "invented",
            "playlist": "https://video.invalid/playlist.m3u8",
            "thumbnail": "https://video.invalid/thumb.jpg",
            "alt": "An invented moving shape",
            "aspectRatio": {"width": 1280, "height": 720},
        }
        direct = self.post(view)
        self.assertEqual(
            direct.video, Video(view["playlist"], view["alt"], view["thumbnail"], 1280, 720)
        )
        self.assertFalse(direct.unavailable)
        wrapped = self.post({"$type": "app.bsky.embed.recordWithMedia#view", "media": view})
        self.assertEqual(wrapped.video, direct.video)

    def test_untrusted_playlist_schemes_and_credentials_are_unavailable(self):
        for playlist in (
            "http://video.invalid/a.m3u8",
            "file:///private/a",
            "https://user:secret@video.invalid/a",
            "https://user@video.invalid/a",
            "javascript:bad",
            "",
        ):
            with self.subTest(playlist=playlist):
                post = self.post({"$type": "app.bsky.embed.video#view", "playlist": playlist})
                self.assertIsNone(post.video)
                self.assertEqual(post.unavailable, "This video is unavailable.")

    def test_invalid_aspect_and_thumbnail_do_not_hide_playable_video(self):
        post = self.post(
            {
                "$type": "app.bsky.embed.video#view",
                "playlist": "https://video.invalid/a.m3u8",
                "thumbnail": "http://video.invalid/a.jpg",
                "aspectRatio": {"width": -1, "height": "large"},
            }
        )
        self.assertEqual((post.video.width, post.video.height), (0, 0))
        self.assertFalse(post.video.thumbnail)

    def test_cache_restores_video_and_legacy_posts_and_deletion_removes_it(self):
        post = Post(
            "invented",
            "cid",
            Author("did:plc:invented", "invented.invalid", "Invented"),
            "",
            "",
            video=Video("https://video.invalid/a.m3u8", "Alt"),
        )
        self.assertEqual(post_restore(asdict(post)), post)
        legacy = asdict(replace(post, video=None))
        legacy.pop("video")
        self.assertIsNone(post_restore(legacy).video)
        self.assertIsNone(deleted_post(post).video)
