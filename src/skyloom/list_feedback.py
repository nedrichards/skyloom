"""Bounded upper-edge feedback and transient, page-scoped new-item notifications."""

import math
import weakref

from gi.repository import Adw, Gdk, GLib, Graphene, Gtk

from .motion import allowed


class TopPeek(Adw.Bin):
    """Move only the snapshot: no list reallocation, model change or scroll correction."""

    def __init__(self, scroller, window):
        super().__init__(child=scroller)
        self.window = window
        self.offset = 0.0
        self.closed = False
        self.queued = None
        ref = weakref.ref(self)

        def frame(progress):
            widget = ref()
            if widget is not None:
                widget.offset = (
                    0.0
                    if progress >= 1
                    else 48 * math.sin(math.pi * progress) * math.exp(-2 * progress)
                )
                widget.queue_draw()

        self.animation = Adw.TimedAnimation.new(
            self, 0, 1, 360, Adw.CallbackAnimationTarget.new(frame)
        )
        self.animation.set_easing(Adw.Easing.LINEAR)
        adjustment = scroller.get_vadjustment()
        self.signals = [(adjustment, adjustment.connect("value-changed", self.moved))]
        settings = Gtk.Settings.get_default()
        for name in ("gtk-enable-animations", "gtk-interface-reduced-motion"):
            self.signals.append(
                (settings, settings.connect("notify::" + name, self.motion_changed))
            )
        if hasattr(window, "connect"):
            self.signals.append((window, window.connect("notify::is-active", self.motion_changed)))
        self.connect("unmap", self.reset)
        self.scroll_input = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.VERTICAL,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        self.scroll_input.connect("scroll", self.scrolled)
        scroller.add_controller(self.scroll_input)

    def do_snapshot(self, snapshot):
        child = self.get_child()
        if child is None:
            return
        if self.offset == 0:
            self.snapshot_child(child, snapshot)
            return
        snapshot.push_clip(Graphene.Rect().init(0, 0, self.get_width(), self.get_height()))
        snapshot.save()
        snapshot.translate(Graphene.Point().init(0, self.offset))
        self.snapshot_child(child, snapshot)
        snapshot.restore()
        snapshot.pop()

    def at_top(self):
        adjustment = self.get_child().get_vadjustment()
        return adjustment.get_value() <= adjustment.get_lower() + 0.5

    def pulse(self):
        if self.closed or not self.get_mapped() or not allowed(self.window) or not self.at_top():
            return False
        if self.animation.get_state() != Adw.AnimationState.PLAYING:
            self.animation.play()
        return True

    def scrolled(self, controller, _dx, dy):
        # GTK supplies smooth/touch overscroll itself. Never consume the scroll.
        if dy < 0 and controller.get_unit() == Gdk.ScrollUnit.WHEEL and self.queued is None:

            def after_scroll():
                self.queued = None
                self.pulse()
                return False

            self.queued = GLib.idle_add(after_scroll)
        return False

    def moved(self, *_args):
        if not self.at_top():
            self.reset()

    def motion_changed(self, *_args):
        if not allowed(self.window):
            self.reset()

    def reset(self, *_args):
        if self.queued is not None:
            GLib.source_remove(self.queued)
            self.queued = None
        if self.animation is not None:
            self.animation.reset()
        self.offset = 0.0
        self.queue_draw()

    def close(self):
        if self.closed:
            return
        self.reset()
        self.closed = True
        self.get_child().remove_controller(self.scroll_input)
        for obj, signal in self.signals:
            obj.disconnect(signal)
        self.signals.clear()
        self.animation = None


class UpdateNotice:
    """Share the window's native toast queue; staging never changes the viewport."""

    def __init__(self, view):
        self.view = weakref.ref(view)
        self.title = ""
        self.toast = None
        self.announced = False
        self.queued = None
        self.revision = None

    def schedule(self):
        view = self.view()
        if self.queued is not None or self.announced or view is None or not view.pending_update:
            return

        def present():
            self.queued = None
            self.show()
            return False

        self.queued = GLib.idle_add(present)

    def offer(self, title, button_label="Show", *, revision=None):
        identity = (revision, title, button_label)
        if self.revision == identity:
            return
        self.hide()
        self.revision = identity
        self.title = title
        self.button_label = button_label
        self.announced = False

    def show(self):
        view = self.view()
        if (
            view is None
            or view.paging.closed
            or not view.get_mapped()
            or not getattr(view.window, "is_active", lambda: True)()
            or not view.pending_update
            or self.announced
            or not hasattr(view.window, "overlay")
            or view.window.interactions.context() in {"dialog", "popup"}
            or view.window.interactions.current_view() is not view
        ):
            return
        self.announced = True
        toast = Adw.Toast(
            title=self.title, button_label=self.button_label, timeout=5, use_markup=False
        )
        self.toast = toast

        def clicked(_toast):
            current = self.view()
            if (
                self.toast is _toast
                and current is not None
                and current.window.interactions.current_view() is current
            ):
                current.apply_update()

        def dismissed(_toast):
            if self.toast is _toast:
                self.toast = None

        toast.connect("button-clicked", clicked)
        toast.connect("dismissed", dismissed)
        view.window.overlay.add_toast(toast)

    def hide(self):
        if self.queued is not None:
            GLib.source_remove(self.queued)
            self.queued = None
        toast, self.toast = self.toast, None
        if toast is not None:
            toast.dismiss()

    def unmap(self, *_args):
        self.hide()
        # Losing visibility/activity is not a new batch. Keep the action available,
        # but do not replay a notice already presented before this interruption.

    def clear(self):
        self.hide()
        self.title = ""
        self.announced = False
        self.revision = None
