"""Brief, layout-stable feedback; nothing runs while idle or in reduced motion."""

from gi.repository import Adw, Gtk


def allowed(window=None):
    settings = Gtk.Settings.get_default()
    connection = getattr(getattr(window, "interactions", None), "connection", None)
    return (
        settings.get_property("gtk-enable-animations")
        and settings.get_property("gtk-interface-reduced-motion") != Gtk.ReducedMotion.REDUCE
        and not getattr(connection, "power_saver", False)
        and (window is None or getattr(window, "is_active", lambda: True)())
    )


class Feedback:
    def __init__(self, window):
        self.window = window
        self.active = {}
        self.closed = False
        settings = Gtk.Settings.get_default()
        self.signals = [
            (settings, settings.connect("notify::gtk-enable-animations", self.changed)),
            (settings, settings.connect("notify::gtk-interface-reduced-motion", self.changed)),
            (window, window.connect("notify::is-active", self.changed)),
            (window, window.connect("unrealize", self.close)),
        ]

    def visible(self, widget):
        if not widget.get_mapped():
            return False
        clip = widget.get_ancestor(Gtk.ScrolledWindow) or self.window
        valid, bounds = widget.compute_bounds(clip)
        return (
            valid
            and bounds.size.width > 0
            and bounds.size.height > 0
            and bounds.origin.x + bounds.size.width > 0
            and bounds.origin.y + bounds.size.height > 0
            and bounds.origin.x < clip.get_width()
            and bounds.origin.y < clip.get_height()
        )

    def finish_offscreen(self):
        for widget in tuple(self.active):
            if not self.visible(widget):
                self.finish(widget)

    def fade(self, widget, end=1, *, start=None):
        self.finish(widget)
        if self.closed or not allowed(self.window) or not self.visible(widget):
            widget.set_opacity(end)
            return
        if start is not None:
            widget.set_opacity(start)
        target = Adw.CallbackAnimationTarget.new(widget.set_opacity)
        animation = Adw.TimedAnimation.new(widget, widget.get_opacity(), end, 160, target)
        animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        signal = widget.connect("unmap", lambda *_: self.finish(widget))
        self.active[widget] = (animation, signal)

        def done(_animation):
            current = self.active.get(widget)
            if current is not None and current[0] is _animation:
                self.active.pop(widget)
                widget.disconnect(signal)

        animation.connect("done", done)
        animation.play()

    def finish(self, widget):
        current = self.active.get(widget)
        if current is not None:
            current[0].skip()

    def changed(self, *_args):
        if allowed(self.window):
            return
        for widget in tuple(self.active):
            self.finish(widget)
        for view in getattr(self.window, "views", ()):
            view.motion_changed(Gtk.Settings.get_default(), None)
            if not self.window.is_active():
                view.cancel_arrivals()

    def close(self, *_args):
        if self.closed:
            return
        self.closed = True
        for widget in tuple(self.active):
            self.finish(widget)
        for obj, signal in self.signals:
            obj.disconnect(signal)
        self.signals.clear()
