"""Measure synthetic native cell binding, not compositor frame rate or live scrolling."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from weakref import WeakSet

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from skyloom import APP_ID  # noqa: E402
from skyloom.domain import Author, Post  # noqa: E402
from skyloom.widgets import PostRow  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("construct", "reuse"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bindings", type=int, default=1000)
    args = parser.parse_args()
    if not 10 <= args.bindings <= 10000:
        parser.error("Use 10..10000 bindings")
    if not Gtk.init_check():
        parser.error("Native GTK display required")
    Adw.init()
    schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
    window = SimpleNamespace(
        settings=Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None),
        mutations=set(),
        read_only=False,
        content_gates=WeakSet(),
        revealed_labels={},
    )
    post = Post(
        "at://did:example:cell/app.bsky.feed.post/0",
        "invented-cid",
        Author("did:example:cell", "cell.invalid", "Invented author"),
        "Invented selectable text for native cell binding. " * 5,
        "2026-11-08T12:00:00Z",
    )
    counts = {"text_trees": 0, "action_trees": 0}
    original_text, original_actions = PostRow.create_text, PostRow.create_actions

    def create_text(self, owner):
        counts["text_trees"] += 1
        return original_text(self, owner)

    def create_actions(self, value, owner):
        counts["action_trees"] += 1
        return original_actions(self, value, owner)

    PostRow.create_text, PostRow.create_actions = create_text, create_actions
    samples = []
    cell = None
    try:
        for n in range(args.bindings):
            value = replace(post, uri=f"at://did:example:cell/app.bsky.feed.post/{n}", likes=n)
            start = perf_counter()
            if args.mode == "construct" or cell is None:
                cell = PostRow(value, window)
            else:
                cell.bind_post(value)
            cell.cancel()
            samples.append((perf_counter() - start) * 1000)
    finally:
        PostRow.create_text, PostRow.create_actions = original_text, original_actions
    ordered = sorted(samples)
    result = {
        "scope": "unmapped text-only native cells; construct simulates discarded rows, not an old binary",
        "mode": args.mode,
        "bindings": args.bindings,
        **counts,
        "total_ms": round(sum(samples), 3),
        "p50_ms": round(ordered[len(ordered) // 2], 3),
        "p95_ms": round(ordered[int(len(ordered) * 0.95)], 3),
        "max_ms": round(max(samples), 3),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
