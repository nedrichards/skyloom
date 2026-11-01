"""Profile real native widgets with invented data; no credentials or external requests.

Run inside the installed Flatpak with the checkout exposed (see docs/PERFORMANCE.md).
Frame sampling is passive except for scripted scrolling. cProfile is a separate run
because its overhead invalidates frame comparisons. Raw captures belong in build*/.
"""

import argparse
import cProfile
import json
import math
import os
import resource
import sys
import time
from dataclasses import replace
from itertools import pairwise
from pathlib import Path


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {
        "samples": len(ordered),
        "p50_ms": round(ordered[math.ceil(len(ordered) * 0.5) - 1], 3),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
        "p99_ms": round(ordered[math.ceil(len(ordered) * 0.99) - 1], 3),
        "max_ms": round(ordered[-1], 3),
        "over_16_67_ms": sum(value > 1000 / 60 for value in ordered),
        "over_25_ms": sum(value > 25 for value in ordered),
        "over_50_ms": sum(value > 50 for value in ordered),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline", type=Path, help="Fail if a matching baseline exceeds comparison budgets"
    )
    parser.add_argument("--profile", action="store_true", help="Separate main-thread cProfile run")
    parser.add_argument("--reduced-motion", action="store_true")
    parser.add_argument(
        "--idle-only",
        action="store_true",
        help="Quiet mapped and unmapped CPU/context-switch samples",
    )
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--posts", type=int, choices=(30, 100, 250), default=250)
    parser.add_argument(
        "--interactions-only",
        action="store_true",
        help="Editing, notices, menus and connectivity workloads",
    )
    parser.add_argument(
        "--startup-only", action="store_true", help="Short first-frame/process startup measurement"
    )
    parser.add_argument(
        "--scroll-only",
        action="store_true",
        help="Short content scrolling run for renderer comparisons",
    )
    parser.add_argument(
        "--control", action="store_true", help="Short plain-label list control; not the app score"
    )
    args = parser.parse_args()
    os.environ["GSETTINGS_BACKEND"] = "memory"
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk

    from skyloom.application import Application
    from skyloom.conversation import ThreadPage
    from skyloom.domain import Media, Notice, Page, Pager
    from skyloom.refresh import Connection
    from skyloom.service import Attachment
    from skyloom.widgets import FeedView, PostRow

    process_started = float(
        Path("/proc/self/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[19]
    ) / os.sysconf("SC_CLK_TCK")
    application = Application(demo=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile() if args.profile else None
    records, counters = [], {"row_binds": 0, "row_unbinds": 0, "image_calls": 0}
    bind, unbind, image_get = FeedView.bind, FeedView.unbind, application.images.get

    def counted_bind(*params):
        counters["row_binds"] += 1
        return bind(*params)

    def counted_unbind(*params):
        counters["row_unbinds"] += 1
        return unbind(*params)

    async def counted_image(*params, **kwargs):
        counters["image_calls"] += 1
        return await image_get(*params, **kwargs)

    FeedView.bind, FeedView.unbind = counted_bind, counted_unbind
    application.images.get = counted_image
    state = {
        "failure": None,
        "name": "startup",
        "frames": [],
        "spans": [],
        "actions": [],
        "callbacks": [],
    }
    dispatch = getattr(application.worker, "dispatch", None)
    if dispatch is not None:

        def timed_dispatch(callback, value):
            started = time.perf_counter()
            try:
                return dispatch(callback, value)
            finally:
                state["callbacks"].append((time.perf_counter() - started) * 1000)

        application.worker.dispatch = timed_dispatch
    launch = time.perf_counter()
    if profiler:
        profiler.enable()

    def failed(kind, value, traceback):
        import traceback as tb

        state["failure"] = kind.__name__
        tb.print_exception(kind, value, traceback)
        application.quit()

    sys.excepthook = failed

    def activated(_app):
        window = application.window
        # Window activity is a fixture input, as in controller/GUI scenarios.
        window.is_active = lambda: True
        window.set_title("Skyloom — invented-data performance fixture")
        window.set_default_size(args.width, 820)
        window.refresh_monitor.close()
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-enable-animations", not args.reduced_motion)
        settings.set_property(
            "gtk-interface-reduced-motion",
            Gtk.ReducedMotion.REDUCE if args.reduced_motion else Gtk.ReducedMotion.NO_PREFERENCE,
        )
        clock = window.get_frame_clock()
        state["renderer"] = window.get_renderer().__gtype__.name
        state["monitor_hz"] = (
            window.get_display().get_monitors().get_item(0).get_refresh_rate() / 1000
        )
        state.update(
            start=time.perf_counter(),
            cpu=time.process_time(),
            before=counters.copy(),
            usage=resource.getrusage(resource.RUSAGE_SELF),
        )

        def before(_clock):
            state["paint_start"] = time.perf_counter()

        def after(frame_clock):
            now = time.perf_counter()
            state["spans"].append((now - state.get("paint_start", now)) * 1000)
            state["frames"].append((now, frame_clock.get_current_timings()))
            state.setdefault("first_frame_ms", (now - launch) * 1000)
            state.setdefault(
                "process_first_frame_ms",
                (time.clock_gettime(time.CLOCK_BOOTTIME) - process_started) * 1000,
            )

        clock.connect("before-paint", before)
        clock.connect("after-paint", after)
        base = application.service.posts[0]
        posts = [
            replace(
                base,
                uri=f"at://did:example:performance/app.bsky.feed.post/{i}",
                text=f"Invented post {i}. " + "Readable native text, links and images. " * 6,
                images=(Media("demo-landscape", "Invented landscape", local=True),) * 2
                if i % 3 == 0
                else (),
                quote=application.service.posts[1] if i % 5 == 0 else None,
                labels=("sexual",) if i % 7 == 0 else (),
            )
            for i in range(args.posts)
        ]
        home = window.feed_views["following"]
        if args.control:
            home.render = lambda post: Gtk.Label(
                label=post.text, wrap=True, margin_top=20, margin_bottom=20
            )
            home.feed_preview = False

        async def thread(uri, **_kwargs):
            await application.service.pause()
            return ThreadPage(
                tuple(
                    replace(
                        post,
                        parent=(posts[(i - 1) // 3].uri, posts[(i - 1) // 3].cid) if i else None,
                        root=(posts[0].uri, posts[0].cid) if i else None,
                    )
                    for i, post in enumerate(posts)
                )
            )

        application.service.thread = thread

        def feed():
            if window.split.get_collapsed():
                window.split.set_show_sidebar(False)
            application.service.posts = posts
            pager = Pager()
            for start in range(0, len(posts), 25):
                pager.merge(
                    Page(
                        tuple(posts[start : start + 25]),
                        str(start + 25) if start + 25 < len(posts) else None,
                    )
                )
            window.pagers["following"] = pager
            home.set_posts(pager.posts, reset=True)
            home.paging.complete(None, len(posts))

        def current():
            return window.interactions.current_view()

        def scroll(progress):
            view = current()
            if view:
                adjustment = view.scroll.get_vadjustment()
                # A realistic 1800 logical px/s sweep, not a jump through every row.
                extent = max(0, adjustment.get_upper() - adjustment.get_page_size())
                previous = adjustment.get_value()
                adjustment.set_value(min(extent, progress * 1800))
                state["scroll_distance"] += abs(adjustment.get_value() - previous)

        def scroll_back(progress):
            view = current()
            if view:
                adjustment = view.scroll.get_vadjustment()
                previous = adjustment.get_value()
                adjustment.set_value(max(0, 7200 - progress * 1800))
                state["scroll_distance"] += abs(adjustment.get_value() - previous)

        def counters_update():
            for post in window.pagers["following"].posts:
                home.update_post(replace(post, likes=post.likes + 1))

        def staged():
            arrivals = [replace(posts[0], uri=posts[0].uri + f"-new-{i}") for i in range(3)]
            window.show_feed_update("following", Page((*arrivals, *posts[:27])))

        def search():
            window.search()
            page = window.nav.get_visible_page()
            page.focus_widget.set_text("Invented")
            page.focus_widget.emit("activate")

        def labels():
            window.settings.set_boolean("warn-labelled-content", True)

        def labels_back():
            window.settings.set_boolean("warn-labelled-content", False)

        def navigate():
            window.go_home()
            window.split.set_show_sidebar(not window.split.get_show_sidebar())

        def composer_type():
            if not window.composer.ready:
                raise RuntimeError("Composer did not become ready")
            window.composer.buffer.set_text(("An invented readable draft. " * 12)[:300])

        def composer_images():
            window.composer.attachments = [
                Attachment(
                    str(application.fixture_dir / "demo-landscape.png"), f"Invented landscape {i}"
                )
                for i in range(4)
            ]
            window.composer.render_attachments()
            window.composer.changed()

        def composer_close():
            window.composer.force_close()

        async def notices(cursor=None):
            await application.service.pause()
            return (
                tuple(
                    Notice(
                        base.author,
                        "like",
                        f"at://invented/notice/{i}",
                        posts[0].uri,
                        False,
                        base.created,
                    )
                    for i in range(100)
                ),
                None,
                base.created,
            )

        def notifications():
            application.service.notifications = notices
            window.notifications()

        def walk(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from walk(child)
                child = child.get_next_sibling()

        def mark_seen():
            view = current()
            state["notice_offset"] = view.scroll.get_vadjustment().get_value()
            state["notice_objects"] = [
                view.model.get_item(i) for i in range(view.model.get_n_items())
            ]
            control = next(
                widget
                for widget in walk(window.nav.get_visible_page())
                if isinstance(widget, Gtk.Button)
                and widget.get_tooltip_text() == "Mark all notifications as seen"
            )
            control.emit("clicked")

        def notices_home():
            view = current()
            if abs(view.scroll.get_vadjustment().get_value() - state["notice_offset"]) > 2:
                raise RuntimeError("Mark seen changed the reading position")
            if not all(
                view.model.get_item(i) is obj and obj.post.read
                for i, obj in enumerate(state["notice_objects"])
            ):
                raise RuntimeError("Mark seen replaced items or failed to update read state")
            window.go_home()

        def close_dialog():
            dialog = window.get_visible_dialog()
            if dialog:
                dialog.close()

        def menu_open():
            home.interaction.top()
            rows = home.interaction.visible_rows()
            if rows:
                state["post_menu"] = rows[0][1].menu
                state["post_menu"].popup()

        extras = [
            (
                "reaction-roundtrip",
                lambda: window.mutate(window.pagers["following"].posts[0], "like"),
                None,
                0.8,
            ),
            ("composer-open", window.compose, None, 0.8),
            ("composer-type-save", composer_type, None, 1),
            ("composer-four-previews", composer_images, None, 1),
            ("composer-close", composer_close, None, 0.8),
            ("notifications-open-100", notifications, None, 1),
            ("notifications-scroll", lambda: None, scroll, 2),
            ("notifications-mark-seen", mark_seen, None, 1),
            ("interactions-home", notices_home, None, 0.8),
            ("preferences-open", window.preferences, None, 0.8),
            ("preferences-close", close_dialog, None, 0.8),
            (
                "image-open",
                lambda: window.view_media(
                    Media("demo-landscape", "Invented landscape", local=True)
                ),
                None,
                0.8,
            ),
            ("image-close", close_dialog, None, 0.8),
            ("post-menu-open", menu_open, None, 0.5),
            ("post-menu-close", lambda: state["post_menu"].popdown(), None, 0.5),
            (
                "connection-offline",
                lambda: window.connection_changed(Connection(available=False, internet=False)),
                None,
                0.5,
            ),
            ("connection-online", lambda: window.connection_changed(Connection()), None, 0.5),
        ]

        scenarios = [
            ("startup", lambda: None, None, 1),
            (f"feed-create-{args.posts}", feed, None, 1),
            ("feed-scroll-cold", lambda: None, scroll, 4),
            ("feed-scroll-warm", lambda: None, scroll_back, 4),
            (f"counter-update-{args.posts}", counters_update, None, 0.8),
            ("show-arrivals", staged, None, 1),
            ("refresh-undo", lambda: window.interactions.undo(), None, 1),
            ("labels-hide", labels, None, 0.8),
            ("labels-reveal", labels_back, None, 0.8),
            (f"conversation-open-{args.posts}", lambda: window.thread(posts[0].uri), None, 1.5),
            ("conversation-scroll", lambda: None, scroll, 4),
            ("back", lambda: window.interactions.back(), None, 0.8),
            ("profile-open", lambda: window.profile(base.author.did), None, 1.5),
            ("profile-scroll", lambda: None, scroll, 4),
            ("search-open-results", search, None, 1.5),
            ("search-scroll", lambda: None, scroll, 4),
            ("sidebar-transition", navigate, None, 0.8),
            ("sidebar-restore", navigate, None, 0.8),
            ("idle", lambda: None, None, 2),
        ]
        if args.idle_only:
            scenarios = [
                *scenarios[:1],
                ("quiet-idle", lambda: None, None, 8),
                ("unmapped-idle", lambda: window.set_visible(False), None, 8),
            ]
        elif args.interactions_only:
            scenarios = scenarios[:2] + extras + scenarios[-1:]
        elif args.startup_only:
            scenarios = scenarios[:1]
        elif args.control or args.scroll_only:
            scenarios = scenarios[:4] + scenarios[-1:]
        else:
            scenarios = scenarios[:-1] + extras + scenarios[-1:]
        stages = iter(scenarios)
        scroll_tick = None

        def finish_stage():
            now = time.perf_counter()
            usage = resource.getrusage(resource.RUSAGE_SELF)
            previous_usage = state["usage"]
            record = {
                "name": state["name"],
                "voluntary_context_switches": usage.ru_nvcsw - previous_usage.ru_nvcsw,
                "involuntary_context_switches": usage.ru_nivcsw - previous_usage.ru_nivcsw,
                "wall_ms": round((now - state["start"]) * 1000, 3),
                "cpu_ms": round((time.process_time() - state["cpu"]) * 1000, 3),
                "frames": state["frames"],
                "frame_work_ms": distribution(state["spans"]),
                "action_ms": distribution(state["actions"]),
                "worker_callback_ms": distribution(state["callbacks"]),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "post_rows": sum(isinstance(row, PostRow) for v in window.views for row in v.rows),
                "views": len(window.views),
                "scroll_distance": round(state.get("scroll_distance", 0), 1),
                "worker_jobs": len(window.worker.pending),
                **{key: value - state["before"][key] for key, value in counters.items()},
            }
            records.append(record)
            print("PHASE", record["name"], "work", record["frame_work_ms"], flush=True)

        def next_stage():
            nonlocal scroll_tick
            if scroll_tick is not None:
                window.remove_tick_callback(scroll_tick)
                scroll_tick = None
            if state["frames"] or state["actions"]:
                finish_stage()
            stage = next(stages, None)
            if stage is None:
                application.quit()
                return False
            name, setup, frame_action, duration = stage
            state.update(
                name=name,
                start=time.perf_counter(),
                cpu=time.process_time(),
                usage=resource.getrusage(resource.RUSAGE_SELF),
                before=counters.copy(),
                frames=[],
                spans=[],
                actions=[],
                callbacks=[],
                scroll_distance=0,
            )
            started = time.perf_counter()
            setup()
            state["actions"].append((time.perf_counter() - started) * 1000)
            if frame_action:

                def tick(*_):
                    started = time.perf_counter()
                    frame_action(started - state["start"])
                    state["actions"].append((time.perf_counter() - started) * 1000)
                    return True

                scroll_tick = window.add_tick_callback(tick)
            GLib.timeout_add(int(duration * 1000), next_stage)
            return False

        GLib.timeout_add(100, next_stage)

    application.connect_after("activate", activated)
    status = application.run([sys.argv[0]])
    if profiler:
        profiler.disable()
        profiler.dump_stats(str(output.with_suffix(".pstats")))
    for record in records:
        frames = record.pop("frames")
        actual = [timings.get_presentation_time() for _, timings in frames if timings]
        actual = [value for value in actual if value]
        intervals = [(b - a) * 1000 for (a, _), (b, _) in pairwise(frames)]
        record["callback_interval_ms"] = distribution(intervals)
        record["presentation_interval_ms"] = distribution(
            [(b - a) / 1000 for a, b in pairwise(actual)]
        )
        record["presentation_samples"] = len(actual)
        record["presentation_fps"] = (
            round((len(actual) - 1) * 1_000_000 / (actual[-1] - actual[0]), 2)
            if len(actual) > 1 and actual[-1] > actual[0]
            else None
        )
        if "scroll" in record["name"] and not record["scroll_distance"]:
            report_failure = f"No scroll movement during {record['name']}"
            state["failure"] = state["failure"] or report_failure
    window = application.window
    report = {
        "report_version": 1,
        "workload_version": 3,
        "runtime": {
            "python": list(sys.version_info[:3]),
            "gtk": [Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()],
            "adwaita": [Adw.get_major_version(), Adw.get_minor_version(), Adw.get_micro_version()],
        },
        "fixture": f"Invented {args.posts}-post feed and conversation; real widgets/worker/decoder, no network",
        "posts": args.posts,
        "profiled": args.profile,
        "idle_only": args.idle_only,
        "reduced_motion": args.reduced_motion,
        "control": args.control,
        "scroll_only": args.scroll_only,
        "startup_only": args.startup_only,
        "interactions_only": args.interactions_only,
        "width": args.width,
        "backend": window.get_display().__gtype__.name,
        "renderer": state.get("renderer"),
        "monitor_hz": state.get("monitor_hz"),
        "first_frame_ms": round(state.get("first_frame_ms", 0), 3),
        "process_first_frame_ms": round(state.get("process_first_frame_ms", 0), 3),
        "failure": state["failure"],
        "phases": records,
        "timing_scope": "Frame work is before-paint to after-paint, not GPU completion. Callback gaps during static phases are not dropped frames. Presentation timing is null when unavailable.",
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PERFORMANCE_PASS_COMPLETE", output, flush=True)
    if args.baseline:
        import runpy

        compare = runpy.run_path(str(Path(__file__).with_name("compare-performance.py")))[
            "compare_reports"
        ]
        errors = compare(json.loads(args.baseline.read_text(encoding="utf-8")), report)
        for error in errors:
            print("PERFORMANCE_CHECK_FAIL:", error, flush=True)
        if errors:
            return 1
        print("PERFORMANCE_COMPARISON_PASS", flush=True)
    return 1 if state["failure"] else status


if __name__ == "__main__":
    raise SystemExit(main())
