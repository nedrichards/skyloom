"""Native thread-control editor retains unsaved values after independent failures."""

import asyncio
import json
import unittest
from types import SimpleNamespace

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class ThreadControlViewTests(unittest.TestCase):
    def test_independent_save_failure_preserves_reply_choices_and_quote_success(self):
        from skyloom.domain import Author, Post
        from skyloom.thread_controls import ThreadControls
        from skyloom.thread_service import POST, THREAD, Gate

        did = "did:plc:abcdefghijklmnopqrstuvwx"
        uri = f"at://{did}/app.bsky.feed.post/root"
        gates = tuple(
            Gate(
                did,
                collection,
                "root",
                "cid",
                json.dumps({"$type": collection, "post": uri, "createdAt": "2026-11-13T12:00:00Z"}),
            )
            for collection in (THREAD, POST)
        )
        window = Adw.Window(title="Invented controls", default_width=600, default_height=700)
        window.generation = 1
        window.read_only = False
        messages = []
        window.toast = messages.append
        window.thread_cache = SimpleNamespace(clear=lambda: None)
        window.interactions = SimpleNamespace(current_view=lambda **_kwargs: None)
        window.online_control = lambda widget, busy=False: widget.set_sensitive(not busy)
        self.addCleanup(window.destroy)

        async def load(_uri, **_kwargs):
            return gates

        async def fail(*_args):
            raise ValueError("Invented failure")

        async def succeed(gate, _allowed):
            return gate

        def submit(operation, ready, failed):
            try:
                value = asyncio.run(operation)
            except ValueError as error:
                failed(str(error))
            else:
                ready(value)

        window.worker = SimpleNamespace(submit=submit)
        window.service = SimpleNamespace(
            account=object(), thread_controls=load, save_reply_rules=fail, save_quote_rule=succeed
        )
        post = Post(uri, "cid", Author(did, "invented.invalid", "Invented"), "Test", "")
        dialog = ThreadControls(window, post)
        self.addCleanup(dialog.force_close)
        dialog.present(window)
        self.assertTrue(settle(window))
        dialog.mode.set_selected(2)
        dialog.groups["follower"].set_active(True)
        controls = []
        child = dialog.body.get_first_child()
        while child:
            if isinstance(child, Gtk.Button):
                controls.append(child)
            child = child.get_next_sibling()
        controls[0].emit("clicked")
        self.assertIn("Invented failure", messages[-1])
        self.assertEqual(dialog.mode.get_selected(), 2)
        self.assertTrue(dialog.groups["follower"].get_active())
        self.assertTrue(controls[0].get_sensitive())
        controls[1].emit("clicked")
        self.assertEqual(messages[-1], "Quote permissions saved.")
        self.assertTrue(dialog.groups["follower"].get_active())
