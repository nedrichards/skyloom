"""Retained cell resources and parent chains across changing invented records."""

import unittest
from concurrent.futures import Future
from dataclasses import replace

from gtk_support import DISPLAY

if DISPLAY:
    pass


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class CellResidencyTests(unittest.TestCase):
    def test_avatar_media_and_core_parent_chains_survive_recycling(self):
        from content_fixture import ContentFixture

        from skyloom.widgets import PostRow

        fixture = ContentFixture()
        callbacks, futures = [], []

        def submit(coro, *handlers):
            coro.close()
            callbacks.append(handlers)
            future = Future()
            futures.append(future)
            return future

        fixture.window.worker.submit = submit
        first = replace(fixture.post, labels=(), author=replace(fixture.post.author, avatar=""))
        row = PostRow(first, fixture.window)
        self.addCleanup(row.cancel)
        avatar, content, actions = row.avatar_cell, row.content, row.actions
        media_cell = row.media_cells[0]
        picture, viewer = media_cell.pic, media_cell.viewer
        late_loaded = callbacks[0][0]
        binds = []
        fixture.window.images.bind = lambda *args: binds.append(args)
        for n in range(30):
            media = replace(first.images[0], url=f"demo-image-{n}", alt=f"Invented description {n}")
            post = replace(
                first, uri=f"at://did:example:media/app.bsky.feed.post/{n}", images=(media,)
            )
            row.bind_post(post)
            self.assertIs(row.avatar_cell, avatar)
            self.assertIs(row.content, content)
            self.assertIs(row.actions, actions)
            self.assertIs(content.get_parent(), row.body)
            self.assertIs(actions.get_parent(), content)
            self.assertIs(row.media_cells[0], media_cell)
            self.assertIs(media_cell.get_parent(), row.attachments)
            self.assertIs(media_cell.pic, picture)
            self.assertIs(media_cell.viewer, viewer)
            self.assertEqual(media_cell.alt.get_text(), "ALT · " + media.alt)
            self.assertLessEqual(len(avatar._avatar_signals), 2)
        late_loaded(object())
        self.assertFalse(binds)
        self.assertTrue(all(future.cancelled() for future in futures[:-1]))
        opened = []
        fixture.window.view_media = opened.append
        viewer.emit("clicked")
        self.assertEqual(opened, list(post.images))
        row.bind_post(replace(first, images=()))
        self.assertEqual(len(row.media_cells), 1)
        self.assertFalse(media_cell.get_visible())
        self.assertFalse(row.attachments.get_visible())
        self.assertIsNone(media_cell.media)
        self.assertEqual(media_cell.alt.get_text(), "")
        self.assertIsNone(picture.get_paintable())
        viewer.emit("clicked")
        self.assertEqual(opened, list(post.images))

    def test_reused_avatar_rejects_previous_author_completion_and_bounds_handlers(self):
        from content_fixture import ContentFixture

        from skyloom.widgets import PostRow

        fixture = ContentFixture()
        callbacks, futures = [], []

        def submit(coro, loaded):
            coro.close()
            callbacks.append(loaded)
            future = Future()
            futures.append(future)
            return future

        fixture.window.worker.submit = submit
        first = replace(
            fixture.post,
            labels=(),
            images=(),
            author=replace(fixture.post.author, avatar="invented-avatar-0"),
        )
        row = PostRow(first, fixture.window)
        self.addCleanup(row.cancel)
        avatar = row.avatar_cell
        late = callbacks[0]
        for n in range(1, 20):
            row.bind_post(
                replace(
                    first,
                    author=replace(
                        first.author,
                        did=f"did:example:avatar:{n}",
                        name=f"Invented author {n}",
                        avatar=f"invented-avatar-{n}",
                    ),
                )
            )
            self.assertIs(row.avatar_cell, avatar)
            self.assertEqual(len(avatar._avatar_signals), 2)
        binds = []
        fixture.window.images.bind = lambda *args: binds.append(args)
        late(object())
        self.assertFalse(binds)
        self.assertIsNone(avatar.get_custom_image())
        self.assertEqual(avatar.get_text(), "Invented author 19")
        self.assertTrue(all(future.cancelled() for future in futures[:-1]))
        row.cancel()
        self.assertFalse(avatar._avatar_signals)
        self.assertEqual(avatar.get_text(), "")

    def test_counter_update_keeps_identical_immutable_post_without_copy(self):
        from content_fixture import ContentFixture

        from skyloom.widgets import PostRow

        fixture = ContentFixture()
        post = replace(fixture.post, labels=(), images=())
        row = PostRow(post, fixture.window)
        self.addCleanup(row.cancel)
        self.assertIs(row.post, post)
        updated = replace(post, likes=5)
        row.update_counters(updated)
        self.assertIs(row.post, updated)
