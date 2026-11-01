"""Connected native conversation rows in the shared virtualised content scroller."""

from dataclasses import replace

from gi.repository import Gtk, Pango

from .conversation import Continuation, EarlierMessages, ThreadGap
from .domain import Post
from .widgets import FeedView, PostRow, box, button, label, list_children, post_positions


class ConversationView(FeedView):
    def __init__(self, window, state, load):
        self.state, self.load = state, load
        self.is_conversation = True
        self.presentation = {}
        self.pending_focus = None
        self.pending_loader_focus = None
        self.request_active = None
        super().__init__(window, render=self.render_message)
        self.add_css_class("conversation-view")
        self.return_button = button(
            "go-jump-symbolic", "Return to opened post", self.return_to_opened
        )
        self.return_button.set_visible(False)
        self.relative_controls = box(False, 4)
        self.parent_button = button(
            "go-up-symbolic", "Parent message (Alt+Up)", lambda: self.relative("parent")
        )
        self.child_button = button(
            "go-down-symbolic", "First reply (Alt+Down)", lambda: self.relative("child")
        )
        self.relative_controls.append(self.parent_button)
        self.relative_controls.append(self.child_button)
        self.store.connect("notify::selected", self.update_controls)
        self.scroll.get_vadjustment().connect("value-changed", self.queue_controls)
        self.scroll.get_vadjustment().connect("changed", self.queue_controls)
        self.connect("map", self.queue_controls)
        self.controls_tick = None
        self.cleanups.append(self.close_controls)
        self.update_controls()

    def queue_controls(self, *_args):
        if self.controls_tick is None and not self.paging.closed:

            def allocated(*_):
                if self.position_tick is not None:
                    return True
                self.controls_tick = None
                self.update_controls()
                nav = getattr(self.window, "nav", None)
                if nav is None or self.is_ancestor(nav.get_visible_page()):
                    self.restore_loader_focus()
                    self.restore_focus()
                return False

            self.controls_tick = self.add_tick_callback(allocated)

    def close_controls(self):
        if self.controls_tick is not None:
            self.remove_tick_callback(self.controls_tick)
            self.controls_tick = None

    def target(self, direction):
        post = self.interaction.selected()
        if not isinstance(post, Post):
            return None
        if direction == "parent":
            parent = self.state.parents.get(post.uri)
            return parent if any(p.uri == parent for p in self.state.posts) else None
        return next(
            (p.uri for p in self.state.posts if self.state.parents.get(p.uri) == post.uri), None
        )

    def relative(self, direction):
        target = self.target(direction)
        if target is None:
            return False
        self.focus_post(target)
        return True

    def update_controls(self, *_args):
        self.parent_button.set_sensitive(self.target("parent") is not None)
        self.child_button.set_sensitive(self.target("child") is not None)
        visible = any(
            row._value.uri == self.state.anchor for _, row in self.interaction.visible_rows()
        )
        self.return_button.set_visible(
            any(p.uri == self.state.anchor for p in self.state.posts) and not visible
        )

    def return_to_opened(self):
        place = self.interaction.capture()
        self.focus_post(self.state.anchor)
        if place is not None:
            self.window.interactions.offer_undo(
                "Returned to opened post", lambda: self.interaction.restore(place), self
            )

    def focus_body(self):
        for _, row in self.interaction.visible_rows():
            if row._value.uri == self.state.anchor:
                row.body.child_focus(Gtk.DirectionType.TAB_FORWARD)
                return

    def restore_loader_focus(self):
        identity = self.pending_loader_focus
        self.pending_loader_focus = None
        if identity is None:
            return
        uri, parent = identity
        for row in tuple(self.rows):
            if getattr(row._value, "uri", None) == uri and hasattr(row, "control"):
                if row.control.get_sensitive():
                    row.control.grab_focus()
                else:
                    row.set_focusable(True)
                    row.grab_focus()
                return
        visible = [
            row._value.uri
            for _, row in self.interaction.visible_rows()
            if isinstance(row._value, Post)
        ]
        target = parent if parent in visible else visible[0] if visible else self.state.anchor
        self.pending_focus = (target, None)

    def remember_focus(self, focus):
        marker = None
        while focus is not None and focus is not self:
            marker = marker or getattr(focus, "focus_key", None)
            if isinstance(focus, PostRow):
                return (focus.post.uri, marker)
            focus = focus.get_parent()
        return None

    def restore_focus(self):
        if self.pending_focus is None:
            return
        uri, marker = self.pending_focus
        self.pending_focus = None

        def walk(widget):
            yield widget
            for child in list_children(widget):
                yield from walk(child)

        for _, row in self.interaction.visible_rows():
            for nested in walk(row):
                if isinstance(nested, PostRow) and nested.post.uri == uri:
                    for control in walk(nested):
                        if marker is not None and getattr(control, "focus_key", None) == marker:
                            control.grab_focus()
                            return
        index = self.interaction.index(uri)
        if index is None:
            index = self.interaction.index(self.state.anchor)
        self.interaction.select(index, focus=False)
        self.list.grab_focus()

    def sync(self, *, earlier_busy=False, earlier_error="", active=None, errors=None):
        errors = errors or {}
        self.request_active = active
        place = self.interaction.capture()
        focus = getattr(self.window, "get_focus", lambda: None)()
        if focus is not None and not focus.is_ancestor(self):
            focus = None
        loader_parent = getattr(focus, "continuation_parent", None)
        loader_uri = getattr(focus, "continuation_uri", None)
        focus_identity = self.remember_focus(focus)
        rows = self.state.project()
        partial = bool(
            self.state.earlier
            or self.state.branches
            or self.state.gaps
            or self.state.unavailable
            or self.state.limited
        )
        post_positions(self.window).remember(
            self.state.posts, incomplete=partial, parents=self.state.parents
        )
        presentation = {
            key: (position.parent, position.opened, position.branch_start)
            for key, position in self.state.positions.items()
        }
        posts = {post.uri: post for post in self.state.posts}
        decorated = []
        for item in rows:
            if isinstance(item, Post):
                position = self.state.positions[item.uri]
                parent = posts.get(position.parent)
                context = (
                    "Opened here"
                    if position.opened
                    else f"Replying to {parent.author.name}"
                    if parent
                    else "Earlier in this conversation"
                    if position.parent
                    else "Conversation start"
                )
                item = replace(item, context=context)
            elif isinstance(item, Continuation):
                item = replace(item, busy=active == item.parent, error=errors.get(item.parent, ""))
            decorated.append(item)
        if self.state.earlier:
            decorated.insert(0, EarlierMessages(earlier_busy, earlier_error))
        rebind = {
            uri
            for uri, value in presentation.items()
            if uri in self.presentation and self.presentation[uri] != value
        }
        self.set_posts(decorated, rebind=rebind)
        self.presentation = presentation
        for row in tuple(self.rows):
            control = getattr(row, "control", None)
            if control is not None and hasattr(self.window, "online_control"):
                self.window.online_control(control, busy=active is not None)
        if focus_identity is not None and (focus is None or focus.get_root() is None):
            self.pending_focus = focus_identity
        if loader_uri:
            self.pending_loader_focus = (loader_uri, loader_parent)
        elif focus is not None and focus.get_root() is not None:
            # GTK retains live descendant focus; viewport restoration must not grab the list.
            self.interaction.select(
                self.interaction.index(self.key(self.interaction.selected()))
                if self.interaction.selected() is not None
                else None,
                focus=False,
            )
        if place is not None:
            self.interaction.restore(place)
        self.queue_controls()

    def render_message(self, item):
        if isinstance(item, Post):
            position = self.state.positions.get(item.uri)
            known_parent = position and any(p.uri == position.parent for p in self.state.posts)
            row = PostRow(
                replace(item, context="" if known_parent and not position.opened else item.context),
                self.window,
            )
            row.add_css_class("conversation-message")
            if position and position.opened:
                row.add_css_class("opened-message")
            if position and position.branch_start:
                row.add_css_class("conversation-branch")
            if position and position.parent:
                row.add_css_class("conversation-reply")
                parent = position.parent
                if any(p.uri == parent for p in self.state.posts):
                    link = button(
                        "go-up-symbolic",
                        "Go to parent message",
                        lambda: self.focus_post(parent),
                        f"Replying to {next(p.author.name for p in self.state.posts if p.uri == parent)}",
                    )
                    caption = link.get_child()
                    caption.set_ellipsize(Pango.EllipsizeMode.END)
                    caption.set_max_width_chars(26)
                    link.set_tooltip_text(caption.get_label() + ". Go to parent message")
                    link.update_property([Gtk.AccessibleProperty.LABEL], [link.get_tooltip_text()])
                    link.add_css_class("flat")
                    link.set_halign(Gtk.Align.START)
                    row.body.prepend(link)
            row.update_property([Gtk.AccessibleProperty.DESCRIPTION], [item.context])
            return row
        row = box(spacing=8, margin=20)
        if isinstance(item, ThreadGap):
            row.append(
                label(
                    "A blocked message is unavailable."
                    if item.kind == "blocked"
                    else "A message is deleted or unavailable.",
                    "dim-label",
                )
            )
            return row
        earlier = isinstance(item, EarlierMessages)
        parent = None if earlier else item.parent
        row.append(
            label(
                item.error
                or (
                    "Earlier messages are available."
                    if earlier
                    else "More replies are available here."
                ),
                "dim-label",
            )
        )
        control = button(
            "",
            "Load earlier messages" if earlier else "Load more replies",
            lambda: self.load(earlier=earlier, branch=parent),
            "Loading…"
            if item.busy
            else "Try again"
            if item.error
            else "Load earlier messages"
            if earlier
            else "Load more replies",
        )
        control.set_sensitive(
            self.request_active is None and not item.busy and not self.window.read_only
        )
        if hasattr(self.window, "online_control"):
            self.window.online_control(control, busy=self.request_active is not None or item.busy)
        row.control = control
        row.add_css_class("conversation-loader")
        row.continuation_uri = control.continuation_uri = item.uri
        row.continuation_parent = parent or self.state.anchor
        row.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Loading messages" if item.busy else "More messages"]
        )
        control.continuation_parent = parent or self.state.anchor
        control.set_halign(Gtk.Align.START)
        row.append(control)
        return row
