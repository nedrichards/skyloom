"""Invented-data prefetch work counters and optional native top-jump measurements.

Run in GNOME 51 with PYTHONPATH selecting either installed or candidate code.
Use separate processes and identical arguments for before/after comparisons.
This records CPU/wall samples, not hardware energy or physical-input acceptance.
"""

import argparse
import hashlib
import importlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


def provenance():
    modules = (
        "application",
        "conversation",
        "list_interaction",
        "reading",
        "refresh_monitor",
        "request_scope",
        "service",
        "thread_context",
        "thread_prefetch",
        "widgets",
        "window",
        "worker",
    )
    result = {}
    for name in modules:
        module = importlib.import_module("skyloom." + name)
        path = Path(module.__file__).resolve()
        result[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    probe = Path(__file__).resolve()
    return {
        "modules": result,
        "probe_path": str(probe),
        "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
    }


def elapsed(callback, iterations=1):
    start, cpu = time.perf_counter(), time.process_time()
    for _ in range(iterations):
        callback()
    return {
        "iterations": iterations,
        "wall_ms": round((time.perf_counter() - start) * 1000, 3),
        "cpu_ms": round((time.process_time() - cpu) * 1000, 3),
    }


def micro():
    from skyloom.conversation import ThreadPage
    from skyloom.domain import Author, Post
    from skyloom.refresh import Connection
    from skyloom.thread_context import ThreadContext
    from skyloom.thread_prefetch import HomeThreadPrefetch, ThreadCache
    from skyloom.widgets import PostPositions
    from skyloom.window import Window

    author = Author("did:example:prefetch-probe", "probe.invalid", "Invented probe")
    base = Post("at://invented/probe/0", "cid", author, "Invented", "2026-11-01T12:00:00Z")
    posts = [
        replace(
            base,
            uri=f"at://invented/probe/{i}",
            parent=(f"at://invented/probe/{i - 1}", "cid") if i else None,
            root=(base.uri, "cid") if i else None,
            replies=int(i < 1999),
        )
        for i in range(2000)
    ]
    context = ThreadContext()
    result = {"context_bulk_2000": elapsed(lambda: context.remember(posts))}
    changed = [replace(post, replies=post.replies + 1) for post in posts[:200]]
    result["context_200_changed_single_remembers"] = elapsed(
        lambda: [context.remember([post]) for post in changed]
    )
    result["context_200_unchanged_single_remembers"] = elapsed(
        lambda: [context.remember([post]) for post in changed]
    )
    cache = ThreadCache()
    for group in range(32):
        page = ThreadPage(
            tuple(
                replace(
                    base,
                    uri=f"at://invented/{group}/{i}",
                    parent=(f"at://invented/{group}/{i - 1}", "cid") if i else None,
                )
                for i in range(250)
            )
        )
        cache.put(page.posts[0].uri, page)
    result["cache_1000_oldest_hits"] = elapsed(lambda: cache.get("at://invented/0/249"), 1000)
    result["cache_1000_misses"] = elapsed(lambda: cache.get("at://invented/missing"), 1000)

    class Row:
        def __init__(self, post):
            self.post, self.updates = post, 0

        def update_position(self, _position):
            self.updates += 1

    owner = PostPositions()
    known = [replace(base, uri=f"at://invented/independent/{i}") for i in range(1000)]
    owner.remember(known)
    rows = [Row(post) for post in known]
    for row in rows:
        owner.rows.add(row)
    result["unrelated_prefetch_250"] = elapsed(lambda: owner.remember(posts[:250]))
    result["unrelated_prefetch_unchanged_row_updates"] = sum(row.updates for row in rows)

    import skyloom.thread_prefetch as prefetch_module

    class TimerSink:
        def __init__(self):
            self.adds = self.removes = 0

        def timeout_add(self, *_args):
            self.adds += 1
            return self.adds

        def source_remove(self, _source):
            self.removes += 1

    sink = TimerSink()
    view = SimpleNamespace(
        paging=SimpleNamespace(closed=False),
        get_mapped=lambda: True,
        connect=lambda *_args: 1,
        cleanups=[],
    )
    window = SimpleNamespace(
        views=[view],
        is_active=lambda: True,
        read_only=False,
        connect=lambda *_args: 1,
        disconnect=lambda *_args: None,
        automatic_pause_reason=lambda: "",
        page_requests={},
        interactions=SimpleNamespace(
            current_view=lambda: view,
            context=lambda: "list",
            connection_changed=lambda _connection: None,
        ),
        motion=SimpleNamespace(changed=lambda: None),
    )
    original = prefetch_module.GLib
    try:
        prefetch_module.GLib = sink
        prefetch = HomeThreadPrefetch(window, view, ThreadCache())
        view.viewport_changed = prefetch.schedule
        view.prefetch_reconsider = getattr(prefetch, "reconsider", prefetch.schedule)
        result["unchanged_connection_dispatches_200"] = elapsed(
            lambda: Window.connection_changed(window, Connection()), 200
        )
        result["unchanged_connection_timer_adds"] = sink.adds
        result["unchanged_connection_timer_removes"] = sink.removes
    finally:
        prefetch_module.GLib = original
    return result


def native(args):
    from gi.repository import GLib, Gtk

    from skyloom.application import Application
    from skyloom.domain import Pager
    from skyloom.widgets import FeedView

    app = Application(demo=True)
    records, counts = [], {"binds": 0, "unbinds": 0}
    original_bind, original_unbind = FeedView.bind, FeedView.unbind
    state = {"failure": None}

    def bind(*params):
        counts["binds"] += 1
        return original_bind(*params)

    def unbind(*params):
        counts["unbinds"] += 1
        return original_unbind(*params)

    FeedView.bind, FeedView.unbind = bind, unbind

    def fail(kind, value, traceback):
        import traceback as trace

        state["failure"] = f"{kind.__name__}: {value}"
        trace.print_exception(kind, value, traceback)
        app.quit()

    previous_hook = sys.excepthook
    sys.excepthook = fail

    def activated(_app):
        window = app.window
        window.set_title("Skyloom — invented prefetch/top-jump performance probe")
        window.is_active = lambda: True
        window.set_default_size(args.width, 820)
        window.refresh_monitor.close()
        state["renderer"] = window.get_renderer().__gtype__.name
        state["gtk_enable_animations"] = Gtk.Settings.get_default().get_property(
            "gtk-enable-animations"
        )
        started = time.perf_counter()

        def ready():
            if window.page_requests:
                if time.perf_counter() - started > 10:
                    raise RuntimeError("Initial invented feed did not settle")
                return True
            view = window.feed_views["following"]
            view.viewport_changed = lambda: None
            view.load_more = lambda: None
            view.check_start = lambda: False
            base = app.service.posts[0]
            posts = [
                replace(
                    base,
                    uri=f"at://invented/jump/{i}",
                    images=(),
                    quote=None,
                    external=None,
                    labels=(),
                    replies=0,
                    parent=None,
                    root=None,
                    text=f"Invented post {i}. " + "Readable native content. " * 8,
                )
                for i in range(args.posts)
            ]
            pager = Pager()
            pager.posts = posts
            window.pagers["following"] = pager
            view.set_posts(posts, reset=True)
            view.paging.complete(None, len(posts))
            adjustment = view.scroll.get_vadjustment()
            targets = [min(45, args.posts - 1), args.posts - 1] * args.iterations

            def prepare():
                if not targets:
                    app.quit()
                    return False
                target = targets.pop(0)
                view.interaction.select(target)
                GLib.timeout_add(500, jump, target)
                return False

            def jump(target):
                if view.position_tick is not None or view.check_pending:
                    return True
                before = view.interaction.capture()
                if before is None or adjustment.get_value() <= adjustment.get_page_size():
                    raise RuntimeError("Jump source is not a distant rendered reading position")
                sample = {
                    "source_index": target,
                    "source_key": before.key,
                    "source_offset": before.offset,
                    "source_scroll": adjustment.get_value(),
                    "adjustment_values": [],
                    "counts_before": counts.copy(),
                }
                signal = adjustment.connect(
                    "value-changed", lambda adj: sample["adjustment_values"].append(adj.get_value())
                )
                wall, cpu = time.perf_counter(), time.process_time()
                place = view.interaction.top()
                sample["action_ms"] = round((time.perf_counter() - wall) * 1000, 3)
                stable = 0

                def landed():
                    nonlocal stable
                    if time.perf_counter() - wall > 5:
                        raise RuntimeError("Top jump did not settle")
                    settled = (
                        adjustment.get_value() <= 1
                        and view.position_tick is None
                        and not view.check_pending
                    )
                    stable = stable + 1 if settled else 0
                    if stable < 3:
                        return True
                    adjustment.disconnect(signal)
                    sample["settled_ms"] = round((time.perf_counter() - wall) * 1000, 3)
                    sample["cpu_ms"] = round((time.process_time() - cpu) * 1000, 3)
                    sample["row_binds"] = counts["binds"] - sample["counts_before"]["binds"]
                    sample["row_unbinds"] = counts["unbinds"] - sample["counts_before"]["unbinds"]
                    del sample["counts_before"]
                    sample["mapped_rows"] = sum(row.get_mapped() for row in view.rows)
                    if not view.interaction.restore(place):
                        raise RuntimeError("Jump Undo anchor unavailable")

                    restore_started = time.perf_counter()

                    def restored():
                        if time.perf_counter() - restore_started > 5:
                            raise RuntimeError("Jump Undo did not settle")
                        if view.position_tick is not None or view.check_pending:
                            return True
                        actual = view.interaction.capture()
                        sample["undo_key_matches"] = bool(actual and actual.key == place.key)
                        sample["undo_offset_error"] = (
                            abs(actual.offset - place.offset) if actual else None
                        )
                        records.append(sample)
                        if not sample["undo_key_matches"] or sample["undo_offset_error"] > 3:
                            raise RuntimeError("Jump Undo changed the reading anchor")
                        GLib.timeout_add(150, prepare)
                        return False

                    GLib.timeout_add(30, restored)
                    return False

                GLib.timeout_add(10, landed)
                return False

            GLib.timeout_add(700, prepare)
            return False

        GLib.timeout_add(100, ready)

    app.connect_after("activate", activated)
    try:
        app.run([])
    finally:
        FeedView.bind, FeedView.unbind = original_bind, original_unbind
        sys.excepthook = previous_hook
    if state["failure"]:
        raise RuntimeError(state["failure"])
    if len(records) != args.iterations * 2:
        raise RuntimeError("Native probe ended before all requested jumps completed")
    return {
        "renderer": state.get("renderer"),
        "gtk_enable_animations": state.get("gtk_enable_animations"),
        "posts": args.posts,
        "width": args.width,
        "iterations": args.iterations,
        "settled_ms_scope": "10 ms polling plus three stable checks; not frame-presentation latency",
        "jumps": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--posts", type=int, default=250)
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    if args.posts < 50 or args.iterations < 1:
        parser.error("Use at least 50 posts and one iteration")
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk

    if args.native:
        if not Gtk.init_check():
            parser.error("Native probe requires a graphical display")
        Adw.init()
    code_before = provenance()
    result = {
        "schema": 2,
        "code_before": code_before,
        "python": sys.version,
        "scope": "Invented isolated process; no live account or external requests",
        "micro": micro(),
    }
    if args.native:
        result["native"] = native(args)
    result["code_after"] = provenance()
    result["source_files_unchanged_during_probe"] = result["code_after"] == code_before
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not result["source_files_unchanged_during_probe"]:
        raise RuntimeError("Source files changed during the probe; discard comparative timing")
    print(f"PREFETCH_PERFORMANCE_PROBE_PASS: {args.output}")


if __name__ == "__main__":
    main()
