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
