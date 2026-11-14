"""A successful publish stays successful when later local cleanup fails."""

import unittest

from gtk_support import DISPLAY
from startup_fixture import StartupFixture


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ComposerCompletion(StartupFixture, unittest.TestCase):
    def test_published_post_closes_composer_refreshes_profile_and_reports_cleanup_separately(self):
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.window.show_offline(False)
        self.window.profile(self.account.did)
        page = self.window.nav.get_visible_page()
        self.wait(lambda: hasattr(page, "profile_edit"))
        refreshes, messages, attempts = [], [], []
        page.content_view.refresh = lambda: refreshes.append("profile")
        self.window.toast = messages.append
        original_save, original_send = self.app.service.draft_save, self.app.service.send

        async def save(key, value):
            if not value:
                raise OSError("Invented local storage failure after publishing")
            return await original_save(key, value)

        async def send(*args, **kwargs):
            attempts.append(args[0])
            return await original_send(*args, **kwargs)

        self.app.service.draft_save = save
        self.app.service.send = send
        self.window.compose(draft_key="invented-publish-cleanup")
        editor = self.window.composer
        self.addCleanup(editor.force_close)
        self.wait(lambda: editor.ready)
        editor.buffer.set_text("Invented successful post")
        editor.send()
        self.wait(lambda: self.window.composer is None)
        self.assertEqual(attempts, ["Invented successful post"])
        self.assertEqual(refreshes, ["profile"])
        self.assertTrue(any("Post published" in m and "draft" in m for m in messages))
        self.assertFalse(any("draft is kept" in m for m in messages))
