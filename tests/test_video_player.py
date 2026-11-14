"""Native video dialog ownership, explicit playback and recovery controls."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class VideoPlayerTests(unittest.TestCase):
    def setUp(self):
        self.window = Adw.Window(
            title="Invented video fixture", default_width=800, default_height=600
        )
        self.window.service = SimpleNamespace(account=object())
        self.window.generation = 1
        self.window.read_only = False
        self.window.closing = False
        self.messages = []
        self.window.toast = self.messages.append
        self.addCleanup(self.window.destroy)
        self.assertTrue(settle(self.window))

    def test_offline_or_invalid_remote_sources_do_not_create_a_player(self):
        from skyloom.domain import Video
        from skyloom.video_player import open_video

        self.window.read_only = True
        self.assertIsNone(open_video(self.window, Video("https://video.invalid/a.m3u8")))
        self.window.read_only = False
        self.assertIsNone(open_video(self.window, Video("http://video.invalid/a.m3u8")))
        self.assertEqual(len(self.messages), 2)
        self.assertIsNone(getattr(self.window, "video_player", None))

    def test_account_change_and_close_clear_stream_and_ownership_watch(self):
        from skyloom.domain import Video
        from skyloom.video_player import VideoPlayer

        player = VideoPlayer(self.window, Video("https://video.invalid/a.m3u8", "Invented motion"))
        player.present(self.window)
        self.addCleanup(player.force_close)
        self.assertFalse(player.video.get_autoplay())
        self.assertIsNone(player.stream)
        self.window.generation += 1
        self.assertFalse(player.check_owner())
        player.finished()
        self.assertTrue(player.closed)
        self.assertIsNone(player.stream)
        self.assertIsNone(player.owner_watch)
        self.assertIsNone(player.timeout)

    def test_replacing_player_closes_previous_and_failure_offers_explicit_retry(self):
        from skyloom.domain import Video
        from skyloom.video_player import VideoPlayer, open_video

        with patch.object(VideoPlayer, "start") as start:
            first = open_video(self.window, Video("https://video.invalid/a.m3u8"))
            self.addCleanup(first.force_close)
            second = open_video(self.window, Video("https://video.invalid/b.m3u8"))
            self.addCleanup(second.force_close)
            self.assertEqual(start.call_count, 2)
            first.finished()
            self.assertIs(self.window.video_player, second)
            second.fail("Invented playback failure")
            self.assertEqual(second.message.get_label(), "Invented playback failure")
            self.assertTrue(second.retry.get_visible())
            second.retry.emit("clicked")
            self.assertEqual(start.call_count, 3)
            second.finished()
            self.assertIsNone(self.window.video_player)

    def inline_player(self, source):
        from gi.repository import Gtk

        from skyloom.video_player import InlineVideo
        from skyloom.widgets import ImagePreview

        player = InlineVideo(self.window, source, ImagePreview(Gtk.Label(label="Invented poster")))
        self.addCleanup(player.finished)
        return player

    def test_inline_play_is_explicit_single_owner_and_unmap_releases_pipeline(self):
        from gi.repository import Gtk

        from skyloom.domain import Video
        from skyloom.video_player import Playback

        first = self.inline_player(Video("/invented-first.mp4", local=True))
        second = self.inline_player(Video("/invented-second.mp4", local=True))
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(first)
        body.append(second)
        self.window.set_content(body)
        self.assertTrue(settle(self.window))
        self.assertIsNone(first.stream)
        self.assertIsNone(first.video)
        self.assertIsNone(first.owner_watch)
        with patch.object(Playback, "start") as start:
            first.play.emit("clicked")
            self.assertEqual(start.call_count, 1)
            self.assertIs(first.preview.get_first_child(), first.video)
            self.assertIs(self.window.video_player, first)
            second.play.emit("clicked")
            self.assertIs(self.window.video_player, second)
            self.assertIsNone(first.owner_watch)
            self.assertIs(first.play.get_child(), first.preview)
            second.set_visible(False)
            self.assertIsNone(second.stream)
            self.assertIsNone(second.owner_watch)
            self.assertIsNone(self.window.video_player)
            self.assertIs(second.preview.get_first_child(), second.poster)

    def test_inline_offline_retry_and_account_replacement(self):
        from skyloom.domain import Video
        from skyloom.video_player import Playback

        player = self.inline_player(Video("https://video.invalid/invented.m3u8"))
        self.window.set_content(player)
        self.assertTrue(settle(self.window))
        self.window.read_only = True
        player.play.emit("clicked")
        self.assertIsNone(player.stream)
        self.assertIn("offline", player.message.get_label())
        self.assertTrue(player.retry.get_visible())
        self.window.read_only = False
        with patch.object(Playback, "start") as start:
            player.retry.emit("clicked")
            start.assert_called_once()
        self.window.generation += 1
        player.check_owner()
        self.assertIsNone(player.owner_watch)
        self.assertIsNone(self.window.video_player)
        with patch.object(Playback, "start") as start:
            player.play.emit("clicked")
            start.assert_not_called()
        self.assertTrue(player.closed)

    def test_feed_thumbnail_obeys_download_policy_and_recycling_disposes_player(self):
        from dataclasses import replace

        from content_fixture import ContentFixture

        from skyloom.domain import Video
        from skyloom.video_player import InlineVideo
        from skyloom.widgets import PostRow, list_children

        fixture = ContentFixture()
        fixture.window.generation = 1
        callbacks = []

        def submit(coro, success, failure):
            coro.close()
            callbacks.append((success, failure))

        fixture.window.worker.submit = submit
        source = Video(
            "https://video.invalid/invented.m3u8",
            "Invented video description",
            "https://video.invalid/invented.jpg",
            160,
            90,
        )
        post = replace(fixture.post, images=(), labels=(), video=source)
        for enabled in (False, True):
            fixture.requests.clear()
            fixture.window.settings.set_boolean("load-images", enabled)
            row = PostRow(post, fixture.window)
            player = next(c for c in list_children(row.attachments) if isinstance(c, InlineVideo))
            self.assertEqual(player.preview.ratio, 160 / 90)
            self.assertEqual(source.thumbnail in fixture.requests, enabled)
            self.assertNotIn(source.playlist, fixture.requests)
            self.assertIsNone(player.stream)
            fallback = player.poster.get_last_child().get_last_child()
            self.assertTrue(fallback.get_visible())
            if enabled:
                callbacks[-1][1]("Invented failure")
                self.assertIn("Preview unavailable", fallback.get_label())
            row.cancel()
            self.assertTrue(player.closed)
            self.assertIsNone(player.stream)
