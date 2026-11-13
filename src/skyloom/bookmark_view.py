"""Native saved-post browsing and explicit bookmark mutations."""

from dataclasses import replace
from time import monotonic

from gi.repository import Gtk

from .bookmark_service import UnavailableBookmark
from .domain import Post
from .records import RecordPager
from .request_scope import guard, submit
from .widgets import FeedView, box, label


class BookmarkView(FeedView):
    def __init__(self, window, page):
        super().__init__(window, render=self.render_bookmark, recycle=self.render_post)
        self.page = page
        self.records = RecordPager(lambda item: item.uri)

    def render_bookmark(self, item):
        if isinstance(item, Post):
            return self.render_post(item)
        row = box(spacing=12, margin=16)
        row.append(label(item.reason, "dim-label"))
        remove = Gtk.Button(label="Remove bookmark", halign=Gtk.Align.START)
        remove.connect("clicked", lambda *_: change_bookmark(self.window, item, False))
        self.window.online_control(remove)
        row.append(remove)
        return row

    def update_post(self, post):
        if post.unavailable == "This post was deleted.":
            self.records.items = [
                UnavailableBookmark(item.uri, post.unavailable) if item.uri == post.uri else item
                for item in self.records.items
            ]
            self.set_items(self.records.items, lambda item: item.uri)
            return
        super().update_post(post)

    def changed_bookmark(self, post, saved):
        items = self.records.items
        if not saved:
            self.records.items = [item for item in items if item.uri != post.uri]
        elif isinstance(post, Post):
            self.records.items = [post if item.uri == post.uri else item for item in items]
        self.set_items(self.records.items, lambda item: item.uri)
        if not self.records.items and not self.paging.busy:
            self.paging.message = (
                "No saved posts." if not self.records.cursor else "Load more saved posts."
            )
            self.paging.changed()


def open_bookmarks(window):
    window.go_home()
    page, toolbar, _header = window.new_page("Bookmarks")
    page.destination = "bookmarks"
    view = BookmarkView(window, page)
    page.content_view = view
    toolbar.set_content(view)

    def load(reset=True):
        if not reset and not view.records.cursor:
            return
        revision = getattr(window, "bookmark_revision", 0)
        view.paging.begin("Loading bookmarks…", reset=reset)

        def done(result):
            # A read already in flight must not restore a bookmark just removed.
            overrides = getattr(window, "bookmark_overrides", {})
            items = []
            for item in result.items:
                changed = overrides.get(item.uri)
                if changed and (
                    changed[0] > revision or (len(changed) > 2 and monotonic() < changed[2])
                ):
                    if not changed[1]:
                        continue
                    if isinstance(item, Post):
                        item = replace(item, bookmarked=True)
                items.append(item)
            place = view.interaction.capture()
            view.records.merge(
                items, result.cursor, reset=reset, anchor=place.key if place else None
            )
            added = view.set_items(view.records.items, lambda item: item.uri, reset=reset)
            view.load_more = lambda: load(False)
            view.paging.complete(
                view.records.cursor,
                len(view.records.items) if reset else added,
                "No saved posts." if not view.records.items else "",
            )

        def failed(message):
            view.load_more = lambda: load(reset)
            view.paging.fail(message)

        submit(
            window,
            page,
            window.service.bookmarks(None if reset else view.records.cursor),
            done,
            failed,
            page=page,
        )

    view.refresh = load
    load()
    return view


def change_bookmark(window, post, saved=None):
    if window.read_only or window.service.account is None:
        return
    if saved is None:
        saved = not getattr(post, "bookmarked", False)
    if isinstance(post, UnavailableBookmark) and saved:
        return
    key = (post.uri, "bookmark")
    if any(uri == post.uri for uri, _kind in window.mutations):
        return
    window.mutations.add(key)
    generation = window.generation
    account = window.service.account

    def done(result):
        window.mutations.discard(key)
        if generation != window.generation:
            return
        window.bookmark_revision = getattr(window, "bookmark_revision", 0) + 1
        overrides = getattr(window, "bookmark_overrides", {})
        overrides[post.uri] = (window.bookmark_revision, saved, monotonic() + 120)
        while len(overrides) > 2000:
            overrides.pop(next(iter(overrides)))
        window.bookmark_overrides = overrides
        if isinstance(result, Post):
            window.update_post(result)
        for view in window.views:
            if isinstance(view, BookmarkView):
                view.changed_bookmark(result, saved)
        window.toast("Post bookmarked" if saved else "Bookmark removed")

    def failed(message):
        window.mutations.discard(key)
        if generation == window.generation:
            window.toast(message + " Refresh bookmarks to check before trying again.")

    window.worker.submit(
        window.service.bookmark(post, saved, expected_account=account),
        guard(window, None, done),
        guard(window, None, failed),
    )
