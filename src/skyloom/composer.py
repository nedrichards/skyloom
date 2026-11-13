"""A responsive composer with durable drafts and guarded close/send operations."""

import asyncio
import threading
from dataclasses import asdict, replace

from gi.repository import Adw, Gio, GLib, Gtk

from .keyboard import match
from .richtext import counts, validate
from .service import Attachment
from .storage import post_restore
from .video_upload import VideoAttachment
from .widgets import box, button, label


class Composer(Adw.Dialog):
    def __init__(self, window, reply=None, quote=None, draft_key=None):
        super().__init__(
            title="Reply" if reply else "Quote post" if quote else "New post",
            content_width=620,
            content_height=620,
            can_close=False,
        )
        self.window, self.reply, self.quote = window, reply, quote
        self.account = window.service.account
        self.generation = window.generation
        self.key = "reply:" + reply.uri if reply else "quote:" + quote.uri if quote else "new"
        self.key = draft_key or self.key
        self.attachments = []
        self.video = None
        self.preparing = False
        self.prepare_cancel = None
        self.sending = False
        self.ready = False
        self.closed = False
        self.save_timer = None
        self.revision = 0
        self.toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        self.cancel_button = button("", "Keep or discard draft", self.close, "Cancel")
        self.send_button = button("", "Publish post (Ctrl+Enter)", self.send, "Post")
        self.send_button.add_css_class("suggested-action")
        self.send_button.set_sensitive(False)
        header.pack_start(self.cancel_button)
        header.pack_end(self.send_button)
        self.toolbar.add_top_bar(header)
        content = box(spacing=16, margin=20)
        self.context_label = box(spacing=6)
        content.append(self.context_label)
        if reply or quote:
            p = reply or quote
            self.context_label.append(
                label(("Replying to " if reply else "Quoting ") + p.author.name, "heading")
            )
            self.context_label.append(label(p.text[:200], "dim-label", lines=3))
        if window.demo:
            content.append(label("Demo · posts stay on this computer", "dim-label"))
        self.editor = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=10,
            bottom_margin=10,
            left_margin=10,
            right_margin=10,
            hexpand=True,
            vexpand=True,
        )
        self.editor.update_property([Gtk.AccessibleProperty.LABEL], ["Post text"])
        self.editor.set_size_request(-1, 160)
        self.editor.set_editable(False)
        self.buffer = self.editor.get_buffer()
        self.buffer.set_enable_undo(True)
        self.buffer.connect("changed", self.changed)
        content.append(self.editor)
        self.attach_box = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            min_children_per_line=1,
            max_children_per_line=2,
            row_spacing=10,
            column_spacing=10,
        )
        content.append(self.attach_box)
        footer = Adw.WrapBox(child_spacing=6, line_spacing=6)
        self.add = button(
            "insert-image-symbolic", "Attach JPEG or PNG image", self.choose_image, "Add image"
        )
        footer.append(self.add)
        self.add_video = button(
            "camera-video-symbolic", "Attach an MP4 video", self.choose_video, "Add video"
        )
        footer.append(self.add_video)
        self.count = label("", "dim-label", hexpand=True, xalign=1)
        content.append(footer)
        content.append(self.count)
        self.feedback = label("Loading saved draft…", "dim-label", selectable=True)
        content.append(self.feedback)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=content)
        self.toolbar.set_content(scroll)
        self.set_child(self.toolbar)
        self.connect("close-attempt", self.close_attempt)
        self.connect("closed", self.on_closed)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self.key_pressed)
        self.add_controller(key)
        self.window.worker.submit(window.service.draft_get(self.key), self.loaded, self.load_error)

    def key_pressed(self, _controller, keyval, _code, state):
        if (binding := match(keyval, state, "composer")) and binding.command == "publish":
            if self.send_button.get_sensitive():
                self.send()
            return True
        return False

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def alive(self):
        return (
            not self.closed
            and self.window.generation == self.generation
            and self.window.service.account is self.account
        )

    def validation(self):
        return validate(self.text(), self.attachments, self.video)

    def loaded(self, saved):
        if not self.alive():
            return
        if saved.get("reply") or saved.get("quote"):
            self.reply = post_restore(saved["reply"]) if saved.get("reply") else None
            self.quote = post_restore(saved["quote"]) if saved.get("quote") else None
            while child := self.context_label.get_first_child():
                self.context_label.remove(child)
            p = self.reply or self.quote
            self.context_label.append(
                label(("Replying to " if self.reply else "Quoting ") + p.author.name, "heading")
            )
            self.context_label.append(label(p.text[:200], "dim-label", lines=3))
            self.set_title("Reply" if self.reply else "Quote post")
        self.buffer.set_text(saved.get("text", ""))
        self.attachments = [Attachment(**x) for x in saved.get("attachments", [])]
        self.video = VideoAttachment(**saved["video"]) if saved.get("video") else None
        self.ready = True
        self.editor.set_editable(True)
        self.render_attachments()
        self.changed()
        self.editor.grab_focus()

    def load_error(self, msg):
        self.ready = True
        self.feedback.set_label("Couldn’t restore the draft. " + msg)
        self.editor.set_editable(False)
        self.add.set_sensitive(False)
        self.add_video.set_sensitive(False)
        self.send_button.set_sensitive(False)

    def snapshot(self):
        if not self.text().strip() and not self.attachments and self.video is None:
            return {}
        return {
            "text": self.text(),
            "attachments": [asdict(a) for a in self.attachments],
            "video": asdict(self.video) if self.video else None,
            "reply": asdict(self.reply) if self.reply else None,
            "quote": asdict(self.quote) if self.quote else None,
        }

    def changed(self, *_args):
        if not self.ready or self.closed:
            return
        self.revision += 1
        n, size = counts(self.text())
        self.count.set_label(f"{300 - n} characters · {size}/3000 bytes")
        error = self.validation()
        self.feedback.set_label(error or "Draft saves automatically on this device.")
        self.update_send_sensitivity()
        self.add.set_sensitive(
            len(self.attachments) < 4
            and self.video is None
            and not self.sending
            and not self.preparing
        )
        self.add_video.set_sensitive(
            not self.attachments and self.video is None and not self.sending and not self.preparing
        )
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(450, self.autosave)

    def update_send_sensitivity(self):
        self.send_button.set_sensitive(
            self.ready
            and not self.closed
            and not self.window.read_only
            and not self.sending
            and not self.preparing
            and not self.validation()
        )

    def autosave(self):
        self.save_timer = None
        self.window.worker.submit(
            self.window.service.draft_save(self.key, self.snapshot()),
            error=lambda msg: self.feedback.set_label("Draft not saved. " + msg),
        )
        return False

    def choose_image(self):
        service = self.window.service
        account = service.account
        if (
            self.closed
            or account is None
            or getattr(self, "video", None) is not None
            or getattr(self, "preparing", False)
        ):
            return
        storage = service.storage
        token = storage.token(account.did)
        chooser = Gtk.FileDialog(title="Choose an image")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter(name="JPEG and PNG images")
        f.add_mime_type("image/jpeg")
        f.add_mime_type("image/png")
        filters.append(f)
        chooser.set_filters(filters)

        def picked(dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if (
                self.closed
                or service.account is not account
                or not file
                or not file.get_path()
                or getattr(self, "video", None) is not None
                or getattr(self, "preparing", False)
                or len(self.attachments) >= 4
            ):
                return
            self.preparing = True
            self.add.set_sensitive(False)
            if hasattr(self, "add_video"):
                self.add_video.set_sensitive(False)
                self.update_send_sensitivity()

            async def make():
                return await asyncio.to_thread(
                    storage.run, account.did, token, "prepare_image", file.get_path()
                )

            def ready(path):
                if path is not None and not self.closed and service.account is account:
                    self.preparing = False
                    self.attachments.append(Attachment(path, ""))
                    self.render_attachments()
                    self.changed()

            def failed(msg):
                if not self.closed and service.account is account:
                    self.preparing = False
                    self.add.set_sensitive(True)
                    if hasattr(self, "add_video"):
                        self.changed()
                    self.feedback.set_label(msg)

            self.window.worker.submit(make(), ready, failed)

        chooser.open(self.window, None, picked)

    def choose_video(self):
        if not self.alive() or self.preparing or self.attachments or self.video is not None:
            return
        service, account = self.window.service, self.account
        storage, token = service.storage, service.storage.token(account.did)
        chooser = Gtk.FileDialog(title="Choose an MP4 video")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        file_filter = Gtk.FileFilter(name="MP4 videos")
        file_filter.add_mime_type("video/mp4")
        filters.append(file_filter)
        chooser.set_filters(filters)

        def picked(dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if (
                not self.alive()
                or not file
                or not file.get_path()
                or self.attachments
                or self.preparing
                or self.video is not None
            ):
                return
            self.preparing = True
            self.prepare_cancel = threading.Event()
            cancel = self.prepare_cancel
            self.changed()
            self.feedback.set_label("Preparing video… The original file is unchanged.")

            async def make():
                return await asyncio.to_thread(
                    storage.run, account.did, token, "prepare_video", file.get_path(), cancel
                )

            def ready(video):
                if self.alive():
                    self.preparing = False
                    self.prepare_cancel = None
                    self.video = video
                    self.render_attachments()
                    self.changed()

            def failed(msg):
                if self.alive():
                    self.preparing = False
                    self.prepare_cancel = None
                    self.changed()
                    self.feedback.set_label(msg)

            self.window.worker.submit(make(), ready, failed)

        chooser.open(self.window, None, picked)

    def render_attachments(self):
        while child := self.attach_box.get_first_child():
            self.attach_box.remove(child)
        if self.video is not None:
            group = box(spacing=8, margin=8)
            group.add_css_class("card")
            group.append(label(f"Video · {self.video.duration:.0f} seconds", "heading"))
            group.append(label("Description required", "caption"))
            description = Gtk.Entry(
                text=self.video.alt, placeholder_text="Describe what matters in this video"
            )
            description.update_property([Gtk.AccessibleProperty.LABEL], ["Video description"])

            def describe(entry):
                if self.video is not None:
                    self.video = replace(self.video, alt=entry.get_text())
                    self.changed()

            description.connect("changed", describe)
            group.append(description)

            def preview():
                from .domain import Video
                from .video_player import open_video

                open_video(self.window, Video(self.video.path, self.video.alt, local=True))

            group.append(
                button("media-playback-start-symbolic", "Preview video", preview, "Preview")
            )

            def remove_video():
                self.video = None
                self.render_attachments()
                self.changed()

            group.append(
                button("edit-delete-symbolic", "Remove video", remove_video, "Remove video")
            )
            self.attach_box.append(group)
        for index, attachment in enumerate(self.attachments):
            group = box(spacing=8, margin=8)
            group.add_css_class("card")
            preview = Gtk.Picture(
                can_shrink=True, height_request=90, content_fit=Gtk.ContentFit.CONTAIN
            )
            group.append(Adw.Clamp(maximum_size=200, tightening_threshold=160, child=preview))

            def loaded(pix, pic=preview):
                if not self.closed:
                    pic.set_paintable(pix)

            self.window.worker.submit(
                self.window.images.get(attachment.path, local=True),
                loaded,
                lambda msg: self.feedback.set_label("Preview unavailable. " + msg),
            )
            alt = Gtk.Entry(
                placeholder_text="Describe what matters in this image",
                text=attachment.alt,
                max_length=2000,
                width_chars=12,
                max_width_chars=16,
            )
            alt.update_property(
                [Gtk.AccessibleProperty.LABEL], [f"Description for image {index + 1}"]
            )

            def edited(entry, i=index):
                if i < len(self.attachments):
                    self.attachments[i] = Attachment(self.attachments[i].path, entry.get_text())
                    self.changed()

            alt.connect("changed", edited)
            group.append(label(f"Image {index + 1} · description required", "caption"))
            group.append(alt)

            def remove(i=index):
                self.attachments.pop(i)
                self.render_attachments()
                self.changed()

            group.append(
                button("edit-delete-symbolic", f"Remove image {index + 1}", remove, "Remove image")
            )
            self.attach_box.append(group)

    def send(self):
        if (
            not self.alive()
            or self.preparing
            or self.sending
            or self.window.read_only
            or self.validation()
        ):
            return
        self.sending = True
        self.send_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.add.set_sensitive(False)
        self.add_video.set_sensitive(False)
        self.editor.set_editable(False)
        self.attach_box.set_sensitive(False)
        self.feedback.set_label("Uploading and processing video…" if self.video else "Publishing…")
        if self.save_timer:
            GLib.source_remove(self.save_timer)
            self.save_timer = None

        service, account = self.window.service, self.account

        async def publish():
            if service.account is not account:
                return None
            await service.draft_save(self.key, self.snapshot_value)
            if service.account is not account:
                return None
            kwargs = {"video": self.send_video} if self.send_video else {}
            result = await service.send(
                self.send_text,
                self.send_attachments,
                self.reply,
                self.quote,
                expected_account=account,
                **kwargs,
            )
            if service.account is account:
                await service.draft_save(self.key, {})
            return result

        self.snapshot_value, self.send_text, self.send_attachments = (
            self.snapshot(),
            self.text(),
            tuple(self.attachments),
        )
        self.send_video = self.video

        def success(_result):
            if not self.alive():
                return
            self.window.toast("Demo post added" if self.window.demo else "Post published")
            self.force_close()
            self.window.refresh()

        def failure(msg):
            if not self.alive():
                return
            self.sending = False
            self.cancel_button.set_sensitive(True)
            self.editor.set_editable(True)
            self.attach_box.set_sensitive(True)
            self.changed()
            self.feedback.set_label(
                msg
                + " Your draft is kept. If the connection failed, check your profile before trying again to avoid a duplicate."
            )

        self.window.worker.submit(publish(), success, failure)

    def close_attempt(self, *_args):
        if self.sending:
            return
        if not self.ready:
            self.force_close()
            return
        if not self.text().strip() and not self.attachments and self.video is None:
            self.window.worker.submit(
                self.window.service.draft_save(self.key, {}),
                lambda _: self.force_close(),
                lambda msg: self.feedback.set_label(msg),
            )
            return
        alert = Adw.AlertDialog(
            heading="Keep this draft?",
            body="Keep it on this device to finish later, or discard it.",
        )
        alert.add_response("cancel", "Continue writing")
        alert.add_response("discard", "Discard")
        alert.add_response("keep", "Keep draft")
        alert.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_default_response("keep")
        alert.set_close_response("cancel")

        def response(_a, value):
            if value == "cancel":
                return
            if self.save_timer:
                GLib.source_remove(self.save_timer)
                self.save_timer = None
            self.set_sensitive(False)
            snapshot = self.snapshot() if value == "keep" else {}

            def saved(_):
                self.force_close()

            def failed(msg):
                self.set_sensitive(True)
                self.feedback.set_label(msg)

            self.window.worker.submit(
                self.window.service.draft_save(self.key, snapshot), saved, failed
            )

        alert.connect("response", response)
        alert.present(self.window)

    def on_closed(self, *_args):
        self.closed = True
        if self.prepare_cancel is not None:
            self.prepare_cancel.set()
        if self.save_timer:
            GLib.source_remove(self.save_timer)
            self.save_timer = None
        self.window.composer = None
