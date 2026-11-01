"""Debounced account-scoped reading checkpoints; GTK capture, worker-only SQLite IO."""

from dataclasses import replace

from gi.repository import GLib

from .domain import Post
from .feed_state import Bookmark
from .list_state import ListPlace


class ReadingSession:
    def __init__(self, window, view, feed):
        self.window, self.view, self.feed = window, view, feed
        self.account = window.service.account
        self.ready = False
        self.timer = self.future = self.latest = None
        self.dirty = False
        self.submitted = None
        self.warned = False
        self.closed = False
        adjustment = view.scroll.get_vadjustment()
        signal = adjustment.connect("value-changed", lambda *_: self.changed())
        view.cleanups.append(lambda: adjustment.disconnect(signal))
        signal = view.store.connect("notify::selected", lambda *_: self.changed())
        view.cleanups.append(lambda: view.store.disconnect(signal))
        view.cleanups.append(self.close)
        view.connect("unmap", lambda *_: self.flush())

    def capture(self):
        pager = self.window.pagers.get(self.feed)
        if not pager or not pager.posts:
            return None
        rows = [
            (y, row)
            for y, row in self.view.interaction.visible_rows()
            if isinstance(row._value, Post)
        ]
        if not rows:
            return None
        # The first intersecting border box preserves the entire visible viewport.
        y, row = rows[0]
        keys = [p.uri for p in pager.posts]
        uri = row._value.uri
        if uri not in keys:
            return None
        index = keys.index(uri)
        selected = self.view.interaction.selected()
        neighbours = tuple(keys[index + 1 : index + 5] + keys[max(0, index - 4) : index][::-1])
        return Bookmark(uri, y, getattr(selected, "uri", None), neighbours)

    def restore(self, bookmark):
        if bookmark is None:
            return False
        return self.view.interaction.restore(
            ListPlace(bookmark.uri, bookmark.offset, bookmark.selected)
        )

    def changed(self):
        if not self.ready or self.closed or self.timer is not None:
            return
        self.timer = GLib.timeout_add(1000, self.flush)

    def snapshot(self):
        if not self.ready:
            return self.latest
        pager = self.window.pagers.get(self.feed)
        if not pager or not pager.posts:
            return self.latest
        bookmark = self.capture() if self.view.position_tick is None else None
        if bookmark is None and self.latest:
            bookmark = self.latest[1]
        self.latest = (
            replace(
                pager,
                posts=list(pager.posts),
                seen_cursors=set(pager.seen_cursors),
                page_starts=pager.page_starts.copy(),
                gaps=pager.gaps.copy(),
            ),
            bookmark,
        )
        return self.latest

    def flush(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if not self.snapshot():
            return False
        if self.latest == self.submitted:
            return False
        self.dirty = True
        if self.future is not None:
            return False
        self.dirty = False
        pager, bookmark = self.latest
        self.submitted = self.latest

        def finished(_value):
            self.future = None
            if self.dirty:
                self.flush()

        def failed(_message):
            self.future = None
            self.submitted = None
            if not self.warned and not self.closed:
                self.warned = True
                self.window.toast(
                    "Could not save your reading position. Cached posts remain available."
                )

        self.future = self.window.worker.submit(
            self.window.service.save_feed_state(self.feed, pager, bookmark, self.account),
            finished,
            failed,
        )
        return False

    def close(self):
        if not self.closed:
            self.flush()
            self.closed = True
