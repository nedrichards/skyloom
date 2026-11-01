"""Wait for real rendered frames and controller work, with a bounded deadline."""

import time


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
