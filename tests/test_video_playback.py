"""Installed native decoder proof with a tiny generated, invented H.264/HLS clip."""

import subprocess
import tempfile
import time
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from gtk_support import DISPLAY

if DISPLAY:
    from gi.repository import GLib, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class NativeVideoPlayback(unittest.TestCase):
    def test_h264_hls_prepares_and_advances_native_frames(self):
        with tempfile.TemporaryDirectory(prefix="skyloom-invented-video-") as directory:
            playlist = Path(directory) / "playlist.m3u8"
            subprocess.run(  # noqa: S603 - fixed encoder arguments and temporary invented output
                [
                    "/usr/bin/ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=160x90:rate=15",
                    "-t",
                    "3",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-f",
                    "hls",
                    "-hls_time",
                    "1",
                    "-hls_list_size",
                    "0",
                    "-y",
                    str(playlist),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            from skyloom.video_stream import VideoStream

            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self, _format, *_args):
                    pass

            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), partial(QuietHandler, directory=directory)
            )
            server_thread = Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            stream = VideoStream(f"http://127.0.0.1:{server.server_port}/playlist.m3u8")
            video = Gtk.Video(media_stream=stream, autoplay=False)
            window = Gtk.Window(child=video, default_width=400, default_height=300)
            try:
                window.present()
                stream.play()
                loop = GLib.MainLoop()
                started = time.monotonic()
                success = False

                def poll():
                    nonlocal success
                    success = bool(
                        stream.is_prepared()
                        and stream.has_video()
                        and stream.get_timestamp() > 0
                        and stream.sink.get_property("stats").get_value("rendered") > 0
                        and stream.get_intrinsic_width() > 0
                    )
                    if success or stream.get_error() is not None or time.monotonic() - started > 10:
                        loop.quit()
                        return False
                    return True

                GLib.timeout_add(50, poll)
                loop.run()
                self.assertIsNone(
                    stream.get_error(),
                    "Installed native media backend could not decode invented HLS",
                )
                self.assertTrue(success, "Native H.264/HLS playback did not advance")
                self.assertGreater(stream.sink.get_property("stats").get_value("rendered"), 0)
                self.assertGreater(stream.get_intrinsic_width(), 0)
                stream.set_muted(True)
                self.assertTrue(stream.pipeline.get_property("mute"))
                stream.set_volume(0.25)
                self.assertAlmostEqual(stream.pipeline.get_property("volume"), 0.25)
            finally:
                stream.pause()
                stream.clear()
                video.set_media_stream(None)
                window.destroy()
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def test_inline_player_renders_local_clip_and_releases_on_unmap(self):
        from types import SimpleNamespace

        from gtk_support import settle

        from skyloom.domain import Video
        from skyloom.video_player import InlineVideo
        from skyloom.widgets import ImagePreview

        with tempfile.TemporaryDirectory(prefix="skyloom-inline-fixture-") as directory:
            clip = Path(directory) / "invented.mp4"
            subprocess.run(  # noqa: S603 - fixed encoder and invented temporary fixture
                [
                    "/usr/bin/ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=160x90:rate=15",
                    "-t",
                    "3",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    str(clip),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
            window = Gtk.Window(default_width=480, default_height=360)
            window.service = SimpleNamespace(account=object())
            window.generation = 1
            window.read_only = False
            player = InlineVideo(
                window,
                Video(str(clip), "Invented moving pattern", local=True),
                ImagePreview(Gtk.Label(label="Invented preview")),
            )
            window.set_child(player)
            try:
                self.assertTrue(settle(window))
                self.assertIsNone(player.stream)
                player.play.emit("clicked")
                stream = player.stream
                self.assertIsNotNone(stream)
                self.assertTrue(settle(window, ready=lambda: stream.get_timestamp() > 0))
                self.assertIsNone(stream.get_error())
                self.assertGreater(stream.sink.get_property("stats").get_value("rendered"), 0)
                player.set_visible(False)
                self.assertIsNone(player.stream)
                self.assertIsNone(player.owner_watch)
                self.assertIsNone(window.video_player)
            finally:
                player.finished()
                window.destroy()
