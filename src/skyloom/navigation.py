"""Hideable navigation with the same visibility state in wide and overlay layouts."""

from gi.repository import Adw, GObject, Gtk


class Navigation:
    def __init__(self):
        self.view = Adw.OverlaySplitView(
            min_sidebar_width=210, max_sidebar_width=240, show_sidebar=True, pin_sidebar=True
        )
        # The default collapse handoff skips the native reveal animation. Keep
        # visibility under our control and use the animated show-sidebar setter
        # after the layout changes, including when reversing a resize mid-slide.
        self.pending_visibility = None
        self.visibility_tick = None
        self.settings_signal = None
        self.view.connect("notify::collapsed", self.collapsed_changed)
        self.view.connect("map", self.mapped)
        self.view.connect("unmap", self.unmapped)
        self.view.connect("realize", self.watch_motion)
        self.view.connect("unrealize", self.unwatch_motion)

    def collapsed_changed(self, view, _ps):
        target = not view.get_collapsed()
        if view.get_mapped() and self.visibility_tick is None:
            self.pending_visibility = None
            view.set_show_sidebar(target)
        else:
            # BreakpointBin temporarily unmaps its child during the handoff.
            # Starting an animation there would make libadwaita skip it.
            self.pending_visibility = target

    def mapped(self, view):
        if self.pending_visibility is None:
            return
        if self.pending_visibility == view.get_show_sidebar():
            self.pending_visibility = None
            return
        frames = 0

        def after_layout(*_args):
            nonlocal frames
            frames += 1
            if frames < 3:
                return True
            # Let the first narrow allocation finish before starting the spring:
            # rewrapping a large reading window can otherwise consume its clock.
            self.visibility_tick = None
            target, self.pending_visibility = self.pending_visibility, None
            if target is not None:
                view.set_show_sidebar(target)
            return False

        self.visibility_tick = view.add_tick_callback(after_layout)

    def unmapped(self, view):
        if self.visibility_tick is not None:
            view.remove_tick_callback(self.visibility_tick)
            self.visibility_tick = None

    def watch_motion(self, view):
        settings = view.get_settings()

        def changed(*_args):
            # libadwaita 1.10 follows gtk-enable-animations itself, but not GTK's
            # newer reduced-motion setting. Keep its instant collapse for that.
            view.set_pin_sidebar(
                settings.get_property("gtk-interface-reduced-motion") != Gtk.ReducedMotion.REDUCE
            )

        self.settings_signal = settings.connect("notify::gtk-interface-reduced-motion", changed)
        changed()

    def unwatch_motion(self, view):
        if self.settings_signal is not None:
            view.get_settings().disconnect(self.settings_signal)
            self.settings_signal = None

    def create_toggle(self, *, overlay_only=False):
        toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")

        def changed(button, _property):
            title = "Hide navigation" if button.get_active() else "Show navigation"
            button.set_tooltip_text(title)
            button.update_property([Gtk.AccessibleProperty.LABEL], [title])

        toggle.connect("notify::active", changed)
        self.view.bind_property(
            "show-sidebar",
            toggle,
            "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        if overlay_only:
            self.view.bind_property(
                "collapsed", toggle, "visible", GObject.BindingFlags.SYNC_CREATE
            )
        changed(toggle, None)
        return toggle

    def reveal_content(self):
        if self.view.get_collapsed():
            self.view.set_show_sidebar(False)

    def bind_menu(self, menu, *, sidebar=False):
        flags = GObject.BindingFlags.SYNC_CREATE
        if not sidebar:
            flags |= GObject.BindingFlags.INVERT_BOOLEAN
        self.view.bind_property("show-sidebar", menu, "visible", flags)
        menu.connect(
            "notify::visible",
            lambda button, _ps: button.popdown() if not button.get_visible() else None,
        )

    def reveal_sidebar(self):
        self.view.set_show_sidebar(True)
