"""Distinct invented photos retained by native Pictures, run one mode per process.

Run in GNOME 51 with the app's decoder environment and source PYTHONPATH.
retain-all simulates the previous widget retention; viewport releases old consumers.
This measures retained references/pixel estimates and process peak RSS, not frame rate.
"""

import argparse
import asyncio
import gc
import json
import resource
from pathlib import Path
from tempfile import TemporaryDirectory

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk  # noqa: E402

from skyloom.media import Images  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("retain-all", "viewport"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--images", type=int, default=64)
    parser.add_argument("--visible", type=int, default=12)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=768)
    args = parser.parse_args()
    if not (1 <= args.images <= 128 and 1 <= args.visible <= args.images):
        parser.error("Use 1..128 images and 1..images visible consumers")
    if not (1 <= args.width <= 1600 and 1 <= args.height <= 1600):
        parser.error("Dimensions must be in 1..1600")
    if not Gtk.init_check():
        parser.error("A native GTK display is required")

    async def exercise(directory):
        images = Images(
            directory,
            max_cache_bytes=(2**63 - 1 if args.mode == "retain-all" else 48 * 1024 * 1024),
        )
        pictures = [Gtk.Picture() for _ in range(args.images)]
        paths = []
        for index in range(args.images):
            pixbuf = GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, False, 8, args.width, args.height
            )
            pixbuf.fill(
                ((index * 37 % 256) << 24)
                | ((index * 71 % 256) << 16)
                | ((index * 101 % 256) << 8)
                | 255
            )
            path = Path(directory) / f"invented-photo-{index}.png"
            pixbuf.savev(str(path), "png", [], [])
            paths.append(path)
        del pixbuf
        samples = []
        for direction, indices in (
            ("forward", range(args.images)),
            ("reverse", range(args.images - 1, -1, -1)),
        ):
            active = []
            for index in indices:
                picture = pictures[index]
                paintable = await images.get(str(paths[index]), local=True)
                picture.set_paintable(paintable)
                images.bind(picture, paintable)
                active.append(index)
                if args.mode == "viewport" and len(active) > args.visible:
                    released = pictures[active.pop(0)]
                    released.set_paintable(None)
                    images.unbind(released)
                del paintable
                stats = images.residency()
                stats.update(
                    direction=direction,
                    native_paintables=sum(p.get_paintable() is not None for p in pictures),
                )
                samples.append(stats)
            if args.mode == "viewport":
                for picture in pictures:
                    picture.set_paintable(None)
                    images.unbind(picture)
        gc.collect()
        final = images.residency()
        for picture in pictures:
            picture.set_paintable(None)
            images.unbind(picture)
        images.cache.clear()
        gc.collect()
        return samples, final, images.residency()

    with TemporaryDirectory(prefix="skyloom-photo-residency-") as directory:
        samples, final, released = asyncio.run(exercise(directory))
    report = {
        "mode": args.mode,
        "images": args.images,
        "visible_budget": args.visible,
        "dimensions": [args.width, args.height],
        "scope": "Separate process per mode; distinct locally generated PNGs and real native Picture paintables. retain-all is an explicit old-behaviour simulation, not an old installed binary. Pixel estimates exclude decoder/renderer copies; peak RSS includes the entire process. No frame-rate or hardware energy measurement.",
        "max_native_paintables": max(s["native_paintables"] for s in samples),
        "max_resident_bytes": max(s["resident_bytes"] for s in samples),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "final": final,
        "after_release": released,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}))


if __name__ == "__main__":
    main()
