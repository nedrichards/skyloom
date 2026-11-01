"""Small session-only thread cache and idle Home viewport prefetch."""

import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace

from gi.repository import GLib

from .conversation import ThreadPage
from .domain import Post
from .request_scope import submit
from .widgets import post_positions


@dataclass(frozen=True, slots=True)
class ThreadSnapshot:
    anchor: str
    page: ThreadPage
    created: float
    uris: frozenset[str] = field(init=False)
    covered: frozenset[str] = field(init=False)

    def __post_init__(self):
        uris = frozenset(post.uri for post in self.page.posts)
        object.__setattr__(self, "uris", uris)
        # Ancestors are returned for context; their sibling replies were not fetched.
        edges = dict(self.page.edges)
        children = {}
        for post in self.page.posts:
            parent = edges.get(post.uri, post.parent[0] if post.parent else "")
            children.setdefault(parent, []).append(post.uri)
        covered, stack = set(), [self.anchor] if self.anchor in uris else []
        while stack:
            uri = stack.pop()
            if uri not in covered:
                covered.add(uri)
                stack.extend(children.get(uri, ()))
        object.__setattr__(self, "covered", frozenset(covered))


class ThreadCache:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pages = OrderedDict()
        self.attempts = OrderedDict()
        self.requests = []
        self.reactions = OrderedDict()
        self.revision = 0

    def clear(self):
        self.pages.clear()
        self.attempts.clear()
        self.requests.clear()
        self.reactions.clear()
        self.revision += 1

    def get_snapshot(self, uri):
        now = self.clock()
        return next(
            (
                snapshot
                for snapshot in reversed(self.pages.values())
                if now - snapshot.created < 120 and uri in snapshot.covered
            ),
            None,
        )

    def get(self, uri):
        snapshot = self.get_snapshot(uri)
        return snapshot.page if snapshot is not None else None

    def reconcile(self, page, *, started=None):
        if not self.reactions:
            return page

        def latest(post):
            known = self.reactions.get(post.uri)
            changes = {}
            if known:
                revision, values = known
                if started is None or revision > started or "pending" in values[2:]:
                    changes = dict(
                        zip(("likes", "reposts", "like_uri", "repost_uri"), values, strict=True)
                    )
            if post.quote:
                quote = latest(post.quote)
                if quote is not post.quote:
                    changes["quote"] = quote
            if changes and any(getattr(post, key) != value for key, value in changes.items()):
                return replace(post, **changes)
            return post

        posts = tuple(latest(post) for post in page.posts)
        return (
            replace(page, posts=posts)
            if any(a is not b for a, b in zip(posts, page.posts, strict=True))
            else page
        )

    def update_post(self, post):
        self.revision += 1
        self.reactions[post.uri] = (
            self.revision,
            (post.likes, post.reposts, post.like_uri, post.repost_uri),
        )
        self.reactions.move_to_end(post.uri)
        while len(self.reactions) > 2000:
            self.reactions.popitem(last=False)
        for anchor, snapshot in self.pages.items():
            page = self.reconcile(snapshot.page, started=self.revision - 1)
            if page is not snapshot.page:
                self.pages[anchor] = replace(snapshot, page=page)

    def put(self, uri, page, *, started=None):
        page = self.reconcile(page, started=started)
        self.pages[uri] = ThreadSnapshot(uri, page, self.clock())
        self.pages.move_to_end(uri)
        while len(self.pages) > 32:
            self.pages.popitem(last=False)
        return page

    def claim(self, uri):
        now = self.clock()
        self.requests = [stamp for stamp in self.requests if now - stamp < 60]
        if len(self.requests) >= 6 or now - self.attempts.get(uri, -float("inf")) < 300:
            return False
        self.attempts[uri] = now
        self.attempts.move_to_end(uri)
        while len(self.attempts) > 128:
            self.attempts.popitem(last=False)
        self.requests.append(now)
        return True


class HomeThreadPrefetch:
    def __init__(self, window, view, cache):
        self.window, self.view, self.cache = window, view, cache
        self.timer = None
        self.future = None
        self.allowed = None
        self.waiting = False
        self.key = "thread-prefetch"
        view.connect("unmap", self.cancel)
        view.cleanups.append(self.cancel)
        signal = window.connect("notify::is-active", lambda *_: self.schedule())
        view.cleanups.append(lambda: window.disconnect(signal))

    def eligible(self):
        window, view = self.window, self.view
        return (
            not view.paging.closed
            and view.get_mapped()
            and window.is_active()
            and window.interactions.current_view() is view
            and window.interactions.context() not in {"dialog", "popup", "text"}
            and not window.read_only
            and not window.automatic_pause_reason()
        )

    def reconsider(self):
        # Policy/worker notifications can resume pending work, but are not scrolling
        # and must not restart an existing viewport debounce.
        abandoned = (
            self.future is not None and self.window.page_requests.get(self.key) is not self.future
        )
        if abandoned:
            self.future.cancel()
            self.future = None
        allowed = self.eligible()
        resumed = allowed and self.allowed is not True
        self.allowed = allowed
        if not allowed:
            self.cancel()
        elif resumed or abandoned or (self.waiting and not self.busy()):
            self.schedule()

    def busy(self):
        return bool(self.window.page_requests or getattr(self.window, "mutations", ()))

    def schedule(self):
        self.allowed = self.eligible()
        if not self.allowed:
            self.cancel()
            return
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.future is None:
            self.waiting = False
            self.timer = GLib.timeout_add(350, self.run)

    def cancel(self, *_args):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.future is not None:
            if self.window.page_requests.get(self.key) is self.future:
                self.window.page_requests.pop(self.key)
            self.future.cancel()
            self.future = None

    def run(self):
        self.timer = None
        if not self.eligible():
            return False
        self.waiting = self.busy()
        if self.waiting:
            return False
        context = post_positions(self.window).context
        for _y, row in self.view.interaction.visible_rows():
            post = row._value
            if not isinstance(post, Post) or not (post.parent or post.root or post.replies):
                continue
            position = context.positions.get(post.uri)
            if position and not position[2]:
                continue
            uri = post.uri
            group = post.root[0] if post.root else uri
            if self.cache.get(uri) is not None or not self.cache.claim(group):
                continue
            started = self.cache.revision

            def done(page, uri=uri, started=started):
                self.future = None
                page = self.cache.put(uri, page, started=started)
                if self.eligible():
                    post_positions(self.window).remember(
                        page.posts,
                        incomplete=bool(
                            page.earlier
                            or page.branches
                            or page.gaps
                            or page.unavailable
                            or page.truncated
                        ),
                        parents=dict(page.edges),
                    )
                    self.schedule()

            def failed(_message):
                self.future = None
                # Automatic errors retain existing content; explicit opening can retry.

            self.future = submit(
                self.window, self.key, self.window.service.thread(uri), done, failed
            )
            break
        return False
