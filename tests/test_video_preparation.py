"""Real runtime ffmpeg preparation with a tiny generated, invented MP4."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from skyloom.errors import UserError
from skyloom.video_upload import _run, inspect_video, prepare_video


class VideoPreparation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "invented-source.mp4"
        _run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x90:r=5",
                "-t",
                "0.4",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-metadata",
                "title=Invented private title",
                "-metadata",
                "comment=Invented private comment",
                str(self.source),
            ]
        )

    def test_remux_strips_metadata_keeps_original_and_bounds_media(self):
        before = self.source.read_bytes()
        prepared = prepare_video(self.source, self.root / "prepared")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual((prepared.width, prepared.height), (160, 90))
        self.assertAlmostEqual(prepared.duration, 0.4, delta=0.1)
        target = Path(prepared.path)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("invented-source", target.name)
        payload = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags:stream_tags",
                "-of",
                "json",
                prepared.path,
            ]
        )
        self.assertNotIn("Invented private", payload.decode())
        self.assertEqual(list(target.parent.glob(".video-*")), [])

    def test_failed_remux_removes_partial_output(self):
        real = _run

        def run(command, **kwargs):
            if command[0] == "ffmpeg":
                Path(command[-1]).write_bytes(b"invented partial output")
                raise UserError("Invented remux failure")
            return real(command, **kwargs)

        directory = self.root / "prepared"
        with (
            patch("skyloom.video_upload._run", side_effect=run),
            self.assertRaisesRegex(UserError, "remux failure"),
        ):
            prepare_video(self.source, directory)
        self.assertEqual(list(directory.iterdir()), [])

    def test_cancelled_preparation_does_not_create_output(self):
        cancelled = threading.Event()
        cancelled.set()
        directory = self.root / "prepared"
        with self.assertRaisesRegex(UserError, "cancelled"):
            prepare_video(self.source, directory, cancel=cancelled)
        self.assertFalse(directory.exists())

    def test_rejects_duration_size_and_unsupported_codec(self):
        info = {
            "format": {"format_name": "mov,mp4", "duration": "601"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 160, "height": 90}],
        }
        with (
            patch("skyloom.video_upload._run", return_value=json.dumps(info).encode()),
            self.assertRaisesRegex(UserError, "10 minutes"),
        ):
            inspect_video(self.source)
        info["format"]["duration"] = "1"
        info["streams"][0]["codec_name"] = "mpeg4"
        with (
            patch("skyloom.video_upload._run", return_value=json.dumps(info).encode()),
            self.assertRaisesRegex(UserError, "H.264"),
        ):
            inspect_video(self.source)
        with self.source.open("r+b") as source:
            source.truncate(300_000_001)
        with self.assertRaisesRegex(UserError, "300 MB"):
            inspect_video(self.source)
