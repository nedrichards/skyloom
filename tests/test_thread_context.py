"""Position knowledge uses only invented relationships, never fetches or stores text."""

import unittest
from dataclasses import replace

from test_conversation import node

from skyloom.domain import post_from
from skyloom.thread_context import ThreadContext


class ThreadContextTests(unittest.TestCase):
    def setUp(self):
        root = node("root", reply_count=2)
        first = node("first", root, reply_count=1)
        self.posts = [
            post_from(item["post"])
            for item in (root, first, node("second", root), node("child", first))
        ]
        self.context = ThreadContext()

    def test_parent_first_order_is_independent_of_feed_order_and_authors(self):
        root, first, second, child = self.posts
        second = replace(second, author=replace(second.author, did="did:example:other"))
        self.context.remember([second, child, first, root])
        for index, post in enumerate((root, first, child, second), start=1):
            self.assertEqual(self.context.positions[post.uri], (index, 4, False))

    def test_missing_context_is_partial_and_later_pages_enrich_retained_positions(self):
        root, first, second, child = self.posts
        self.context.remember([first])
        self.assertNotIn(first.uri, self.context.positions)
        self.context.remember([second])
        self.assertEqual(self.context.positions[first.uri], (1, 2, True))
        self.context.remember([root, child])
        self.assertEqual(self.context.positions[first.uri], (2, 4, False))
        self.context.remember([first])
        self.assertEqual(self.context.positions[first.uri], (2, 4, False))

    def test_reply_count_alone_does_not_produce_a_pill(self):
        root = self.posts[0]
        self.context.remember([root])
        self.assertNotIn(root.uri, self.context.positions)
        self.context.remember([self.posts[1]])
        self.assertEqual(self.context.positions[root.uri], (1, 2, True))

    def test_independent_posts_do_not_acquire_pills_and_quotes_are_not_edges(self):
        plain = post_from(node("plain")["post"])
        self.context.remember([replace(plain, quote=self.posts[0]), *self.posts])
        self.assertNotIn(plain.uri, self.context.positions)
        self.assertEqual(self.context.positions[self.posts[0].uri], (1, 4, False))

    def test_single_message_has_no_pill_even_when_opened_or_incomplete(self):
        plain = post_from(node("plain")["post"])
        self.context.remember([plain], incomplete=True)
        self.assertNotIn(plain.uri, self.context.positions)
        self.context.remember([plain], incomplete=False)
        self.assertNotIn(plain.uri, self.context.positions)
        self.context.remember([plain])
        self.assertNotIn(plain.uri, self.context.positions)

    def test_reaction_only_remember_retains_metadata_and_projection(self):
        self.context.remember(self.posts)
        original = dict(self.context.messages)
        projection = self.context.positions
        for post in self.posts:
            self.assertFalse(self.context.remember([replace(post, likes=post.likes + 1)]))
            self.assertIs(self.context.messages[post.uri], original[post.uri])
        self.assertIs(self.context.positions, projection)
        changed = replace(self.posts[0], replies=self.posts[0].replies + 1)
        self.assertTrue(self.context.remember([changed]))
        self.assertIsNot(self.context.messages[changed.uri], original[changed.uri])
        self.assertTrue(self.context.positions[changed.uri][2])

    def test_unchanged_metadata_still_promotes_lru_and_preserves_context(self):
        root, first, second, _ = self.posts
        context = ThreadContext(limit=2)
        context.remember([root, first], incomplete=True)
        original = context.messages[root.uri]
        self.assertFalse(context.remember([replace(root, likes=1)]))
        self.assertIs(context.messages[root.uri], original)
        self.assertTrue(original.incomplete)
        self.assertTrue(original.conversation)
        context.remember([second])
        self.assertIn(root.uri, context.messages)
        self.assertNotIn(first.uri, context.messages)
        context.remember([root], incomplete=False, parents={root.uri: second.uri})
        self.assertFalse(context.messages[root.uri].incomplete)
        self.assertEqual(context.messages[root.uri].parent, second.uri)

    def test_bounded_metadata_eviction_keeps_counts_honest_and_handles_cycles(self):
        context = ThreadContext(limit=2)
        root, first, second, child = self.posts
        context.remember([root, first, second, child])
        self.assertEqual(len(context.messages), 2)
        self.assertTrue(all(value[2] for value in context.positions.values()))
        self.assertFalse(hasattr(next(iter(context.messages.values())), "text"))
        first = replace(first, parent=(child.uri, child.cid), root=None)
        child = replace(child, root=None)
        context.remember([first, child])
        self.assertEqual(len(context.positions), 2)
        self.assertTrue(all(value[2] for value in context.positions.values()))
