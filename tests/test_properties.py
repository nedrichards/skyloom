"""Bounded, reproducible generated cases for untrusted text, cache and paging boundaries."""

import asyncio
import html
import json
import os
import random
import re
import unittest
from dataclasses import asdict

from skyloom.domain import Author, Post
from skyloom.pagination import AutoPager
from skyloom.richtext import counts, facets_for, markup, validate
from skyloom.storage import post_restore

CASES = min(5000, max(1, int(os.getenv("SKYLOOM_PROPERTY_CASES", "50"))))
SEED = 0x5A7100
CLUSTERS = ("a", "<", "&", "é", "e\u0301", "👩🏽‍💻", "🇬🇧", "क्‍ष", "\n")


class GeneratedBoundaryTests(unittest.TestCase):
    def test_unicode_limits_and_facet_byte_boundaries(self):
        rng = random.Random(SEED)  # noqa: S311 — deterministic invented test data.

        async def resolve(_handle):
            return "did:plc:invented"

        for case in range(CASES):
            with self.subTest(seed=SEED, case=case):
                prefix = "".join(rng.choices(CLUSTERS, k=rng.randrange(320)))
                text = prefix + " https://example.invalid/path @person.invalid #invented"
                graphemes, size = counts(text)
                self.assertEqual(bool(validate(text)), graphemes > 300 or size > 3000)
                raw = text.encode("utf-8")
                facets = asyncio.run(facets_for(text, resolve))
                previous = 0
                for facet in facets:
                    start = facet["index"]["byteStart"]
                    end = facet["index"]["byteEnd"]
                    self.assertGreaterEqual(start, previous)
                    self.assertTrue(raw[start:end].decode("utf-8"))
                    raw[:start].decode("utf-8")
                    raw[end:].decode("utf-8")
                    previous = end
                # Malformed offsets/features must not lose or inject visible text.
                broken = [
                    {
                        "index": {
                            "byteStart": rng.randrange(-10, len(raw) + 10),
                            "byteEnd": rng.randrange(-10, len(raw) + 10),
                        },
                        "features": [None],
                    },
                    {"index": {"byteStart": True, "byteEnd": "bad"}},
                    None,
                ]
                rendered = markup(text, (*facets, *broken))
                self.assertEqual(html.unescape(re.sub(r"<[^>]*>", "", rendered)), text)
                self.assertNotIn("<script", rendered)

    def test_cache_json_roundtrips_and_corruption_rejection(self):
        rng = random.Random(SEED + 1)  # noqa: S311 — deterministic invented test data.
        for case in range(CASES):
            with self.subTest(seed=SEED + 1, case=case):
                post = Post(
                    f"at://did:plc:invented/app.bsky.feed.post/{case}",
                    "invented-cid",
                    Author("did:plc:invented", "person.invalid", "Invented"),
                    "".join(rng.choices(CLUSTERS, k=rng.randrange(100))),
                    "2026-11-14T12:00:00Z",
                )
                encoded = json.loads(json.dumps(asdict(post)))
                self.assertEqual(post_restore(encoded), post)
                # Missing mandatory fields and unknown schema keys are rejected,
                # rather than becoming a partly restored production record.
                if rng.randrange(2):
                    del encoded[rng.choice(("author", "images", "uri", "cid"))]
                else:
                    encoded[f"unknown{case}"] = rng.choice((None, [], {}))
                with self.assertRaises((KeyError, TypeError)):
                    post_restore(encoded)

    def test_generated_paging_sequences_never_overlap_or_auto_retry(self):
        rng = random.Random(SEED + 2)  # noqa: S311 — deterministic invented test data.
        for case in range(CASES):
            with self.subTest(seed=SEED + 2, case=case):
                calls = []
                pager = AutoPager(lambda calls=calls: calls.append(True))
                seen = set()
                for _ in range(20):
                    cursor, added = rng.choice((None, "a", "b", "c")), rng.randrange(3)
                    pager.complete(cursor, added)
                    requested = pager.request(automatic=True)
                    self.assertEqual(requested, bool(cursor and added and cursor not in seen))
                    if requested:
                        seen.add(cursor)
                    self.assertFalse(pager.request(automatic=True))
                    if rng.randrange(3) == 0:
                        pager.fail("Invented offline error")
                        before = len(calls)
                        self.assertFalse(pager.near_end(0, 100, 600))
                        self.assertEqual(len(calls), before)
                pager.closed = True
                self.assertFalse(pager.request())
