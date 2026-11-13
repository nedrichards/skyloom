"""Incremental conversation context with synthetic network-shaped records."""

import unittest
from dataclasses import replace

from skyloom.conversation import Conversation, ThreadPage, thread_from
from skyloom.domain import feed_from


def node(name, parent=None, replies=None, reply_count=0):
    uri = "at://did:example:invented/app.bsky.feed.post/" + name
    record = {"text": name, "createdAt": "2026-10-27T12:00:00Z"}
    if parent:
        record["reply"] = {
            "parent": {"uri": parent["post"]["uri"], "cid": "invented-cid"},
            "root": {"uri": parent["post"]["uri"], "cid": "invented-cid"},
        }
    return {
        "post": {
            "uri": uri,
            "cid": "invented-cid",
            "record": record,
            "author": {"did": "did:example:invented", "handle": "invented.invalid"},
            "replyCount": reply_count,
        },
        "parent": parent,
        "replies": replies,
    }


class ConversationTests(unittest.TestCase):
    def test_selected_reply_has_ancestors_and_reply_frontiers(self):
        root = node("root")
        parent = node("parent", root)
        selected = node("selected", parent)
        child = node("child", selected, reply_count=2)
        # Thread response descendants do not repeat their parent trees.
        child["parent"] = None
        selected["replies"] = [child]
        page = thread_from(selected)
        self.assertEqual([p.text for p in page.posts], ["root", "parent", "selected", "child"])
        self.assertEqual(page.posts[2].context, "Selected post")
        self.assertEqual(page.posts[2].parent[0], parent["post"]["uri"])
        self.assertEqual(page.branches, (child["post"]["uri"],))
        self.assertFalse(page.earlier)
        self.assertIn(
            "conversation", feed_from({"feed": [{"post": selected["post"]}]}).posts[0].context
        )

    def test_merge_inserts_descendants_at_their_branch_and_preserves_anchor(self):
        root = node("root")
        first = node("first", root, reply_count=1)
        second = node("second", root)
        first["parent"] = second["parent"] = None
        root["replies"] = [first, second]
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        self.assertEqual(state.next_branch, first["post"]["uri"])
        grandchild = node("grandchild", first)
        grandchild["parent"] = None
        first["replies"] = [grandchild]
        state.merge(thread_from(first), first["post"]["uri"])
        self.assertEqual([p.text for p in state.posts], ["root", "first", "grandchild", "second"])
        self.assertEqual(state.posts[0].context, "Selected post")
        self.assertIsNone(state.next_branch)

    def test_prepend_earlier_pages_without_duplicates_or_repeated_requests(self):
        root = node("root")
        parent = node("parent", root)
        selected = node("selected", parent)
        parent["parent"] = (
            None  # Ancestor response stopped here, but the record retains its parent ref.
        )
        page = thread_from(selected)
        self.assertEqual(page.earlier, root["post"]["uri"])
        state = Conversation(selected["post"]["uri"])
        state.merge(page, state.anchor)
        self.assertEqual(state.earlier, root["post"]["uri"])
        state.merge(thread_from(root, include_replies=False), state.earlier, earlier=True)
        self.assertEqual([p.text for p in state.posts], ["root", "parent", "selected"])
        self.assertFalse(state.earlier)
        self.assertEqual(len({p.uri for p in state.posts}), 3)
        repeated = ThreadPage((state.posts[0],), earlier=root["post"]["uri"])
        self.assertEqual(state.merge(repeated, root["post"]["uri"], earlier=True), 0)
        self.assertFalse(state.earlier)

    def test_threadgate_hidden_reply_is_a_gap_but_direct_open_remains_readable(self):
        root = node("root", reply_count=1)
        child = node("child", root)
        root["replies"] = [child]
        child_uri = child["post"]["uri"]
        root["post"]["threadgate"] = {"record": {"hiddenReplies": [child_uri]}}
        page = thread_from(root)
        self.assertNotIn(child_uri, [post.uri for post in page.posts])
        self.assertEqual(page.gaps[0].kind, "hidden")
        self.assertEqual(thread_from(child).posts[-1].uri, child_uri)

    def test_deleted_blocked_and_cyclic_nodes_do_not_break_context_or_spin(self):
        root = node("root", reply_count=2)
        root["replies"] = [{"uri": "at://invented/deleted", "notFound": True}, root]
        page = thread_from(root)
        self.assertTrue(page.unavailable)
        self.assertEqual(len(page.posts), 1)
        state = Conversation(root["post"]["uri"])
        state.merge(page, state.anchor)
        self.assertIsNone(state.next_branch)
        self.assertIn("unavailable", state.message)

    def test_server_repeats_no_children_frontier_only_once(self):
        root = node("root", reply_count=3)
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        self.assertIsNone(state.next_branch)
        self.assertEqual(state.fetched, {state.anchor})

    def test_reaction_updates_survive_loading_and_keep_conversation_context(self):
        root = node("root")
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        state.update_post(replace(state.posts[0], likes=1, context="In a conversation"))
        state.merge(thread_from(root), state.anchor)
        self.assertEqual(state.posts[0].likes, 1)
        self.assertEqual(state.posts[0].context, "Selected post")

    def test_conversation_is_bounded_and_never_drops_the_selected_post(self):
        root = node("root")
        root["replies"] = [node(str(i)) for i in range(300)]
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        self.assertEqual(len(state.posts), 250)
        self.assertEqual(state.posts[0].uri, state.anchor)
        self.assertTrue(state.limited)
        self.assertIsNone(state.next_branch)
        self.assertIn("Open a message", state.message)
        added = replace(state.posts[-1], uri="at://invented/extra")
        self.assertEqual(state.merge(ThreadPage((added,)), state.anchor), 0)

    def test_siblings_sort_oldest_first_with_causal_subtrees_and_invalid_dates_last(self):
        root = node("root")
        early = node("early", root)
        late = node("late", root)
        grandchild = node("grandchild", early)
        invalid = node("invalid", root)
        early["post"]["record"]["createdAt"] = "2026-10-27T11:01:00Z"
        late["post"]["record"]["createdAt"] = "2026-10-27T12:02:00+01:00"
        grandchild["post"]["record"]["createdAt"] = "2026-10-27T11:04:00Z"
        invalid["post"]["record"]["createdAt"] = "not-a-date"
        early["parent"] = late["parent"] = grandchild["parent"] = invalid["parent"] = None
        early["replies"] = [grandchild]
        root["replies"] = [late, invalid, early]
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        self.assertEqual(
            [p.text for p in state.posts], ["root", "early", "grandchild", "late", "invalid"]
        )
        self.assertEqual(state.positions[grandchild["post"]["uri"]].depth, 2)
        self.assertTrue(state.positions[late["post"]["uri"]].branch_start)

    def test_projection_retains_gaps_and_continuations_at_their_branch(self):
        from skyloom.conversation import Continuation, ThreadGap

        root = node("root")
        first = node("first", root, reply_count=3)
        second = node("second", root)
        first["parent"] = second["parent"] = None
        root["replies"] = [second, {"uri": "at://invented/blocked", "blocked": True}, first]
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        rows = state.project()
        self.assertEqual(
            [getattr(p, "text", type(p).__name__) for p in rows],
            ["root", "first", "Continuation", "second", "ThreadGap"],
        )
        self.assertIsInstance(rows[2], Continuation)
        self.assertEqual(rows[2].parent, first["post"]["uri"])
        self.assertIsInstance(rows[-1], ThreadGap)
        self.assertEqual(state.parents[rows[-1].uri], state.anchor)

    def test_refresh_updates_records_without_losing_deeper_loaded_branches(self):
        root = node("root")
        child = node("child", root, reply_count=1)
        child["parent"] = None
        root["replies"] = [child]
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        grandchild = node("grandchild", child)
        grandchild["parent"] = None
        child["replies"] = [grandchild]
        state.merge(thread_from(child), child["post"]["uri"])
        child["replies"] = None
        root["post"]["record"]["text"] = "Updated root"
        state.merge(thread_from(root), state.anchor)
        self.assertEqual([p.text for p in state.posts], ["Updated root", "child", "grandchild"])

    def test_new_older_sibling_inserts_without_changing_existing_sibling_order(self):
        root = node("root")
        later = node("later", root)
        later["post"]["record"]["createdAt"] = "2026-10-27T12:02:00Z"
        later["parent"] = None
        root["replies"] = [later]
        state = Conversation(root["post"]["uri"])
        state.merge(thread_from(root), state.anchor)
        earlier = node("earlier", root)
        earlier["parent"] = None
        root["replies"] = [later, earlier]
        state.merge(thread_from(root), state.anchor)
        self.assertEqual([p.text for p in state.posts], ["root", "earlier", "later"])
        self.assertEqual(len({p.uri for p in state.posts}), 3)
