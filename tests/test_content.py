"""Real GTK disclosure/model integration using invented posts, no service calls."""

import unittest
from dataclasses import replace
from types import SimpleNamespace
from weakref import WeakSet

from gtk_support import settle

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, Gtk

    DISPLAY = Gtk.init_check()
    if DISPLAY:
        Adw.init()
except ImportError, ValueError, AttributeError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ContentTests(unittest.TestCase):
    def setUp(self):
        from skyloom import APP_ID
        from skyloom.domain import Author, Media, Post

        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        self.assertIsNotNone(schema)
        settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        self.requests = []

        def get(url, local=False):
            self.requests.append(url)

            async def result():
                return None

            return result()

        def submit(coro, *args, **kwargs):
            coro.close()

        self.window = SimpleNamespace(
            settings=settings,
            content_gates=WeakSet(),
            revealed_labels={},
            images=SimpleNamespace(
                get=get,
                has_cached=lambda *_args: False,
                bind=lambda *_: None,
                unbind=lambda *_: None,
            ),
            worker=SimpleNamespace(submit=submit),
            read_only=False,
            mutations=set(),
            profile=lambda *_: None,
            open_uri=lambda *_: None,
            thread=lambda *_: None,
            compose=lambda **_: None,
            mutate=lambda *_: None,
            copy=lambda *_: None,
            toast=lambda *_: None,
            preferences=lambda: None,
            view_media=lambda *_: None,
            views=[],
        )
        self.post = Post(
            "at://did:example:labelled/app.bsky.feed.post/1",
            "fixture-cid",
            Author("did:example:labelled", "labelled.invalid", "Labelled fixture"),
            "This labelled post remains readable.",
            "2026-10-27T08:00:00Z",
            labels=("sexual",),
            images=(Media("demo-landscape", "Invented landscape", local=True),),
        )

    def labels(self, widget):
        from skyloom.widgets import list_children

        result = []
        if isinstance(widget, Gtk.Label):
            result.append(widget.get_text())
        for child in list_children(widget):
            result.extend(self.labels(child))
        return result

    def walk(self, widget):
        from skyloom.widgets import list_children

        yield widget
        for child in list_children(widget):
            yield from self.walk(child)

    def pump(self, milliseconds=100):
        from gi.repository import GLib

        loop = GLib.MainLoop()
        GLib.timeout_add(milliseconds, lambda: (loop.quit(), False)[1])
        loop.run()

    def test_unrelated_prefetch_does_not_rewrite_unchanged_mounted_pills(self):
        from test_conversation import node

        from skyloom.domain import post_from
        from skyloom.widgets import PostPositions

        class Row:
            def __init__(self, post):
                self.post = post
                self.updates = []

            def update_position(self, position):
                self.updates.append(position)

        owner = PostPositions()
        plain = post_from(node("independent")["post"])
        owner.remember([plain])
        row = Row(plain)
        owner.rows.add(row)
        root_node = node("root", reply_count=1)
        posts = [post_from(root_node["post"]), post_from(node("child", root_node)["post"])]
        owner.remember(posts)
        self.assertEqual(row.updates, [])
        connected = Row(posts[0])
        owner.rows.add(connected)
        owner.remember([replace(posts[0], replies=3)])
        self.assertEqual(connected.updates, [(1, 2, True)])

    def test_profile_and_label_targets_match_visible_controls_at_both_widths(self):
        from skyloom.content import LabelledContent
        from skyloom.widgets import PostRow

        for width in (480, 800):
            with self.subTest(width=width):
                row = PostRow(replace(self.post, images=()), self.window)
                window = Adw.Window(content=row, default_width=width, default_height=500)
                try:
                    window.present()
                    self.assertTrue(settle(window))
                    profile = row.author_button
                    valid, bounds = profile.compute_bounds(row)
                    self.assertTrue(valid)
                    self.assertLess(bounds.size.width, width * 0.7)
                    # Empty header space opens the conversation, never the profile.
                    picked = row.pick(
                        bounds.origin.x + bounds.size.width + 12,
                        bounds.origin.y + bounds.size.height / 2,
                        Gtk.PickFlags.DEFAULT,
                    )
                    self.assertIsNot(picked, profile)
                    self.assertFalse(picked.is_ancestor(profile))
                    gate = next(w for w in self.walk(row) if isinstance(w, LabelledContent))
                    self.assertFalse(any(isinstance(w, Gtk.FlowBoxChild) for w in self.walk(gate)))
                    chip = gate.chips[0]
                    self.assertLess(chip.get_width(), width * 0.7)
                    valid, chip_bounds = chip.compute_bounds(row)
                    self.assertTrue(valid)
                    picked = row.pick(
                        chip_bounds.origin.x + chip_bounds.size.width / 2,
                        chip_bounds.origin.y + chip_bounds.size.height / 2,
                        Gtk.PickFlags.DEFAULT,
                    )
                    self.assertTrue(picked is chip or picked.is_ancestor(chip))
                finally:
                    row.cancel()
                    window.destroy()

    def test_native_feed_activation_opens_post_but_never_footer(self):
        from skyloom.widgets import FeedView

        opened = []
        self.window.thread = opened.append
        view = FeedView(self.window)
        view.set_posts([self.post])
        try:
            self.assertFalse(
                view.list.get_single_click_activate(),
                "Hover must not move the keyboard cursor; row gestures provide single-click opening",
            )
            view.list.emit("activate", 0)
            view.list.emit("activate", 1)
            self.assertEqual(opened, [self.post.uri])
        finally:
            view.close()

    def test_counter_refresh_keeps_media_and_body_widgets_without_new_jobs(self):
        from skyloom.widgets import FeedView

        view = FeedView(self.window)
        window = Adw.Window(content=view, default_width=800, default_height=500)
        self.addCleanup(window.destroy)
        self.addCleanup(view.close)
        view.set_posts([self.post])
        window.present()
        self.assertTrue(settle(window))
        row = next(row for row in view.rows if row._value == self.post)
        widgets = list(self.walk(row))
        requests = self.requests.copy()
        self.assertTrue(requests)
        obj = view.model.get_item(0)
        for count in range(1, 11):
            view.set_posts([replace(self.post, likes=count, replies=count, reposts=count)])
        self.assertTrue(settle(window))
        self.assertIs(view.model.get_item(0), obj)
        self.assertEqual(list(self.walk(row)), widgets)
        self.assertEqual(self.requests, requests)
        self.assertEqual(row.post.likes, 10)

    def test_prefetched_rows_only_request_media_near_the_viewport_and_cancel_on_close(self):
        from skyloom.domain import Media
        from skyloom.widgets import FeedView

        posts = [
            replace(
                self.post,
                uri=f"at://invented/{i}",
                labels=(),
                images=(Media(f"https://cdn.bsky.app/img/invented-{i}.png", "Invented image"),),
            )
            for i in range(100)
        ]
        view = FeedView(self.window)
        window = Adw.Window(content=view, default_width=800, default_height=500)
        self.addCleanup(window.destroy)
        self.addCleanup(view.close)
        view.set_posts(posts)
        self.assertFalse(self.requests)
        window.present()
        self.assertTrue(settle(window, ready=lambda: not view.check_pending))
        self.assertGreater(len(self.requests), 0)
        self.assertLess(len(self.requests), 8)
        self.assertTrue(view.pending_media)
        view.interaction.move("last")
        self.assertTrue(
            settle(window, ready=lambda: view.position_tick is None and not view.check_pending)
        )
        self.assertIn(posts[-1].images[0].url, self.requests)
        self.assertLess(len(self.requests), 16)
        view.close()
        self.assertFalse(view.pending_media)

    def test_offscreen_pictures_release_textures_and_ignore_late_callbacks(self):
        from gi.repository import Gdk, GLib

        from skyloom.domain import Media
        from skyloom.media import Images
        from skyloom.widgets import FeedView, image_callback

        images = Images(".")
        self.window.images = images
        posts = [
            replace(
                self.post,
                uri=f"at://invented/residency/{i}",
                labels=(),
                images=(Media(f"https://cdn.bsky.app/img/invented-{i}.png", "Invented"),),
            )
            for i in range(30)
        ]
        for i, post in enumerate(posts):
            images.cache[(post.images[0].url, False)] = Gdk.MemoryTexture.new(
                8, 8, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(bytes([i, 0, 0, 255]) * 64), 32
            )
        view = FeedView(self.window)
        window = Adw.Window(content=view, default_width=800, default_height=500)
        self.addCleanup(window.destroy)
        self.addCleanup(view.close)
        view.set_posts(posts)
        window.present()
        self.assertTrue(settle(window, ready=lambda: not view.check_pending))
        self.assertGreater(images.residency()["bound_consumers"], 0)
        self.assertLess(images.residency()["bound_consumers"], 8)
        first = next(row for row in view.rows if row._value == posts[0])
        picture = next(w for w in self.walk(first) if isinstance(w, Gtk.Picture))
        self.assertIsNotNone(picture.get_paintable())
        calls = []
        late = image_callback(picture, calls.append)
        view.interaction.move("last")
        self.assertTrue(settle(window, ready=lambda: not view.check_pending))
        self.assertIsNone(picture.get_paintable())
        self.assertEqual(picture.get_size_request()[1], 220)
        late(images.cache[(posts[0].images[0].url, False)])
        self.assertEqual(calls, [])
        self.assertLess(images.residency()["bound_consumers"], 8)
        view.close()
        self.assertEqual(images.residency()["bound_consumers"], 0)

    def test_reaction_feedback_only_follows_viewer_state_not_counts_or_acknowledgements(self):
        from skyloom.widgets import PostRow

        flashes = []
        self.window.motion = SimpleNamespace(
            fade=lambda widget, **kwargs: flashes.append(widget), finish=lambda widget: None
        )
        post = replace(self.post, labels=(), images=(), like_uri="", repost_uri="")
        row = PostRow(post, self.window)
        self.addCleanup(row.cancel)
        row.update_counters(replace(post, likes=3))
        self.assertFalse(flashes)
        row.update_counters(replace(post, likes=4, like_uri="pending"))
        self.assertEqual(flashes, [row.action_buttons[2]])
        self.assertTrue(row.action_buttons[2].has_css_class("reaction-selected"))
        row.update_counters(replace(post, likes=4, like_uri="at://invented/like"))
        self.assertEqual(len(flashes), 1)
        row.update_counters(post)
        self.assertEqual(len(flashes), 2)
        self.assertFalse(row.action_buttons[2].has_css_class("reaction-selected"))

    def test_notification_read_updates_preserve_objects_widgets_and_focus(self):
        from skyloom.domain import Notice
        from skyloom.widgets import FeedView, NoticeRow

        jobs = []

        def submit(coro, *_args):
            coro.close()
            job = SimpleNamespace(cancelled=False, add_done_callback=lambda _callback: None)
            job.cancel = lambda: setattr(job, "cancelled", True)
            jobs.append(job)
            return job

        self.window.worker.submit = submit
        author = replace(self.post.author, avatar="https://cdn.bsky.app/img/invented-avatar.png")
        notices = [
            Notice(
                author,
                "like",
                f"at://invented/notice/{i}",
                self.post.uri,
                False,
                self.post.created,
            )
            for i in range(100)
        ]
        view = FeedView(
            self.window,
            render=lambda value: NoticeRow(value, self.window),
            update=NoticeRow.update_notice,
        )
        window = Adw.Window(content=view, default_width=800, default_height=500)
        self.addCleanup(window.destroy)
        self.addCleanup(view.close)
        view.set_items(notices, lambda notice: notice.uri)
        window.present()
        self.assertTrue(settle(window))
        rows = {row._value.uri: row for row in view.rows if row._value is not None}
        objects = [view.model.get_item(i) for i in range(100)]
        rows[notices[0].uri].row.grab_focus()
        focus = window.get_focus()
        changes = []
        view.model.connect("items-changed", lambda _model, *args: changes.append(args))
        view.set_items([replace(n, read=True) for n in notices], lambda notice: notice.uri)
        self.assertTrue(settle(window))
        self.assertFalse(changes)
        self.assertIs(window.get_focus(), focus)
        self.assertTrue(all(view.model.get_item(i) is obj for i, obj in enumerate(objects)))
        self.assertTrue(all(row.notice.read for row in rows.values()))
        self.assertTrue(all(row.row.get_subtitle() == "like" for row in rows.values()))
        changed = [replace(n, read=True) for n in notices]
        changed[0] = replace(changed[0], reason="reply")
        view.set_items(changed, lambda notice: notice.uri)
        self.assertIsNot(view.model.get_item(0), objects[0])
        self.assertTrue(jobs)
        view.close()
        self.assertTrue(all(job.cancelled for job in jobs))

    def test_post_menu_is_lazy_and_uses_the_current_reaction_snapshot(self):
        from skyloom.widgets import PostRow

        quoted = []
        self.window.compose = lambda **kwargs: quoted.append(kwargs["quote"])
        row = PostRow(self.post, self.window)
        window = Adw.Window(content=row, default_width=800, default_height=500)
        self.addCleanup(window.destroy)
        self.addCleanup(row.cancel)
        window.present()
        self.assertTrue(settle(window))
        self.assertIsNone(row.menu.get_popover())
        updated = replace(self.post, likes=12, like_uri="invented-like")
        row.update_counters(updated)
        row.menu.popup()
        self.assertTrue(settle(window))
        popover = row.menu.get_popover()
        quote = next(
            widget
            for widget in self.walk(popover)
            if isinstance(widget, Gtk.Button) and widget.get_label() == "Quote post"
        )
        quote.emit("clicked")
        self.assertEqual(quoted, [updated])

    def test_post_and_quote_use_inner_padding_without_open_buttons(self):
        from skyloom.widgets import PostRow

        quoted = replace(self.post, uri="at://invented/quoted", labels=(), images=())
        row = PostRow(replace(self.post, quote=quoted), self.window)
        self.addCleanup(row.cancel)
        quote = row.quoted_rows[0]
        self.assertEqual(row.get_margin_start(), 0)
        self.assertEqual(quote.get_margin_start(), 0)
        self.assertEqual(row.body.get_margin_start(), 20)
        self.assertEqual(quote.body.get_margin_start(), 16)
        self.assertEqual(quote.body.get_margin_end(), quote.body.get_margin_start())
        self.assertNotIn("Read post", self.labels(row))
        self.assertNotIn("Open image", self.labels(row))
        self.assertFalse(
            any(widget.get_tooltip_text() == "Read conversation" for widget in self.walk(row))
        )

    def test_text_click_waits_for_selection_and_is_cancelled_on_unbind(self):
        from gi.repository import Gdk

        from skyloom.widgets import PostRow

        opened = []
        self.window.thread = opened.append
        row = PostRow(replace(self.post, labels=(), images=()), self.window)
        window = Adw.Window(content=row, default_width=800, default_height=500)
        settings = Gtk.Settings.get_default()
        previous = settings.get_property("gtk-double-click-time")
        settings.set_property("gtk-double-click-time", 30)
        try:
            window.present()
            self.pump()
            text = next(
                w
                for w in self.walk(row)
                if isinstance(w, Gtk.Label) and w.get_text() == self.post.text
            )
            click = next(
                c
                for c in text.observe_controllers()
                if isinstance(c, Gtk.GestureClick) and c.get_button() == Gdk.BUTTON_PRIMARY
            )
            text.select_region(0, 0)
            click.emit("pressed", 1, 0.0, 0.0)
            click.emit("released", 1, 0.0, 0.0)
            self.assertFalse(opened)
            self.pump()
            self.assertEqual(opened, [self.post.uri])
            opened.clear()
            click.emit("pressed", 1, 0.0, 0.0)
            click.emit("released", 1, 0.0, 0.0)
            click.emit("pressed", 2, 0.0, 0.0)
            text.select_region(0, 5)
            self.pump()
            self.assertFalse(opened)
            text.select_region(0, 0)
            click.emit("pressed", 1, 0.0, 0.0)
            click.emit("released", 1, 0.0, 0.0)
            row.cancel()
            self.pump()
            self.assertFalse(opened)
        finally:
            settings.set_property("gtk-double-click-time", previous)
            row.cancel()
            window.destroy()

    def test_quoted_keyboard_and_child_controls_keep_their_own_targets(self):
        from gi.repository import Gdk

        from skyloom.widgets import PostRow

        opened, profiles = [], []
        self.window.thread = opened.append
        self.window.profile = profiles.append
        quoted = replace(self.post, uri="at://invented/quoted", labels=(), images=())
        row = PostRow(replace(self.post, quote=quoted), self.window)
        window = Adw.Window(content=row, default_width=800, default_height=500)
        try:
            window.present()
            self.pump()
            quote = row.quoted_rows[0]
            quote.grab_focus()
            keys = next(
                c for c in quote.observe_controllers() if isinstance(c, Gtk.EventControllerKey)
            )
            self.assertTrue(keys.emit("key-pressed", Gdk.KEY_Return, 0, Gdk.ModifierType(0)))
            self.assertEqual(opened, [quoted.uri])
            self.assertTrue(quote.activate())
            self.assertEqual(opened, [quoted.uri, quoted.uri])
            profile = next(
                w
                for w in self.walk(quote)
                if isinstance(w, Gtk.Button) and w.get_tooltip_text() == "View profile"
            )
            profile.emit("clicked")
            self.assertEqual(profiles, [quoted.author.did])
            self.assertEqual(opened, [quoted.uri, quoted.uri])
        finally:
            row.cancel()
            window.destroy()

    def test_text_pointer_jitter_opens_but_deliberate_selection_does_not(self):
        from gi.repository import Gdk

        from skyloom.widgets import PostRow

        opened = []
        self.window.thread = opened.append
        row = PostRow(replace(self.post, labels=(), images=()), self.window)
        window = Adw.Window(content=row, default_width=800, default_height=500)
        settings = Gtk.Settings.get_default()
        previous = settings.get_property("gtk-double-click-time")
        settings.set_property("gtk-double-click-time", 30)
        try:
            window.present()
            self.assertTrue(settle(window))
            text = next(
                w for w in self.walk(row) if isinstance(w, Gtk.Label) and w.get_selectable()
            )
            click = next(
                c
                for c in text.observe_controllers()
                if isinstance(c, Gtk.GestureClick) and c.get_button() == Gdk.BUTTON_PRIMARY
            )
            click.emit("pressed", 1, 10.0, 10.0)
            text.select_region(0, 1)  # Native selection caused by a tiny pointer movement.
            click.emit("released", 1, 11.0, 10.0)
            self.pump()
            self.assertEqual(opened, [self.post.uri])
            self.assertFalse(text.get_selection_bounds()[0])
            opened.clear()
            click.emit("pressed", 1, 10.0, 10.0)
            row.text_motion(click, 100.0, 10.0)
            text.select_region(0, 5)
            click.emit("released", 1, 11.0, 10.0)  # Return near the origin after dragging.
            self.pump()
            self.assertFalse(opened)
            self.assertTrue(text.get_selection_bounds()[0])
            click.emit("pressed", 1, 10.0, 10.0)  # Dismiss an existing selection.
            text.select_region(0, 0)
            click.emit("released", 1, 10.0, 10.0)
            self.pump()
            self.assertFalse(opened)
            shift = SimpleNamespace(
                get_widget=lambda: text,
                get_current_event_state=lambda: Gdk.ModifierType.SHIFT_MASK,
                get_device=lambda: None,
                set_state=lambda _state: None,
            )
            row.text_pressed(shift, 1, 10, 10)
            text.select_region(0, 5)
            row.text_clicked(shift, 1, 10, 10)
            self.pump()
            self.assertFalse(opened)
            self.assertTrue(text.get_selection_bounds()[0])
        finally:
            settings.set_property("gtk-double-click-time", previous)
            row.cancel()
            window.destroy()

    def test_thread_pills_share_context_across_views_and_quotes_without_rebinding(self):
        from skyloom.widgets import FeedView, PostRow, post_positions

        root = replace(self.post, labels=(), images=(), replies=1)
        reply = replace(root, uri=root.uri + "-reply", parent=(root.uri, root.cid), replies=0)
        feed = FeedView(self.window)
        search = FeedView(self.window, render=lambda value: PostRow(value, self.window))
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        container.append(feed)
        container.append(search)
        window = Adw.Window(content=container, default_width=800, default_height=700)
        try:
            feed.set_posts([reply])
            search.set_posts([replace(root, quote=reply)])
            window.present()
            self.assertTrue(settle(window))
            row = next(row for row in feed.rows if isinstance(row, PostRow))
            other = next(row for row in search.rows if isinstance(row, PostRow))
            body = row.body
            self.assertEqual(row.position_pill.get_label(), "2/2")
            self.assertEqual(other.position_pill.get_label(), "1/2")
            self.assertEqual(other.quoted_rows[0].position_pill.get_label(), "2/2")
            earlier = replace(root, uri=root.uri + "-earlier", replies=1, quote=None)
            post_positions(self.window).remember([earlier], parents={root.uri: earlier.uri})
            post_positions(self.window).remember([root, earlier], parents={root.uri: earlier.uri})
            self.assertIs(row.body, body)
            self.assertEqual(row.position_pill.get_label(), "3/3")
            self.assertEqual(other.quoted_rows[0].position_pill.get_label(), "3/3")
        finally:
            feed.close()
            search.close()
            window.destroy()

    def test_links_and_reactions_keep_their_own_actions(self):
        from skyloom.widgets import PostRow

        opened, links, reactions = [], [], []
        self.window.thread = opened.append
        self.window.open_uri = links.append
        self.window.mutate = lambda post, kind: reactions.append((post.uri, kind))
        url = "https://example.invalid/context"
        post = replace(
            self.post,
            labels=(),
            images=(),
            text="Link text",
            facets=(
                {
                    "index": {"byteStart": 0, "byteEnd": 4},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
                },
            ),
        )
        row = PostRow(post, self.window)
        self.addCleanup(row.cancel)
        text = next(
            w for w in self.walk(row) if isinstance(w, Gtk.Label) and w.get_text() == post.text
        )
        self.assertTrue(text.emit("activate-link", url))
        like = next(
            w
            for w in self.walk(row)
            if isinstance(w, Gtk.Button) and (w.get_tooltip_text() or "").startswith("Like ·")
        )
        like.emit("clicked")
        self.assertEqual(links, [url])
        self.assertEqual(reactions, [(post.uri, "like")])
        self.assertFalse(opened)
        self.assertIsNone(row.text_open_source)

    def test_labelled_post_and_media_visible_by_default(self):
        from skyloom.widgets import PostRow

        row = PostRow(self.post, self.window)
        gate = next(iter(self.window.content_gates))
        self.assertTrue(gate.get_revealed())
        self.assertIn(self.post.text, self.labels(row))
        self.assertIn("demo-landscape", self.requests)
        self.assertTrue("Sexually suggestive" in self.labels(row))

    def test_warning_reveal_survives_row_rebind(self):
        from skyloom.widgets import PostRow

        self.window.settings.set_boolean("warn-labelled-content", True)
        row = PostRow(self.post, self.window)
        gate = next(iter(self.window.content_gates))
        self.assertFalse(gate.get_revealed())
        self.assertIsNone(gate.revealer.get_child())
        self.assertFalse(self.requests)
        row.update_counters(replace(self.post, likes=2))
        gate.show_button.emit("clicked")
        self.assertEqual(row.action_buttons[2].count.get_label(), "2")
        self.assertIn(self.post.text, self.labels(row))
        self.assertEqual(self.requests, ["demo-landscape"])
        rebound = PostRow(replace(self.post, likes=2), self.window)
        self.assertIn(self.post.text, self.labels(rebound))
        gate.hide_button.emit("clicked")
        self.assertFalse(gate.get_revealed())

    def test_labelled_quote_can_be_revealed_independently(self):
        from skyloom.widgets import PostRow

        self.window.settings.set_boolean("warn-labelled-content", True)
        outer = replace(
            self.post,
            uri="at://did:example:outer/app.bsky.feed.post/2",
            text="A quote",
            labels=(),
            images=(),
            quote=self.post,
        )
        row = PostRow(outer, self.window)
        self.assertIn("A quote", self.labels(row))
        self.assertNotIn(self.post.text, self.labels(row))
        gate = next(iter(self.window.content_gates))
        gate.show_button.emit("clicked")
        self.assertIn(self.post.text, self.labels(row))

    def test_preference_reveals_existing_content_and_retains_labels(self):
        from skyloom.content import LabelledContent

        self.window.settings.set_boolean("warn-labelled-content", True)
        gate = LabelledContent(
            self.window,
            ("profile", "fixture"),
            ("adult",),
            lambda: Gtk.Label(label="Profile biography"),
        )
        self.assertIsNone(gate.revealer.get_child())
        self.window.settings.set_boolean("warn-labelled-content", False)
        gate.sync()
        self.assertTrue(gate.get_revealed())
        self.assertIn("Profile biography", self.labels(gate))
        self.assertTrue("Adult" in self.labels(gate))

    def test_label_details_preserve_scope_custom_values_and_bound_inline_chips(self):
        from skyloom.content import LabelledContent

        values = ("sexual", "sexual", "graphic-media", "bot", "<custom-label>", "x" * 200)
        gate = LabelledContent(
            self.window,
            ("post", "details"),
            values,
            lambda: Gtk.Label(label="Readable"),
            author_labels=("sexual", "nudity"),
        )
        self.assertEqual(len(gate.labels), 6)
        self.assertEqual(gate.labels[0].scopes, ("On this post", "On the author"))
        self.assertEqual(len(gate.chips), 4)
        self.assertTrue(all(chip.get_popover() is None for chip in gate.chips))
        popup = gate.details(gate.labels)
        texts = self.labels(popup)
        self.assertIn("On this post · On the author", texts)
        self.assertIn("<custom-label>", texts)
        self.assertIn("x" * 200, texts)
        self.assertIn("On the author", texts)
        self.assertIn(
            "No definition was supplied for this label. Its meaning depends on the labeller.", texts
        )
        profile = LabelledContent(self.window, ("profile", "p"), ("bot",), lambda: Gtk.Box())
        self.assertEqual(profile.labels[0].scopes, ("On this profile",))

    def test_label_controls_sync_mounted_copies_and_keep_keyboard_focus(self):
        from skyloom.content import LabelledContent

        builds = []

        def build():
            builds.append(True)
            return Gtk.Label(label="Readable")

        first = LabelledContent(self.window, ("post", "same"), ("sexual",), build)
        second = LabelledContent(self.window, ("post", "same"), ("sexual",), build)
        other = LabelledContent(self.window, ("post", "other"), ("sexual",), build)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for gate in (first, second, other):
            body.append(gate)
        window = Gtk.Window(child=body, default_width=480, default_height=600)
        window.present()
        try:
            settle(window)
            first.hide_button.grab_focus()
            first.hide_button.emit("clicked")
            self.assertFalse(first.get_revealed())
            self.assertFalse(second.get_revealed())
            self.assertTrue(other.get_revealed())
            self.assertTrue(first.show_button.is_focus())
            first.show_button.emit("clicked")
            self.assertTrue(second.get_revealed())
            self.assertTrue(first.hide_button.is_focus())
            self.assertEqual(len(builds), 3)
            first.chips[0].popup()
            settle(window)
            popup = first.chips[0].get_popover()
            self.assertTrue(popup.get_mapped())
            self.assertIn("sexual", self.labels(popup))
            self.assertIsNotNone(window.get_focus())
            first.chips[0].popdown()
        finally:
            window.destroy()

    def test_label_popover_actions_copy_exact_value_and_open_preferences(self):
        from skyloom.content import LabelledContent

        actions = []
        self.window.toast = actions.append
        self.window.preferences = lambda: actions.append("preferences")
        gate = LabelledContent(self.window, ("post", "actions"), ("test-label",), Gtk.Box)
        window = Gtk.Window(child=gate)
        window.present()
        try:
            settle(window)
            gate.chips[0].popup()
            settle(window)
            popup = gate.chips[0].get_popover()
            copy = next(
                w
                for w in self.walk(popup)
                if isinstance(w, Gtk.Button) and w.get_label() == "Copy label"
            )
            copy.emit("clicked")
            copied = []
            gate.get_clipboard().read_text_async(
                None, lambda clipboard, result: copied.append(clipboard.read_text_finish(result))
            )
            settle(window, ready=lambda: bool(copied))
            self.assertEqual(copied, ["test-label"])
            preferences = next(
                w
                for w in self.walk(popup)
                if isinstance(w, Gtk.Button) and w.get_label() == "Label preferences…"
            )
            preferences.emit("clicked")
            self.assertEqual(actions, ["Label copied", "preferences"])
            self.assertFalse(popup.get_visible())
        finally:
            window.destroy()

    def test_connectivity_updates_controls_without_rebinding_posts_or_reloading_media(self):
        from skyloom.widgets import FeedView
        from skyloom.window import Window

        fixture = self.window
        fixture.online_controls = WeakSet()
        fixture.online_control = lambda control, **kwargs: Window.online_control(
            fixture, control, **kwargs
        )
        fixture.service = SimpleNamespace(account=self.post.author)
        fixture.offline_banner = SimpleNamespace(set_revealed=lambda _: None)
        fixture.compose_button = Gtk.Button()
        fixture.composer = None
        view = FeedView(fixture)
        view.set_posts([self.post])
        window = Gtk.Window(child=view, default_width=800, default_height=600)
        window.present()
        try:
            self.assertTrue(settle(window))
            changes = []
            view.model.connect("items-changed", lambda *_: changes.append(True))
            requests = len(self.requests)
            controls = tuple(fixture.online_controls)
            self.assertEqual(len(controls), 2)
            for _ in range(5):
                Window.show_offline(fixture, False)
            Window.show_offline(fixture, True)
            self.assertTrue(all(not control.get_sensitive() for control in controls))
            self.assertTrue(fixture.compose_button.get_sensitive())
            Window.show_offline(fixture, False)
            self.assertTrue(all(control.get_sensitive() for control in controls))
            self.assertTrue(settle(window))
            self.assertFalse(changes)
            self.assertEqual(len(self.requests), requests)
            self.assertFalse(fixture.read_only)
        finally:
            view.close()
            window.destroy()

    def test_queued_media_rechecks_cache_before_starting_io(self):
        import asyncio

        from skyloom.media import Images

        async def run():
            images = Images(".")
            images.sem = asyncio.Semaphore(0)
            sentinel = object()
            task = asyncio.create_task(images.get("invented-no-network"))
            await asyncio.sleep(0)
            images.cache[("invented-no-network", False)] = sentinel
            images.sem.release()
            self.assertIs(await task, sentinel)

        asyncio.run(run())

    def test_unbound_post_cancels_avatar_work(self):
        from skyloom.widgets import PostRow

        cancelled = []

        def submit(coro, *_args):
            coro.close()
            return SimpleNamespace(
                cancel=lambda: cancelled.append(True), add_done_callback=lambda _callback: None
            )

        self.window.worker.submit = submit
        post = replace(
            self.post, images=(), author=replace(self.post.author, avatar="invented-avatar")
        )
        row = PostRow(post, self.window)
        row.cancel()
        self.assertEqual(cancelled, [True])

    def test_external_preview_keeps_text_actions_and_parenting(self):
        from skyloom.widgets import PostRow

        row = PostRow(
            replace(self.post, external=("https://example.invalid", "Link title", "Preview")),
            self.window,
        )
        texts = self.labels(row)
        self.assertIn(self.post.text, texts)
        self.assertIn("Link title", texts)
        self.assertIn(row.action_buttons[2].count.get_label(), texts)
        self.assertEqual(row.action_buttons[2].glyph.get_icon_name(), "skyloom-like-symbolic")

    def test_explicit_mute_and_block_remain_separate(self):
        from skyloom.widgets import PostRow

        for author in (
            replace(self.post.author, muted=True),
            replace(self.post.author, blocking="at://example/block/1"),
        ):
            row = PostRow(replace(self.post, author=author), self.window)
            self.assertNotIn(self.post.text, self.labels(row))
            self.assertFalse(self.requests)

    def test_post_append_reports_progress_for_multiple_auto_pages(self):
        from skyloom.widgets import FeedView

        self.window.views = []
        view = FeedView(self.window)
        try:
            self.assertEqual(view.set_posts([self.post]), 1)
            view.paging.complete("two", 1)
            added = view.set_posts([self.post, replace(self.post, uri=self.post.uri + "2")])
            self.assertEqual(added, 1)
            view.paging.complete("three", added)
            self.assertTrue(view.paging.auto)
        finally:
            view.close()

    def test_native_list_recycles_post_cells_across_distant_scrolls(self):
        from unittest.mock import patch

        from skyloom.widgets import FeedView, PostRow

        bindings = {}
        original = PostRow.bind_post

        def bound(row, post):
            bindings.setdefault(row, set()).add(post.uri)
            original(row, post)

        view = FeedView(self.window)
        window = Gtk.Window(child=view, default_width=800, default_height=600)
        posts = [
            replace(
                self.post,
                uri=f"at://did:example:scroll/app.bsky.feed.post/{n}",
                text=f"Invented scroll post {n} " * 10,
                labels=(),
                images=(),
            )
            for n in range(250)
        ]
        try:
            with patch.object(PostRow, "bind_post", bound):
                view.set_posts(posts)
                window.present()
                self.assertTrue(settle(window, ready=lambda: not view.check_pending))
                for direction in ("last", "first", "last", "first"):
                    view.interaction.move(direction)
                    self.assertTrue(settle(window, ready=lambda: not view.check_pending))
                self.assertTrue(
                    any(len(uris) > 1 for uris in bindings.values()), "No cell was recycled"
                )
                for row in view.rows:
                    if isinstance(row, PostRow):
                        self.assertEqual(row.post.uri, row._value.uri)
                        self.assertEqual(row.text.get_text(), row.post.text)
        finally:
            view.close()
            window.destroy()

    def test_recycled_post_retains_controls_and_routes_only_to_current_data(self):
        from skyloom.widgets import PostRow

        first = replace(self.post, labels=(), images=(), like_uri="at://invented/like")
        row = PostRow(first, self.window)
        self.addCleanup(row.cancel)
        widgets = row.heading, row.text, row.actions, row.menu, row.author_button
        row.text.select_region(0, 10)
        row.create_post_menu(row.menu)
        row.text_press = (row.text, 0, 0, False, False)
        opened, profiles, mutations, replies = [], [], [], []
        self.window.thread = opened.append
        self.window.profile = profiles.append
        self.window.mutate = lambda post, kind: mutations.append((post, kind))
        self.window.compose = lambda **kwargs: replies.append(kwargs)
        for index in range(100):
            post = replace(
                first,
                uri=f"at://did:example:recycled/app.bsky.feed.post/{index}",
                text=f"Invented post {index}",
                author=replace(first.author, did=f"did:example:{index}", name=f"Author {index}"),
                like_uri="",
                repost_uri="",
                likes=index,
            )
            row.bind_post(post)
            self.assertEqual(
                widgets, (row.heading, row.text, row.actions, row.menu, row.author_button)
            )
            self.assertEqual(row.text.get_text(), post.text)
            self.assertFalse(row.text.get_selection_bounds()[0])
            self.assertIsNone(row.menu.get_popover())
            self.assertIsNone(row.text_press)
            self.assertFalse(row.action_buttons[2].has_css_class("reaction-selected"))
            self.assertEqual(row.action_buttons[2].glyph.get_icon_name(), "skyloom-like-symbolic")
        row.activate()
        row.author_button.emit("clicked")
        row.action_buttons[2].emit("clicked")
        row.action_buttons[0].emit("clicked")
        self.assertEqual(opened, [post.uri])
        self.assertEqual(profiles, [post.author.did])
        self.assertEqual(mutations, [(post, "like")])
        self.assertEqual(replies, [{"reply": post}])
        row.cancel()
        self.assertIsNone(row.post)
        self.assertIsNone(row._value)
        self.assertEqual(row.text.get_text(), "")
        self.assertNotIn(row, row.position_owner.rows)

    def test_recycled_post_respects_mute_and_lazy_label_disclosure(self):
        from skyloom.widgets import PostRow

        plain = replace(self.post, labels=(), images=())
        row = PostRow(plain, self.window)
        self.addCleanup(row.cancel)
        text = row.text
        row.bind_post(replace(plain, author=replace(plain.author, muted=True)))
        self.assertIn("This account is muted.", self.labels(row))
        self.assertNotIn(plain.text, self.labels(row))
        self.window.settings.set_boolean("warn-labelled-content", True)
        row.bind_post(self.post)
        gate = row.gate
        self.assertIsNone(gate.revealer.get_child())
        self.assertNotIn(plain.text, self.labels(row))
        gate.set_revealed(True)
        self.assertIs(row.text, text)
        self.assertIn(plain.text, self.labels(row))
        row.bind_post(plain)
        self.assertNotIn(gate, self.window.content_gates)
        self.assertIsNone(gate.revealer.get_child())
        self.assertIs(row.text, text)
        self.assertIn(plain.text, self.labels(row))

    def test_recycled_quote_reuses_text_and_clears_previous_binding(self):
        from skyloom.widgets import PostRow

        quote = replace(
            self.post, uri="at://did:example:quote/app.bsky.feed.post/1", labels=(), images=()
        )
        row = PostRow(replace(self.post, labels=(), images=(), quote=quote), self.window)
        self.addCleanup(row.cancel)
        child, text = row.quoted_rows[0], row.quoted_rows[0].text
        row.bind_post(replace(self.post, labels=(), images=(), quote=None))
        self.assertIsNone(child.post)
        self.assertIsNone(child.get_parent())
        newer = replace(quote, uri="at://did:example:quote/app.bsky.feed.post/2", text="New quote")
        row.bind_post(replace(self.post, labels=(), images=(), quote=newer))
        self.assertIs(row.quoted_rows[0], child)
        self.assertIs(child.text, text)
        self.assertEqual(child.text.get_text(), "New quote")

    def test_recycled_post_rejects_late_media_completion(self):
        from skyloom.widgets import PostRow

        callbacks = []

        def submit(coro, loaded, failed):
            coro.close()
            callbacks.append((loaded, failed))

        self.window.worker.submit = submit
        row = PostRow(self.post, self.window)
        self.addCleanup(row.cancel)
        picture = next(w for w in self.walk(row) if isinstance(w, Gtk.Picture))
        loaded, failed = callbacks[-1]
        binds = []
        self.window.images.bind = lambda *args: binds.append(args)
        row.bind_post(replace(self.post, labels=(), images=(), text="New binding"))
        loaded(object())
        failed("Late failure")
        self.assertFalse(binds)
        self.assertIsNone(picture.get_paintable())
        self.assertIn("New binding", self.labels(row))

    def test_failed_image_keeps_reserved_geometry_and_view_action(self):
        from skyloom.widgets import PostRow

        failures = []

        def submit(coro, loaded, failed):
            coro.close()
            failures.append(failed)

        self.window.worker.submit = submit
        row = PostRow(self.post, self.window)
        picture = next(widget for widget in self.walk(row) if isinstance(widget, Gtk.Picture))
        viewer = picture.get_parent()
        self.assertEqual(picture.get_size_request().height, 220)
        failures[-1]("Invented download failure")
        self.assertIs(viewer.get_child(), picture)
        self.assertTrue(viewer.get_visible())
        self.assertEqual(picture.get_size_request().height, 220)
        self.assertIn("unavailable", viewer.get_tooltip_text())
        opened = []
        self.window.view_media = opened.append
        viewer.emit("clicked")
        self.assertEqual(opened, list(self.post.images))
        row.cancel()

    def test_images_off_has_a_named_explicit_view_action(self):
        from skyloom.widgets import PostRow

        self.window.settings.set_boolean("load-images", False)
        row = PostRow(
            replace(self.post, images=(replace(self.post.images[0], alt=""),)), self.window
        )
        self.assertIn("View image", self.labels(row))
        self.assertFalse(self.requests)
        self.assertFalse(any(text.startswith("ALT") for text in self.labels(row)))

    def test_empty_alt_has_no_visible_alt_section(self):
        from skyloom.widgets import PostRow

        images = (replace(self.post.images[0], alt=""), replace(self.post.images[0], alt="  "))
        row = PostRow(replace(self.post, images=images), self.window)
        texts = self.labels(row)
        self.assertFalse(any(text.startswith("ALT") or "No description" in text for text in texts))


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class PagingWidgetTests(unittest.TestCase):
    def flush(self):
        self.assertTrue(
            settle(self.native_window, ready=lambda: not self.native_view.check_pending),
            "Native paging window did not finish rendering/checking",
        )

    def test_single_virtualised_surface_appends_and_fallback_retries(self):
        from skyloom.widgets import FeedView

        view = FeedView(
            SimpleNamespace(views=[]), render=lambda n: Gtk.Label(label=str(n), height_request=40)
        )
        window = Adw.Window(content=view, default_width=1000, default_height=600)
        self.native_window, self.native_view = window, view
        calls = []
        view.load_more = lambda: calls.append(True)
        try:
            view.paging.begin()
            window.present()
            self.flush()
            view.set_items(list(range(40)), lambda n: n)
            first = view.model.get_item(0)
            view.paging.complete("next", 40)
            window.present()
            self.flush()
            self.assertFalse(calls)
            self.assertTrue(all(not footer.more.get_visible() for footer in view.footers))
            self.assertIs(view.scroll.get_child(), view.list)
            self.assertEqual(view.flat.get_n_items(), 41)
            adjustment = view.scroll.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            self.flush()
            self.assertEqual(len(calls), 1)
            self.assertTrue(view.paging.busy)
            view.set_items(list(range(100)), lambda n: n)
            self.assertIs(view.model.get_item(0), first)
            view.paging.complete("last", 60)
            self.flush()
            self.assertEqual(len(calls), 1)
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            self.flush()
            self.assertEqual(len(calls), 2)
            view.paging.fail("Try later")
            self.flush()
            self.assertEqual(len(calls), 2)
            footer = next(iter(view.footers))
            self.assertTrue(footer.more.get_visible())
            footer.more.emit("clicked")
            self.assertEqual(len(calls), 3)
            view.paging.complete(None, 0)
        finally:
            view.close()
            window.destroy()
