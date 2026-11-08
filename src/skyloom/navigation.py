"""Hideable navigation with the same visibility state in wide and overlay layouts."""

from gi.repository import Adw, GObject, Graphene, Gsk, Gtk


class SlidingContent(Gtk.Box):
    """Translate the live content without rewrapping it on every frame."""

    def __init__(self, child):
        super().__init__(hexpand=True, vexpand=True, overflow=Gtk.Overflow.HIDDEN)
        self.child = child
        self.offset = 0.0
        self.set_layout_manager(None)
        self.append(child)

    def do_measure(self, orientation, for_size):
        return self.child.measure(orientation, for_size)

    def do_size_allocate(self, width, height, baseline):
        point = Graphene.Point().init(self.offset, 0)
        self.child.allocate(width, height, baseline, Gsk.Transform().translate(point))

    def do_snapshot(self, snapshot):
        self.snapshot_child(self.child, snapshot)

    def move(self, offset):
        self.offset = offset
        self.queue_allocate()


class SidebarSlide(Gtk.Widget):
    """A short-lived render of the sidebar, never an input or accessibility pane."""

    def __init__(self):
        super().__init__(can_target=False, accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.image = None
        self.offset = 0.0
        self.width = 0
        self.height = 0
        self.rtl = False

    def capture(self, sidebar):
        # Capture the themed pane (including its background) before the native
        # visibility setter starts its faster, non-configurable spring.
        pane = sidebar.get_parent()
        self.width, self.height = pane.get_width(), pane.get_height()
        snapshot = Gtk.Snapshot.new()
        Gtk.WidgetPaintable.new(pane).snapshot(snapshot, self.width, self.height)
        self.image = snapshot.to_paintable(Graphene.Size().init(self.width, self.height))
        self.rtl = sidebar.get_direction() == Gtk.TextDirection.RTL
        self.offset = 0.0
        self.queue_draw()

    def clear(self):
        self.image = None
        self.offset = 0.0
        self.queue_draw()

    def do_snapshot(self, snapshot):
        if self.image is None:
            return
        x = self.get_width() - self.width if self.rtl else 0
        snapshot.save()
        snapshot.translate(Graphene.Point().init(x + self.offset, 0))
        self.image.snapshot(snapshot, self.width, self.height)
        snapshot.restore()


class Navigation:
    def __init__(self):
        self.view = Adw.OverlaySplitView(
            min_sidebar_width=210, max_sidebar_width=240, show_sidebar=True, pin_sidebar=True
        )
        # The default collapse handoff skips the native reveal animation. Keep
        # visibility under our control and use the animated show-sidebar setter
        # after the layout changes, including when reversing a resize mid-slide.
        self.sidebar_slide = SidebarSlide()
        self.root = Gtk.Overlay(child=self.view)
        self.root.add_overlay(self.sidebar_slide)
        self.content = None
        self.content_animation = None
        self.pending_visibility = None
        self.visibility_tick = None
        self.settings_signal = None
        self.view.connect("notify::collapsed", self.collapsed_changed)
        self.view.connect("notify::show-sidebar", self.visibility_changed)
        self.view.connect("map", self.mapped)
        self.view.connect("unmap", self.unmapped)
        self.view.connect("realize", self.watch_motion)
        self.view.connect("unrealize", self.unwatch_motion)

    def set_content(self, child):
        self.cancel_content_slide()
        old = self.content
        self.view.set_content(None)
        if old is not None:
            old.remove(old.child)
        self.content = SlidingContent(child) if child is not None else None
        self.view.set_content(self.content)

    def cancel_content_slide(self):
        if self.content_animation is not None:
            animation, self.content_animation = self.content_animation, None
            animation.pause()
        self.sidebar_slide.clear()
        if self.content is not None:
            self.content.move(0)

    def visibility_changed(self, _view, _ps):
        self.pending_visibility = None
        self.cancel_content_slide()

    def finish_handoff(self, target):
        view = self.view
        if target or self.content is None or not view.get_show_sidebar():
            self.cancel_content_slide()
            view.set_show_sidebar(target)
            return
        settings = view.get_settings()
        if not settings.get_property("gtk-enable-animations") or not view.get_pin_sidebar():
            self.cancel_content_slide()
            view.set_show_sidebar(target)
            return
        # Collapse has allocated the content at its final full width. Translate
        # that live allocation from the old seam, beneath the pinned sidebar.
        offset = self.content.offset
        if not offset:
            direction = -1 if view.get_direction() == Gtk.TextDirection.RTL else 1
            offset = direction * view.get_sidebar().get_width()
            self.content.move(offset)
        self.sidebar_slide.capture(view.get_sidebar())
        image = self.sidebar_slide.image
        view.set_show_sidebar(False)
        # The native visibility notification clears old motion. Retain this
        # immutable render only until the coordinated transition completes.
        self.sidebar_slide.image = image
        self.content.move(offset)

        def frame(progress):
            self.content.move(offset * (1 - progress))
            direction = 1 if self.sidebar_slide.rtl else -1
            self.sidebar_slide.offset = direction * self.sidebar_slide.width * progress
            self.sidebar_slide.queue_draw()

        animation = Adw.TimedAnimation.new(view, 0, 1, 340, Adw.CallbackAnimationTarget.new(frame))
        animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.content_animation = animation

        def done(current):
            if self.content_animation is current:
                self.content_animation = None
                self.content.move(0)
                self.sidebar_slide.clear()

        animation.connect("done", done)
        animation.play()

    def collapsed_changed(self, view, _ps):
        self.cancel_content_slide()
        target = not view.get_collapsed()
        if view.get_mapped() and self.visibility_tick is None:
            self.pending_visibility = None
            self.finish_handoff(target)
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
        if not self.pending_visibility and self.content is not None and view.get_pin_sidebar():
            direction = -1 if view.get_direction() == Gtk.TextDirection.RTL else 1
            self.content.move(direction * view.get_sidebar().get_width())
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
                self.finish_handoff(target)
            return False

        self.visibility_tick = view.add_tick_callback(after_layout)

    def unmapped(self, view):
        self.cancel_content_slide()
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
