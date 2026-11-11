"""Native list cursor, stable reading positions and deliberate touch refresh."""

from dataclasses import replace

from gi.repository import Gdk, Gtk

from .domain import Author, Notice, Post
from .list_state import ListPlace, PullRefresh


class ListInteraction:
    def __init__(self, view):
        self.view = view
        self.pull = PullRefresh()
        pointer = Gtk.GestureClick(
            button=Gdk.BUTTON_PRIMARY, propagation_phase=Gtk.PropagationPhase.CAPTURE
        )
        pointer.connect("pressed", self.pointer_pressed)
        view.list.add_controller(pointer)
        background = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        background.connect("released", self.background_clicked)
        view.list.add_controller(background)
        drag = Gtk.GestureDrag(touch_only=True, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        drag.connect("drag-begin", self.pull_begin)
        drag.connect("drag-update", self.pull_update)
        drag.connect("drag-end", self.pull_end)
        drag.connect("cancel", self.pull_cancel)
        view.scroll.add_controller(drag)
        self.drag = drag

    def positions(self):
        return [
            i
            for i in range(self.view.model.get_n_items())
            if isinstance(self.view.model.get_item(i).post, Post | Author | Notice)
        ]

    def selected(self):
        item = self.view.store.get_selected_item()
        return item.post if item is not None else None

    def visible_rows(self, margin=0):
        result = []
        for row in list(self.view.rows):
            if not row.get_mapped() or row._value is None:
                continue
            valid, bounds = row.compute_bounds(self.view.scroll)
            if (
                valid
                and bounds.origin.y + bounds.size.height > -self.view.scroll.get_height() * margin
                and bounds.origin.y < self.view.scroll.get_height() * (1 + margin)
            ):
                result.append((bounds.origin.y, row))
        return sorted(result, key=lambda pair: pair[0])

    def row_at(self, y):
        for row in list(self.view.rows):
            if row.get_mapped() and row._value is not None:
                valid, bounds = row.compute_bounds(self.view.list)
                if valid and bounds.origin.y <= y < bounds.origin.y + bounds.size.height:
                    return row
        return None

    def index(self, key):
        return next(
            (
                i
                for i in range(self.view.model.get_n_items())
                if self.view.key(self.view.model.get_item(i).post) == key
            ),
            None,
        )

    def select(self, index, focus=True):
        if index is None or index not in self.positions():
            return False
        if focus:
            self.view.list.grab_focus()
        self.view.store.set_selected(index)
        if focus:
            self.view.list.scroll_to(index, Gtk.ListScrollFlags.FOCUS, None)
        return True

    def focus(self, preserve_position=False):
        positions = self.positions()
        if not positions:
            self.view.focus_when_ready = True
            return False
        current = self.view.store.get_selected()
        rows = self.visible_rows()
        target = self.index(self.view.key(rows[0][1]._value)) if rows else positions[0]
        if preserve_position and (rows or self.view.header_visible()):
            place = self.capture()
            visible = {self.view.key(row._value) for _y, row in rows}
            if current in positions and self.view.key(self.selected()) in visible:
                target = current
            self.select(target)
            return self.restore(replace(place, selected=self.view.key(self.selected())))
        return self.select(current if current in positions else target)

    def move(self, command):
        self.view.user_input()
        positions = self.positions()
        if not positions:
            self.view.focus_when_ready = True
            return False
        current = self.view.store.get_selected()
        if command in {"page-up", "page-down"}:
            adjustment = self.view.scroll.get_vadjustment()
            delta = adjustment.get_page_size() * 0.9 * (1 if command == "page-down" else -1)
            if command == "page-up" and self.view.top_peek.at_top():
                self.view.top_peek.pulse()
            adjustment.set_value(
                max(
                    adjustment.get_lower(),
                    min(
                        adjustment.get_upper() - adjustment.get_page_size(),
                        adjustment.get_value() + delta,
                    ),
                )
            )

            def choose():
                rows = self.visible_rows()
                if rows:
                    self.select(self.index(self.view.key(rows[0][1]._value)))

            self.view.after_position(choose)
            return True
        if command == "first":
            target = positions[0]
        elif command == "last":
            target = positions[-1]
        elif current not in positions:
            rows = self.visible_rows()
            target = self.index(self.view.key(rows[0][1]._value)) if rows else positions[0]
        else:
            offset = positions.index(current) + (1 if command == "next" else -1)
            target = positions[max(0, min(len(positions) - 1, offset))]
        if target == current and command in {"previous", "first"}:
            self.view.top_peek.pulse()
        return self.select(target)

    def pointer_pressed(self, _gesture, _presses, _x, y):
        self.view.user_input()
        row = self.row_at(y)
        if row:
            self.select(self.index(self.view.key(row._value)), focus=False)

    def background_clicked(self, gesture, presses, _x, y):
        row = self.row_at(y)
        if presses == 1 and row and isinstance(row._value, Post):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.select(self.index(self.view.key(row._value)), focus=False)
            self.view.activate_item(self.view.list, self.view.store.get_selected())

    def at_top(self):
        adjustment = self.view.scroll.get_vadjustment()
        return adjustment.get_value() <= adjustment.get_lower() + 0.5

    def can_restore(self, place):
        return (
            place is not None
            and not self.view.paging.closed
            and (
                (self.view.content_header is not None and place.key is self.view.content_header)
                or self.index(place.key) is not None
            )
        )

    def capture(self):
        selected = self.selected()
        selected_key = self.view.key(selected) if selected is not None else None
        if self.view.header_visible():
            return ListPlace(
                self.view.content_header,
                -self.view.scroll.get_vadjustment().get_value(),
                selected_key,
            )
        rows = self.visible_rows()
        if not rows:
            return None
        offset, row = rows[0]
        return ListPlace(
            self.view.key(row._value),
            offset,
            selected_key,
        )

    def restore(self, place, *, reveal=True):
        if not self.can_restore(place):
            return False
        serial = self.view.input_serial
        if place.key is self.view.content_header:
            self.select(self.index(place.selected), focus=False)
            adjustment = self.view.scroll.get_vadjustment()
            adjustment.set_value(-place.offset)
            self.view.after_position(
                lambda: (
                    adjustment.set_value(-place.offset)
                    if serial == self.view.input_serial
                    else None
                ),
                settle_layout=True,
            )
            return True
        index = self.index(place.key)
        if index is None:
            return False
        self.select(self.index(place.selected), focus=False)
        if reveal:
            self.view.list.scroll_to(index, Gtk.ListScrollFlags(0), None)

        def correct():
            if serial != self.view.input_serial:
                return True
            for _y, row in self.visible_rows():
                if self.view.key(row._value) == place.key:
                    valid, bounds = row.compute_bounds(self.view.scroll)
                    if valid:
                        adjustment = self.view.scroll.get_vadjustment()
                        adjustment.set_value(
                            adjustment.get_value()
                            + bounds.origin.y
                            - max(
                                -max(0, bounds.size.height - 1),
                                min(place.offset, self.view.scroll.get_height() - 1),
                            )
                        )
                    return valid

            # scroll_to can be requested before the native rows are mapped. Retry
            # only within after_position's bounded allocation-settling window.
            self.view.list.scroll_to(index, Gtk.ListScrollFlags(0), None)
            return False

        self.view.after_position(correct, settle_layout=True)
        return True

    def top(self):
        self.view.user_input()
        place = self.capture()
        positions = self.positions()
        if positions:
            self.select(positions[0], focus=False)
        adjustment = self.view.scroll.get_vadjustment()
        distant = adjustment.get_value() > adjustment.get_page_size()
        # For a distant jump, set the native viewport directly instead of issuing
        # a second item-based positioning request across intermediate rows.
        if not distant:
            self.view.list.scroll_to(0, Gtk.ListScrollFlags(0), None)
        adjustment.set_value(0)

        # Cancel an outstanding focus/restore correction before completing the jump.
        def landed():
            self.view.scroll.get_vadjustment().set_value(0)
            if not distant:
                self.view.top_peek.pulse()

        self.view.after_position(landed)
        return place

    def pull_begin(self, gesture, _x, _y):
        self.view.user_input()
        enabled = self.view.refresh is not None and not self.view.paging.busy
        self.pull.begin(self.view.scroll.get_vadjustment().get_value() <= 1, enabled)
        if self.pull.state == "idle":
            gesture.set_state(Gtk.EventSequenceState.DENIED)

    def pull_update(self, gesture, x, y):
        state = self.pull.update(x, y)
        if state == "idle":
            gesture.set_state(Gtk.EventSequenceState.DENIED)
        elif state in {"pulling", "armed"}:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.view.pull_hint.set_label(
                "Release to refresh" if state == "armed" else "Pull to refresh"
            )
            self.view.pull_hint.set_visible(True)

    def pull_end(self, _gesture, _x, _y):
        refresh = self.pull.finish(
            True, self.view.refresh is not None and not self.view.paging.busy
        )
        self.view.pull_hint.set_visible(False)
        if refresh:
            self.view.refresh()

    def pull_cancel(self, *_args):
        self.pull.finish(False, False)
        self.view.pull_hint.set_visible(False)
