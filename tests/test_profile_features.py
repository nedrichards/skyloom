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

    def test_saved_banner_uses_upload_while_profile_read_is_stale(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from unittest.mock import patch

        self.window.profile(self.account.did)
        page = self.window.nav.get_visible_page()
        self.wait(lambda: hasattr(page, "profile_edit"))
        calls = []

        def editor(window, saved, author):
            result = SimpleNamespace(images={"banner": ""}, present=lambda _: None, saved=saved)
            calls.append(result)
            return result

        # Both replacement and removal override an immediately stale AppView
        # result without requiring another mutation or a manual refresh.
        with patch("skyloom.window.ProfileEditor", side_effect=editor):
            page.profile_edit.emit("clicked")
        path = str(self.window.images.fixture_dir / "demo-landscape.svg")
        calls[0].images["banner"] = path
        with patch.object(self.window.images, "get", wraps=self.window.images.get) as get:
            calls[0].saved(replace(self.account, banner="https://invented.invalid/stale.png"))
            get.assert_any_call(path, local=True)
        self.wait(lambda: page.profile_banner.get_paintable() is not None)
        self.assertTrue(settle(self.window))
        self.assertEqual(page.profile_banner.get_height(), 160)
        self.wait(lambda: page not in self.window.page_requests)
        with patch("skyloom.window.ProfileEditor", side_effect=editor):
            page.profile_edit.emit("clicked")
        with patch.object(self.window.images, "get", wraps=self.window.images.get) as get:
            calls[1].saved(replace(self.account, banner="https://invented.invalid/stale.png"))
            self.assertFalse(any(call.args[0].endswith("stale.png") for call in get.call_args_list))

    def test_own_and_other_profile_actions_share_the_identity_row_when_wide(self):
        for actor in (self.account.did, self.app.service.posts[0].author.did):
            with self.subTest(actor=actor):
                self.window.set_default_size(1280, 820)
                self.window.profile(actor)
                page = self.window.nav.get_visible_page()
                self.wait(lambda page=page: hasattr(page, "profile_controls"))
                self.assertTrue(settle(self.window))
                row = page.profile_identity_row
                valid, details = page.profile_details.compute_bounds(row)
                self.assertTrue(valid)
                valid, actions = page.profile_controls.compute_bounds(row)
                self.assertTrue(valid)
                self.assertGreaterEqual(actions.origin.x, details.origin.x + details.size.width)
                self.assertLess(actions.origin.y, details.origin.y + details.size.height)
                # At a narrow width the same controls remain in the identity
                # section, wrapping underneath rather than creating a footer.
                self.window.set_default_size(480, 820)
                self.assertTrue(settle(self.window))
                self.assertIs(page.profile_controls.get_parent(), row)
                self.assertLessEqual(row.get_width(), page.content_view.get_width())
                self.assertTrue(page.profile_browser.get_mapped())
                self.assertTrue(page.profile_filter.get_mapped())
