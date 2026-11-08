"""Compare native wrapped-label requests; no rendering or scrolling speed claim."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("inherit", "none", "word"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=int, default=250)
    parser.add_argument("--width-chars", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.labels <= 1000:
        parser.error("Use 1..1000 labels")
    if not Gtk.init_check():
        parser.error("Native GTK display required")
    Adw.init()
    modes = {
        "inherit": Gtk.NaturalWrapMode.INHERIT,
        "none": Gtk.NaturalWrapMode.NONE,
        "word": Gtk.NaturalWrapMode.WORD,
    }
    labels = [
        Gtk.Label(
            label=f"Invented post {n}. " + "Readable native text, links and images. " * 6,
            wrap=True,
            selectable=True,
            width_chars=args.width_chars,
            hexpand=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            natural_wrap_mode=modes[args.mode],
        )
        for n in range(args.labels)
    ]
    samples = []
    for orientation, size in (
        (Gtk.Orientation.HORIZONTAL, -1),
        (Gtk.Orientation.HORIZONTAL, 120),
        (Gtk.Orientation.HORIZONTAL, 240),
        (Gtk.Orientation.VERTICAL, 440),
        (Gtk.Orientation.VERTICAL, 720),
    ):
        start = perf_counter()
        values = [tuple(widget.measure(orientation, size)) for widget in labels]
        samples.append(
            {
                "orientation": orientation.value_nick,
                "for_size": size,
                "elapsed_ms": round((perf_counter() - start) * 1000, 3),
                "first_request": values[0],
                "last_request": values[-1],
            }
        )
    result = {
        "scope": "unmapped selectable body labels; label width-for-height request probe, not app FPS",
        "mode": args.mode,
        "labels": args.labels,
        "width_chars": args.width_chars,
        "requests": samples,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
