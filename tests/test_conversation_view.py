"""Rendered connected conversations and exact reply activation, invented records only."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

import test_content
from gtk_support import settle
from test_conversation import node


@unittest.skipUnless(test_content.DISPLAY, "GNOME GTK display required")
class ConversationViewTests(unittest.TestCase):
    def setUp(self):
        from gi.repository import Gtk

        from skyloom.conversation import Conversation, thread_from
        from skyloom.conversation_view import ConversationView

        fixture = test_content.ContentTests()
        fixture.setUp()
        self.labels = fixture.labels
        self.owner = fixture.window
        self.calls = []
        root = node("root")
        first = node("first", root, reply_count=1)
        second = node("second", root)
        first["parent"] = second["parent"] = None
        root["replies"] = [second, first]
        self.state = Conversation(first["post"]["uri"])
        self.state.merge(thread_from(root), root["post"]["uri"])
        self.view = ConversationView(
            self.owner, self.state, lambda **kwargs: self.calls.append(kwargs)
        )
        self.native = Gtk.Window(child=self.view, default_width=480, default_height=600)
        self.owner.get_focus = self.native.get_focus
        self.native.present()
        self.view.sync()
        self.addCleanup(self.view.close)
        self.addCleanup(self.native.destroy)
        self.assertTrue(settle(self.native))

    def test_loading_state_keeps_loader_and_does_not_reposition_reader(self):
        from unittest.mock import patch

        from skyloom.conversation import Continuation

        loader = next(row for row in self.view.rows if isinstance(row._value, Continuation))
        control = loader.control
        model_changes = []
        self.view.model.connect("items-changed", lambda *_: model_changes.append(True))
        with patch.object(
            self.view.interaction, "restore", wraps=self.view.interaction.restore
        ) as restore:
            with patch.object(self.state, "project", wraps=self.state.project) as project:
                self.view.sync(active=self.state.anchor, content_changed=False)
                self.assertTrue(settle(self.native))
                project.assert_not_called()
            restore.assert_not_called()
        current = next(row for row in self.view.rows if isinstance(row._value, Continuation))
        self.assertIs(current, loader)
        self.assertFalse(model_changes)
        self.assertIs(current.control, control)
        self.assertTrue(current._value.busy)
        self.assertFalse(control.get_sensitive())
        self.assertEqual(control.get_label(), "Loading…")

    def test_appending_replies_below_anchor_issues_no_scroll_request(self):
        from unittest.mock import patch

        from skyloom.conversation import ThreadPage

        parent = self.state.posts[-1]
        reply = replace(
            parent,
            uri=parent.uri + "-new",
            parent=(parent.uri, parent.cid),
            text="Invented appended reply",
        )
        with patch.object(self.view.list, "scroll_to", wraps=self.view.list.scroll_to) as scroll:
            self.state.merge(ThreadPage((parent, reply)), parent.uri)
            self.view.sync()
            self.assertTrue(settle(self.native))
            scroll.assert_not_called()

    def test_active_scroll_does_not_get_repositioned_by_prepend(self):
        from unittest.mock import patch

        from skyloom.conversation import ThreadPage

        root = self.state.posts[0]
        ancestor = replace(root, uri=root.uri + "-ancestor", parent=None)
        self.view.scroll_event()
        self.view.scrolled()  # Continued native momentum, without another input event.
        self.assertTrue(self.view.scrolling())
        with patch.object(self.view.list, "scroll_to", wraps=self.view.list.scroll_to) as scroll:
            self.state.merge(
                ThreadPage((ancestor,), edges=((root.uri, ancestor.uri),)),
                ancestor.uri,
                earlier=True,
            )
            self.view.sync()
            self.assertTrue(settle(self.native))
            scroll.assert_not_called()
        self.view.user_input()  # A new explicit action ends the scrolling interval.
        self.assertFalse(self.view.scrolling())

    def test_conversation_uses_branch_geometry_not_generic_end_paging(self):
        self.view.load_more = lambda: self.calls.append("unrelated end paging")
        self.view.check_start = lambda: False
        self.view.paging.complete(self.state.anchor, 1)
        adjustment = self.view.scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        self.view.queue_check()
        self.assertTrue(settle(self.native, ready=lambda: not self.view.check_pending))
        self.assertEqual(self.calls, [])

    def test_projection_and_keyboard_share_order_skipping_branch_controls(self):
        from skyloom.conversation import Continuation

        self.assertEqual(
            [self.view.model.get_item(i).post.text for i in self.view.interaction.positions()],
            ["root", "first", "second"],
        )
        self.view.focus_post(self.state.anchor)
        self.assertTrue(settle(self.native))
        self.assertTrue(self.view.parent_button.get_sensitive())
        self.assertTrue(self.view.relative("parent"))
        self.assertEqual(self.view.interaction.selected().text, "root")
        self.assertTrue(self.view.relative("child"))
        self.assertEqual(self.view.interaction.selected().text, "first")
        self.view.interaction.move("next")
        self.assertEqual(self.view.interaction.selected().text, "second")
        loader = next(row for row in self.view.rows if isinstance(row._value, Continuation))
        loader.control.emit("clicked")
        self.assertEqual(self.calls, [{"earlier": False, "branch": self.state.anchor}])
        opened = next(
            row for row in self.view.rows if getattr(row._value, "uri", None) == self.state.anchor
        )
        self.assertTrue(opened.has_css_class("opened-message"))
        self.assertIn("Opened here", self.labels(opened))

    def test_cross_author_reply_in_feed_opens_its_exact_uri(self):
        from skyloom.widgets import FeedView

        opened = []
        self.owner.thread = opened.append
        root, reply = self.state.posts[:2]
        reply = replace(
            reply, author=replace(reply.author, did="did:example:another", name="Another author")
        )
        feed = FeedView(self.owner)
        try:
            feed.set_posts([reply, root])
            feed.list.emit("activate", 0)
            self.assertEqual(opened, [reply.uri])
            self.assertFalse(feed.connections)
            self.assertEqual(feed.model.get_item(0).post.uri, reply.uri)
        finally:
            feed.close()

    def test_position_pills_follow_loaded_order_and_update_without_rebuilding(self):
        from skyloom.conversation import ThreadPage

        def messages():
            return {row.post.uri: row for row in self.view.rows if hasattr(row, "position_pill")}

        before = messages()
        for index, post in enumerate(self.state.posts, start=1):
            pill = before[post.uri].position_pill
            self.assertEqual(pill.get_label(), f"{index}/3")
            self.assertIn("known messages in reading order", pill.get_tooltip_text())
            self.assertIn("incomplete", pill.get_tooltip_text())
            self.assertFalse(pill.get_focusable())
        root = self.state.posts[0]
        ancestor = replace(root, uri="at://invented/ancestor", text="Earlier", parent=None)
        self.state.parents[root.uri] = ancestor.uri
        self.view.sync()
        self.assertTrue(settle(self.native))
        retained = messages()[self.state.anchor]
        self.state.merge(ThreadPage((ancestor,)), ancestor.uri, earlier=True)
        parent = next(post for post in self.state.posts if post.uri == self.state.anchor)
        child = replace(
            parent, uri="at://invented/child", parent=(parent.uri, parent.cid), replies=0
        )
        self.state.merge(ThreadPage((parent, child)), parent.uri)
        self.view.sync()
        self.assertTrue(settle(self.native))
        after = messages()
        self.assertIs(after[self.state.anchor], retained)
        for index, post in enumerate(self.state.posts, start=1):
            pill = after[post.uri].position_pill
            self.assertEqual(pill.get_label(), f"{index}/5")
            self.assertNotIn("incomplete", pill.get_tooltip_text())

    def test_joined_feed_preview_requires_adjacent_verified_same_author_links(self):
        from skyloom.widgets import FeedView

        feed = FeedView(self.owner)
        root, reply = self.state.posts[:2]
        try:
            feed.set_posts([reply, root])
            self.assertEqual(feed.connections, {reply.uri, root.uri})
            self.assertEqual(feed.model.get_item(0).post.uri, reply.uri)
            unrelated = replace(reply, uri="at://invented/unrelated", parent=None)
            feed.set_posts([reply, unrelated, root])
            self.assertFalse(feed.connections)
        finally:
            feed.close()

    def test_content_refresh_restores_the_focused_profile_target(self):
        self.view.focus_post(self.state.anchor)
        self.assertTrue(settle(self.native))
        row = next(
            row for row in self.view.rows if getattr(row._value, "uri", None) == self.state.anchor
        )
        row.author_button.grab_focus()
        self.state.update_post(replace(row.post, text="Updated invented conversation message"))
        self.view.sync()
        self.assertTrue(settle(self.native))
        focus = self.native.get_focus()
        self.assertEqual(getattr(focus, "focus_key", None), ("post-author", self.state.anchor))
        self.assertEqual(focus.get_tooltip_text(), "View profile")

    def test_refreshed_message_retains_focused_reaction_control(self):
        from gi.repository import Gtk

        from skyloom.widgets import list_children

        def walk(widget):
            yield widget
            for child in list_children(widget):
                yield from walk(child)

        self.view.focus_post(self.state.anchor)
        self.assertTrue(settle(self.native))
        row = next(
            row for row in self.view.rows if getattr(row._value, "uri", None) == self.state.anchor
        )
        like = next(
            w
            for w in walk(row)
            if isinstance(w, Gtk.Button) and (w.get_tooltip_text() or "").startswith("Like ·")
        )
        like.grab_focus()
        self.state.update_post(
            replace(next(p for p in self.state.posts if p.uri == self.state.anchor), likes=7)
        )
        self.view.sync()
        self.assertTrue(settle(self.native))
        focus = self.native.get_focus()
        self.assertEqual(getattr(focus, "focus_key", None), ("button", "skyloom-like-symbolic"))
        self.assertIn("7", focus.count.get_label())

    def test_ancestor_insertion_does_not_replace_every_deeper_post(self):
        from skyloom.conversation import ThreadPage

        root = self.state.posts[0]
        ancestor = replace(root, uri="at://invented/ancestor", text="Earlier ancestor", parent=None)
        self.state.parents[root.uri] = ancestor.uri
        self.view.sync()
        self.assertTrue(settle(self.native))
        changed = []

        def replaced(model, position, removed, added):
            if removed and added:
                changed.append(model.get_item(position).post.uri)

        self.view.model.connect("items-changed", replaced)
        self.state.merge(ThreadPage((ancestor,)), ancestor.uri, earlier=True)
        self.view.sync()
        self.assertTrue(settle(self.native))
        self.assertNotIn(self.state.anchor, changed)
        self.assertTrue(all(uri == root.uri for uri in changed))

    def test_cached_opened_message_rebinds_when_its_parent_context_arrives(self):
        from skyloom.conversation import ThreadPage

        root, selected = self.state.posts[:2]
        self.state.posts = [selected]
        self.state.parents = {}
        self.view.sync()
        self.assertTrue(settle(self.native))
        self.state.merge(
            ThreadPage((root, selected), edges=((selected.uri, root.uri),)), selected.uri
        )
        self.view.sync()
        self.assertTrue(settle(self.native))
        row = next(
            row for row in self.view.rows if getattr(row._value, "uri", None) == selected.uri
        )
        self.assertTrue(any(value.startswith("Replying to ") for value in self.labels(row)))
        self.assertTrue(row.has_css_class("conversation-reply"))

    def test_parent_discovery_keeps_index_and_visible_counter_updates_together(self):
        self.test_cached_opened_message_rebinds_when_its_parent_context_arrives()
        uri = self.state.anchor
        index, entry = self.view.entries[uri]
        self.assertIs(entry, self.view.model.get_item(index))
        row = next(row for row in self.view.rows if getattr(row._value, "uri", None) == uri)
        body = row.body
        changed = replace(entry.post, likes=entry.post.likes + 1)
        self.view.update_post(changed)
        self.assertEqual(self.view.model.get_item(index).post.likes, changed.likes)
        self.assertEqual(row._value.likes, changed.likes)
        self.assertIs(row.body, body)

    def test_loading_keeps_logical_loader_focus_then_returns_to_a_message(self):
        from skyloom.conversation import Continuation, ThreadPage

        loader = next(row for row in self.view.rows if isinstance(row._value, Continuation))
        loader.control.grab_focus()
        before = self.view.scroll.get_vadjustment().get_value()
        self.view.sync(active=self.state.anchor)
        self.assertTrue(settle(self.native))
        focus = self.native.get_focus()
        self.assertEqual(getattr(focus, "continuation_uri", None), loader._value.uri)
        from skyloom.interactions import Interactions

        self.owner.get_visible_dialog = lambda: None
        controller = SimpleNamespace(window=self.owner, current_view=lambda: self.view)
        self.assertEqual(Interactions.context(controller), "control")
        self.assertAlmostEqual(self.view.scroll.get_vadjustment().get_value(), before, delta=3)
        parent = next(post for post in self.state.posts if post.uri == self.state.anchor)
        child = replace(
            parent, uri="at://invented/loaded", parent=(parent.uri, parent.cid), text="Loaded reply"
        )
        self.state.merge(ThreadPage((parent, child)), parent.uri)
        self.view.sync()
        self.assertTrue(settle(self.native))
        self.assertEqual(self.view.interaction.selected().uri, parent.uri)
        self.assertIsNotNone(self.native.get_focus())

    def test_completion_does_not_take_focus_from_another_content_view(self):
        from gi.repository import Gtk

        self.native.set_child(None)
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        container.append(self.view)
        elsewhere = Gtk.Button(label="Another page’s loading action")
        elsewhere.continuation_uri = "skyloom:continue:elsewhere"
        elsewhere.continuation_parent = "at://invented/elsewhere"
        container.append(elsewhere)
        self.native.set_child(container)
        self.assertTrue(settle(self.native))
        # Verify native logical focus independently of compositor window activation.
        self.assertTrue(elsewhere.grab_focus())
        self.assertIs(self.native.get_focus(), elsewhere)
        self.view.sync()
        self.assertTrue(settle(self.native))
        self.assertIs(self.native.get_focus(), elsewhere)
        self.assertIsNone(self.view.pending_loader_focus)
