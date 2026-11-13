"""Native own-profile editing and people navigation with invented demo data."""

import unittest

from gtk_support import DISPLAY, settle
from startup_fixture import StartupFixture


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ProfileFeatures(StartupFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")

    def test_editor_preserves_failed_edits_then_saves(self):
        from skyloom.profile_editor import ProfileEditor

        saved = []
        editor = ProfileEditor(self.window, saved.append)
        editor.present(self.window)
        self.addCleanup(editor.force_close)
        self.wait(lambda: editor.original is not None)
        editor.name.set_text("Changed invented name")
        editor.buffer.set_text("Changed invented biography")
        self.assertTrue(settle(self.window))
        self.app.service.offline = True
        editor.save()
        self.wait(lambda: not editor.saving)
        self.assertEqual(editor.name.get_text(), "Changed invented name")
        self.assertEqual(editor.text(), "Changed invented biography")
        self.assertIn("changes are kept", editor.feedback.get_text())
        self.app.service.offline = False
        editor.save()
        self.wait(lambda: bool(saved))
        self.assertEqual(saved[0].name, "Changed invented name")
        self.assertEqual(saved[0].bio, "Changed invented biography")

    def test_editor_stale_account_cannot_save(self):
        from dataclasses import replace

        from skyloom.profile_editor import ProfileEditor

        editor = ProfileEditor(self.window, lambda _: self.fail("Stale editor saved"))
        editor.present(self.window)
        self.addCleanup(editor.force_close)
        self.wait(lambda: editor.original is not None)
        self.app.service.account = replace(self.account, did="did:plc:otherinvented")
        editor.name.set_text("Must not save")
        editor.save()
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertFalse(editor.saving)

    def test_following_browse_opens_native_people_and_profile(self):
        from skyloom.domain import Author

        page = self.window.follow_people(self.account, "following")
        view = page.content_view
        self.wait(lambda: not view.paging.busy)
        self.assertGreater(view.model.get_n_items(), 0)
        self.assertTrue(
            all(
                isinstance(view.model.get_item(index).post, Author)
                for index in range(view.model.get_n_items())
            )
        )
        self.assertTrue(settle(self.window))
        self.assertIs(self.window.nav.get_visible_page(), page)
        first = view.model.get_item(0).post
        self.window.profile(first.did)
        self.wait(lambda: hasattr(self.window.nav.get_visible_page(), "profile_browser"))
        self.assertIsNot(self.window.nav.get_visible_page(), page)
