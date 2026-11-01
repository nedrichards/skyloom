"""Shared native feed presentation, also used by demo and conversation views."""

from contextvars import ContextVar
from dataclasses import replace
from difflib import SequenceMatcher
from itertools import pairwise
from time import monotonic
from typing import ClassVar
from weakref import WeakSet

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from .content import LabelledContent
from .domain import Author, Notice, Post, relative_time, safe_url
from .feed_state import FeedGap
from .list_feedback import TopPeek, UpdateNotice
from .list_interaction import ListInteraction
from .motion import allowed as motion_allowed
from .pagination import AutoPager
from .richtext import markup
from .thread_context import ThreadContext


def box(vertical=True, spacing=12, margin=0):
    widget = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
        spacing=spacing,
    )
    for edge in ("top", "bottom", "start", "end"):
        getattr(widget, "set_margin_" + edge)(margin)
    return widget


def label(text="", css=None, **kwargs):
    w = Gtk.Label(label=text, **{"xalign": 0, "wrap": True, **kwargs})
    if css:
        w.add_css_class(css)
    return w


def button(icon, tooltip, callback, text=None, *, count=None):
    if count is None:
        w = Gtk.Button(label=text) if text is not None else Gtk.Button(icon_name=icon)
    else:
        # Construct the final children once; avoid creating and discarding an icon
        # for every action in GTK's large native row buffer.
        w = Gtk.Button()
        content = box(False, 6)
        w.glyph = Gtk.Image(icon_name=icon, pixel_size=16)
        w.count = Gtk.Label(label=str(count))
        content.append(w.glyph)
        content.append(w.count)
        w.set_child(content)
    w.set_tooltip_text(tooltip)
    w.focus_key = ("button", icon or tooltip)
    w.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
    w.connect("clicked", lambda _b: callback())
    return w


def status(title, description, icon="dialog-information-symbolic", retry=None):
    w = Adw.StatusPage(title=title, description=description, icon_name=icon)
    if retry:
        b = Gtk.Button(label="Try again", halign=Gtk.Align.CENTER)
        b.add_css_class("suggested-action")
        b.connect("clicked", lambda _b: retry())
        w.set_child(b)
    return w


def should_load_image(window, url="", local=False):
    if not window.settings.get_boolean("load-images"):
        return False
    if local or window.images.has_cached(url, local):
        return True
    return not getattr(window, "automatic_pause_reason", lambda: "")()


media_binding = ContextVar("media-binding", default=None)


class PendingMedia:
    """One reusable viewport consumer; releasing it never changes card geometry."""

    def __init__(self, view, widget, load, release=lambda: None):
        self.view, self.widget, self.load, self.clear = view, widget, load, release
        self.future = None
        self.active = False
        view.pending_media.add(self)
        view.media_bindings.add(self)

    def start(self):
        if self.active:
            return
        self.active = True
        self.view.pending_media.discard(self)
        self.future = self.load()

    def release(self):
        if not self.active:
            return
        self.active = False
        self.widget._image_serial = getattr(self.widget, "_image_serial", 0) + 1
        if self.future is not None:
            self.future.cancel()
            self.future = None
        self.clear()
        self.view.pending_media.add(self)

    def cancel(self):
        self.release()
        self.view.pending_media.discard(self)
        self.view.media_bindings.discard(self)


def image_callback(widget, callback):
    serial = getattr(widget, "_image_serial", 0)
    return lambda value: callback(value) if serial == getattr(widget, "_image_serial", 0) else None


def start_image(widget, load, owner=None, release=lambda: None):
    context = media_binding.get()
    if context is None and owner is not None:
        view = owner.get_ancestor(FeedView)
        if view is not None:
            context = (view, owner._media_requests)
    if context is None:
        return load()
    view, requests = context
    requests.append(PendingMedia(view, widget, load, release))
    view.queue_check()
    return None


def remember_request(pending, future):
    if pending is None or future is None:
        return
    pending.append(future)

    def completed(finished):
        def forget():
            if finished in pending:
                pending.remove(finished)
            return False

        GLib.idle_add(forget)

    future.add_done_callback(completed)


def avatar(author, window, size=44, *, pending=None):
    w = Adw.Avatar(size=size, text=author.name, show_initials=True)
    if (
        author.avatar
        and should_load_image(window, author.avatar)
        and not (author.labels and window.settings.get_boolean("warn-labelled-content"))
    ):

        def loaded(pix):
            window.images.bind(w, pix)
            w.set_custom_image(pix)

        def release():
            w.set_custom_image(None)
            window.images.unbind(w)

        def load():
            cached = getattr(window.images, "cache", {}).get((author.avatar, False))
            if cached is not None:
                loaded(cached)
                return None
            future = window.worker.submit(
                window.images.get(author.avatar), image_callback(w, loaded)
            )
            remember_request(pending, future)
            return future

        def unrealized(*_):
            w._image_serial = getattr(w, "_image_serial", 0) + 1
            release()

        w.connect("unrealize", unrealized)
        if media_binding.get() is None:
            w.connect("map", lambda *_: load() if w.get_custom_image() is None else None)
        start_image(w, load, release=release)
    return w


def counters_only(previous, current):
    return (
        isinstance(previous, Post)
        and isinstance(current, Post)
        and replace(
            previous,
            likes=current.likes,
            reposts=current.reposts,
            replies=current.replies,
            like_uri=current.like_uri,
            repost_uri=current.repost_uri,
        )
        == current
    )


class PostObject(GObject.Object):
    __gsignals__: ClassVar[dict] = {"changed": (GObject.SignalFlags.RUN_LAST, None, ())}

    def update(self, post):
        self.post = post
        self.emit("changed")

    def __init__(self, post):
        super().__init__()
        self.post = post


class NoticeRow(Gtk.ListBox):
    """Read-state changes keep the native notification row and its focus intact."""

    def __init__(self, notice, window):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE)
        self.notice = notice
        self.row = Adw.ActionRow(
            use_markup=False,
            title=notice.author.name,
            activatable=True,
            margin_start=16,
            margin_end=16,
        )
        self.window = window
        self.row.add_prefix(avatar(notice.author, window))
        self.marker = Gtk.Image(icon_name="mail-unread-symbolic", pixel_size=16)
        self.marker.add_css_class("unread-indicator")
        self.marker.set_tooltip_text("Unread notification")
        self.marker.update_state([Gtk.AccessibleState.HIDDEN], [True])
        self.row.add_suffix(self.marker)
        self.row.set_subtitle(notice.reason.replace("-", " "))
        self.row.connect(
            "activated",
            lambda _: (
                window.profile(self.notice.author.did)
                if self.notice.reason == "follow"
                else window.thread(self.notice.subject or self.notice.uri)
            ),
        )
        self.append(self.row)
        self.update_notice(notice)

    def update_notice(self, notice):
        self.notice = notice
        self.marker.set_can_target(not notice.read)
        self.row.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            ["Read notification" if notice.read else "Unread notification"],
        )
        motion = getattr(self.window, "motion", None)
        if motion is None:
            self.marker.set_opacity(0 if notice.read else 1)
        else:
            motion.fade(self.marker, 0 if notice.read else 1)


class PageFooter(Gtk.Box):
    def __init__(self, view):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_top=12,
            margin_bottom=16,
            margin_start=20,
            margin_end=20,
        )
        self.view = view
        self.spinner = Gtk.Spinner(halign=Gtk.Align.CENTER)
        self.message = label("", "dim-label", halign=Gtk.Align.CENTER)
        self.more = button("", "Load more results", lambda: view.paging.request(), "Load more")
        self.more.set_halign(Gtk.Align.CENTER)
        self.append(self.spinner)
        self.append(self.message)
        self.append(self.more)
        view.footers.add(self)
        self.sync()

    def sync(self):
        state = self.view.paging
        self.set_visible(not getattr(self.view, "status_active", False))
        self.spinner.set_visible(state.busy)
        self.spinner.set_spinning(state.busy and self.get_visible())
        text = state.error or state.message or (self.view.pause_reason() if state.cursor else "")
        self.message.set_label(text)
        self.message.set_visible(bool(text))
        self.more.set_visible(
            bool(state.cursor or state.error or state.manual_available) and not state.busy
        )
        self.more.set_label(
            "Try again" if state.error else "Load posts" if state.manual_available else "Load more"
        )
        action = (
            "Retry loading results"
            if state.error
            else "Load posts"
            if state.manual_available
            else "Load more results"
        )
        self.more.set_tooltip_text(action)
        self.more.update_property([Gtk.AccessibleProperty.LABEL], [action])
        self.more.set_sensitive(
            not state.busy
            and not (getattr(self.view, "is_conversation", False) and self.view.window.read_only)
        )

    def cancel(self):
        self.view.footers.discard(self)


class PostPositions:
    """Share bounded relationship knowledge and update mounted pills in place."""

    def __init__(self):
        self.context = ThreadContext()
        self.rows = WeakSet()

    def remember(self, posts, *, incomplete=None, parents=None):
        previous = self.context.positions
        if self.context.remember(posts, incomplete=incomplete, parents=parents):
            for row in tuple(self.rows):
                position = self.context.positions.get(row.post.uri)
                if position != previous.get(row.post.uri):
                    row.update_position(position)

    def bind(self, row):
        self.remember((row.post,))
        self.rows.add(row)
        row.position_owner = self
        row.update_position(self.context.positions.get(row.post.uri))


def post_positions(window):
    if getattr(window, "post_positions", None) is None:
        window.post_positions = PostPositions()
    return window.post_positions


class FeedView(Gtk.Box):
    """One full-width virtualised scrolling surface, including its pager footer."""

    def __init__(self, window, render=None, update=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        self.reading = None
        self.feed = None
        self.input_serial = 0
        self.update_row = update
        self.window = window
        self.feed_preview = render is None
        self.connections = set()
        self.render = render or self.render_post
        self.load_more = lambda: None
        self.refresh = None
        self.focus_when_ready = False
        self.key = lambda item: getattr(item, "uri", None)
        self.rows = WeakSet()
        self.pending_update = None
        self.pending_media = set()
        self.media_bindings = set()
        self.update_notice = UpdateNotice(self)
        self.connect("unmap", self.update_notice.unmap)
        self.post_updated = lambda _post: None
        self.footers = WeakSet()
        self.paging = AutoPager(lambda: self.load_more(), self.paging_changed)
        self.check_pending = False
        self.paging_ready = True
        self.position_tick = None
        self.cleanups = []
        self.arrival_keys = set()
        self.reveal_rows = set()
        self.arrival_active = False
        self.arrival_tick = self.reveal_source = None
        self.animate_arrivals = False
        motion = Gtk.Settings.get_default()
        for name in ("gtk-enable-animations", "gtk-interface-reduced-motion"):
            signal = motion.connect("notify::" + name, self.motion_changed)
            self.cleanups.append(lambda signal=signal: motion.disconnect(signal))
        self.connect("unmap", lambda *_: (self.cancel_arrivals(), self.release_media()))
        scroll_input = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES,
            propagation_phase=Gtk.PropagationPhase.CAPTURE,
        )
        scroll_input.connect("scroll", lambda *_: (self.user_input(), False)[1])
        self.scroll_input = scroll_input
        self.content_header = None
        self.fill_header = False
        self.header_fit_tick = None
        self.header_binding = None
        self.header_focus = None
        self.check_start = lambda: False
        self.viewport_changed = lambda: None
        self.prefetch_reconsider = lambda: None
        self.model = Gio.ListStore.new(PostObject)
        self.entries = {}
        self.footer_model = Gio.ListStore.new(PostObject)
        self.footer_model.append(PostObject(None))
        self.sections = Gio.ListStore.new(Gio.ListStore)
        self.sections.append(self.model)
        self.sections.append(self.footer_model)
        self.flat = Gtk.FlattenListModel.new(self.sections)
        self.store = Gtk.SingleSelection.new(self.flat)
        self.store.set_autoselect(False)
        self.store.set_can_unselect(True)
        self.store.set_selected(Gtk.INVALID_LIST_POSITION)
        self.store.connect(
            "notify::selected", lambda *_: getattr(self.window, "view_changed", lambda: None)()
        )
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.setup)
        factory.connect("bind", self.bind)
        factory.connect("unbind", self.unbind)
        self.list = Gtk.ListView(
            model=self.store, factory=factory, single_click_activate=False, show_separators=True
        )
        self.list.add_css_class("content-list")
        self.list.connect("activate", self.activate_item)
        self.scroll = Gtk.ScrolledWindow(
            vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.list
        )
        self.scroll.add_controller(self.scroll_input)
        key_input = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        key_input.connect("key-pressed", lambda *_: (self.user_input(), False)[1])
        self.scroll.add_controller(key_input)
        self.top_peek = TopPeek(self.scroll, window)
        overlay = Gtk.Overlay(child=self.top_peek, vexpand=True)
        self.pull_hint = label(
            "Pull to refresh",
            "osd",
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.START,
            margin_top=12,
            visible=False,
        )
        overlay.add_overlay(self.pull_hint)
        self.append(overlay)
        self.interaction = ListInteraction(self)
        self.model.connect(
            "items-changed", lambda *_: getattr(self.window, "view_changed", lambda: None)()
        )
        adjustment = self.scroll.get_vadjustment()
        adjustment.connect("value-changed", lambda *_: self.queue_check())
        notice_signal = adjustment.connect("value-changed", self.update_notice.reached_top)
        self.cleanups.append(lambda: adjustment.disconnect(notice_signal))
        adjustment.connect("changed", lambda *_: self.queue_check())
        adjustment.connect("changed", self.fit_header)
        self.connect("map", lambda *_: self.queue_check())
        self.connect("map", lambda *_: self.update_notice.schedule())
        self.connect("map", lambda *_: getattr(self.window, "view_changed", lambda: None)())
        self.window.views.append(self)
        if hasattr(window, "connect"):

            def active_changed(*_args):
                if window.is_active() and self.get_mapped():
                    self.queue_check()
                    self.update_notice.schedule()
                else:
                    self.top_peek.reset()
                    self.update_notice.unmap()

            signal = window.connect("notify::is-active", active_changed)
            self.cleanups.append(lambda: window.disconnect(signal))

    def set_header(self, widget):
        """Put introductory content in the virtual list's first native section header."""
        if self.header_binding is not None:
            self.header_binding.set_child(None)
            self.header_binding = None
        self.content_header = Adw.Clamp(maximum_size=760, tightening_threshold=600, child=widget)
        self.content_header.add_css_class("page-intro")
        factory = Gtk.SignalListItemFactory()

        def detach(header):
            focus = self.window.get_focus()
            if focus and focus.is_ancestor(self.content_header):
                self.header_focus = focus
            header.set_child(None)

        def bind(_factory, header):
            if header.get_start() == 0:
                if self.header_binding is not None and self.header_binding is not header:
                    detach(self.header_binding)
                header.set_child(self.content_header)
                self.header_binding = header
                if self.header_focus is not None:
                    self.after_position(self.reset_header_position)

        def unbind(_factory, header):
            if self.header_binding is header:
                detach(header)
                self.header_binding = None

        factory.connect("bind", bind)
        factory.connect("unbind", unbind)
        self.list.set_header_factory(factory)
        self.fit_header()

    def fit_header(self, *_args):
        if self.content_header is None:
            return
        if not self.fill_header:
            if self.header_fit_tick is not None:
                self.remove_tick_callback(self.header_fit_tick)
                self.header_fit_tick = None
            self.content_header.set_size_request(-1, -1)
            return
        if self.header_fit_tick is not None or self.paging.closed:
            return
        frames = 0

        def allocated(_widget, _clock):
            nonlocal frames
            frames += 1
            if frames < 2:
                return True
            self.header_fit_tick = None
            # Measure after allocation: native section/row padding is outside
            # the header's content box and varies with the theme and font size.
            viewport = int(self.scroll.get_vadjustment().get_page_size())
            if viewport > 0 and self.fill_header:
                total = self.list.measure(Gtk.Orientation.VERTICAL, self.list.get_width()).minimum
                header = self.content_header.measure(
                    Gtk.Orientation.VERTICAL, self.content_header.get_width()
                ).minimum
                height = max(0, viewport - max(0, total - header))
                if self.content_header.get_size_request().height != height:
                    self.content_header.set_size_request(-1, height)
            return False

        self.header_fit_tick = self.add_tick_callback(allocated)

    def reset_header_position(self):
        self.scroll.get_vadjustment().set_value(0)
        focus, self.header_focus = self.header_focus, None
        if focus and focus.is_ancestor(self.content_header):
            focus.grab_focus()

    def focus_header(self, widget):
        self.header_focus = widget
        self.list.scroll_to(0, Gtk.ListScrollFlags(0), None)
        self.scroll.get_vadjustment().set_value(0)
        self.after_position(self.reset_header_position)

    def header_visible(self):
        if self.content_header is None or not self.content_header.get_mapped():
            return False
        valid, bounds = self.content_header.compute_bounds(self.scroll)
        return (
            valid
            and bounds.origin.y + bounds.size.height > 0
            and bounds.origin.y < self.scroll.get_height()
        )

    def setup(self, _factory, item):
        item.set_child(Adw.Clamp(maximum_size=760, tightening_threshold=600))

    def bind(self, _factory, item):
        value = item.get_item().post
        selectable = isinstance(value, Post | Author | Notice)
        item.set_activatable(selectable)
        item.set_selectable(selectable)
        requests = []
        token = media_binding.set((self, requests))
        try:
            row = PageFooter(self) if value is None else self.render(value)
        finally:
            media_binding.reset(token)
        row._media_requests = requests
        row._value = value
        if (
            value is not None
            and self.arrival_active
            and self.animate_arrivals
            and self.key(value) in self.arrival_keys
        ):
            row.set_opacity(0)
            self.reveal_rows.add(row)
        model_item = item.get_item()

        def changed(model):
            row._value = model.post
            if isinstance(row, PostRow):
                row.update_counters(model.post)
            elif self.update_row is not None:
                self.update_row(row, model.post)

        item._changed = (model_item, model_item.connect("changed", changed))
        self.rows.add(row)
        item.get_child().set_child(row)
        item._row = row

    def activate_item(self, _list, position):
        item = self.flat.get_item(position)
        if item and isinstance(item.post, Post):
            self.window.thread(item.post.uri)
        elif item and isinstance(item.post, Author):
            self.window.profile(item.post.did)
        elif item and isinstance(item.post, Notice):
            notice = item.post
            if notice.reason == "follow":
                self.window.profile(notice.author.did)
            else:
                self.window.thread(notice.subject or notice.uri)

    def unbind(self, _factory, item):
        binding = getattr(item, "_changed", None)
        if binding:
            binding[0].disconnect(binding[1])
            item._changed = None
        row = getattr(item, "_row", None)
        for request in getattr(row, "_media_requests", ()):
            request.cancel()
        if row and hasattr(row, "cancel"):
            row.cancel()
        if row:
            self.rows.discard(row)
        item._row = None
        item.get_child().set_child(None)

    def release_media(self):
        for request in tuple(self.media_bindings):
            request.release()

    def load_visible_media(self):
        height = self.scroll.get_height()
        for request in tuple(self.media_bindings):
            widget = request.widget
            valid, bounds = (
                widget.compute_bounds(self.scroll) if widget.get_mapped() else (False, None)
            )
            if (
                not valid
                or bounds.origin.y + bounds.size.height < -height
                or bounds.origin.y > height * 2
            ):
                request.release()
            elif (
                bounds.origin.y + bounds.size.height >= -height * 0.5
                and bounds.origin.y <= height * 1.5
            ):
                request.start()

    def paging_changed(self):
        for footer in list(self.footers):
            footer.sync()
        self.queue_check()

    def queue_check(self):
        if self.check_pending or self.paging.closed or not self.paging_ready:
            return
        self.check_pending = True
        self.viewport_changed()
        frames = 0

        def check(_widget, _clock):
            nonlocal frames
            frames += 1
            if frames < 2:
                return True
            self.check_pending = False
            self.check_tick = None
            if (
                self.get_mapped()
                and not self.paging.closed
                and getattr(self.window, "is_active", lambda: True)()
            ):
                self.load_visible_media()
                motion = getattr(self.window, "motion", None)
                if motion is not None:
                    motion.finish_offscreen()
                if self.pause_reason():
                    for footer in list(self.footers):
                        footer.sync()
                    return False
                if self.check_start():
                    return False
                adjustment = self.scroll.get_vadjustment()
                self.paging.near_end(
                    adjustment.get_value(), adjustment.get_upper(), adjustment.get_page_size()
                )
            return False

        # Wait for allocation after model changes, rather than reading the old end-of-page geometry.
        self.check_tick = self.add_tick_callback(check)

    def user_input(self):
        self.input_serial += 1
        self.cancel_arrivals()
        if self.position_tick is not None:
            self.remove_tick_callback(self.position_tick)
            self.position_tick = None
            self.paging_ready = True
        if self.feed:
            self.feed.startup = False
        if self.reading:
            self.reading.changed()

    def render_post(self, post):
        if isinstance(post, FeedGap):
            row = box(margin=18)
            row.append(
                label(post.error or "Saved reading position · newer posts above", "dim-label")
            )
            if post.cursor:
                control = button(
                    "view-refresh-symbolic",
                    "Load posts in between",
                    lambda *_: self.window.load_feed_gap(self, post.before),
                    text="Loading…" if post.busy else "Load posts in between",
                )
                control.set_sensitive(not post.busy)
                row.append(control)
            return row
        row = PostRow(post, self.window)
        if post.uri in self.connections:
            row.add_css_class("feed-thread-member")
            row.body.prepend(label("Thread", "dim-label"))
        return row

    def set_posts(self, posts, reset=False, *, rebind=()):
        previous = self.connections
        self.connections = set()
        if self.feed_preview:
            for first, second in pairwise(posts):
                if (
                    isinstance(first, Post)
                    and isinstance(second, Post)
                    and first.author.did == second.author.did
                    and (
                        (first.parent and first.parent[0] == second.uri)
                        or (second.parent and second.parent[0] == first.uri)
                    )
                ):
                    self.connections.update((first.uri, second.uri))
        return self.set_items(
            posts,
            lambda post: post.uri,
            reset=reset,
            rebind=set(rebind) | (previous ^ self.connections),
        )

    def set_items(self, items, key, reset=False, *, rebind=()):
        posts = [item for item in items if isinstance(item, Post)]
        post_positions(self.window).remember(posts + [post.quote for post in posts if post.quote])
        selected = self.interaction.selected()
        selected_key = self.key(selected) if selected is not None else None
        self.key = key
        # Preserve object identities/scroll anchors when appending or trimming a page.
        old = [self.model.get_item(i).post for i in range(self.model.get_n_items())]
        before, after = [key(x) for x in old], [key(x) for x in items]
        added = len(set(after) - set(before))
        for tag, a, b, c, d in reversed(
            SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes()
        ):
            if tag != "equal":
                self.model.splice(a, b - a, [PostObject(x) for x in items[c:d]])
        for i, value in enumerate(items):
            entry = self.model.get_item(i)
            if key(value) in rebind:
                self.model.splice(i, 1, [PostObject(value)])
            elif entry.post != value:
                if counters_only(entry.post, value) or (
                    self.update_row is not None
                    and isinstance(entry.post, Notice)
                    and isinstance(value, Notice)
                    and replace(entry.post, read=value.read) == value
                ):
                    entry.update(value)
                else:
                    self.model.splice(i, 1, [PostObject(value)])
        self.entries = {
            key(self.model.get_item(i).post): (i, self.model.get_item(i))
            for i in range(self.model.get_n_items())
        }
        if items and (reset or not old):
            self.list.scroll_to(0, Gtk.ListScrollFlags(0), None)
            if self.content_header is not None:
                self.scroll.get_vadjustment().set_value(0)
                self.after_position(self.reset_header_position)
        if reset and selected_key is not None and self.interaction.positions():
            self.interaction.select(self.interaction.positions()[0], focus=False)
        elif selected_key is not None:
            self.interaction.select(self.interaction.index(selected_key), focus=False)
        if items and self.focus_when_ready:
            self.focus_when_ready = False
            self.interaction.focus()
        return added

    def motion_changed(self, settings, _ps):
        if not motion_allowed(self.window):
            self.top_peek.reset()
            self.animate_arrivals = False
            self.stop_reveals()

    def stop_reveals(self):
        if self.reveal_source is not None:
            GLib.source_remove(self.reveal_source)
            self.reveal_source = None
        for row in self.reveal_rows:
            row.set_opacity(1)
            row.remove_css_class("arriving-post")
        self.reveal_rows.clear()

    def cancel_arrivals(self):
        active = self.arrival_active
        if self.arrival_tick is not None:
            self.remove_tick_callback(self.arrival_tick)
            self.arrival_tick = None
        self.arrival_active = False
        self.arrival_keys.clear()
        self.stop_reveals()
        if active:
            self.paging_ready = True

    def show_latest(self, posts, arrivals):
        """Commit keyed changes and jump once; reveal only visible arrivals after allocation."""
        self.cancel_arrivals()
        if self.position_tick is not None:
            self.remove_tick_callback(self.position_tick)
            self.position_tick = None
        self.arrival_keys = set(arrivals)
        self.arrival_active = True
        self.animate_arrivals = motion_allowed(self.window)
        self.paging_ready = False
        self.clear_update()
        self.set_posts(posts)
        if posts:
            self.list.grab_focus()
            self.interaction.select(self.interaction.positions()[0], focus=False)
            self.list.scroll_to(0, Gtk.ListScrollFlags(0), None)
        adjustment = self.scroll.get_vadjustment()
        adjustment.set_value(0)
        started, stable, previous = monotonic(), 0, None

        def positioned(*_):
            nonlocal stable, previous
            geometry = (
                adjustment.get_upper(),
                adjustment.get_page_size(),
            )
            adjustment.set_value(0)
            stable = stable + 1 if geometry == previous else 0
            previous = geometry
            elapsed = monotonic() - started
            if stable < 3 and elapsed < 1:
                return True
            self.arrival_tick = None
            keys = self.arrival_keys.copy()
            self.arrival_keys.clear()
            self.arrival_active = False
            for row in self.reveal_rows:
                row.set_opacity(1)
            self.reveal_rows.clear()
            if self.animate_arrivals and elapsed < 0.7:
                for _, row in self.interaction.visible_rows():
                    if self.key(row._value) in keys:
                        row.add_css_class("arriving-post")
                        self.reveal_rows.add(row)
                if self.reveal_rows:

                    def finish():
                        self.reveal_source = None
                        self.stop_reveals()
                        return False

                    self.reveal_source = GLib.timeout_add(180, finish)
            self.paging_ready = True
            self.queue_check()
            return False

        self.arrival_tick = self.add_tick_callback(positioned)

    def pause_reason(self):
        return getattr(self.window, "automatic_pause_reason", lambda: "")()

    def offer_update(self, title, callback, *, button_label="Show", revision=None):
        self.pending_update = callback
        self.update_notice.offer(title, button_label, revision=revision)
        self.update_notice.reached_top(self.scroll.get_vadjustment())
        self.update_notice.schedule()
        getattr(self.window, "view_changed", lambda: None)()

    def clear_update(self):
        self.pending_update = None
        self.update_notice.clear()
        getattr(self.window, "view_changed", lambda: None)()

    def apply_update(self):
        callback = self.pending_update
        self.clear_update()
        if callback is not None and not self.paging.closed:
            callback()
            return True
        return False

    def update_post(self, post):
        self.post_updated(post)
        match = self.entries.get(post.uri)
        if match is None:
            return
        index, entry = match
        if self.reading:
            self.reading.changed()
        current = entry.post
        value = replace(post, context=current.context)
        if counters_only(current, value):
            entry.update(value)
            return
        selected = self.interaction.selected()
        selected_key = self.key(selected) if selected is not None else None
        entry = PostObject(value)
        self.model.splice(index, 1, [entry])
        self.entries[post.uri] = (index, entry)
        if selected_key is not None:
            self.interaction.select(self.interaction.index(selected_key), focus=False)

    def close(self):
        if self.paging.closed:
            return
        self.paging.closed = True
        self.cancel_arrivals()
        self.top_peek.close()
        for request in tuple(self.media_bindings):
            request.cancel()
        for cleanup in self.cleanups:
            cleanup()
        self.cleanups.clear()
        self.entries.clear()
        self.clear_update()
        for row in list(self.rows):
            for request in getattr(row, "_media_requests", ()):
                request.cancel()
            if hasattr(row, "cancel"):
                row.cancel()
        if self.position_tick is not None:
            self.remove_tick_callback(self.position_tick)
            self.position_tick = None
        if self.header_fit_tick is not None:
            self.remove_tick_callback(self.header_fit_tick)
            self.header_fit_tick = None
        if self.check_pending:
            self.remove_tick_callback(self.check_tick)
            self.check_pending = False

    def focus_post(self, uri):
        position = next(
            i for i in range(self.model.get_n_items()) if self.model.get_item(i).post.uri == uri
        )
        self.paging_ready = False
        self.list.grab_focus()
        self.store.set_selected(position)
        self.list.scroll_to(position, Gtk.ListScrollFlags.FOCUS, None)
        self.after_position()

    def after_position(self, callback=lambda: None, *, settle_layout=False):
        if self.position_tick is not None:
            self.remove_tick_callback(self.position_tick)
        self.paging_ready = False
        frames, stable, previous = 0, 0, None
        started = monotonic()

        def positioned(_widget, _clock):
            nonlocal frames, stable, previous
            frames += 1
            if frames < 4:
                return True
            if settle_layout:
                complete = callback() is not False
                adjustment = self.scroll.get_vadjustment()
                geometry = (
                    adjustment.get_upper(),
                    adjustment.get_page_size(),
                    adjustment.get_value(),
                )
                stable = stable + 1 if complete and geometry == previous else 0
                previous = geometry
                if stable < 3 and monotonic() - started < 1:
                    return True
            self.position_tick = None
            self.paging_ready = True
            if not settle_layout:
                callback()
            self.queue_check()
            return False

        self.position_tick = self.add_tick_callback(positioned)


class PostRow(Gtk.Box):
    __gsignals__: ClassVar[dict] = {
        "activate": (GObject.SignalFlags.RUN_LAST | GObject.SignalFlags.ACTION, None, ())
    }

    def __init__(self, post, window, compact=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.post, self.window, self.pending = post, window, []
        self.add_css_class("post-tile")
        self._media_requests = []
        self.alive = True
        self.text_open_source = None
        self.text_press = None
        self.text_dragged = False
        self.quoted_rows = []
        self.online_actions = []
        self.body = box(spacing=10, margin=16 if compact else 20)
        self.append(self.body)
        cancel_click = Gtk.GestureClick(
            button=Gdk.BUTTON_PRIMARY, propagation_phase=Gtk.PropagationPhase.CAPTURE
        )
        cancel_click.connect("pressed", self.cancel_text_open)
        self.add_controller(cancel_click)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL], [f"Post by {post.author.name}. Open conversation"]
        )
        if compact:
            self.set_focusable(True)
            self.add_css_class("quoted-post")
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self.quoted_key)
            self.add_controller(keys)
        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.connect("released", self.quoted_clicked)
        self.add_controller(click)
        if post.context:
            context = label(post.context, "dim-label")
            context.add_css_class("caption")
            self.body.append(context)
        heading = box(False, 12)
        self.heading = heading
        author = box(False, 10)
        author.append(avatar(post.author, window, 36 if compact else 44, pending=self.pending))
        identity = box(spacing=2)
        name = label(post.author.name, "heading", ellipsize=Pango.EllipsizeMode.END)
        name.set_wrap(False)
        identity.append(name)
        handle = label("@" + post.author.handle, "dim-label", ellipsize=Pango.EllipsizeMode.END)
        handle.add_css_class("caption")
        handle.set_wrap(False)
        identity.append(handle)
        author.append(identity)
        # START consumes only the identity's natural width inside the expanding slot.
        # The timestamp and empty header space remain part of the conversation target.
        self.author_button = Gtk.Button(child=author, hexpand=True, halign=Gtk.Align.START)
        self.author_button.focus_key = ("post-author", post.uri)
        self.author_button.add_css_class("flat")
        self.author_button.add_css_class("post-author")
        self.author_button.set_tooltip_text("View profile")
        self.author_button.update_property(
            [Gtk.AccessibleProperty.LABEL], [f"View profile of {post.author.name}"]
        )
        self.author_button.connect("clicked", lambda _: window.profile(post.author.did))
        heading.append(self.author_button)
        timestamp = label(relative_time(post.created), "dim-label", wrap=False)
        timestamp.add_css_class("caption")
        heading.append(timestamp)
        self.position_pill = label("", "conversation-position", wrap=False)
        self.position_pill.add_css_class("caption")
        self.position_pill.set_valign(Gtk.Align.CENTER)
        heading.append(self.position_pill)
        post_positions(window).bind(self)
        self.body.append(heading)
        if post.author.muted or post.author.blocking:
            self.body.append(
                label(
                    "This account is blocked."
                    if post.author.blocking
                    else "This account is muted.",
                    "heading",
                )
            )
            self.body.append(
                button(
                    "avatar-default-symbolic",
                    "View profile to change mute or block",
                    lambda: window.profile(post.author.did),
                    "View profile",
                )
            )
            return
        labels = post.labels + post.author.labels
        if labels:
            self.body.append(
                LabelledContent(
                    window,
                    ("post", post.uri),
                    post.labels,
                    lambda: self.build_content(self.post, window, compact),
                    author_labels=post.author.labels,
                )
            )
        else:
            self.body.append(self.build_content(post, window, compact))

    def quoted_clicked(self, gesture, presses, _x, _y):
        if presses == 1 and self.alive:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.activate()

    def do_activate(self):
        if self.alive:
            self.window.thread(self.post.uri)

    def quoted_key(self, _keys, key, _code, modifiers):
        if (
            self.is_focus()
            and key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space)
            and not modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK)
        ):
            self.activate()
            return True
        return False

    def update_position(self, position):
        self.position_pill.set_visible(position is not None)
        if position is None:
            return
        index, total, partial = position
        self.position_pill.set_label(f"{index}/{total}")
        description = f"Post {index} of {total} known messages in reading order."
        if partial:
            description += " The conversation is incomplete."
        self.position_pill.set_tooltip_text(description)
        self.position_pill.update_property([Gtk.AccessibleProperty.LABEL], [description])

    def text_pressed(self, gesture, presses, x, y):
        self.cancel_text_open()
        text = gesture.get_widget()
        self.text_press = (
            text,
            x,
            y,
            bool(text.get_selection_bounds()[0]),
            bool(gesture.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK),
        )
        self.text_dragged = presses != 1

    def text_motion(self, controller, x, y):
        if self.text_press is not None and controller.get_widget() is self.text_press[0]:
            text, start_x, start_y, *_ = self.text_press
            self.text_dragged |= text.drag_check_threshold(
                int(start_x), int(start_y), int(x), int(y)
            )

    def text_clicked(self, gesture, presses, x, y):
        text = gesture.get_widget()
        self.text_motion(gesture, x, y)
        press, self.text_press = self.text_press, None
        device = gesture.get_device()
        touch = device and device.get_source() == Gdk.InputSource.TOUCHSCREEN
        # Native labels can select a character after only a pixel of pointer jitter.
        # A deliberate drag, existing selection or Shift-click stays native.
        selecting = self.text_dragged or (press is not None and (press[3] or press[4]))
        if press is not None:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if presses == 1 and press and not touch and not selecting and not text.get_current_uri():
            text.select_region(0, 0)
        if (
            presses == 1
            and self.alive
            and not selecting
            and not text.get_selection_bounds()[0]
            and not text.get_current_uri()
        ):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.cancel_text_open()

            def open_post():
                self.text_open_source = None
                if self.alive and self.get_mapped() and not text.get_selection_bounds()[0]:
                    self.activate()
                return False

            # Let a second mouse click select a word instead of navigating on its first release.
            delay = 0 if touch else Gtk.Settings.get_default().get_property("gtk-double-click-time")
            self.text_open_source = GLib.timeout_add(delay, open_post)

    def cancel_text_open(self, *_args):
        if self.text_open_source is not None:
            GLib.source_remove(self.text_open_source)
            self.text_open_source = None

    def build_content(self, post, window, compact):
        content = box(spacing=10)
        text = Gtk.Label(
            xalign=0,
            wrap=True,
            selectable=True,
            use_markup=True,
            label=markup(post.text, post.facets),
            hexpand=True,
        )
        text.add_css_class("post-body")
        text.focus_key = ("post-text", post.uri)
        text.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        text.set_width_chars(1)
        text.connect("activate-link", lambda _l, uri: (window.open_uri(uri), True)[1])
        # Share the label's sequence so a plain click opens the post while drag/double-click
        # selection and rich-text links retain their native behaviour.
        selection_clicks = [
            controller
            for controller in text.observe_controllers()
            if isinstance(controller, Gtk.GestureClick)
        ]
        click = Gtk.GestureClick(
            button=Gdk.BUTTON_PRIMARY, propagation_phase=Gtk.PropagationPhase.CAPTURE
        )
        click.connect("pressed", self.text_pressed)
        click.connect("released", self.text_clicked)
        text.add_controller(click)
        for selection_click in selection_clicks:
            selection_click.group(click)
        motion = Gtk.EventControllerMotion(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        motion.connect("motion", self.text_motion)
        text.add_controller(motion)
        content.append(text)
        for media in post.images:
            self.add_image(media, content)
        if post.quote and not compact:
            quoted = PostRow(post.quote, window, compact=True)
            self.quoted_rows.append(quoted)
            quoted.add_css_class("card")
            content.append(quoted)
        if post.external:
            uri, title, description = post.external
            card = box(spacing=4, margin=12)
            card.append(label(title, "heading"))
            card.append(label(description, "dim-label", lines=3, ellipsize=Pango.EllipsizeMode.END))
            if safe_url(uri):
                link = Gtk.Button(child=card)
                link.add_css_class("flat")
                link.connect("clicked", lambda _: window.open_uri(uri))
                content.append(link)
            else:
                content.append(card)
        if post.unavailable:
            content.append(label(post.unavailable, "dim-label"))
        if compact:
            return content
        actions = box(False, 12)
        actions.add_css_class("post-actions")
        reply = button(
            "mail-reply-sender-symbolic",
            f"Reply · {post.replies} replies",
            lambda: window.compose(reply=self.post),
            count=post.replies,
        )
        actions.append(reply)
        actions.append(
            button(
                "media-playlist-repeat-symbolic",
                f"{'Undo repost' if post.repost_uri else 'Repost'} · {post.reposts} reposts",
                lambda: window.mutate(self.post, "repost"),
                count=post.reposts,
            )
        )
        actions.append(
            button(
                "skyloom-like-symbolic",
                f"{'Unlike' if post.like_uri else 'Like'} · {post.likes} likes",
                lambda: window.mutate(self.post, "like"),
                count=post.likes,
            )
        )
        self.action_buttons = list(list_children(actions))
        for index, b in enumerate(self.action_buttons):
            b.add_css_class("flat")
            if (index == 1 and post.repost_uri) or (index == 2 and post.like_uri):
                b.add_css_class("reaction-selected")
                if index == 1:
                    b.count.set_label("✓ " + b.count.get_label())
                else:
                    b.glyph.set_from_icon_name("skyloom-liked-symbolic")
            busy = any(k[0] == post.uri for k in window.mutations)
            if b is not reply and hasattr(window, "online_control"):
                self.online_actions.append(b)
                window.online_control(b, busy=busy)
            else:
                b.set_sensitive((b is reply or not window.read_only) and not busy)
        spacer = Gtk.Box(hexpand=True)
        actions.append(spacer)
        menu = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Post actions")
        self.menu = menu
        menu.focus_key = ("post-menu", post.uri)
        menu.add_css_class("flat")
        menu.set_create_popup_func(self.create_post_menu)
        actions.append(menu)
        content.append(actions)

        return content

    def create_post_menu(self, menu):
        window = self.window
        post = self.post
        pop = Gtk.Popover()
        choices = box(spacing=4, margin=6)
        for title, callback in [
            ("Quote post", lambda: window.compose(quote=self.post)),
            ("Copy link", lambda: window.copy(post.link)),
            ("Open in Bluesky / report", lambda: window.open_uri(post.link)),
        ]:

            def clicked(cb=callback):
                pop.popdown()
                cb()

            b = Gtk.Button(label=title)
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, cb=clicked: cb())
            choices.append(b)
        pop.set_child(choices)
        menu.set_popover(pop)

    def add_image(self, media, content):
        group = box(spacing=4)
        group.add_css_class("card")
        pic = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER, height_request=220)
        pic.set_alternative_text(media.alt if media.alt.strip() else "Image")
        viewer = Gtk.Button(child=pic, tooltip_text="View image and description")
        viewer.add_css_class("flat")
        viewer.connect("clicked", lambda _: self.window.view_media(media))
        group.append(viewer)
        alt = None
        if media.alt.strip():
            alt = label(
                "ALT · " + media.alt,
                "dim-label",
                margin_start=10,
                margin_end=10,
                margin_top=6,
                margin_bottom=10,
                selectable=True,
            )
            group.append(alt)
        if should_load_image(self.window, media.url, media.local):

            def loaded(pix):
                if self.alive:
                    self.window.images.bind(pic, pix)
                    pic.set_paintable(pix)
                    pic.set_size_request(-1, 220)

            def failed(_msg):
                if self.alive:
                    if self.window.automatic_pause_reason():
                        viewer.set_child(Gtk.Label(label="View image", height_request=220))
                        return
                    viewer.set_visible(False)
                    group.append(
                        label("Image unavailable", "dim-label", margin_start=10, margin_end=10)
                    )

            def release():
                pic.set_paintable(None)
                self.window.images.unbind(pic)

            def load():
                cached = getattr(self.window.images, "cache", {}).get((media.url, media.local))
                if cached is not None:
                    loaded(cached)
                    return None
                future = self.window.worker.submit(
                    self.window.images.get(media.url, media.local),
                    image_callback(pic, loaded),
                    image_callback(pic, failed),
                )
                remember_request(self.pending, future)
                return future

            pic.connect("unrealize", lambda *_: self.window.images.unbind(pic))
            start_image(pic, load, self, release)
        else:
            viewer.set_child(Gtk.Label(label="View image"))
        content.append(group)

    def update_counters(self, post):
        previous = self.post
        self.post = replace(post, context=self.post.context)
        self.position_owner.remember((post,))
        buttons = getattr(self, "action_buttons", ())
        if not buttons:
            return
        values = [
            f"Reply · {post.replies} replies",
            f"{'Undo repost' if post.repost_uri else 'Repost'} · {post.reposts} reposts",
            f"{'Unlike' if post.like_uri else 'Like'} · {post.likes} likes",
        ]
        busy = any(key[0] == post.uri for key in self.window.mutations)
        for index, (control, tooltip) in enumerate(zip(buttons, values, strict=True)):
            selected = (
                bool(post.repost_uri)
                if index == 1
                else bool(post.like_uri)
                if index == 2
                else False
            )
            count = ("✓ " if selected and index == 1 else "") + str(
                (post.replies, post.reposts, post.likes)[index]
            )
            if control.count.get_label() != count:
                control.count.set_label(count)
            if control.get_tooltip_text() != tooltip:
                control.set_tooltip_text(tooltip)
                control.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
            if index:
                field = "repost_uri" if index == 1 else "like_uri"
                selected = bool(getattr(post, field))
                if selected:
                    control.add_css_class("reaction-selected")
                else:
                    control.remove_css_class("reaction-selected")
                if index == 2 and selected != bool(previous.like_uri):
                    control.glyph.set_from_icon_name(
                        "skyloom-liked-symbolic" if selected else "skyloom-like-symbolic"
                    )
                if selected != bool(getattr(previous, field)):
                    motion = getattr(self.window, "motion", None)
                    if motion is not None:
                        motion.fade(control, start=0.5)
            if index and hasattr(self.window, "online_control"):
                self.window.online_control(control, busy=busy)
            else:
                control.set_sensitive(not busy and (not index or not self.window.read_only))

    def cancel(self):
        self.alive = False
        self.position_owner.rows.discard(self)
        self.cancel_text_open()
        for request in self._media_requests:
            request.cancel()
        for future in self.pending:
            if future:
                future.cancel()
        for child in self.quoted_rows:
            child.cancel()


PostRow.set_activate_signal_from_name("activate")


def list_children(widget):
    child = widget.get_first_child()
    while child:
        yield child
        child = child.get_next_sibling()
