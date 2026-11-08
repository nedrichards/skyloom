"""Rendered startup states with synthetic async session lookup, never a real keyring."""

import asyncio
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from gtk_support import settle

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib, Gtk

    DISPLAY = Gtk.init_check()
    if DISPLAY:
        Adw.init()
except ImportError, ValueError, AttributeError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class StartupTests(unittest.TestCase):
    count = 0

    def setUp(self):
        from skyloom import APP_ID
        from skyloom.demo import DemoService
        from skyloom.media import Images
        from skyloom.worker import Worker

        type(self).count += 1
        self.app = Adw.Application(
            application_id=f"{APP_ID}.StartupFixture{self.count}",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.assertTrue(self.app.register(None))
        self.app.demo = False
        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        self.app.settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        self.app.settings.set_boolean("auto-refresh", False)
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        self.app.service = DemoService(fixtures / "demo-feed.json")
        self.app.service.cached_feeds = self.app.service.feeds
        self.account = self.app.service.account
        self.app.service.account = None
        self.app.worker = Worker()
        self.app.images = Images(fixtures, self.app.service.storage.images)
        self.window = None
        self.frames = []
        settings = Gtk.Settings.get_default()
        animations = settings.get_property("gtk-enable-animations")
        settings.set_property("gtk-enable-animations", True)
        self.addCleanup(settings.set_property, "gtk-enable-animations", animations)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.window:
            self.window.cancel_startup()
            self.window.refresh_monitor.close()
            for view in self.window.views:
                view.close()
            self.window.destroy()
        self.app.worker.close(self.app.service.close())

    def open(self, restore):
        from skyloom.window import Window

        self.app.service.restore = restore
        self.window = Window(self.app)
        self.window.set_title("Skyloom startup fixture")

        def frame(*_args):
            self.frames.append(
                (
                    self.window.stack.get_visible_child_name(),
                    self.window.stack.spinner.get_spinning(),
                )
            )
            return True

        self.window.add_tick_callback(frame)
        self.window.present()

    def wait(self, predicate, timeout=2):
        started = time.monotonic()
        loop = GLib.MainLoop()
        success = False

        def check():
            nonlocal success
            success = bool(predicate())
            if success or time.monotonic() - started >= timeout:
                loop.quit()
                return False
            return True

        GLib.timeout_add(10, check)
        loop.run()
        self.assertTrue(success, "Startup state did not settle before its deadline")

    async def restored_account(self):
        self.app.service.account = self.account
        return self.account

    def test_branch_completion_preserves_reading_after_scroll_during_request(self):
        from dataclasses import replace
        from threading import Event
        from unittest.mock import patch

        from test_conversation import node

        from skyloom.conversation import ThreadPage
        from skyloom.domain import post_from

        self.app.settings.set_boolean("load-images", False)
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: False  # Only explicit fixture requests are allowed.
        root = post_from(node("cold-root")["post"])
        posts = [root] + [
            replace(
                root,
                uri=root.uri + f"-{n:03}",
                text=f"Invented message {n}. " * 8,
                parent=(root.uri, "cid"),
                created=f"2026-11-08T12:{n // 60:02}:{n % 60:02}Z",
            )
            for n in range(80)
        ]
        branch = posts[40]
        reply = replace(posts[-1], uri=root.uri + "-new-reply", parent=(branch.uri, "cid"))
        started, release = Event(), Event()
        self.addCleanup(release.set)

        async def thread(uri, **kwargs):
            if uri == root.uri:
                return ThreadPage(tuple(posts), branches=(branch.uri,))
            started.set()
            await asyncio.to_thread(release.wait)
            return ThreadPage((branch, reply))

        self.app.service.thread = thread
        window.thread(root.uri)
        self.wait(lambda: not window.page_requests)
        view = window.nav.get_visible_page().content_view
        self.assertTrue(settle(window, ready=lambda: view.position_tick is None))
        self.assertFalse(branch.author.following)
        with patch.object(view.interaction, "restore", wraps=view.interaction.restore) as restore:
            view.load(branch=branch.uri)
            self.wait(started.is_set)
            view.interaction.move("last")

            def past_branch():
                place = view.interaction.capture()
                return (
                    view.position_tick is None
                    and place is not None
                    and view.entries[place.key][0] > view.entries[branch.uri][0]
                )

            self.assertTrue(settle(window, ready=past_branch))
            reading = view.interaction.capture()
            restore.reset_mock()
            release.set()
            self.wait(lambda: not window.page_requests)
            self.assertTrue(settle(window, ready=lambda: view.position_tick is None))
            self.assertEqual(restore.call_count, 1)
            self.assertEqual(restore.call_args.args[0].key, reading.key)
            actual = view.interaction.capture()
            self.assertEqual(actual.key, reading.key)
            self.assertAlmostEqual(actual.offset, reading.offset, delta=3)

    def test_thread_lookahead_renews_only_after_reading_progress(self):
        from dataclasses import replace
        from types import SimpleNamespace

        from test_conversation import node

        from skyloom.conversation import Continuation, ThreadPage
        from skyloom.domain import Post, post_from

        self.app.settings.set_boolean("load-images", False)
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: False
        root = post_from(node("lookahead-root")["post"])
        posts = [root] + [
            replace(root, uri=root.uri + f"-{n}", parent=(root.uri, "cid")) for n in range(8)
        ]
        calls = []

        async def thread(uri, **kwargs):
            calls.append(uri)
            if uri == root.uri:
                return ThreadPage(tuple(posts), branches=tuple(post.uri for post in posts[1:]))
            return ThreadPage((next(post for post in posts if post.uri == uri),))

        self.app.service.thread = thread
        window.thread(root.uri)
        self.wait(lambda: not window.page_requests)
        view = window.nav.get_visible_page().content_view
        self.assertTrue(settle(window, ready=lambda: view.position_tick is None))
        marker = [root]
        lookahead_y = [1200]

        def visible(margin=0):
            rows = [(0, SimpleNamespace(_value=marker[0]))]
            if margin and view.state.next_branch:
                rows.append(
                    (lookahead_y[0], SimpleNamespace(_value=Continuation(view.state.next_branch)))
                )
            return rows

        original = view.interaction.visible_rows
        view.interaction.visible_rows = visible
        self.addCleanup(setattr, view.interaction, "visible_rows", original)
        original_restore = view.interaction.restore
        view.interaction.restore = lambda _place, **_kwargs: (
            True
        )  # Synthetic viewport tests request policy only.
        self.addCleanup(setattr, view.interaction, "restore", original_restore)
        for _ in range(3):
            self.assertTrue(view.check_start())
            self.wait(lambda: not window.page_requests)
        self.assertFalse(view.check_start())
        self.assertEqual(len(calls), 4)
        marker[0] = posts[-1]  # A different first visible post replenishes the budget.
        self.assertIsInstance(marker[0], Post)
        lookahead_y[0] = -200  # Behind a downward-moving reader: do not insert there.
        self.assertFalse(view.check_start())
        self.assertEqual(len(calls), 4)
        lookahead_y[0] = 1200
        self.assertTrue(view.check_start())
        self.wait(lambda: not window.page_requests)
        self.assertEqual(len(calls), 5)
        marker[0] = posts[3]
        lookahead_y[0] = -200  # Reading upwards: the same upper margin is now ahead.
        self.assertTrue(view.check_start())
        self.wait(lambda: not window.page_requests)
        self.assertEqual(len(calls), 6)

    def test_home_prefetch_enriches_visible_posts_and_opening_reuses_snapshot(self):
        from test_conversation import node

        from skyloom.conversation import ThreadPage
        from skyloom.domain import post_from

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: True
        root_node = node("prefetch-root", reply_count=1)
        root = post_from(root_node["post"])
        child = post_from(node("prefetch-child", root_node)["post"])
        calls = []

        async def thread(uri, **_kwargs):
            calls.append(uri)
            return ThreadPage((root, child))

        self.app.service.thread = thread
        view = window.feed_views["following"]
        view.set_posts([root])
        view.list.grab_focus()
        view.queue_check()
        self.wait(lambda: window.thread_cache.get(child.uri) is not None)
        self.assertEqual(calls, [root.uri])
        self.assertEqual(view.model.get_n_items(), 1)
        self.assertEqual(window.post_positions.context.positions[root.uri], (1, 2, False))
        window.thread(child.uri)
        self.wait(lambda: window.nav.get_visible_page().get_title() == "Conversation")
        self.wait(lambda: not window.page_requests)
        conversation = window.nav.get_visible_page().content_view
        self.assertEqual([post.uri for post in conversation.state.posts], [root.uri, child.uri])
        self.assertEqual(conversation.state.anchor, child.uri)
        self.assertEqual(calls, [root.uri])

    def test_opening_cached_ancestor_fetches_its_own_replies_and_preserves_sibling(self):
        from test_conversation import node

        from skyloom.conversation import ThreadPage, thread_from
        from skyloom.domain import post_from

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: False
        root_node = node("ancestor-root", reply_count=2)
        child_node = node("ancestor-child", root_node)
        root = post_from(root_node["post"])
        child = post_from(child_node["post"])
        sibling = post_from(node("ancestor-sibling", root_node)["post"])
        window.thread_cache.put(child.uri, thread_from(child_node))
        window.feed_views["following"].set_posts([root, child])
        calls = []

        async def thread(uri, **_kwargs):
            calls.append(uri)
            return ThreadPage((root, child, sibling))

        self.app.service.thread = thread
        window.thread(root.uri)
        self.wait(lambda: window.nav.get_visible_page().get_title() == "Conversation")
        self.wait(lambda: not window.page_requests)
        state = window.nav.get_visible_page().content_view.state
        self.assertEqual(calls, [root.uri])
        self.assertEqual(state.anchor, root.uri)
        self.assertEqual({post.uri for post in state.posts}, {root.uri, child.uri, sibling.uri})

    def test_cached_child_keeps_original_fetch_identity_and_unloaded_replies(self):
        from test_conversation import node

        from skyloom.conversation import ThreadPage
        from skyloom.domain import post_from

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: False
        root_node = node("cached-root", reply_count=1)
        root = post_from(root_node["post"])
        child = post_from(node("cached-child", root_node, reply_count=1)["post"])
        window.thread_cache.put(root.uri, ThreadPage((root, child), branches=(child.uri,)))
        window.feed_views["following"].set_posts([root, child])
        window.thread(child.uri)
        self.wait(lambda: window.nav.get_visible_page().get_title() == "Conversation")
        self.wait(lambda: not window.page_requests)
        state = window.nav.get_visible_page().content_view.state
        self.assertEqual(state.anchor, child.uri)
        self.assertEqual(state.fetched, {root.uri})
        self.assertEqual(state.branches, [child.uri])
        self.assertFalse(state.unavailable)

    def test_opening_cached_descendant_does_not_renew_snapshot_freshness(self):
        from unittest.mock import Mock

        from test_conversation import node

        from skyloom.conversation import ThreadPage
        from skyloom.domain import post_from

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: False
        clock = Mock(return_value=1000)
        window.thread_cache.clock = clock
        root_node = node("expiring-root", reply_count=1)
        root = post_from(root_node["post"])
        child = post_from(node("expiring-child", root_node)["post"])
        window.thread_cache.pages.clear()
        window.thread_cache.put(root.uri, ThreadPage((root, child)))
        window.feed_views["following"].set_posts([root, child])
        clock.return_value = 1110
        window.thread(child.uri)
        self.wait(lambda: window.nav.get_visible_page().get_title() == "Conversation")
        self.wait(lambda: not window.page_requests)
        self.assertEqual(len(window.thread_cache.pages), 1)
        snapshot = window.thread_cache.get_snapshot(child.uri)
        self.assertEqual(snapshot.created, 1000)
        self.assertEqual(snapshot.anchor, root.uri)
        clock.return_value = 1121
        self.assertIsNone(window.thread_cache.get(child.uri))

    def test_opening_prefetched_post_preserves_latest_local_reactions(self):
        from dataclasses import replace

        from test_conversation import node

        from skyloom.conversation import ThreadPage
        from skyloom.domain import post_from

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        window = self.window
        window.is_active = lambda: False
        root_node = node("reaction-root", reply_count=1)
        root = post_from(root_node["post"])
        child = post_from(node("reaction-child", root_node)["post"])
        window.thread_cache.put(root.uri, ThreadPage((root, child)))
        window.feed_views["following"].set_posts([root])
        latest = replace(
            root,
            likes=7,
            like_uri="at://invented/like/confirmed",
            reposts=3,
            repost_uri="at://invented/repost/confirmed",
        )
        window.update_post(latest)
        window.thread(root.uri)
        self.wait(lambda: window.nav.get_visible_page().get_title() == "Conversation")
        self.wait(lambda: not window.page_requests)
        state = window.nav.get_visible_page().content_view.state
        actual = next(post for post in state.posts if post.uri == root.uri)
        self.assertEqual((actual.likes, actual.like_uri), (latest.likes, latest.like_uri))
        self.assertEqual((actual.reposts, actual.repost_uri), (latest.reposts, latest.repost_uri))

    def test_dense_feed_resize_renders_sidebar_slide_after_content_reflow(self):
        from dataclasses import replace

        settings = Gtk.Settings.get_default()
        reduced = settings.get_property("gtk-interface-reduced-motion")
        self.addCleanup(settings.set_property, "gtk-interface-reduced-motion", reduced)
        settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.NO_PREFERENCE)
        self.app.service.posts = [
            replace(
                self.app.service.posts[0],
                uri=f"at://did:example:sidebar/post/{i}",
                images=(),
                external=None,
            )
            for i in range(250)
        ]
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        self.assertTrue(settle(self.window, 250))
        split = self.window.split
        sidebar = split.get_sidebar()
        view = self.window.feed_views["following"]
        before = tuple(self.window.pagers["following"].posts)
        samples = []

        def frame(*_args):
            valid, bounds = sidebar.compute_bounds(split)
            if valid and sidebar.get_mapped():
                samples.append((bounds.origin.x, bounds.size.width))
            return True

        tick = self.window.add_tick_callback(frame)
        try:
            self.window.set_default_size(480, 820)
            self.assertTrue(settle(self.window, 1200, lambda: not sidebar.get_mapped()))
        finally:
            self.window.remove_tick_callback(tick)
        self.assertTrue(any(-width + 2 < x < -2 for x, width in samples))
        self.assertTrue(split.get_collapsed())
        self.assertFalse(split.get_show_sidebar())
        self.assertIs(self.window.feed_views["following"], view)
        self.assertEqual(tuple(self.window.pagers["following"].posts), before)
        self.assertIsNone(self.window.navigation.visibility_tick)

    def test_deep_cached_restart_restores_reading_then_accepts_fresh_order(self):
        from dataclasses import replace

        from skyloom.domain import Page, Pager
        from skyloom.feed_state import Bookmark

        service = self.app.service
        invented = [
            replace(
                service.posts[0], uri=f"at://did:example:restart/post/{i}", images=(), external=None
            )
            for i in range(240)
        ]
        pager = Pager(invented, "real-tail")
        bookmark = Bookmark(
            invented[180].uri, -35, invented[182].uri, (invented[181].uri, invented[179].uri)
        )
        service.storage.cache(
            self.account.did, "following", Page(tuple(invented[:30]), "real-head")
        )
        service.storage.checkpoint(self.account.did, "following", pager, bookmark)
        service.offline = True
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.window.is_active = lambda: True
        self.wait(lambda: not self.window.page_requests)
        view = self.window.feed_views["following"]
        self.assertTrue(settle(self.window, 500, lambda: view.position_tick is None))
        restored = self.window.pagers["following"]
        self.assertEqual(restored.posts, invented)
        self.assertEqual(restored.cursor, "real-tail")
        self.assertEqual(view.interaction.capture().key, bookmark.uri)
        self.assertAlmostEqual(view.interaction.capture().offset, bookmark.offset, delta=3)
        self.assertEqual(view.interaction.selected().uri, bookmark.selected)
        new = replace(invented[0], uri="at://did:example:restart/post/new")
        self.window.show_feed_update(
            "following", Page((new, invented[180], invented[0]), "fresh"), automatic=True
        )
        self.assertTrue(settle(self.window, 250, lambda: view.position_tick is None))
        self.assertEqual(
            self.window.pagers["following"].posts[:3], [new, invented[180], invented[0]]
        )
        self.assertEqual(view.interaction.capture().key, bookmark.uri)
        self.assertAlmostEqual(view.interaction.capture().offset, bookmark.offset, delta=3)
        # A subsequent live reorder is ignored, while metadata still updates.
        before = list(self.window.pagers["following"].posts)
        changed = replace(invented[4], likes=23)
        with patch.object(view, "offer_update", wraps=view.offer_update) as offer:
            self.window.show_feed_update(
                "following", Page((changed, invented[3]), "later"), automatic=True
            )
            offer.assert_not_called()
        self.assertTrue(settle(self.window, 250, lambda: view.position_tick is None))
        current = self.window.pagers["following"].posts
        self.assertEqual([p.uri for p in current], [p.uri for p in before])
        self.assertEqual(next(p.likes for p in current if p.uri == changed.uri), 23)

    def test_opening_conversation_saves_the_last_reading_place_before_unmap(self):
        from dataclasses import replace

        service = self.app.service
        service.posts = [
            replace(
                service.posts[0], uri=f"at://did:example:leaving/post/{i}", images=(), external=None
            )
            for i in range(40)
        ]
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.window.is_active = lambda: True
        self.wait(lambda: not self.window.page_requests)
        view = self.window.feed_views["following"]
        self.assertTrue(settle(self.window, 200))
        view.reading.flush()
        self.wait(lambda: view.reading.future is None)
        view.interaction.move("last")
        self.assertTrue(settle(self.window, 150, lambda: view.position_tick is None))
        bookmark = view.reading.capture()
        self.window.thread(view.interaction.selected().uri)
        self.wait(lambda: not view.get_mapped())
        self.wait(lambda: view.reading.future is None)
        restored = service.storage.cached_state(self.account.did, "following")
        self.assertEqual(restored.bookmark.uri, bookmark.uri)
        self.assertAlmostEqual(restored.bookmark.offset, bookmark.offset, delta=3)

    def test_profile_pager_request_uses_request_ownership_not_its_loading_presentation(self):
        from dataclasses import replace

        from skyloom.domain import Page

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        self.window.is_active = lambda: False
        calls = []

        async def author_feed(_actor, cursor=None, feed_filter="posts_no_replies"):
            calls.append(cursor)
            post = replace(
                self.app.service.posts[0], uri=f"at://did:example:paging/post/{len(calls)}"
            )
            return Page((post,), "second" if cursor is None else None)

        self.app.service.author_feed = author_feed
        self.window.profile(self.account.did)
        self.wait(lambda: not self.window.page_requests)
        page = self.window.nav.get_visible_page()
        view = page.content_view
        self.assertEqual(view.paging.cursor, "second")
        self.assertTrue(view.paging.request())
        self.wait(lambda: not self.window.page_requests)
        self.assertEqual(calls, [None, "second"])
        self.assertEqual(view.model.get_n_items(), 2)
        self.assertFalse(view.paging.busy)

    def test_search_retry_starts_a_new_owned_request_and_renders_its_results(self):
        from skyloom.domain import Page
        from skyloom.errors import UserError

        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.wait(lambda: not self.window.page_requests)
        calls = []

        async def search(_query, _people=False, _cursor=None):
            calls.append(True)
            if len(calls) == 1:
                raise UserError("Invented search failure")
            return Page((self.app.service.posts[0],))

        self.app.service.search = search
        self.window.search()
        page = self.window.nav.get_visible_page()
        view = page.content_view
        view.entry.set_text("invented")
        view.entry.emit("activate")
        self.wait(lambda: not self.window.page_requests)
        self.assertEqual(view.paging.error, "Invented search failure")
        view.status_action.emit("clicked")
        self.assertIn(page, self.window.page_requests)
        self.wait(lambda: not self.window.page_requests)
        self.assertEqual(len(calls), 2)
        self.assertEqual(view.model.get_n_items(), 1)
        self.assertFalse(view.paging.busy)
        self.assertFalse(view.paging.error)

    def test_fast_saved_session_never_maps_sign_in_or_flashes_a_spinner(self):
        self.open(self.restored_account)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.assertTrue(settle(self.window, 300))
        self.assertTrue(self.frames)
        self.assertNotIn("welcome", [page for page, _spinner in self.frames])
        self.assertFalse(any(spinning for _page, spinning in self.frames))
        self.assertFalse(self.window.handle.get_mapped())
        self.assertIsNone(self.window.stack.loading_source)

    def test_slow_saved_session_stays_neutral_then_shows_delayed_feedback(self):
        async def slow():
            await asyncio.sleep(0.6)
            return await self.restored_account()

        self.open(slow)
        self.assertEqual(self.window.stack.get_visible_child_name(), "pending")
        self.assertFalse(self.window.stack.spinner.get_spinning())
        self.wait(lambda: self.window.stack.spinner.get_spinning())
        self.assertEqual(self.window.stack.get_visible_child_name(), "pending")
        self.assertFalse(self.window.handle.get_mapped())
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.assertNotIn("welcome", [page for page, _spinner in self.frames])
        self.assertFalse(self.window.stack.spinner.get_spinning())
        self.assertIsNone(self.window.stack.loading_source)

    def test_missing_session_shows_sign_in_only_after_lookup_finishes(self):
        async def missing():
            await asyncio.sleep(0.1)

        Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
        self.open(missing)
        self.assertEqual(self.window.stack.get_visible_child_name(), "pending")
        self.assertFalse(self.window.handle.get_mapped())
        self.wait(lambda: self.window.stack.get_visible_child_name() == "welcome")
        self.assertTrue(settle(self.window))
        self.assertTrue(self.window.handle.get_mapped())
        self.assertFalse(self.window.retry_restore.get_visible())
        self.assertFalse(self.window.stack.get_transition_running())
        self.assertFalse(self.window.stack.spinner.get_spinning())

    def test_lookup_error_keeps_recovery_and_retry_uses_the_same_pending_gate(self):
        from skyloom.errors import UserError

        async def fail():
            raise UserError("Invented locked keyring")

        self.open(fail)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "recovery")
        self.assertEqual(self.window.login_feedback.get_text(), "Invented locked keyring")
        self.assertEqual(self.window.stack.error_page.get_description(), "Invented locked keyring")
        self.assertFalse(self.window.handle.get_mapped())
        self.app.service.restore = self.restored_account
        self.window.stack.retry_button.emit("clicked")
        self.assertEqual(self.window.stack.get_visible_child_name(), "pending")
        self.wait(lambda: self.window.stack.get_visible_child_name() == "shell")
        self.assertTrue(settle(self.window, 300))
        self.assertIsNone(self.window.stack.loading_source)
        self.assertFalse(self.window.stack.spinner.get_spinning())

    def test_failed_lookup_can_open_sign_in_explicitly(self):
        from skyloom.errors import UserError

        async def fail():
            raise UserError("Invented expired saved session")

        self.open(fail)
        self.wait(lambda: self.window.stack.get_visible_child_name() == "recovery")
        self.assertFalse(self.window.handle.get_mapped())
        self.window.stack.sign_in_button.emit("clicked")
        self.assertTrue(settle(self.window, 200))
        self.assertEqual(self.window.stack.get_visible_child_name(), "welcome")
        self.assertTrue(self.window.handle.get_mapped())
        self.assertTrue(self.window.login_button.get_sensitive())

    def test_closing_cancels_lookup_timer_and_late_callbacks(self):
        async def slow():
            await asyncio.sleep(0.6)
            return await self.restored_account()

        self.open(slow)
        request = self.window.request
        self.window.close()
        self.assertTrue(self.window.closing)
        self.assertTrue(request.cancelled())
        self.assertIsNone(self.window.stack.loading_source)
        self.assertFalse(self.window.stack.spinner.get_spinning())
        self.window.restored(self.account)
        self.window.restore_error("Invented late failure")
        self.assertEqual(self.window.stack.get_visible_child_name(), "pending")

    def test_native_crossfade_runs_only_with_animations_enabled(self):
        from skyloom.startup import StartupStack

        stack = StartupStack()
        stack.add_named(Gtk.Label(label="Invented ready state"), "ready")
        window = Adw.Window(title="Skyloom startup motion fixture", content=stack)
        self.addCleanup(window.destroy)
        self.addCleanup(stack.close)
        self.assertTrue(settle(window))
        stack.resolve("ready")
        self.assertTrue(stack.get_transition_running())
        self.wait(lambda: not stack.get_transition_running())
        Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
        stack.begin()
        self.assertFalse(stack.get_transition_running())
        stack.resolve("ready")
        self.assertFalse(stack.get_transition_running())
        self.assertIsNone(stack.loading_source)
