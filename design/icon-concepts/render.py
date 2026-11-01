"""Render the selected production icon and its compact light/dark QA sheet."""

from pathlib import Path

import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402 — select the typelib before importing it.

ROOT = Path(__file__).resolve().parent
ICONS = ROOT.parents[1] / "data/icons"
FULL = ICONS / "com.nedrichards.Skyloom.svg"
SYMBOLIC = ICONS / "com.nedrichards.Skyloom-symbolic.svg"


def draw_icon(context, path, x, y, size):
    handle = Rsvg.Handle.new_from_file(str(path))
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = x, y, size, size
    handle.render_document(context, viewport)


def draw_symbolic(context, x, y, size, color):
    mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    draw_icon(cairo.Context(mask), SYMBOLIC, 0, 0, size)
    context.set_source_rgb(*color)
    context.mask_surface(mask, x, y)


def text(context, value, x, y, size, color, bold=False):
    context.select_font_face(
        "Adwaita Sans",
        cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )
    context.set_font_size(size)
    context.set_source_rgb(*color)
    context.move_to(x, y)
    context.show_text(value)


def main():
    previews = ROOT / "previews"
    previews.mkdir(exist_ok=True)
    for path, sizes, name in (
        (FULL, (32, 64, 128, 256), "skyloom"),
        (SYMBOLIC, (16, 32, 64), "skyloom-symbolic"),
    ):
        for size in sizes:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            draw_icon(cairo.Context(surface), path, 0, 0, size)
            surface.write_to_png(str(previews / f"{name}-{size}.png"))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1120, 820)
    context = cairo.Context(surface)
    context.set_source_rgb(0.965, 0.961, 0.953)
    context.paint()
    ink, muted, light = (0.16, 0.18, 0.21), (0.42, 0.44, 0.47), (0.88, 0.9, 0.92)
    text(context, "Skyloom · Open Loom", 40, 65, 32, ink, True)
    text(context, "Chosen identity · refined maple frame and sky-blue weave", 40, 103, 18, muted)
    context.set_source_rgb(1, 1, 1)
    context.rectangle(32, 140, 512, 344)
    context.fill()
    context.set_source_rgb(0.14, 0.15, 0.17)
    context.rectangle(576, 140, 512, 344)
    context.fill()
    text(context, "Light background", 56, 180, 17, muted)
    text(context, "Dark background", 600, 180, 17, light)
    draw_icon(context, FULL, 160, 208, 256)
    draw_icon(context, FULL, 704, 208, 256)
    text(context, "Full colour · actual-size checks", 40, 539, 18, ink, True)
    for size, x in ((128, 56), (64, 248), (32, 392)):
        draw_icon(context, FULL, x, 574 + (128 - size) / 2, size)
        text(context, str(size), x + size / 2 - 12, 744, 14, muted)
    context.set_source_rgb(0.14, 0.15, 0.17)
    context.rectangle(576, 512, 512, 268)
    context.fill()
    text(context, "Matching symbolic · foreground adapts to theme", 600, 550, 17, light)
    for size, x in ((16, 632), (32, 764), (64, 920)):
        draw_symbolic(context, x, 600 + (80 - size) / 2, size, light)
        text(context, str(size), x + size / 2 - 10, 744, 14, (0.63, 0.66, 0.69))
    text(context, "Original editable SVGs · GNOME 128 px grid · 16 px symbolic", 40, 801, 14, muted)
    surface.write_to_png(str(ROOT / "open-loom-final.png"))


if __name__ == "__main__":
    main()
