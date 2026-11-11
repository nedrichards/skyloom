"""One header-height feed selector with scrolling and a compact dropdown fallback."""

from gi.repository import Adw, Graphene, Gsk, Gtk, Pango

from .motion import allowed


class FeedSwitcher(Gtk.Box):
    def __init__(self, picker, window, actions=()):
        super().__init__(hexpand=True, halign=Gtk.Align.FILL)
        self.set_layout_manager(None)
        self.picker, self.window = picker, window
        self.actions = tuple(actions)
        self.buttons = []
        self.width = -1
        self.tick = None
        self.closed = False
        self.mode = "compact"
        self.layout_ready = False
        self.scroll_animation = None
        self.model_signal = None
        self.model = None
        self.stack = Gtk.Stack(
            hhomogeneous=False,
            vhomogeneous=True,
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=280,
        )
        self.append(self.stack)
        for action in self.actions:
            self.append(action)
        self.row = Gtk.Box(spacing=2)
        self.strip = Gtk.Box(spacing=2)
        self.previous = self.control("go-previous-symbolic", "Earlier feeds", -1)
        self.next = self.control("go-next-symbolic", "Later feeds", 1)
        self.scroller = Gtk.ScrolledWindow(
            child=self.strip,
            hexpand=True,
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        self.row.append(self.previous)
        self.row.append(self.scroller)
        self.row.append(self.next)
        self.stack.add_named(self.row, "strip")
        self.compact = Gtk.Box(spacing=2, halign=Gtk.Align.CENTER)
        self.compact.append(picker)
        self.stack.add_named(self.compact, "compact")
        self.stack.set_visible_child_name("compact")
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.setup_label)
        factory.connect("bind", self.bind_label)
        picker.set_factory(factory)
        # Popup rows retain full names; only the closed header label ellipsises.
        list_factory = Gtk.SignalListItemFactory()
        list_factory.connect("setup", self.setup_list_label)
        list_factory.connect("bind", self.bind_label)
        picker.set_list_factory(list_factory)
        self.signals = [
            (picker, picker.connect("notify::selected", self.selection_changed)),
            (picker, picker.connect("notify::model", self.model_changed)),
        ]
        scroll_input = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        scroll_input.connect("scroll", self.stop_scroll)
        self.scroller.add_controller(scroll_input)
        adjustment = self.scroller.get_hadjustment()
        adjustment.connect("changed", self.queue)
        adjustment.connect("value-changed", self.edges_changed)
        self.connect("map", self.queue)
        self.connect("unmap", self.unmapped)
        self.connect("unrealize", self.close)
        self.model_changed()

    @staticmethod
    def setup_label(_factory, item):
        item.set_child(
            Gtk.Label(ellipsize=Pango.EllipsizeMode.END, width_chars=6, max_width_chars=18)
        )

    @staticmethod
    def setup_list_label(_factory, item):
        item.set_child(Gtk.Label(xalign=0))

    @staticmethod
    def bind_label(_factory, item):
        item.get_child().set_label(item.get_item().get_string())

    def control(self, icon, title, direction):
        button = Gtk.Button(icon_name=icon, tooltip_text=title)
        button.update_property([Gtk.AccessibleProperty.LABEL], [title])
        button.add_css_class("flat")
        button.connect("clicked", lambda _button: self.scroll(direction))
        return button

    def model_changed(self, *_args):
        if self.model_signal is not None:
            self.model.disconnect(self.model_signal)
        self.model = self.picker.get_model()
        self.model_signal = (
            self.model.connect("items-changed", self.rebuild) if self.model else None
        )
        self.rebuild()

    def rebuild(self, *_args):
        for button in self.buttons:
            self.strip.remove(button)
        self.buttons.clear()
        selected = self.picker.get_selected()
        if self.model:
            for index in range(self.model.get_n_items()):
                name = self.model.get_item(index).get_string()
                button = Gtk.ToggleButton(label=name, tooltip_text=name, hexpand=True)
                button.add_css_class("flat")
                if self.buttons:
                    button.set_group(self.buttons[0])
                button.set_active(index == selected)
                button.connect("toggled", self.chosen, index)
                self.strip.append(button)
                self.buttons.append(button)
        self.queue_resize()
        self.selection_changed()

    def chosen(self, button, index):
        if button.get_active() and self.picker.get_selected() != index:
            self.picker.set_selected(index)

    def selection_changed(self, *_args):
        selected = self.picker.get_selected()
        if selected < len(self.buttons):
            self.buttons[selected].set_active(True)
            self.picker.set_tooltip_text(self.buttons[selected].get_label())
        self.queue()

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            minimum = self.compact.measure(orientation, -1)[0]
            natural = self.strip.measure(orientation, -1)[1]
            return minimum, max(minimum, min(880, natural)), -1, -1
        sizes = [self.row.measure(orientation, -1), self.compact.measure(orientation, -1)]
        sizes.extend(action.measure(orientation, -1) for action in self.actions)
        return max(size[0] for size in sizes), max(size[1] for size in sizes), -1, -1

    def do_size_allocate(self, width, height, baseline):
        horizontal = Gtk.Orientation.HORIZONTAL
        names = self.strip.measure(horizontal, -1)[1]
        # Budget against the whole allocation, independent of current visibility.
        # Reserve the selector controls and one extra action width as breathing room.
        controls = sum(control.measure(horizontal, -1)[1] for control in (self.previous, self.next))
        available = width - names - controls - 4
        shown = []
        focus = self.get_root().get_focus() if self.get_root() else None
        for action in self.actions:
            size = action.measure(horizontal, -1)[1]
            visible = available >= 2 * (size + 6)
            action.set_child_visible(visible)
            if visible:
                shown.append((action, size))
                available -= size + 6
            else:
                available = -1
                if focus is action or (focus and focus.is_ancestor(action)):
                    selected = self.picker.get_selected()
                    if self.mode != "compact" and selected < len(self.buttons):
                        self.buttons[selected].grab_focus()
                    else:
                        self.picker.grab_focus()
        selector_width = width - sum(size + 6 for _action, size in shown)
        self.stack.allocate(selector_width, height, baseline, None)
        x = selector_width
        for action, size in shown:
            x += 6
            action_height = action.measure(Gtk.Orientation.VERTICAL, size)[1]
            point = Graphene.Point().init(x, max(0, (height - action_height) / 2))
            action.allocate(size, min(height, action_height), -1, Gsk.Transform().translate(point))
            x += size
        if selector_width != self.width:
            self.width = selector_width
            self.queue()

    def do_snapshot(self, snapshot):
        self.snapshot_child(self.stack, snapshot)
        for action in self.actions:
            if action.get_child_visible():
                self.snapshot_child(action, snapshot)

    def queue(self, *_args):
        if not self.closed and self.tick is None:
            frames = 0

            def allocated(*_args):
                nonlocal frames
                frames += 1
                if frames < 2:
                    return True
                self.tick = None
                if self.get_mapped():
                    self.update_layout()
                return False

            self.tick = self.add_tick_callback(allocated)

    def update_layout(self):
        minimum = self.compact.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        natural = self.strip.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        compact = self.width < max(320, minimum + 48) or len(self.buttons) < 2
        mode = "compact" if compact else "expanded" if natural <= self.width else "scrollable"
        focus = self.get_root().get_focus() if self.get_root() else None
        move_focus = focus and focus.is_ancestor(self.row if compact else self.compact)
        self.stack.set_transition_duration(280 if self.layout_ready and allowed(self.window) else 0)
        self.layout_ready = True
        self.previous.set_child_visible(mode == "scrollable")
        self.next.set_child_visible(mode == "scrollable")
        self.mode = mode
        self.stack.set_visible_child_name("compact" if compact else "strip")
        if move_focus:
            selected = self.picker.get_selected()
            if compact:
                self.picker.grab_focus()
            elif selected < len(self.buttons):
                self.buttons[selected].grab_focus()
        self.reveal_selected()
        self.edges_changed()

    def reveal_selected(self):
        selected = self.picker.get_selected()
        if self.mode == "compact" or selected >= len(self.buttons):
            return
        valid, bounds = self.buttons[selected].compute_bounds(self.strip)
        if valid:
            adjustment = self.scroller.get_hadjustment()
            value, page = adjustment.get_value(), adjustment.get_page_size()
            left, right = bounds.origin.x, bounds.origin.x + bounds.size.width
            if left < value:
                adjustment.set_value(left)
            elif right > value + page:
                adjustment.set_value(max(0, right - page))

    def edges_changed(self, *_args):
        adjustment = self.scroller.get_hadjustment()
        self.previous.set_sensitive(adjustment.get_value() > 1)
        self.next.set_sensitive(
            adjustment.get_value() + adjustment.get_page_size() < adjustment.get_upper() - 1
        )

    def stop_scroll(self, *_args):
        if self.scroll_animation:
            self.scroll_animation.pause()
            self.scroll_animation = None
        return False

    def scroll(self, direction):
        adjustment = self.scroller.get_hadjustment()
        start = adjustment.get_value()
        end = max(
            0,
            min(
                adjustment.get_upper() - adjustment.get_page_size(),
                start + direction * adjustment.get_page_size() * 0.7,
            ),
        )
        self.stop_scroll()
        self.scroll_animation = Adw.TimedAnimation.new(
            self,
            start,
            end,
            160 if allowed(self.window) else 0,
            Adw.CallbackAnimationTarget.new(adjustment.set_value),
        )
        self.scroll_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.scroll_animation.play()

    def unmapped(self, *_args):
        if self.tick is not None:
            self.remove_tick_callback(self.tick)
            self.tick = None
        self.stop_scroll()

    def close(self, *_args):
        if self.closed:
            return
        self.closed = True
        self.unmapped()
        if self.model_signal is not None:
            self.model.disconnect(self.model_signal)
            self.model_signal = None
        for obj, signal in self.signals:
            obj.disconnect(signal)
        self.signals.clear()
