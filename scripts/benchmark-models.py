"""Synthetic DTO allocation benchmark. Run in the installed Flatpak with source override.

The timestamp control deliberately retains the former replace-before-parse operation.
These measurements exclude GTK, network, decoder and process-wide memory.
"""

import gc
import json
import statistics
import sys
import timeit
import tracemalloc
from datetime import datetime

from skyloom.domain import post_from

RECORD = {
    "uri": "at://did:plc:invented/app.bsky.feed.post/1",
    "cid": "invented",
    "author": {"did": "did:plc:invented", "handle": "example.test", "displayName": "Invented"},
    "record": {"text": "Synthetic benchmark post", "createdAt": "2026-10-27T12:34:56.123Z"},
    "embed": {"images": [{"thumb": "https://example.test/image", "alt": "Invented image"}] * 2},
}
STAMP = "2026-10-27T12:34:56.123Z"


def replaced_timestamp():
    return datetime.fromisoformat(STAMP.replace("Z", "+00:00"))  # noqa: FURB162 — benchmark control.


def direct_timestamp():
    return datetime.fromisoformat(STAMP)


def main():
    post_from(RECORD)  # Warm imports and URL parsing before tracing.
    allocations = []
    for _ in range(7):
        gc.collect()
        tracemalloc.start()
        posts = [post_from(RECORD) for _ in range(1000)]
        allocations.append(tracemalloc.get_traced_memory()[0])
        tracemalloc.stop()
        del posts
    # Alternate order after warm-up to reduce CPU frequency/order effects.
    timeit.timeit(replaced_timestamp, number=100000)
    timeit.timeit(direct_timestamp, number=100000)
    replaced, direct = [], []
    for index in range(10):
        operations = [(replaced_timestamp, replaced), (direct_timestamp, direct)]
        for operation, samples in operations[:: -1 if index % 2 else 1]:
            samples.append(timeit.timeit(operation, number=100000))
    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "posts": 1000,
                "median_retained_bytes": statistics.median(allocations),
                "mapping_1000_seconds": statistics.median(
                    timeit.repeat(
                        lambda: [post_from(RECORD) for _ in range(1000)], number=1, repeat=9
                    )
                ),
                "timestamp_replace_100000_seconds": statistics.median(replaced),
                "timestamp_direct_100000_seconds": statistics.median(direct),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
