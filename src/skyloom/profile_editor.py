"""Responsive own-profile editor; errors retain the entered text and images."""

import asyncio

from gi.repository import Adw, Gio, GLib, Gtk

from .errors import UserError
from .profile_service import validate_profile
from .richtext import counts
from .widgets import box, button, label, should_load_image


class ProfileEditor(Adw.Dialog):
    def __init__(self, window, saved, author=None):
        super().__init__(
            title="Edit profile", content_width=560, content_height=620, can_close=False
        )
        self.window, self.saved = window, saved
        self.account = window.service.account
        self.author = author or self.account
        self.generation = window.generation
        self.original = None
        self.closed = False
        self.saving = False
        self.preparing = False
        self.images = {"avatar": None, "banner": None}
        self.image_labels = {}
        self.previews = {}
        self.preview_keys = {}
        self.preview_requests = {}
        self.image_controls = []
        self.initial_text = ("", "")
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        self.cancel = button("", "Cancel profile editing", self.close, "Cancel")
        self.save_button = button("", "Save profile", self.save, "Save")
        self.save_button.add_css_class("suggested-action")
        header.pack_start(self.cancel)
        header.pack_end(self.save_button)
        toolbar.add_top_bar(header)
        content = box(spacing=16, margin=20)
        if window.demo:
            content.append(label("Demo · changes stay on this computer", "dim-label"))
        self.name = Adw.EntryRow(title="Display name")
        group = Adw.PreferencesGroup()
        group.add(self.name)
        content.append(group)
        content.append(label("Description", "heading"))
        self.description = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, height_request=140)
        self.description.update_property([Gtk.AccessibleProperty.LABEL], ["Profile description"])
        self.buffer = self.description.get_buffer()
        self.buffer.set_enable_undo(True)
        content.append(self.description)
        self.count = label("", "dim-label")
        content.append(self.count)
        for field, title in (("avatar", "Profile picture"), ("banner", "Banner")):
            content.append(label(title, "heading"))
            preview = Gtk.Picture(
                can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, height_request=100
            )
            preview.set_alternative_text(title)
            preview.set_visible(False)
            self.previews[field] = preview
            content.append(preview)
            status = label("", "dim-label")
            self.image_labels[field] = status
            content.append(status)
            controls = Adw.WrapBox(child_spacing=6, line_spacing=6)
            choose = button(
                "insert-image-symbolic",
                f"Choose {title.lower()}",
                lambda f=field: self.choose(f),
                "Choose image…",
            )
            remove = button(
                "", f"Remove {title.lower()}", lambda f=field: self.set_image(f, ""), "Remove"
            )
            reset = button(
                "",
                f"Keep existing {title.lower()}",
                lambda f=field: self.set_image(f, None),
                "Keep existing",
            )
            for control in (choose, remove, reset):
                controls.append(control)
                self.image_controls.append(control)
            content.append(controls)
        self.feedback = label("Loading profile…", "dim-label", selectable=True)
        content.append(self.feedback)
        self.retry = button("view-refresh-symbolic", "Retry loading profile", self.load, "Retry")
        self.retry.set_visible(False)
        content.append(self.retry)
        toolbar.set_content(
            Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=content)
        )
        self.set_child(toolbar)
        self.name.connect("changed", self.changed)
        self.buffer.connect("changed", self.changed)
        self.connect("close-attempt", self.close_attempt)
        self.connect("closed", self.on_closed)
        self.load()

    def alive(self):
        return (
            not self.closed
            and self.window.generation == self.generation
            and self.window.service.account is self.account
            and not self.window.closing
        )

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def load(self):
        if not self.alive():
            return
        self.retry.set_visible(False)
        self.feedback.set_label("Loading profile…")
        self.changed()

        def ready(original):
            if not self.alive():
                return
            self.original = original
            record = original.record
            self.initial_text = (record.get("displayName", ""), record.get("description", ""))
            self.name.set_text(self.initial_text[0])
            self.buffer.set_text(self.initial_text[1])
            self.feedback.set_label("")
            self.changed()
            self.name.grab_focus()

        def failed(msg):
            if self.alive():
                self.feedback.set_label(msg)
                self.retry.set_visible(True)

        self.window.worker.submit(self.window.service.editable_profile(), ready, failed)

    def changed(self, *_args):
        ready = (
            self.original is not None and self.alive() and not self.saving and not self.preparing
        )
        self.name.set_sensitive(ready)
        self.description.set_editable(ready)
        for control in self.image_controls:
            control.set_sensitive(ready)
        self.window.online_control(
            self.save_button,
            ready=ready and not validate_profile(self.name.get_text(), self.text()),
        )
        n, size = counts(self.name.get_text())
        d, dsize = counts(self.text())
        self.count.set_label(
            f"Name {n}/64 · {size}/640 bytes\nDescription {d}/256 · {dsize}/2560 bytes"
        )
        if self.original:
            for field, status in self.image_labels.items():
                value = self.images[field]
                status.set_label(
                    "New image selected"
                    if value
                    else "Image will be removed"
                    if value == ""
                    else "Keep current image"
                    if self.original.record.get(field)
                    else "No image"
                )
                self.preview(field)

    def preview(self, field):
        selected = self.images[field]
        path = getattr(self.author, field) if selected is None else selected
        local = selected is not None
        key = (path, local)
        if self.preview_keys.get(field) == key:
            return
        self.preview_keys[field] = key
        if pending := self.preview_requests.pop(field, None):
            pending.cancel()
        picture = self.previews[field]
        picture.set_paintable(None)
        picture.set_visible(False)
        if not path or not should_load_image(self.window, path, local=local):
            return

        def ready(texture):
            if self.alive() and self.preview_keys.get(field) == key:
                picture.set_paintable(texture)
                picture.set_visible(True)

        self.preview_requests[field] = self.window.worker.submit(
            self.window.images.get(path, local=local), ready
        )

    def set_image(self, field, path):
        if self.alive() and not self.saving and not self.preparing:
            self.images[field] = path
            self.changed()

    def choose(self, field):
        if not self.alive() or self.saving or self.preparing:
            return
        chooser = Gtk.FileDialog(title="Choose a profile image")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        image_filter = Gtk.FileFilter(name="JPEG and PNG images")
        image_filter.add_mime_type("image/jpeg")
        image_filter.add_mime_type("image/png")
        filters.append(image_filter)
        chooser.set_filters(filters)
        storage = self.window.service.storage
        token = storage.token(self.account.did)

        def picked(dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if not self.alive() or not file or not file.get_path():
                return
            self.preparing = True
            self.feedback.set_label("Preparing image…")
            self.changed()

            async def prepare():
                return await asyncio.to_thread(
                    storage.run, self.account.did, token, "prepare_image", file.get_path()
                )

            def ready(path):
                if self.alive():
                    self.preparing = False
                    if path is not None:
                        self.images[field] = path
                    self.feedback.set_label("")
                    self.changed()

            def failed(msg):
                if self.alive():
                    self.preparing = False
                    self.feedback.set_label(msg)
                    self.changed()

            self.window.worker.submit(prepare(), ready, failed)

        chooser.open(self.window, None, picked)

    def save(self):
        if not self.alive() or self.original is None or self.saving or self.preparing:
            return
        if self.window.read_only:
            self.feedback.set_label("Connect to the internet before saving your profile.")
            return
        if error := validate_profile(self.name.get_text(), self.text()):
            self.feedback.set_label(error)
            return
        self.saving = True
        self.feedback.set_label("Saving profile…")
        self.cancel.set_sensitive(False)
        self.changed()

        def ready(author):
            if self.alive():
                self.saving = False
                self.force_close()
                self.saved(author)

        def failed(msg):
            if self.alive():
                self.saving = False
                self.cancel.set_sensitive(True)
                self.feedback.set_label(
                    msg
                    + " Your changes are kept here. If the connection failed, check your profile before saving again."
                )
                self.changed()

        service, account = self.window.service, self.account
        original, name, description, images = (
            self.original,
            self.name.get_text(),
            self.text(),
            self.images.copy(),
        )

        async def update():
            if service.account is not account:
                raise UserError("The signed-in account changed. Reopen the profile editor.")
            return await service.update_profile(original, name, description, **images)

        self.window.worker.submit(update(), ready, failed)

    def close_attempt(self, *_args):
        if self.saving:
            return
        if self.original is None or (
            self.initial_text == (self.name.get_text(), self.text())
            and all(value is None for value in self.images.values())
        ):
            self.force_close()
            return
        alert = Adw.AlertDialog(
            heading="Discard profile changes?", body="Your changes have not been saved to Bluesky."
        )
        alert.add_response("cancel", "Continue editing")
        alert.add_response("discard", "Discard")
        alert.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_default_response("cancel")
        alert.set_close_response("cancel")
        alert.connect(
            "response",
            lambda _alert, response: self.force_close() if response == "discard" else None,
        )
        alert.present(self.window)

    def on_closed(self, *_args):
        self.closed = True
        for request in self.preview_requests.values():
            request.cancel()
        self.preview_requests.clear()
