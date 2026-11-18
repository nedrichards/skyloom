"""Native browsing, zoom and pan for a post's images."""

from math import ceil, isclose

from gi.repository import Adw, Gdk, Graphene, Gtk, Pango

from .domain import safe_url
from .widgets import box, button, label

ZOOM_STEP = 1.25
MAX_ZOOM = 4


class ImageCanvas(Gtk.Widget):
    def __init__(self):
        super().__init__(accessible_role=Gtk.AccessibleRole.IMG, hexpand=True, vexpand=True)
        self.texture = None
        self.zoom = None

    def do_measure(self, orientation, _for_size):
        size = 0
        if self.texture is not None and self.zoom is not None:
            pixels = (
                self.texture.get_width()
                if orientation == Gtk.Orientation.HORIZONTAL
                else self.texture.get_height()
            )
            size = ceil(pixels * self.zoom)
        return size, size, -1, -1

    def fit(self):
        if self.texture is None:
            return 1
        return min(
            self.get_width() / self.texture.get_width(),
            self.get_height() / self.texture.get_height(),
            1,
        )

    def do_snapshot(self, snapshot):
        if self.texture is None:
            return
        zoom = self.fit() if self.zoom is None else self.zoom
        width = self.texture.get_width() * zoom
        height = self.texture.get_height() * zoom
        if width > 0 and height > 0:
            snapshot.append_texture(
                self.texture,
                Graphene.Rect().init(
                    (self.get_width() - width) / 2, (self.get_height() - height) / 2, width, height
                ),
            )


class ImageViewer(Adw.Dialog):
    def __init__(self, window, gallery, index):
        super().__init__(
            title="Image",
            content_width=800,
            content_height=640,
            width_request=280,
            height_request=260,
        )
        self.window, self.gallery = window, gallery
        self.index, self.media = index, gallery[index]
        self.generation = window.generation
        self.account = window.service.account
        self.task = self.center_tick = self.center = self.drag_origin = None
        self.closed = False
        self.narrow = False
        self.request_serial = 0
        self.portrait = False

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        self.browser = button("web-browser-symbolic", "Open image in browser", self.open_original)
        header.pack_end(self.browser)
        self.gallery_title = None
        if len(gallery) > 1:
            navigation = box(False, 0)
            navigation.add_css_class("linked")
            self.previous = button("go-previous-symbolic", "Previous image", lambda: self.move(-1))
            self.next = button("go-next-symbolic", "Next image", lambda: self.move(1))
            navigation.append(self.previous)
            navigation.append(self.next)
            header.pack_start(navigation)
            self.gallery_title = Adw.WindowTitle(title="Image")
            header.set_title_widget(self.gallery_title)

        self.body = box(spacing=0)
        self.stage = Gtk.Stack(hexpand=True, vexpand=True)
        self.body.append(self.stage)
        self.canvas = ImageCanvas()
        viewport = Gtk.Viewport(child=self.canvas)
        self.image_scroll = Gtk.ScrolledWindow(child=viewport, focusable=True)
        self.image_scroll.add_css_class("viewer-image")
        self.adjustments = (
            self.image_scroll.get_hadjustment(),
            self.image_scroll.get_vadjustment(),
        )
        for adjustment in self.adjustments:
            adjustment.connect("changed", lambda *_: self.update_controls())
        self.stage.add_named(self.image_scroll, "image")
        self.stage.add_named(
            Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER), "loading"
        )
        failure = box(margin=16)
        failure.set_valign(Gtk.Align.CENTER)
        self.error = label("", justify=Gtk.Justification.CENTER, xalign=0.5)
        failure.append(self.error)
        failure.append(button(None, "Retry loading image", self.load, "Try again"))
        self.stage.add_named(failure, "error")

        self.details = box(spacing=8, margin=12)
        self.description_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
            max_content_height=132,
            focusable=True,
        )
        self.details.append(self.description_scroll)
        self.description = label("", selectable=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        self.description_scroll.set_child(self.description)
        self.body.append(self.details)
        self.details_toggle = Gtk.ToggleButton(icon_name="text-x-generic-symbolic", active=True)
        if any(media.alt.strip() for media in gallery):
            copy = button(None, "Copy image description", self.copy_description, "Copy description")
            copy.set_halign(Gtk.Align.START)
            self.details.append(copy)
            self.details_toggle.set_tooltip_text("Image description")
            self.details_toggle.update_property(
                [Gtk.AccessibleProperty.LABEL], ["Image description"]
            )
            self.details_toggle.connect("toggled", lambda *_: self.sync_description_visibility())
            header.pack_end(self.details_toggle)

        zoom_controls = box(False, 8)
        steps = box(False, 0)
        steps.add_css_class("linked")
        self.minus = button("zoom-out-symbolic", "Zoom out (-)", lambda: self.step_zoom(-1))
        self.fit = button(None, "Fit image (0)", lambda: self.set_zoom(None), "Fit")
        self.plus = button("zoom-in-symbolic", "Zoom in (+)", lambda: self.step_zoom(1))
        self.level = Gtk.Label(width_chars=5)
        steps.append(self.minus)
        steps.append(self.plus)
        zoom_controls.append(steps)
        zoom_controls.append(self.level)
        zoom_controls.append(self.fit)
        zoom_bar = Gtk.CenterBox(center_widget=zoom_controls, margin_top=6, margin_bottom=6)
        toolbar.add_bottom_bar(zoom_bar)
        toolbar.set_content(self.body)
        self.set_child(toolbar)

        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 680sp"))
        narrow.connect("apply", lambda *_: self.set_narrow(True))
        narrow.connect("unapply", lambda *_: self.set_narrow(False))
        self.add_breakpoint(narrow)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)
        wheel = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.VERTICAL,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        wheel.connect("scroll", self.scroll_zoom)
        self.image_scroll.add_controller(wheel)
        drag = Gtk.GestureDrag(button=Gdk.BUTTON_PRIMARY)
        drag.connect("drag-begin", self.drag_begin)
        drag.connect("drag-update", self.drag_update)
        # Keep drag coordinates stable while the canvas moves under the pointer.
        viewport.add_controller(drag)
        self.connect("closed", self.finish)
        self.show_image(index)

    def show_image(self, index):
        self.clear_image()
        self.index, self.media = index, self.gallery[index]
        self.portrait = self.media.height > self.media.width > 0
        alt = self.media.alt
        self.description.set_label(alt)
        self.description.select_region(0, 0)
        self.description_scroll.get_vadjustment().set_value(0)
        self.canvas.update_property(
            [Gtk.AccessibleProperty.LABEL], [alt if alt.strip() else "Image"]
        )
        self.browser.set_visible(bool(self.original_uri()))
        self.sync_description_visibility()
        self.layout_details()
        if self.gallery_title is not None:
            self.gallery_title.set_subtitle(f"{index + 1} of {len(self.gallery)}")
            self.previous.set_sensitive(index > 0)
            self.next.set_sensitive(index + 1 < len(self.gallery))
        self.load()

    def sync_description_visibility(self):
        has_description = bool(self.media.alt.strip())
        self.details_toggle.set_visible(has_description)
        self.details.set_visible(has_description and self.details_toggle.get_active())

    def original_uri(self):
        return safe_url(self.media.fullsize or self.media.url)

    def open_original(self):
        if uri := self.original_uri():
            self.window.open_uri(uri)

    def copy_description(self):
        if self.media.alt.strip():
            self.window.get_clipboard().set(self.media.alt)
            self.window.toast("Description copied")

    def move(self, offset):
        index = self.index + offset
        if not 0 <= index < len(self.gallery):
            return False
        source, opposite = (self.next, self.previous) if offset > 0 else (self.previous, self.next)
        focused = source.has_focus()
        self.show_image(index)
        if focused and not source.get_sensitive():
            opposite.grab_focus()
        return True

    def set_narrow(self, narrow):
        self.narrow = narrow
        self.layout_details()

    def layout_details(self):
        side = self.portrait and not self.narrow and bool(self.media.alt.strip())
        self.body.set_orientation(Gtk.Orientation.HORIZONTAL if side else Gtk.Orientation.VERTICAL)
        self.details.set_size_request(250 if side else -1, -1)
        self.description_scroll.set_max_content_height(300 if side else 132)

    def valid(self, serial):
        return (
            not self.closed
            and serial == self.request_serial
            and self.window.generation == self.generation
            and self.window.service.account is self.account
            and not self.window.closing
        )

    def load(self):
        self.request_serial += 1
        serial = self.request_serial
        if self.task is not None:
            self.task.cancel()
        self.stage.set_visible_child_name("loading")
        self.update_controls()
        self.task = self.window.worker.submit(
            self.window.images.get(
                self.media.fullsize or self.media.url, self.media.local, explicit=True
            ),
            lambda texture: self.loaded(serial, texture),
            lambda message: self.failed(serial, message),
        )

    def loaded(self, serial, texture):
        if not self.valid(serial):
            return
        self.task = None
        self.window.images.bind(self.canvas, texture)
        self.canvas.texture = texture
        self.portrait = texture.get_height() > texture.get_width()
        self.layout_details()
        self.canvas.queue_draw()
        self.stage.set_visible_child_name("image")
        self.update_controls()

    def failed(self, serial, message):
        if self.valid(serial):
            self.task = None
            self.error.set_text("Image unavailable. " + message)
            self.stage.set_visible_child_name("error")

    def finish(self, *_args):
        self.closed = True
        self.clear_image()

    def clear_image(self):
        if self.task is not None:
            self.task.cancel()
            self.task = None
        if self.center_tick is not None:
            self.canvas.remove_tick_callback(self.center_tick)
        self.center_tick = self.center = self.drag_origin = None
        if self.canvas.texture is not None:
            self.window.images.unbind(self.canvas)
            self.canvas.texture = None
        self.canvas.zoom = None
        self.canvas.queue_resize()
        self.canvas.queue_draw()
        for adjustment in self.adjustments:
            adjustment.set_value(0)

    def fit_scale(self):
        if not all(a.get_page_size() > 0 for a in self.adjustments):
            return 1
        return min(
            self.adjustments[0].get_page_size() / self.canvas.texture.get_width(),
            self.adjustments[1].get_page_size() / self.canvas.texture.get_height(),
            1,
        )

    def update_controls(self):
        ready = self.canvas.texture is not None
        zoom = self.canvas.zoom
        scale = self.fit_scale() if ready else 0
        self.level.set_label(f"{zoom if zoom is not None else scale:.0%}" if ready else "")
        self.fit.set_sensitive(ready and zoom is not None)
        self.minus.set_sensitive(ready and zoom is not None and zoom > scale)
        self.plus.set_sensitive(ready and (zoom is None or zoom < MAX_ZOOM))
        pannable = any(a.get_upper() > a.get_page_size() for a in self.adjustments)
        self.canvas.set_cursor_from_name("grab" if pannable else None)

    def step_zoom(self, direction):
        if self.canvas.texture is not None:
            scale = self.fit_scale()
            current = self.canvas.zoom if self.canvas.zoom is not None else scale
            target = current * ZOOM_STEP**direction
            self.set_zoom(None if target <= scale * 1.001 else target)

    def set_zoom(self, zoom):
        texture = self.canvas.texture
        if texture is None:
            return
        if zoom is not None:
            zoom = min(MAX_ZOOM, max(self.fit_scale(), zoom))
        if self.canvas.zoom == zoom:
            return
        if self.center is None:
            self.center = tuple(
                (a.get_value() + a.get_page_size() / 2) / a.get_upper() if a.get_upper() else 0.5
                for a in self.adjustments
            )
        self.canvas.zoom = zoom
        self.canvas.queue_resize()
        self.canvas.queue_draw()
        self.update_controls()
        if self.center_tick is None:
            self.center_frames = 0
            self.center_tick = self.canvas.add_tick_callback(self.restore_center)

    def restore_center(self, *_args):
        self.center_frames += 1
        zoom = self.canvas.zoom
        texture = self.canvas.texture
        for adjustment, intrinsic in zip(
            self.adjustments, (texture.get_width(), texture.get_height()), strict=True
        ):
            page = adjustment.get_page_size()
            requested = ceil(zoom * intrinsic) if zoom is not None else 0
            if self.center_frames < 4 and not isclose(
                adjustment.get_upper(), max(page, requested), abs_tol=1
            ):
                return True
        for adjustment, center in zip(self.adjustments, self.center, strict=True):
            adjustment.set_value(center * adjustment.get_upper() - adjustment.get_page_size() / 2)
        self.center_tick = self.center = None
        return False

    def key_pressed(self, _controller, key, _code, modifiers):
        if modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        if key in (Gdk.KEY_Left, Gdk.KEY_Right) and self.gallery_title is not None:
            if self.canvas.zoom is not None or modifiers & Gdk.ModifierType.SHIFT_MASK:
                return False
            focus = self.window.get_focus()
            if focus is not None and (focus is self.details or focus.is_ancestor(self.details)):
                return False
            offset = 1 if key == Gdk.KEY_Right else -1
            return self.move(-offset if self.get_direction() == Gtk.TextDirection.RTL else offset)
        if key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.step_zoom(1)
        elif key in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.step_zoom(-1)
        elif key in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.set_zoom(None)
        elif key in (Gdk.KEY_1, Gdk.KEY_KP_1):
            self.set_zoom(1)
        else:
            return False
        return self.canvas.texture is not None

    def scroll_zoom(self, controller, _dx, dy):
        if dy and controller.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            self.step_zoom(1 if dy < 0 else -1)
            return True
        return False

    def drag_begin(self, gesture, _x, _y):
        device = gesture.get_device()
        if (device and device.get_source() == Gdk.InputSource.TOUCHSCREEN) or not any(
            a.get_upper() > a.get_page_size() for a in self.adjustments
        ):
            self.drag_origin = None
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        self.drag_origin = tuple(a.get_value() for a in self.adjustments)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def drag_update(self, _gesture, dx, dy):
        if self.drag_origin is not None:
            for adjustment, start, offset in zip(
                self.adjustments, self.drag_origin, (dx, dy), strict=True
            ):
                adjustment.set_value(start - offset)
