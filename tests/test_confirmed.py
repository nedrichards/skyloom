"""Confirmed writes survive lagging SDK reads without leaking across sessions."""

import unittest
from dataclasses import replace

from skyloom.confirmed import ConfirmedChanges, at_or_before
from skyloom.domain import Author, Post, deleted_post

DID = "did:example:invented"
URI = f"at://{DID}/app.bsky.feed.post/invented"
CID = "invented-cid"


class ConfirmedStateTests(unittest.TestCase):
    def test_independent_fields_expire_and_memory_is_bounded(self):
        now = [0]
        state = ConfirmedChanges(object(), clock=lambda: now[0], ttl=120, limit=3)
        author = Author(DID, "invented.invalid", "Invented")
        state.remember("author", DID, muted=True)
        now[0] = 60
        state.remember("author", DID, following="confirmed-follow")
        now[0] = 121
        result = state.author(author)
        self.assertFalse(result.muted)
        self.assertEqual(result.following, "confirmed-follow")
        for n in range(10):
            state.remember("author", str(n), muted=True)
        self.assertLessEqual(len(state.values), 3)

    def test_nested_quotes_and_tombstones_keep_their_own_fields(self):
        state = ConfirmedChanges(object())
        author = Author(DID, "invented.invalid", "Invented")
        post = Post(URI, CID, author, "Invented", "")
        state.remember("author", DID, muted=True)
        state.remember("post", URI, like_uri="confirmed-like", likes=2)
        result = state.post(replace(post, uri=URI + "quote", quote=post))
        self.assertTrue(result.author.muted)
        self.assertEqual(result.quote.like_uri, "confirmed-like")
        self.assertFalse(state.post(deleted_post(post)).like_uri)

    def test_seen_cutoff_compares_instants_and_rejects_invalid_times(self):
        self.assertTrue(at_or_before("2026-11-14T01:00:00+01:00", "2026-11-14T00:00:00Z"))
        self.assertFalse(at_or_before("invalid", "2026-11-14T00:00:00Z"))
        self.assertFalse(at_or_before("2026-11-14T00:00:00", "2026-11-14T00:00:00Z"))
