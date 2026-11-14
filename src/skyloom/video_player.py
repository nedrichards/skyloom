"""One explicit native video player, with bounded stream and account lifetime."""

from gi.repository import Adw, Gio, GLib, Gtk

from .domain import safe_https_url
from .video_stream import VideoStream


class Playback:
    """Shared explicit playback and account ownership lifecycle."""

    def check_owner(self):
        if self.closed:
            return False
        if (
            self.window.generation != self.generation
            or self.window.service.account is not self.account
            or getattr(self.window, "closing", False)
        ):
            self.owner_watch = None
            self.stop()
            self.close()
            return False
        if not self.source.local and self.window.read_only:
            self.fail("You’re offline. Reconnect and try again.")
        return True

    def start(self):
        if self.closed:
            return
        self.stop()
        self.retry.set_visible(False)
        if not self.source.local and self.window.read_only:
            self.fail("You’re offline. Reconnect and try again.")
            return
        self.message.set_label("Loading video…")
        self.message.set_visible(True)
        self.video.set_visible(True)
        file = (
            Gio.File.new_for_path(self.source.playlist)
            if self.source.local
            else Gio.File.new_for_uri(self.source.playlist)
        )
        self.stream = VideoStream(file.get_uri())
        self.stream.connect("notify::error", self.changed)
        self.stream.connect("notify::prepared", self.changed)
        self.video.set_media_stream(self.stream)
        self.timeout = GLib.timeout_add_seconds(30, self.loading_timeout)
        self.stream.play()
        self.changed(self.stream)

    def changed(self, stream, *_args):
        if self.closed or stream is not self.stream:
            return
        if stream.get_error() is not None:
            self.fail("Couldn’t play this video. Try again.")
        elif stream.is_prepared():
            if self.timeout is not None:
                GLib.source_remove(self.timeout)
                self.timeout = None
            self.message.set_visible(False)

    def loading_timeout(self):
        self.timeout = None
        self.fail("The video took too long to load. Try again.")
        return False

    def fail(self, message):
        self.stop()
        if self.video is not None:
            self.video.set_visible(False)
        self.message.set_label(message)
        self.message.set_visible(True)
        self.retry.set_visible(True)

    def stop(self):
        if self.timeout is not None:
            GLib.source_remove(self.timeout)
            self.timeout = None
        stream, self.stream = self.stream, None
        if self.video is not None:
            self.video.set_media_stream(None)
        if stream is not None:
            stream.pause()
            stream.clear()

    def finished(self, *_args):
        if self.closed:
            return
        self.closed = True
        self.stop()
        if self.owner_watch is not None:
            GLib.source_remove(self.owner_watch)
            self.owner_watch = None
        if getattr(self.window, "video_player", None) is self:
            self.window.video_player = None


class VideoPlayer(Playback, Adw.Dialog):
    def __init__(self, window, source):
        super().__init__(title="Video", content_width=880, content_height=600)
        self.window = window
        self.source = source
        self.account = window.service.account
        self.generation = window.generation
        self.stream = None
        self.timeout = None
        self.owner_watch = None
        self.closed = False
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.video = Gtk.Video(hexpand=True, vexpand=True, autoplay=False, loop=False)
        self.video.update_property([Gtk.AccessibleProperty.LABEL], [source.alt or "Video"])
        body.append(self.video)
        self.message = Gtk.Label(label="Loading video…", wrap=True)
        self.message.set_margin_start(16)
        self.message.set_margin_end(16)
        self.message.set_margin_bottom(12)
        body.append(self.message)
        self.retry = Gtk.Button(label="Try again", halign=Gtk.Align.CENTER, visible=False)
        self.retry.set_margin_bottom(16)
        self.retry.connect("clicked", lambda *_: self.start())
        body.append(self.retry)
        if source.alt.strip():
            description = Gtk.Label(label=source.alt, wrap=True, selectable=True)
            description.set_margin_start(16)
            description.set_margin_end(16)
            description.set_margin_bottom(16)
            body.append(description)
        toolbar.set_content(body)
        self.set_child(toolbar)
        self.connect("closed", self.finished)
        self.connect("unrealize", self.finished)
        self.owner_watch = GLib.timeout_add(100, self.check_owner)


def open_video(window, video):
    if window.service.account is None:
        return None
    if not video.local and not safe_https_url(video.playlist):
        window.toast("This video is unavailable.")
        return None
    if not video.local and window.read_only:
        window.toast("Reconnect to play this video.")
        return None
    previous = getattr(window, "video_player", None)
    if previous is not None:
        previous.stop()
        previous.close()
    player = VideoPlayer(window, video)
    window.video_player = player
    player.present(window)
    player.start()
    return player


class InlineVideo(Playback, Gtk.Box):
    """A feed player whose pipeline exists only after an explicit play action."""

    def __init__(self, window, source, preview):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.window = window
        self.source = source
        self.account = window.service.account
        self.generation = window.generation
        self.stream = self.timeout = self.owner_watch = None
        self.closed = False
        self.preview = preview
        self.poster = preview.get_first_child()
        self.preview.add_css_class("card")
        self.preview.set_overflow(Gtk.Overflow.HIDDEN)
        self.play = Gtk.Button(child=preview)
        self.play.add_css_class("flat")
        self.play.add_css_class("video-preview")
        self.play.set_tooltip_text("Play video inline; streams when played")
        self.play.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"Play video · {source.alt}" if source.alt else "Play video"],
        )
        self.play.connect("clicked", lambda *_: self.start())
        self.append(self.play)
        self.video = None
        self.message = Gtk.Label(wrap=True, visible=False)
        self.retry = Gtk.Button(label="Try again", halign=Gtk.Align.CENTER, visible=False)
        self.retry.connect("clicked", lambda *_: self.start())
        self.append(self.message)
        self.append(self.retry)
        self.connect("unmap", lambda *_: self.close())

    def start(self):
        if self.closed or not self.get_mapped():
            return
        if (
            self.window.service.account is not self.account
            or self.window.generation != self.generation
        ):
            self.finished()
            return
        if not self.source.local and not safe_https_url(self.source.playlist):
            self.fail("This video is unavailable.")
            return
        previous = getattr(self.window, "video_player", None)
        if previous is not None and previous is not self:
            previous.stop()
            previous.close()
        self.window.video_player = self
        if self.owner_watch is None:
            self.owner_watch = GLib.timeout_add(100, self.check_owner)
        if self.video is None:
            self.video = Gtk.Video(autoplay=False, loop=False, hexpand=True)
            self.video.update_property([Gtk.AccessibleProperty.LABEL], [self.source.alt or "Video"])
        if self.play.get_child() is not None:
            self.play.set_child(None)
            self.preview.set_child(self.video)
            self.prepend(self.preview)
        self.play.set_visible(False)
        super().start()

    def close(self):
        self.stop()
        if self.owner_watch is not None:
            GLib.source_remove(self.owner_watch)
            self.owner_watch = None
        if getattr(self.window, "video_player", None) is self:
            self.window.video_player = None
        if self.preview.get_parent() is self:
            self.remove(self.preview)
            self.preview.set_child(self.poster)
            self.play.set_child(self.preview)
        self.play.set_visible(True)
        self.message.set_visible(False)
        self.retry.set_visible(False)
