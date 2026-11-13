"""Native composer video descriptions and failed-send draft recovery."""

import unittest
from dataclasses import replace
from pathlib import Path

from gtk_support import DISPLAY, settle
from startup_fixture import StartupFixture


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ComposerVideo(StartupFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.window.show_offline(False)

    def composer(self, key):
        self.window.compose(draft_key=key)
        editor = self.window.composer
        self.addCleanup(editor.force_close)
        self.wait(lambda: editor.ready)
        return editor

    def test_video_requires_description_and_excludes_images(self):
        from skyloom.video_upload import VideoAttachment

        editor = self.composer("invented-video-description")
        editor.video = VideoAttachment(
            str(Path(self.app.service.directory.name) / "invented-prepared.mp4"),
            duration=1,
            width=160,
            height=90,
        )
        editor.render_attachments()
        editor.changed()
        self.assertFalse(editor.send_button.get_sensitive())
        self.assertFalse(editor.add.get_sensitive())
        self.assertFalse(editor.add_video.get_sensitive())
        self.assertIn("description", editor.feedback.get_text())
        editor.video = replace(editor.video, alt="A blue invented square")
        editor.changed()
        self.assertTrue(editor.send_button.get_sensitive())
        self.assertTrue(settle(self.window))
        # The video can be removed without losing accompanying text.
        editor.buffer.set_text("An invented caption")
        group = editor.attach_box.get_first_child().get_child()
        group.get_last_child().emit("clicked")
        self.assertIsNone(editor.video)
        self.assertEqual(editor.text(), "An invented caption")
        self.assertTrue(editor.add.get_sensitive())
        self.assertTrue(editor.add_video.get_sensitive())

    def test_failed_video_send_restores_video_from_durable_draft(self):
        from skyloom.errors import UserError
        from skyloom.video_upload import VideoAttachment

        editor = self.composer("invented-video-failure")
        video = VideoAttachment(
            str(Path(self.app.service.directory.name) / "invented-prepared.mp4"),
            "A blue invented square",
            1,
            160,
            90,
        )
        editor.video = video
        editor.buffer.set_text("An invented video caption")
        editor.render_attachments()
        editor.changed()
        attempts = []

        async def failed(*_args, **kwargs):
            attempts.append(kwargs["video"])
            raise UserError("Invented upload failure")

        self.app.service.send = failed
        editor.send()
        self.wait(lambda: not editor.sending)
        self.assertEqual(attempts, [video])
        self.assertEqual(editor.video, video)
        self.assertIn("draft is kept", editor.feedback.get_text())
        editor.force_close()
        self.wait(lambda: self.window.composer is None)
        restored = self.composer("invented-video-failure")
        self.assertEqual(restored.video, video)
        self.assertEqual(restored.text(), "An invented video caption")
        self.assertEqual(restored.snapshot()["video"]["alt"], video.alt)
        self.assertTrue(restored.send_button.get_sensitive())
