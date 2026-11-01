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
