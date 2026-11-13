"""Shared native display setup and bounded rendered-frame waits."""

import time


def init_display():
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("Gdk", "4.0")
        from gi.repository import Adw, Gdk, Gtk

        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            return False
        Adw.init()
        return True
    except ImportError, ValueError, AttributeError:
        return False


DISPLAY = init_display()


def settle(window, milliseconds=150, ready=lambda: True):
    from gi.repository import GLib

    loop = GLib.MainLoop()
    window.present()
    frames, settled = 0, False
    started = time.monotonic()

    def rendered(*_args):
        nonlocal frames
        frames += 1
        return True

    def check():
        nonlocal settled
        elapsed = (time.monotonic() - started) * 1000
        settled = frames >= 6 and elapsed >= milliseconds and ready()
        if settled or elapsed >= 2000:
            loop.quit()
            return False
        return True

    tick = window.add_tick_callback(rendered)
    GLib.timeout_add(16, check)
    try:
        loop.run()
    finally:
        window.remove_tick_callback(tick)
    return settled
