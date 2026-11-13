"""GStreamer URI playback exposed as a native Gtk.MediaStream and paintable."""

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gdk, GLib, Gst, Gtk  # noqa: E402 - select the supported GI ABI first


class VideoStream(Gtk.MediaStream, Gdk.Paintable):
    def __init__(self, uri):
        super().__init__()
        Gst.init(None)
        self.pipeline = Gst.ElementFactory.make("playbin", None)
        self.sink = Gst.ElementFactory.make("gtk4paintablesink", None)
        self.paintable = None
        self.clock = None
        self.bus = None
        self.bus_signal = None
        self.paintable_signals = []
        self.closed = False
        if self.pipeline is None or self.sink is None:
            self.gerror(
                GLib.Error.new_literal(
                    video_error_domain(), "Native video support is unavailable.", 0
                )
            )
            return
        self.paintable = self.sink.get_property("paintable")
        self.paintable_signals = [
            self.paintable.connect("invalidate-contents", lambda *_: self.invalidate_contents()),
            self.paintable.connect("invalidate-size", lambda *_: self.invalidate_size()),
        ]
        self.pipeline.set_property("video-sink", self.sink)
        self.pipeline.set_property("uri", uri)
        self.pipeline.set_property("buffer-duration", 15 * Gst.SECOND)
        self.pipeline.set_property("buffer-size", 10 * 1024 * 1024)
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus_signal = self.bus.connect("message", self.message)
        self.clock = GLib.timeout_add(100, self.position)
        self.pipeline.set_state(Gst.State.PAUSED)

    def do_snapshot(self, snapshot, width, height):
        if self.paintable is not None:
            self.paintable.snapshot(snapshot, width, height)

    def do_get_intrinsic_width(self):
        return self.paintable.get_intrinsic_width() if self.paintable is not None else 0

    def do_get_intrinsic_height(self):
        return self.paintable.get_intrinsic_height() if self.paintable is not None else 0

    def do_get_intrinsic_aspect_ratio(self):
        return self.paintable.get_intrinsic_aspect_ratio() if self.paintable is not None else 0

    def do_play(self):
        return bool(
            not self.closed
            and self.pipeline is not None
            and self.pipeline.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
        )

    def do_pause(self):
        if not self.closed and self.pipeline is not None:
            self.pipeline.set_state(Gst.State.PAUSED)

    def do_seek(self, timestamp):
        if (
            self.closed
            or self.pipeline is None
            or not self.pipeline.seek_simple(
                Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, timestamp * 1000
            )
        ):
            self.seek_failed()

    def do_update_audio(self, muted, volume):
        if self.pipeline is not None:
            self.pipeline.set_property("mute", muted)
            self.pipeline.set_property("volume", volume)

    def message(self, _bus, message):
        if self.closed:
            return
        if message.type == Gst.MessageType.ERROR:
            # Never expose URLs, network diagnostics, or arbitrary stream metadata.
            self.gerror(
                GLib.Error.new_literal(video_error_domain(), "Couldn’t play this video.", 0)
            )
        elif message.type == Gst.MessageType.EOS:
            self.stream_ended()
        elif message.type == Gst.MessageType.ASYNC_DONE:
            if not self.is_prepared():
                _ok, duration = self.pipeline.query_duration(Gst.Format.TIME)
                query = Gst.Query.new_seeking(Gst.Format.TIME)
                seekable = self.pipeline.query(query) and query.parse_seeking()[1]
                self.stream_prepared(
                    self.pipeline.get_property("n-audio") > 0,
                    self.pipeline.get_property("n-video") > 0,
                    seekable,
                    max(0, duration) // 1000,
                )
            if self.is_seeking():
                self.seek_success()

    def position(self):
        if self.closed:
            self.clock = None
            return False
        if self.is_prepared() and self.pipeline is not None:
            success, position = self.pipeline.query_position(Gst.Format.TIME)
            if success:
                self.update(max(0, position) // 1000)
        return True

    def clear(self):
        if self.closed:
            return
        self.pause()
        self.closed = True
        if self.clock is not None:
            GLib.source_remove(self.clock)
            self.clock = None
        if self.bus is not None:
            if self.bus_signal is not None:
                self.bus.disconnect(self.bus_signal)
            self.bus.remove_signal_watch()
            self.bus = None
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if self.paintable is not None:
            for signal in self.paintable_signals:
                self.paintable.disconnect(signal)
        self.paintable_signals.clear()
        self.paintable = self.sink = None
        if self.is_prepared():
            self.stream_unprepared()
        self.invalidate_contents()


def video_error_domain():
    return GLib.quark_from_string("skyloom-video-error")
