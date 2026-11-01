"""Compact profile identity follows the expanded identity in the shared page scroller."""

from gi.repository import Adw, Gtk

from .widgets import avatar, box


class ProfileTitle:
    def __init__(self, header, view, identity, author):
        self.view, self.identity = view, identity
        self.threshold = None
        self.tick = None
        self.closed = False
        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=150,
            hhomogeneous=False,
            vhomogeneous=True,
        )
        self.stack.add_named(Adw.WindowTitle(title="Profile"), "expanded")
        compact = box(False, 8)
        compact.append(avatar(author, view.window, 28))
        compact.append(Adw.WindowTitle(title=author.name, subtitle="@" + author.handle))
        self.stack.add_named(compact, "compact")
        header.set_title_widget(self.stack)
        adjustment = view.scroll.get_vadjustment()
        self.signals = [
            (adjustment, adjustment.connect("value-changed", self.queue)),
            (adjustment, adjustment.connect("changed", self.queue)),
            (view, view.connect("map", self.queue)),
        ]
        view.cleanups.append(self.close)
        self.queue()

    def queue(self, *_args):
        if self.closed or self.tick is not None:
            return
        frames = 0

        def allocated(_widget, _clock):
            nonlocal frames
            frames += 1
            if frames < 2:
                return True
            self.tick = None
            self.update()
            return False

        self.tick = self.view.add_tick_callback(allocated)

    def update(self):
        adjustment = self.view.scroll.get_vadjustment()
        # Local coordinates stay stable while GTK updates the scroll adjustment and
        # row allocation in separate phases. Retain the measurement when recycled.
        if self.view.content_header.get_mapped():
            valid, bounds = self.identity.compute_bounds(self.view.content_header)
            if valid and bounds.size.height > 0:
                self.threshold = bounds.origin.y + bounds.size.height
        compact = adjustment.get_value() > 1 and (
            not self.view.content_header.get_mapped()
            or (self.threshold is not None and adjustment.get_value() >= self.threshold)
        )
        self.stack.set_visible_child_name("compact" if compact else "expanded")

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.tick is not None:
            self.view.remove_tick_callback(self.tick)
            self.tick = None
        for obj, signal in self.signals:
            obj.disconnect(signal)
        self.signals.clear()
