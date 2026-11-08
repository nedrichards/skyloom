"""Check native row minima and height-for-width across body request hints."""

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
from skyloom.domain import Author, Media, Post  # noqa: E402
from skyloom.widgets import PostRow  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not Gtk.init_check():
        parser.error("Native GTK display required")
    Adw.init()
    schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
    settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
    settings.set_boolean("load-images", False)
    window = SimpleNamespace(
        settings=settings,
        mutations=set(),
        read_only=False,
        content_gates=WeakSet(),
        revealed_labels={},
    )
    base = Post(
        "at://did:example:measure/app.bsky.feed.post/0",
        "invented-cid",
        Author("did:example:measure", "measure.invalid", "Invented author"),
        "Invented post. " + "Readable native text, links and images. " * 6,
        "2026-11-08T12:00:00Z",
    )
    variants = {
        "plain": base,
        "quote": replace(base, quote=replace(base, uri=base.uri + "quote")),
        "alt": replace(
            base, images=(Media("invented.invalid", "An invented image description. " * 6),)
        ),
    }
    motion = Gtk.Settings.get_default()
    original_font = motion.get_property("gtk-font-name")
    original_create = PostRow.create_text
    results = []
    try:
        for font in ("Adwaita Sans 11", "Adwaita Sans 16", "Adwaita Sans 24"):
            motion.set_property("gtk-font-name", font)
            for chars in (1, 8, 12):

                def create(self, owner, chars=chars):
                    original_create(self, owner)
                    self.text.set_width_chars(chars)

                PostRow.create_text = create
                for name, post in variants.items():
                    row = PostRow(post, window)
                    clamp = Adw.Clamp(maximum_size=760, tightening_threshold=600, child=row)
                    start = perf_counter()
                    minimum, natural, *_ = clamp.measure(Gtk.Orientation.HORIZONTAL, -1)
                    width_ms = round((perf_counter() - start) * 1000, 3)
                    heights = {
                        str(width): tuple(clamp.measure(Gtk.Orientation.VERTICAL, width))
                        for width in (320, 360, 480, 800)
                    }
                    results.append(
                        {
                            "font": font,
                            "width_chars": chars,
                            "variant": name,
                            "minimum_width": minimum,
                            "natural_width": natural,
                            "width_measure_ms": width_ms,
                            "heights": heights,
                        }
                    )
                    clamp.set_child(None)
                    row.cancel()
    finally:
        PostRow.create_text = original_create
        motion.set_property("gtk-font-name", original_font)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for item in results:
        print(item)


if __name__ == "__main__":
    main()
