"""Native GTK cursor/routing contracts; physical delivery is checked separately."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw, Gdk, Gio, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class KeyboardTests(unittest.TestCase):
    def pump(self, milliseconds=150):
        self.assertTrue(
            settle(
                self.window,
                milliseconds,
                lambda: self.view.position_tick is None and not self.view.check_pending,
            ),
            "Native test window did not finish rendering/positioning",
        )

    def setUp(self):
        from skyloom import APP_ID
        from skyloom.domain import Author, Post
        from skyloom.interactions import Interactions
        from skyloom.widgets import FeedView

        self.window = Adw.Window(
            title="Skyloom GTK controller fixture", default_width=800, default_height=500
        )
        window = self.window
        # Controller/animation eligibility is explicit; OS activation is not a unit-test input.
        # The inactive paging/peek cases below change this input and emit the native signal.
        window.is_active = lambda: True
        window.views, window.page_requests, window.mutations = [], {}, set()
        window.demo, window.generation, window.read_only = True, 0, False
        author = Author("did:example:keyboard", "keyboard.invalid", "Invented author")
        window.service = SimpleNamespace(account=author)
        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        window.settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        self.events = []
        window.thread = lambda uri: self.events.append(("open", uri))
        window.profile = lambda did: self.events.append(("profile", did))
        window.compose = lambda **kwargs: self.events.append(("compose", kwargs))
        window.mutate = lambda post, kind: self.events.append((kind, post.uri))
        window.toast = lambda text: self.events.append(("toast", text))
        window.overlay = Adw.ToastOverlay()
        window.nav = Adw.NavigationView()
        window.overlay.set_child(window.nav)
        window.set_content(window.overlay)
        window.interactions = Interactions(window)
        self.view = FeedView(window)
        self.page = Adw.NavigationPage.new(self.view, "Following")
        window.home_page = self.page
        window.nav.add(self.page)
        base = Post(
            "at://did:example:keyboard/app.bsky.feed.post/0",
            "cid",
            author,
            "Invented post",
            "2026-10-27T12:00:00Z",
        )
        self.posts = [
            replace(base, uri=base.uri.rsplit("/", 1)[0] + "/" + str(i)) for i in range(20)
        ]
        self.view.set_posts(self.posts)
        self.addCleanup(self.view.close)
        self.addCleanup(window.destroy)
        window.present()
        self.pump()
        # Establish native logical focus before deferred window activation can choose a default.
        self.view.list.grab_focus()
        self.view.store.set_selected(Gtk.INVALID_LIST_POSITION)
        self.pump()

    def test_manage_feeds_opens_while_menu_focus_is_closing(self):
        from unittest.mock import patch

        interaction = self.window.interactions
        links = []
        self.window.open_uri = links.append
        for context in ("list", "popup", "chrome"):
            with (
                self.subTest(context=context),
                patch.object(interaction, "context", return_value=context),
                patch.object(interaction, "dismiss_main_menu", return_value=False),
            ):
                self.assertTrue(interaction.command("manage-feeds"))
        self.assertEqual(links, ["https://bsky.app/settings/saved-feeds"] * 3)
        with patch.object(self.window, "get_visible_dialog", return_value=object()):
            self.assertFalse(interaction.command("manage-feeds"))
        self.assertEqual(len(links), 3)

    def key(self, key, modifiers=0):
        return self.window.interactions.key_pressed(None, key, key, modifiers)

    def release(self, key):
        self.window.interactions.key_released(None, key, key, Gdk.ModifierType(0))

    def test_registry_modifiers_and_native_text_undo_exclusion(self):
        from skyloom.keyboard import accelerators, match, parsed

        self.assertTrue(parsed())
        self.assertEqual(match(Gdk.KEY_J, Gdk.ModifierType.LOCK_MASK).command, "next")
        self.assertEqual(match(Gdk.KEY_R, Gdk.ModifierType.SHIFT_MASK).command, "repost")
        self.assertEqual(
            match(
                Gdk.KEY_question, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
            ).command,
            "shortcuts",
        )
        self.assertEqual(accelerators("undo"), [])
        self.assertEqual(accelerators("back"), [])
        self.assertIsNone(match(Gdk.KEY_j, Gdk.ModifierType.ALT_MASK))

    def test_movement_never_opens_or_mutates_and_activation_skips_footer(self):
        self.view.interaction.move("next")
        self.assertEqual(self.view.store.get_selected(), 0)
        self.view.interaction.move("next")
        self.assertEqual(self.view.store.get_selected(), 1)
        self.assertFalse(self.events)
        self.view.interaction.move("last")
        self.assertEqual(self.view.store.get_selected(), 19)
        self.window.interactions.command("open")
        self.assertEqual(self.events, [("open", self.posts[-1].uri)])
        self.view.activate_item(self.view.list, 20)
        self.assertEqual(len(self.events), 1)

    def test_down_from_real_adwaita_header_transfers_to_the_list(self):
        header = Adw.HeaderBar()
        action = Gtk.Button(label="Fixture header action")
        header.pack_end(action)
        self.view.prepend(header)
        action.grab_focus()
        self.pump()
        self.assertEqual(self.window.interactions.context(), "chrome")
        self.assertTrue(self.key(Gdk.KEY_Down))
        self.assertEqual(self.view.store.get_selected(), 0)
        self.pump()
        self.assertTrue(
            self.window.get_focus().is_ancestor(self.view.list),
            "Selecting from the header must transfer real GTK focus to the list",
        )
        self.assertFalse(self.events)

    def test_cursor_survives_reaction_rebind_and_prepended_posts(self):
        self.view.interaction.select(5)
        self.view.update_post(replace(self.posts[5], likes=1))
        self.assertEqual(self.view.interaction.selected().uri, self.posts[5].uri)
        earlier = replace(self.posts[0], uri="at://did:example:keyboard/app.bsky.feed.post/new")
        self.view.set_posts([earlier, *self.posts])
        self.assertEqual(self.view.store.get_selected(), 6)
        self.assertEqual(self.view.interaction.selected().uri, self.posts[5].uri)

    def test_show_new_reuses_rows_patches_counters_and_settles_at_top(self):
        objects = [self.view.model.get_item(i) for i in range(len(self.posts))]
        row = next(row for row in self.view.rows if row._value == self.posts[0])
        child = row.get_first_child()
        changes = []
        self.view.model.connect("items-changed", lambda _m, *args: changes.append(args))
        updated = replace(self.posts[0], likes=7, like_uri="invented-like")
        self.view.update_post(updated)
        self.assertIs(self.view.model.get_item(0), objects[0])
        self.assertIs(row.get_first_child(), child)
        self.assertEqual(row.post.likes, 7)
        self.assertIn("7", row.action_buttons[2].count.get_label())
        self.assertFalse(changes)
        activated = []
        self.window.mutate = lambda post, kind: activated.append((post.like_uri, kind))
        row.action_buttons[2].emit("clicked")
        self.assertEqual(activated, [("invented-like", "like")])
        self.view.interaction.move("last")
        self.pump()
        self.assertGreater(self.view.scroll.get_vadjustment().get_value(), 0)
        new = replace(self.posts[0], uri=self.posts[0].uri + "-new")
        self.view.offer_update(
            "1 new post", lambda: self.view.show_latest([new, updated, *self.posts[1:]], {new.uri})
        )
        self.pump()
        self.view.apply_update()
        self.assertTrue(settle(self.window, 350, lambda: self.view.arrival_tick is None))
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)
        self.assertEqual(self.view.interaction.selected().uri, new.uri)
        self.assertEqual(changes, [(0, 0, 1)])
        for i, original in enumerate(objects):
            self.assertIs(self.view.model.get_item(i + 1), original)
        self.assertTrue(settle(self.window, 220))
        self.assertFalse(self.view.reveal_rows)
        self.assertTrue(all(row.get_opacity() == 1 for row in self.view.rows))

    def test_refresh_at_top_does_not_offer_undo_for_data_or_selection_changes(self):
        from skyloom.domain import Page, Pager
        from skyloom.window import Window

        self.window.feed_views = {"following": self.view}
        self.window.pagers = {"following": Pager(list(self.posts), "tail")}
        self.window.load_feed = lambda *_args, **_kwargs: None
        self.view.interaction.select(3, focus=False)
        self.assertTrue(self.view.interaction.at_top())
        new = replace(self.posts[0], uri=self.posts[0].uri + "-new")
        for posts in (self.posts, [new, *self.posts], [replace(new, likes=7), *self.posts]):
            Window.show_feed_update(self.window, "following", Page(tuple(posts), "head"))
            self.assertTrue(settle(self.window, 350, lambda: self.view.arrival_tick is None))
            self.assertTrue(self.view.interaction.at_top())
            self.assertIsNone(self.window.interactions.undo_action)
            self.assertIsNone(self.window.interactions.undo_toast)
        self.assertEqual(self.window.pagers["following"].posts[0].likes, 7)

    def test_noop_top_and_unrestorable_position_keep_existing_undo(self):
        from skyloom.list_state import ListPlace

        controller = self.window.interactions
        controller.offer_undo("Reaction changed", lambda: None)
        pending, toast = controller.undo_action, controller.undo_toast
        self.assertTrue(controller.top())
        self.assertIs(controller.undo_action, pending)
        self.assertIs(controller.undo_toast, toast)
        for place in (None, ListPlace("missing-post", 0)):
            self.assertFalse(controller.offer_position_undo("Moved to top", self.view, place))
            self.assertIs(controller.undo_action, pending)
        self.view.interaction.move("last")
        self.pump()
        self.assertTrue(controller.top())
        self.pump()
        self.assertEqual(controller.undo_toast.get_title(), "Moved to top")
        jump = controller.undo_action
        self.assertTrue(controller.top())
        self.assertIs(controller.undo_action, jump)

    def test_show_and_undo_preserve_history_cursor_position_and_local_reactions(self):
        from skyloom.domain import Page, Pager
        from skyloom.window import Window

        pager = Pager()
        pager.merge(Page(tuple(self.posts[:10]), "older"))
        pager.merge(Page(tuple(self.posts[10:]), "oldest"))
        self.window.feed_views = {"following": self.view}
        self.window.pagers = {"following": pager}
        self.window.load_feed = lambda *_args, **_kwargs: None
        self.window.show_feed_update = lambda *args: Window.show_feed_update(self.window, *args)
        self.view.paging.complete("oldest", 20)
        self.view.offer_update("1 new post", lambda: None)
        self.pump(350)
        self.view.interaction.move("last")
        self.pump()
        place = self.view.interaction.capture()
        baseline = {post.uri: post for post in self.posts}
        liked = replace(self.posts[0], likes=1, like_uri="local-like")
        pager.posts[0] = liked
        self.view.update_post(liked)
        new = replace(self.posts[0], uri=self.posts[0].uri + "-new")
        self.window.show_feed_update("following", Page((new, *self.posts[:9]), "head"), baseline)
        self.assertTrue(settle(self.window, 350, lambda: self.view.arrival_tick is None))
        refreshed = self.window.pagers["following"]
        self.assertEqual(self.window.interactions.undo_toast.get_title(), "Moved to top")
        self.assertEqual(refreshed.cursor, "oldest")
        self.assertEqual(len(refreshed.posts), 21)
        self.assertEqual(refreshed.posts[1], liked)
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)
        reacted = replace(refreshed.posts[2], reposts=1, repost_uri="local-repost")
        refreshed.posts[2] = reacted
        self.view.update_post(reacted)
        self.assertTrue(self.window.interactions.undo())
        self.pump()
        restored = self.window.pagers["following"]
        self.assertEqual(restored.cursor, "oldest")
        self.assertEqual(len(restored.posts), 21)
        self.assertEqual(restored.posts[:3], [new, liked, reacted])
        self.assertEqual(self.view.interaction.capture().key, place.key)
        self.assertAlmostEqual(self.view.interaction.capture().offset, place.offset, delta=3)
        self.assertFalse(bool(self.view.pending_update))

    def test_background_arrivals_are_present_keep_order_anchor_focus_and_identity(self):
        from skyloom.domain import Page, Pager
        from skyloom.window import Window

        self.window.feed_views = {"following": self.view}
        self.window.pagers = {"following": Pager(list(self.posts), "tail")}
        self.window.load_feed = lambda *_args, **_kwargs: None
        self.view.interaction.move("last")
        self.pump()
        place = self.view.interaction.capture()
        focus = self.window.get_focus()
        objects = {p.uri: self.view.model.get_item(i) for i, p in enumerate(self.posts)}
        new = replace(self.posts[0], uri=self.posts[0].uri + "-new")
        Window.show_feed_update(
            self.window,
            "following",
            Page((new, self.posts[8], self.posts[0]), "head"),
            automatic=True,
        )
        self.pump()
        current = self.window.pagers["following"]
        self.assertEqual(current.posts, [new, *self.posts])
        self.assertEqual(current.cursor, "tail")
        self.assertIs(self.window.get_focus(), focus)
        self.assertEqual(self.view.interaction.capture().key, place.key)
        self.assertAlmostEqual(self.view.interaction.capture().offset, place.offset, delta=3)
        for index, post in enumerate(self.posts, 1):
            self.assertIs(self.view.model.get_item(index), objects[post.uri])
        self.assertEqual(self.view.update_notice.button_label, "Go to top")
        self.assertTrue(self.view.apply_update())
        self.pump()
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)
        self.assertTrue(self.window.interactions.undo())
        self.pump()
        self.assertEqual(self.view.interaction.capture().key, place.key)
        self.assertEqual(current.posts, [new, *self.posts])

    def test_feed_gap_has_a_native_retry_and_is_not_a_post_cursor_stop(self):
        from skyloom.feed_state import FeedGap

        before = self.posts[1].uri
        gap = FeedGap(before, "real-cursor", error="Invented connection failure")
        self.window.load_feed_gap = lambda view, uri: self.events.append(("gap", uri))
        self.view.set_posts([self.posts[0], gap, *self.posts[1:]])
        self.pump()
        self.assertNotIn(1, self.view.interaction.positions())
        row = next(row for row in self.view.rows if isinstance(row._value, FeedGap))
        retry = row.get_last_child()
        self.assertIsInstance(retry, Gtk.Button)
        self.assertTrue(retry.get_sensitive())
        retry.emit("clicked")
        self.assertIn(("gap", before), self.events)
        self.view.set_posts([self.posts[0], replace(gap, busy=True), *self.posts[1:]])
        self.pump()
        row = next(row for row in self.view.rows if isinstance(row._value, FeedGap))
        self.assertFalse(row.get_last_child().get_sensitive())

    def test_gap_loading_preserves_reading_position_through_retry_and_insertion(self):
        from unittest.mock import patch

        from skyloom.domain import Page, Pager
        from skyloom.feed_coordination import FeedCoordination
        from skyloom.reading import ReadingSession
        from skyloom.window import Window

        before = self.posts[10].uri
        pager = Pager(list(self.posts), "tail", gaps={before: "between"})
        self.window.pagers = {"following": pager}
        self.window.feed_page = lambda *_: None
        self.view.feed = FeedCoordination(self.window, self.view, "following")
        self.view.reading = ReadingSession(self.window, self.view, "following")
        self.view.set_posts(pager.projected())
        self.view.list.scroll_to(10, Gtk.ListScrollFlags(0), None)
        self.pump()
        gap_row = next(
            row for row in self.view.rows if getattr(row._value, "uri", None) == "gap:" + before
        )
        gap_row.get_last_child().grab_focus()
        self.pump()
        adjustment = self.view.scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_value() + 45)
        self.pump()
        place = self.view.reading.capture()
        self.assertIsNotNone(place)
        self.assertGreater(adjustment.get_value(), adjustment.get_page_size())

        def unchanged():
            self.pump()
            current = self.view.reading.capture()
            self.assertEqual(current.uri, place.uri)
            self.assertAlmostEqual(current.offset, place.offset, delta=3)

        with patch("skyloom.window.submit_request") as request:
            Window.load_feed_gap(self.window, self.view, before)
            unchanged()
            request.call_args.args[4]("Invented connection failure")
            unchanged()
            Window.load_feed_gap(self.window, self.view, before)
            unchanged()
            inserted = replace(self.posts[0], uri=self.posts[0].uri + "-between")
            request.call_args.args[3](Page((inserted, self.posts[10]), None))
            unchanged()
            self.assertIn(inserted, self.window.pagers["following"].posts)

    def test_top_fetches_evicted_head_and_supersedes_gap_request(self):
        from unittest.mock import Mock

        from skyloom.domain import Page, Pager
        from skyloom.feed_coordination import FeedCoordination
        from skyloom.feed_state import FeedGap
        from skyloom.reading import ReadingSession
        from skyloom.window import Window

        for leading_gap, known_head in ((False, False), (True, False), (False, True)):
            with self.subTest(leading_gap=leading_gap, known_head=known_head):
                before = self.posts[0].uri
                pager = Pager(
                    list(self.posts),
                    "tail",
                    page_starts={before: None if known_head else "older-page"},
                    gaps={before: "between"} if leading_gap else {},
                )
                self.window.pagers = {"following": pager}
                self.window.feed_views = {"following": self.view}
                self.window.feed_id = "following"
                self.window.auto_feeds = set()
                self.window.refresh = lambda: Window.refresh(self.window)
                self.window.feed_view = lambda: self.view
                self.window.load_feed = Mock()
                self.view.feed = FeedCoordination(self.window, self.view, "following")
                self.view.reading = ReadingSession(self.window, self.view, "following")
                if leading_gap:
                    self.view.feed.gap_states[before] = FeedGap(before, "between", busy=True)
                self.view.set_posts(pager.projected(self.view.feed.gap_states))
                self.pump()
                if not leading_gap:
                    self.view.interaction.move("last")
                    self.pump()
                place = self.view.interaction.capture()
                pending = Mock()
                self.window.page_requests["feed:following"] = pending
                self.assertTrue(self.window.interactions.top())
                pending.cancel.assert_called_once()
                self.window.load_feed.assert_called_once_with("following", reset=True)
                self.assertNotIn(before, self.view.feed.gap_states)
                self.pump()
                # No cascade of automatic cursor requests from a leading gap.
                self.assertFalse(self.view.feed.autoload_gap())
                new = replace(self.posts[0], uri=self.posts[0].uri + "-newest")
                Window.show_feed_update(self.window, "following", Page((new,), "head"))
                self.assertTrue(settle(self.window, 350, lambda: self.view.arrival_tick is None))
                self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)
                self.assertEqual(self.view.interaction.capture().key, new.uri)
                if not leading_gap:
                    self.assertTrue(self.window.interactions.undo())
                    self.pump()
                    restored = self.view.interaction.capture()
                    self.assertEqual(restored.key, place.key)
                    self.assertAlmostEqual(restored.offset, place.offset, delta=3)

    def test_stale_undo_toast_cannot_execute_a_newer_action(self):
        calls = []
        first = self.window.interactions.offer_undo("First", lambda: calls.append("first"))
        second = self.window.interactions.offer_undo("Second", lambda: calls.append("second"))
        first.emit("button-clicked")
        self.assertEqual(calls, [])
        second.emit("button-clicked")
        self.assertEqual(calls, ["second"])
        self.assertFalse(self.window.interactions.undo())

    def test_position_toast_is_brief_and_dismissed_when_leaving_window(self):
        calls = []
        interactions = self.window.interactions
        toast = interactions.offer_undo("Moved to top", lambda: calls.append(True), self.view)
        self.assertEqual(toast.get_timeout(), 2)
        self.window.is_active = lambda: False
        interactions.activity_changed()
        self.assertIsNone(interactions.undo_toast)
        self.assertIsNotNone(interactions.undo_action)
        self.assertTrue(interactions.undo())
        self.assertEqual(calls, [True])

    def test_reaction_undo_keeps_its_longer_timeout(self):
        toast = self.window.interactions.offer_undo("Liked", lambda: None)
        self.assertEqual(toast.get_timeout(), 5)

    def test_header_restore_yields_to_input_without_a_reading_session(self):
        self.view.set_header(Gtk.Box(height_request=300))
        self.pump()
        adjustment = self.view.scroll.get_vadjustment()
        adjustment.set_value(10)
        self.pump()
        place = self.view.interaction.capture()
        self.assertIs(place.key, self.view.content_header)
        self.assertTrue(self.view.interaction.restore(place))
        self.view.user_input()
        self.assertIsNone(self.view.position_tick)
        adjustment.set_value(400)
        self.pump()
        self.assertAlmostEqual(adjustment.get_value(), 400, delta=1)

    def test_a_small_visible_row_fragment_keeps_its_exact_offset_after_insertion(self):
        provider = Gtk.CssProvider()
        provider.load_from_string(".offset-padding-case .post-tile { padding: 18px; }")
        display = self.window.get_display()
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.addCleanup(Gtk.StyleContext.remove_provider_for_display, display, provider)
        self.view.add_css_class("offset-padding-case")
        self.pump()
        first = next(
            row
            for _y, row in self.view.interaction.visible_rows()
            if row._value.uri == self.posts[0].uri
        )
        valid, bounds = first.compute_bounds(self.view.scroll)
        self.assertTrue(valid)
        adjustment = self.view.scroll.get_vadjustment()
        adjustment.set_value(bounds.origin.y + bounds.size.height - 11)
        self.pump()
        place = self.view.interaction.capture()
        self.assertEqual(place.key, self.posts[0].uri)
        new = replace(self.posts[0], uri=self.posts[0].uri + "-new")
        self.view.set_posts([new, *self.posts])
        self.assertTrue(self.view.interaction.restore(place))
        self.pump()
        restored = self.view.interaction.capture()
        self.assertEqual(restored.key, place.key)
        self.assertAlmostEqual(restored.offset, place.offset, delta=3)

    def test_distant_top_jump_lands_directly_and_preserves_undo_anchor(self):
        posts = [replace(self.posts[0], uri=f"at://invented/long/{i}") for i in range(60)]
        self.view.set_posts(posts)
        self.view.interaction.select(45)
        self.pump()
        adjustment = self.view.scroll.get_vadjustment()
        self.assertGreater(adjustment.get_value(), adjustment.get_page_size())
        before = self.view.interaction.capture()
        observed = []
        signal = adjustment.connect("value-changed", lambda adj: observed.append(adj.get_value()))
        try:
            place = self.view.interaction.top()
            self.pump()
        finally:
            adjustment.disconnect(signal)
        self.assertEqual(place.key, before.key)
        self.assertTrue(observed)
        self.assertTrue(all(value <= 1 for value in observed), observed)
        self.assertLessEqual(adjustment.get_value(), 1)
        self.assertEqual(self.view.top_peek.offset, 0)
        self.assertTrue(self.view.interaction.restore(place))
        self.pump()
        restored = self.view.interaction.capture()
        self.assertEqual(restored.key, place.key)
        self.assertAlmostEqual(restored.offset, place.offset, delta=3)

    def test_restore_correction_yields_to_new_keyboard_input(self):
        self.view.interaction.move("last")
        self.pump()
        place = self.view.interaction.capture()
        self.view.interaction.top()
        self.pump()
        self.assertTrue(self.view.interaction.restore(place))
        self.view.interaction.move("first")
        self.pump()
        self.assertEqual(self.view.interaction.selected().uri, self.posts[0].uri)
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)

    def test_arrival_cancel_and_reduced_motion_leave_no_invisible_rows(self):
        settings = Gtk.Settings.get_default()
        original = settings.get_property("gtk-enable-animations")
        self.addCleanup(settings.set_property, "gtk-enable-animations", original)
        settings.set_property("gtk-enable-animations", False)
        new = replace(self.posts[0], uri=self.posts[0].uri + "-new")
        self.view.show_latest([new, *self.posts], {new.uri})
        self.assertTrue(settle(self.window, 150, lambda: self.view.arrival_tick is None))
        self.assertFalse(self.view.reveal_rows)
        self.assertTrue(all(row.get_opacity() == 1 for row in self.view.rows))
        settings.set_property("gtk-enable-animations", True)
        newer = replace(new, uri=new.uri + "er")
        self.view.show_latest([newer, new, *self.posts], {newer.uri})
        self.view.cancel_arrivals()
        self.assertIsNone(self.view.arrival_tick)
        self.assertTrue(self.view.paging_ready)
        self.assertTrue(settle(self.window, 250))
        self.assertFalse(self.view.reveal_rows)
        self.assertTrue(all(row.get_opacity() == 1 for row in self.view.rows))

    def test_background_paging_waits_for_activation_without_a_polling_loop(self):
        active = [False]
        self.window.is_active = lambda: active[0]
        pages = []
        self.view.load_more = lambda: pages.append(True)
        self.view.paging.complete("invented-next-page", len(self.posts))
        self.view.interaction.move("last")
        self.pump()
        self.assertFalse(pages)
        self.assertFalse(self.view.check_pending)
        active[0] = True
        self.window.notify("is-active")
        self.pump()
        self.assertEqual(pages, [True])

    def test_text_fields_and_modal_dialogs_keep_single_keys_and_undo(self):
        entry = Gtk.Entry()
        self.view.prepend(entry)
        entry.grab_focus()
        self.pump()
        self.assertEqual(self.window.interactions.context(), "text")
        self.assertFalse(self.key(Gdk.KEY_j))
        self.assertFalse(self.key(Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK))
        self.assertFalse(self.events)
        dialog = Adw.PreferencesDialog()
        dialog.present(self.window)
        self.pump()
        self.assertFalse(self.key(Gdk.KEY_l))
        self.assertFalse(self.window.interactions.command("refresh"))
        dialog.close()
        self.pump()

    def test_held_enter_activates_once_until_key_release(self):
        self.view.interaction.select(0)
        self.pump()
        self.assertTrue(self.key(Gdk.KEY_Return))
        self.assertTrue(self.key(Gdk.KEY_Return))
        self.assertEqual(len(self.events), 1)
        self.release(Gdk.KEY_Return)
        self.assertTrue(self.key(Gdk.KEY_Return))
        self.assertEqual(len(self.events), 2)

    def test_top_jump_and_undo_restore_stable_reading_position(self):
        self.view.interaction.move("last")
        self.pump()
        before = self.view.scroll.get_vadjustment().get_value()
        self.assertGreater(before, 0)
        self.assertTrue(self.window.interactions.top())
        self.pump()
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)
        self.assertTrue(self.window.interactions.undo())
        self.pump()
        self.assertAlmostEqual(self.view.scroll.get_vadjustment().get_value(), before, delta=3)

    def test_unchanged_connectivity_does_not_requeue_lists_but_cost_preference_does(self):
        from skyloom.refresh import Connection

        interactions = self.window.interactions
        queued = []
        self.view.queue_check = lambda: queued.append(True)
        interactions.connection_changed(Connection(metered=True))
        self.assertEqual(len(queued), 1)
        for _ in range(10):
            interactions.connection_changed(Connection(metered=True))
        self.assertEqual(len(queued), 1)
        self.window.settings.set_boolean("use-metered", True)
        interactions.connection_changed(Connection(metered=True))
        self.assertEqual(len(queued), 2)

    def test_conversation_relationship_keys_and_return_jump_keep_native_navigation(self):
        from skyloom.conversation import Conversation
        from skyloom.conversation_view import ConversationView

        self.view.close()
        self.page.set_child(None)
        posts = [
            replace(post, parent=(self.posts[i - 1].uri, "cid") if i else None)
            for i, post in enumerate(self.posts)
        ]
        state = Conversation(posts[4].uri, posts=posts)
        state.parents = {p.uri: p.parent[0] for p in posts if p.parent}
        self.view = ConversationView(self.window, state, lambda **_: None)
        self.page.set_child(self.view)
        self.view.sync()
        self.pump()
        self.view.focus_post(state.anchor)
        self.pump()
        self.assertTrue(self.key(Gdk.KEY_Up, Gdk.ModifierType.ALT_MASK))
        self.release(Gdk.KEY_Up)
        self.assertEqual(self.view.interaction.selected().uri, posts[3].uri)
        self.assertTrue(self.key(Gdk.KEY_Down, Gdk.ModifierType.ALT_MASK))
        self.release(Gdk.KEY_Down)
        self.assertEqual(self.view.interaction.selected().uri, state.anchor)
        self.view.interaction.move("last")
        self.pump()
        before = self.view.scroll.get_vadjustment().get_value()
        self.assertTrue(self.view.return_button.get_visible())
        self.view.return_button.emit("clicked")
        self.pump()
        self.assertEqual(self.view.interaction.selected().uri, state.anchor)
        self.assertTrue(self.window.interactions.undo())
        self.pump()
        self.assertAlmostEqual(self.view.scroll.get_vadjustment().get_value(), before, delta=3)

    def test_update_toast_does_not_resize_or_reposition_and_keyboard_survives_dismissal(self):
        self.view.interaction.move("last")
        self.pump()
        adjustment = self.view.scroll.get_vadjustment()
        before = (adjustment.get_value(), adjustment.get_page_size(), self.view.scroll.get_height())
        objects = [self.view.model.get_item(i) for i in range(self.view.model.get_n_items())]
        applied = []
        self.view.offer_update("2 new posts", lambda: applied.append("latest"))
        self.pump()
        toast = self.view.update_notice.toast
        self.assertIsInstance(toast, Adw.Toast)
        self.assertEqual(toast.get_title(), "2 new posts")
        self.assertEqual(toast.get_button_label(), "Show")
        self.assertEqual(toast.get_timeout(), 5)
        self.assertEqual(
            (adjustment.get_value(), adjustment.get_page_size(), self.view.scroll.get_height()),
            before,
        )
        self.assertTrue(all(self.view.model.get_item(i) is obj for i, obj in enumerate(objects)))
        self.view.queue_check()
        self.pump()
        self.assertIs(self.view.update_notice.toast, toast)
        toast.dismiss()
        self.pump()
        self.assertIsNone(self.view.update_notice.toast)
        self.assertTrue(self.view.pending_update)
        self.assertTrue(
            self.key(Gdk.KEY_Home, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
        )
        self.release(Gdk.KEY_Home)
        self.assertEqual(applied, ["latest"])
        self.assertFalse(self.view.pending_update)
        toast.emit("button-clicked")
        self.assertEqual(applied, ["latest"])

    def test_reaching_top_clears_arrival_notice_without_running_jump(self):
        from types import SimpleNamespace

        adjustment = self.view.scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        self.assertGreater(adjustment.get_value(), 0)
        applied = []
        self.view.feed = SimpleNamespace(unseen={"invented-new-post"})
        self.view.offer_update(
            "1 new post", lambda: applied.append("jump"), button_label="Go to top"
        )
        self.pump()
        toast = self.view.update_notice.toast
        self.assertIsNotNone(toast)
        adjustment.set_value(adjustment.get_lower())
        self.assertIsNone(self.view.pending_update)
        self.assertIsNone(self.view.update_notice.toast)
        self.assertFalse(self.view.feed.unseen)
        toast.emit("button-clicked")
        self.assertFalse(applied)
        self.view.feed = None

    def test_update_notice_replacement_page_scope_and_close_reject_stale_actions(self):
        applied = []
        self.view.offer_update("1 new post", lambda: applied.append("old"))
        self.pump()
        old = self.view.update_notice.toast
        self.view.offer_update("2 new posts", lambda: applied.append("new"))
        self.pump()
        old.emit("button-clicked")
        self.assertFalse(applied)
        current = self.view.update_notice.toast
        page = Adw.NavigationPage.new(Gtk.Label(label="Another invented page"), "Other")
        self.window.nav.push(page)
        self.assertTrue(settle(self.window, 350))
        self.assertIsNone(self.view.update_notice.toast)
        current.emit("button-clicked")
        self.assertFalse(applied)
        self.window.nav.pop()
        self.pump(350)
        self.assertIsNone(self.view.update_notice.toast)
        self.assertTrue(self.view.pending_update)
        self.view.offer_update("3 new posts", lambda: applied.append("newest"))
        self.pump()
        current = self.view.update_notice.toast
        self.assertIsInstance(current, Adw.Toast)
        self.view.close()
        self.assertIsNone(self.view.update_notice.toast)
        current.emit("button-clicked")
        self.assertFalse(applied)

    def test_same_update_batch_does_not_replay_but_its_action_stays_current(self):
        applied = []
        self.view.offer_update("3 new posts", lambda: applied.append("old"), revision=("a",))
        self.pump()
        toast = self.view.update_notice.toast
        self.assertIsInstance(toast, Adw.Toast)
        self.view.offer_update("3 new posts", lambda: applied.append("latest"), revision=("a",))
        self.pump()
        self.assertIs(self.view.update_notice.toast, toast)
        toast.dismiss()
        self.pump()
        for _ in range(3):
            self.view.update_notice.unmap()
            self.view.offer_update("3 new posts", lambda: applied.append("latest"), revision=("a",))
            self.pump()
            self.assertIsNone(self.view.update_notice.toast)
        # A distinct batch with the same count/title must still announce before
        # the previous pending action has been consumed.
        self.view.offer_update("3 new posts", lambda: applied.append("next"), revision=("b",))
        self.pump()
        current = self.view.update_notice.toast
        self.assertIsInstance(current, Adw.Toast)
        toast.emit("button-clicked")
        self.assertEqual(applied, [])
        current.emit("button-clicked")
        self.assertEqual(applied, ["next"])
        self.view.offer_update("3 new posts", lambda: applied.append("stale"), revision=("c",))
        self.pump()
        current = self.view.update_notice.toast
        self.view.offer_update("3 new posts", lambda: applied.append("latest"), revision=("c",))
        self.pump()
        self.assertIs(self.view.update_notice.toast, current)
        current.emit("button-clicked")
        self.assertEqual(applied, ["next", "latest"])

    def test_unseen_update_waits_for_visibility_then_announces_only_once(self):
        self.view.offer_update("1 new post", lambda: None)
        self.view.update_notice.unmap()
        self.assertFalse(self.view.update_notice.announced)
        self.view.update_notice.schedule()
        self.pump()
        self.assertIsInstance(self.view.update_notice.toast, Adw.Toast)
        self.view.update_notice.unmap()
        self.view.update_notice.schedule()
        self.pump()
        self.assertTrue(self.view.update_notice.announced)
        self.assertIsNone(self.view.update_notice.toast)

    def enable_peek_motion(self):
        settings = Gtk.Settings.get_default()
        for name in ("gtk-enable-animations", "gtk-interface-reduced-motion"):
            self.addCleanup(settings.set_property, name, settings.get_property(name))
        settings.set_property("gtk-enable-animations", True)
        settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.NO_PREFERENCE)
        self.view.scroll.get_vadjustment().set_value(0)
        self.pump()
        return settings

    def test_top_peek_is_bounded_draw_only_and_wheel_events_are_not_consumed(self):
        self.enable_peek_motion()
        peek = self.view.top_peek
        adjustment = self.view.scroll.get_vadjustment()
        geometry = (adjustment.get_value(), adjustment.get_upper(), adjustment.get_page_size())
        objects = [self.view.model.get_item(i) for i in range(self.view.model.get_n_items())]
        self.assertFalse(
            peek.scrolled(SimpleNamespace(get_unit=lambda: Gdk.ScrollUnit.SURFACE), 0, -1)
        )
        self.assertIsNone(peek.queued)
        wheel = SimpleNamespace(get_unit=lambda: Gdk.ScrollUnit.WHEEL)
        for _ in range(20):
            self.assertFalse(peek.scrolled(wheel, 0, -1))
        self.assertIsNotNone(peek.queued)
        samples = []
        tick = peek.add_tick_callback(lambda *_: (samples.append(peek.offset), True)[1])
        try:
            self.pump(450)
        finally:
            peek.remove_tick_callback(tick)
        self.assertGreater(max(samples), 1)
        self.assertLess(max(samples), 24)
        self.assertTrue(peek.pulse())
        progress = peek.animation.get_value()
        peek.pulse()
        self.assertGreaterEqual(peek.animation.get_value(), progress)
        self.pump(400)
        self.assertEqual(peek.offset, 0)
        self.assertEqual(peek.animation.get_state(), Adw.AnimationState.FINISHED)
        self.assertEqual(
            (adjustment.get_value(), adjustment.get_upper(), adjustment.get_page_size()), geometry
        )
        self.assertTrue(all(self.view.model.get_item(i) is obj for i, obj in enumerate(objects)))

    def test_top_peek_noop_keys_motion_power_scrolling_and_close(self):
        from skyloom.refresh import Connection

        settings = self.enable_peek_motion()
        peek = self.view.top_peek
        self.view.interaction.select(0)
        self.assertTrue(self.key(Gdk.KEY_Up))
        self.release(Gdk.KEY_Up)
        self.assertEqual(peek.animation.get_state(), Adw.AnimationState.PLAYING)
        settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.REDUCE)
        self.assertEqual(peek.offset, 0)
        self.assertFalse(peek.pulse())
        settings.set_property("gtk-interface-reduced-motion", Gtk.ReducedMotion.NO_PREFERENCE)
        settings.set_property("gtk-enable-animations", False)
        self.assertFalse(peek.pulse())
        settings.set_property("gtk-enable-animations", True)
        self.window.interactions.connection = Connection(power_saver=True)
        self.assertFalse(peek.pulse())
        self.window.interactions.connection = Connection()
        self.assertTrue(peek.pulse())
        self.window.is_active = lambda: False
        self.window.notify("is-active")
        self.assertEqual(peek.offset, 0)
        self.assertFalse(peek.pulse())
        self.window.is_active = lambda: True
        self.window.notify("is-active")
        self.assertTrue(peek.pulse())
        self.view.scroll.get_vadjustment().set_value(40)
        self.assertEqual(peek.offset, 0)
        self.assertFalse(peek.pulse())
        self.view.scroll.get_vadjustment().set_value(0)
        self.assertTrue(peek.pulse())
        self.view.close()
        self.assertEqual(peek.offset, 0)
        self.assertIsNone(peek.animation)
        self.assertFalse(peek.pulse())

    def test_metered_paging_pauses_without_removing_manual_fallback(self):
        from skyloom.refresh import Connection

        self.window.automatic_pause_reason = self.window.interactions.automatic_reason
        self.window.interactions.connection = Connection(metered=True)
        calls = []
        self.view.load_more = lambda: calls.append(True)
        self.view.paging.complete("server-cursor", 1)
        self.view.scroll.get_vadjustment().set_value(100000)
        self.pump()
        self.assertFalse(calls)
        self.assertTrue(self.view.paging.request())
        self.assertEqual(calls, [True])

    def test_home_double_press_returns_to_head_after_native_focus_handoff(self):
        from unittest.mock import Mock

        from skyloom.domain import Page, Pager
        from skyloom.feed_coordination import FeedCoordination
        from skyloom.window import Window

        posts = [
            replace(
                self.posts[0],
                uri=f"at://invented/double-home/{i}",
                text="Invented varying-height post. " * (1 + i % 17),
            )
            for i in range(250)
        ]
        pager = Pager()
        pager.merge(Page(tuple(posts), "tail"), reset=True)
        self.window.pagers = {"following": pager}
        self.window.feed_views = {"following": self.view}
        self.window.feed_id = "following"
        self.window.auto_feeds = set()
        self.window.feed_view = lambda: self.view
        self.window.load_feed = Mock()
        self.window.refresh = lambda: Window.refresh(self.window)
        self.view.feed = FeedCoordination(self.window, self.view, "following")
        self.window.navigation = SimpleNamespace(reveal_content=lambda: None)
        self.view.set_posts(posts)
        self.view.interaction.select(225)
        self.pump()
        place = self.view.interaction.capture()
        button = Gtk.Button(label="Home fixture")
        controller = self.window.interactions.install_destination(button, "home")
        controller.emit("pressed", 1, 0.0, 0.0)
        self.window.interactions.navigate("home")
        controller.emit("pressed", 2, 0.0, 0.0)
        self.window.load_feed.assert_called_once_with("following", reset=True)
        self.pump()
        newest = replace(posts[0], uri="at://invented/double-home/newest")
        Window.show_feed_update(self.window, "following", Page((newest, *posts[:29]), "head"))
        self.assertTrue(settle(self.window, 350, lambda: self.view.arrival_tick is None))
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)
        self.assertEqual(self.view.interaction.capture().key, newest.uri)
        self.assertTrue(self.window.interactions.undo())
        self.pump()
        restored = self.view.interaction.capture()
        self.assertEqual(restored.key, place.key)
        self.assertAlmostEqual(restored.offset, place.offset, delta=3)

    def test_double_press_only_jumps_when_destination_was_already_active(self):
        button = Gtk.Button(label="Home fixture")
        controller = self.window.interactions.install_destination(button, "home")
        jumps = []
        self.window.interactions.top = lambda: jumps.append(True)
        controller.emit("pressed", 1, 0.0, 0.0)
        controller.emit("pressed", 2, 0.0, 0.0)
        self.assertEqual(jumps, [True])
        other = Adw.NavigationPage.new(Gtk.Box(), "Search")
        self.window.nav.push(other)
        controller.emit("pressed", 1, 0.0, 0.0)
        self.window.nav.pop()
        controller.emit("pressed", 2, 0.0, 0.0)
        self.assertEqual(jumps, [True], "Arriving at Home must not also erase its reading position")

    def test_pointer_cursor_and_keyboard_focus_interoperate_without_stealing_child_focus(self):
        self.view.interaction.select(0)
        self.pump()
        original = self.window.get_focus()
        row = next(row for row in self.view.rows if row._value == self.posts[1])
        valid, bounds = row.compute_bounds(self.view.list)
        self.assertTrue(valid)
        self.view.interaction.pointer_pressed(None, 1, bounds.origin.x + 10, bounds.origin.y + 10)
        self.assertEqual(self.view.interaction.selected().uri, self.posts[1].uri)
        self.assertIs(self.window.get_focus(), original)
        self.assertTrue(self.view.interaction.move("next"))
        self.pump()
        self.assertEqual(self.view.interaction.selected().uri, self.posts[2].uri)
        row = next(row for row in self.view.rows if row._value == self.posts[2])
        native_row = row.get_parent().get_parent()
        self.assertTrue(native_row.is_focus())
        row.action_buttons[2].grab_focus()
        self.assertFalse(native_row.is_focus())
        self.assertTrue(row.action_buttons[2].is_focus())
        self.assertEqual(self.window.interactions.context(), "control")

    def test_single_home_press_never_scrolls_or_refreshes_during_focus_handoff(self):
        from unittest.mock import Mock

        button = Gtk.Button(label="Home fixture")
        self.page.set_child(None)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.pack_start(button)
        toolbar.add_top_bar(header)
        toolbar.set_content(self.view)
        self.page.set_child(toolbar)
        self.window.navigation = SimpleNamespace(reveal_content=lambda: None)
        self.window.refresh = Mock()
        button.connect("clicked", lambda *_: self.window.interactions.navigate("home"))
        controller = self.window.interactions.install_destination(button, "home")
        self.pump()
        self.view.interaction.select(0)
        self.view.scroll.get_vadjustment().set_value(1800)
        self.pump()
        place = self.view.interaction.capture()
        adjustment = self.view.scroll.get_vadjustment()
        before = adjustment.get_value()
        observed = []
        signal = adjustment.connect("value-changed", lambda adj: observed.append(adj.get_value()))
        try:
            controller.emit("pressed", 1, 0.0, 0.0)
            button.grab_focus()
            button.emit("clicked")
            self.pump(350)
        finally:
            adjustment.disconnect(signal)
        self.window.refresh.assert_not_called()
        self.assertTrue(all(abs(value - before) <= 3 for value in observed), observed)
        restored = self.view.interaction.capture()
        self.assertEqual(restored.key, place.key)
        self.assertAlmostEqual(restored.offset, place.offset, delta=3)
        self.assertTrue(self.view.interaction.move("next"))

    def test_active_destination_focus_preserves_mouse_scrolled_reading_position(self):
        self.view.interaction.select(0)
        self.pump()
        adjustment = self.view.scroll.get_vadjustment()
        adjustment.set_value(100000)
        self.pump()
        before = adjustment.get_value()
        self.assertGreater(before, 0)
        self.view.interaction.focus(preserve_position=True)
        self.pump()
        self.assertAlmostEqual(adjustment.get_value(), before, delta=3)
        self.assertNotEqual(self.view.store.get_selected(), 0)
        # A fast second press must supersede the first press's queued position correction.
        self.view.interaction.focus(preserve_position=True)
        self.window.interactions.top()
        self.pump()
        self.assertLessEqual(adjustment.get_value(), 1)
        self.assertTrue(self.window.interactions.undo())
        self.pump()
        self.assertAlmostEqual(adjustment.get_value(), before, delta=3)

    def test_scrolling_intro_preserves_post_indices_empty_state_and_native_controls(self):
        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        entry = Gtk.SearchEntry()
        intro.append(entry)
        intro.append(Gtk.Label(label="Invented page introduction", height_request=250))
        self.view.set_header(intro)
        self.view.set_posts(self.posts, reset=True)
        self.pump(250)
        adjustment = self.view.scroll.get_vadjustment()
        self.assertEqual(self.view.scroll.get_child(), self.view.list)
        self.assertTrue(intro.is_ancestor(self.view.list))
        self.assertLessEqual(adjustment.get_value(), 1)
        self.assertEqual(self.view.interaction.positions()[0], 0)
        self.assertEqual(self.view.flat.get_n_items(), len(self.posts) + 1)
        entry.set_text("invented search")
        entry.grab_focus()
        self.pump()
        self.view.set_posts([])
        self.pump()
        self.assertTrue(self.view.header_visible())
        self.assertTrue(entry.get_mapped())
        self.assertTrue(self.window.get_focus().is_ancestor(entry))
        self.assertEqual(entry.get_text(), "invented search")
        self.assertEqual(self.view.flat.get_n_items(), 1)
        self.view.set_posts(self.posts, reset=True)
        self.pump(250)
        self.assertTrue(self.view.header_visible())
        self.assertEqual(entry.get_text(), "invented search")
        self.view.interaction.select(0)
        self.window.interactions.command("open")
        self.assertEqual(self.events, [("open", self.posts[0].uri)])

    def test_recycled_search_header_can_be_focused_from_deep_results(self):
        fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        entry = Gtk.SearchEntry()
        fields.append(entry)
        fields.append(Gtk.Label(label="Search filters", height_request=180))
        self.view.set_header(fields)
        self.view.set_posts(self.posts, reset=True)
        self.pump(250)
        self.view.interaction.move("last")
        self.pump()
        self.assertFalse(self.view.header_visible())
        self.view.focus_header(entry)
        self.pump(300)
        self.assertTrue(self.view.header_visible())
        self.assertTrue(self.window.get_focus().is_ancestor(entry))
        self.assertLessEqual(self.view.scroll.get_vadjustment().get_value(), 1)

    def test_compact_profile_title_tracks_shared_scroll_and_returns_after_top_undo(self):
        from skyloom.profile_header import ProfileTitle

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        self.page.set_child(None)
        toolbar.set_content(self.view)
        self.page.set_child(toolbar)
        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        identity = Gtk.Label(label="Expanded invented profile", height_request=220)
        intro.append(identity)
        intro.append(Gtk.Label(label="Complete biography", height_request=300))
        self.view.set_header(intro)
        title = ProfileTitle(header, self.view, identity, self.posts[0].author)
        self.view.set_posts(self.posts, reset=True)
        self.pump(300)
        adjustment = self.view.scroll.get_vadjustment()
        self.assertEqual(
            title.stack.get_visible_child_name(),
            "expanded",
            f"offset={adjustment.get_value()} threshold={title.threshold} mapped={self.view.header_visible()} identity={identity.get_height()}",
        )
        adjustment.set_value(100)
        self.pump()
        self.assertEqual(title.stack.get_visible_child_name(), "expanded")
        self.assertTrue(self.view.interaction.capture().key is self.view.content_header)
        adjustment.set_value(300)
        self.pump()
        self.assertEqual(title.stack.get_visible_child_name(), "compact")
        self.assertTrue(self.window.interactions.top())
        self.pump(250)
        self.assertLessEqual(adjustment.get_value(), 1)
        self.assertTrue(self.view.header_visible())
        self.assertEqual(title.stack.get_visible_child_name(), "expanded")
        self.assertTrue(self.window.interactions.undo())
        self.pump(250)
        self.assertAlmostEqual(adjustment.get_value(), 300, delta=3)
        self.assertEqual(title.stack.get_visible_child_name(), "compact")
        self.view.close()
        self.assertTrue(title.closed)
        self.assertIsNone(title.tick)
        self.assertFalse(title.signals)
