"""Native destructive confirmation and deletion recovery with invented records."""

import unittest
from dataclasses import replace

from gtk_support import DISPLAY
from startup_fixture import StartupFixture


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class DeletionViewTests(StartupFixture, unittest.TestCase):
    def test_cancel_failure_and_success_preserve_or_strip_content_truthfully(self):
        from skyloom.domain import deleted_post
        from skyloom.errors import UserError

        self.app.settings.set_boolean("load-images", False)
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: self.window.home_title.get_visible_child_name() == "feeds")
        self.wait(lambda: not self.window.page_requests and not self.app.worker.pending)
        window = self.window
        window.is_active = lambda: False
        view = window.feed_views[window.feed_id]
        original = replace(
            self.app.service.posts[0],
            uri=f"at://{self.account.did}/app.bsky.feed.post/deletion-fixture",
            author=self.account,
            text="Invented post to delete",
            quote=None,
        )
        quoted = replace(
            original, uri=original.uri + "-quoting", text="An invented quote", quote=original
        )
        pager = window.pagers[window.feed_id]
        pager.posts = [original, quoted]
        view.set_posts(pager.posts, reset=True)
        calls, messages = [], []
        window.toast = messages.append
        failing = True

        async def delete(post, *, expected_account=None):
            calls.append(post.uri)
            self.assertIs(expected_account, self.account)
            if failing:
                raise UserError("Invented deletion failure")
            return deleted_post(post)

        self.app.service.delete_post = delete

        def respond(response):
            window.delete_post(original)
            self.wait(lambda: window.get_visible_dialog() is not None)
            dialog = window.get_visible_dialog()
            self.assertEqual(dialog.get_heading(), "Delete this post?")
            self.assertEqual(dialog.get_default_response(), "cancel")
            dialog.emit("response", response)
            dialog.force_close()

        respond("cancel")
        self.assertEqual(calls, [])
        self.assertEqual(view.model.get_item(0).post.text, original.text)

        respond("delete")
        self.wait(lambda: bool(messages))
        self.assertIn("Invented deletion failure", messages[-1])
        self.assertEqual(len(calls), 1)
        self.assertEqual(view.model.get_item(0).post.text, original.text)
        self.assertEqual(view.model.get_item(1).post.quote.text, original.text)
        self.assertNotIn(original.uri, window.deleted_posts)

        failing = False
        respond("delete")
        self.wait(lambda: original.uri in window.deleted_posts)
        self.assertEqual(len(calls), 2)
        self.assertEqual(messages[-1], "Post deleted.")
        self.assertEqual(view.model.get_item(0).post.text, "")
        self.assertEqual(view.model.get_item(1).post.quote.text, "")
        self.assertTrue(view.model.get_item(0).post.unavailable)
        # A delayed feed response cannot restore the post or quoted content.
        view.set_posts([original, quoted])
        self.assertEqual(view.model.get_item(0).post.text, "")
        self.assertEqual(view.model.get_item(1).post.quote.text, "")
