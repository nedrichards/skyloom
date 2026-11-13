"""Native, independently saved interaction controls and reversible moderation."""

from gi.repository import Adw, Gtk

from .thread_service import DISABLE, RULES
from .widgets import box, button, label


def menu_options(window, post):
    account = window.service.account
    if not account or post.unavailable == "This post was deleted.":
        return []
    options = []
    if post.author.did == account.did:
        options.append(
            (
                "Thread controls…" if not post.root else "Quote controls…",
                lambda: ThreadControls(window, post).present(window),
            )
        )
    if post.root and post.root[0].startswith(f"at://{account.did}/app.bsky.feed.post/"):
        options.append(
            ("Hide reply…", lambda: relation(window, post.root[0], post.uri, "reply", True))
        )
    if post.quote and post.quote.author.did == account.did:
        options.append(
            ("Detach quote…", lambda: relation(window, post.quote.uri, post.uri, "quote", True))
        )
    return options


def refresh_controls(window):
    window.thread_cache.clear()
    view = window.interactions.current_view(mapped=False)
    if view and hasattr(view, "refresh"):
        view.refresh()


def relation(window, original, target, kind, enabled, done=None):
    if window.read_only:
        return
    generation = window.generation
    account = window.service.account
    title = (
        ("Hide reply" if enabled else "Unhide reply")
        if kind == "reply"
        else ("Detach quote" if enabled else "Reattach quote")
    )
    body = (
        "Hidden replies can still be opened directly. You can unhide them from your thread controls."
        if kind == "reply"
        else "The quoting post remains on Bluesky. You can reattach it from your post's quote controls."
    )
    alert = Adw.AlertDialog(heading=title + "?", body=body)
    alert.add_response("cancel", "Cancel")
    alert.add_response("apply", title)
    alert.set_default_response("cancel")
    alert.set_close_response("cancel")
    if enabled:
        alert.set_response_appearance("apply", Adw.ResponseAppearance.DESTRUCTIVE)

    def response(_alert, value):
        if (
            value != "apply"
            or window.read_only
            or generation != window.generation
            or window.service.account is not account
        ):
            return
        method = window.service.hidden_reply if kind == "reply" else window.service.detached_quote

        def ready(gate):
            if generation == window.generation and window.service.account is account:
                window.toast(title + " saved.")
                if done:
                    done(gate)
                refresh_controls(window)

        def failed(message):
            if generation == window.generation and window.service.account is account:
                window.toast(message + " Reload the controls before trying again.")

        window.worker.submit(
            method(original, target, enabled, expected_account=account), ready, failed
        )

    alert.connect("response", response)
    alert.present(window)


class ThreadControls(Adw.Dialog):
    def __init__(self, window, post):
        super().__init__(title="Thread controls", content_width=480, content_height=620)
        self.window, self.post = window, post
        self.generation = window.generation
        self.account = window.service.account
        self.alive = True
        self.connect("closed", lambda *_: setattr(self, "alive", False))
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.body = box(spacing=16, margin=18)
        scroll.set_child(self.body)
        toolbar.set_content(scroll)
        self.set_child(toolbar)
        self.body.append(label("Loading controls…", "dim-label"))
        self.load()

    def valid(self):
        return (
            self.alive
            and self.generation == self.window.generation
            and self.window.service.account is self.account
        )

    def load(self):
        def ready(value):
            if not self.valid():
                return
            self.thread, self.quote = value
            self.render()

        def failed(message):
            if self.valid():
                self.clear()
                self.body.append(label(message))
                self.body.append(button("", "Reload controls", self.load, "Retry"))

        self.window.worker.submit(
            self.window.service.thread_controls(
                self.post.uri, replies=not bool(self.post.root), expected_account=self.account
            ),
            ready,
            failed,
        )

    def clear(self):
        while child := self.body.get_first_child():
            self.body.remove(child)

    def save(self, widget, operation, assign, message):
        if self.window.read_only or not self.valid():
            return
        self.window.online_control(widget, busy=True)

        def ready(gate):
            if self.valid():
                assign(gate)
                self.window.online_control(widget, busy=False)
                self.window.toast(message)
                refresh_controls(self.window)

        def failed(error):
            if self.valid():
                self.window.online_control(widget, busy=False)
                self.window.toast(error + " Reload controls before trying again.")

        self.window.worker.submit(operation(), ready, failed)

    def render(self):
        self.clear()
        if self.thread:
            record = self.thread.record
            self.body.append(label("Who can reply", "heading"))
            self.mode = Gtk.DropDown.new_from_strings(["Everyone", "Nobody", "Selected groups"])
            self.mode.update_property([Gtk.AccessibleProperty.LABEL], ["Who can reply"])
            rules = record.get("allow")
            self.mode.set_selected(0 if rules is None else 1 if not rules else 2)
            self.body.append(self.mode)
            self.groups = {}
            for name, title in (
                ("mention", "People mentioned in the post"),
                ("follower", "Your followers"),
                ("following", "People you follow"),
            ):
                control = Gtk.CheckButton(label=title)
                control.set_active(any(r.get("$type") == RULES[name] for r in rules or []))
                self.groups[name] = control
                self.body.append(control)
            if any(r.get("$type") not in RULES.values() for r in rules or []):
                self.body.append(
                    label(
                        "Existing list and other rules are kept with Selected groups.", "dim-label"
                    )
                )

            def mode_changed(*_args):
                for control in self.groups.values():
                    control.set_sensitive(self.mode.get_selected() == 2)

            self.mode.connect("notify::selected", mode_changed)
            mode_changed()
            save = button(
                "",
                "Save reply permissions",
                lambda: self.save(
                    save,
                    lambda: self.window.service.save_reply_rules(
                        self.thread,
                        ("everyone", "nobody", "groups")[self.mode.get_selected()],
                        [name for name, control in self.groups.items() if control.get_active()],
                    ),
                    lambda gate: setattr(self, "thread", gate),
                    "Reply permissions saved.",
                ),
                "Save reply permissions",
            )
            self.body.append(save)
            self.window.online_control(save)
            self.restore_rows(record.get("hiddenReplies", []), "reply")

        self.body.append(label("Quote posts", "heading"))
        self.allow_quotes = Gtk.CheckButton(label="Allow people to quote this post")
        self.allow_quotes.set_active(
            not any(r.get("$type") == DISABLE for r in self.quote.record.get("embeddingRules", []))
        )
        self.body.append(self.allow_quotes)
        save_quote = button(
            "",
            "Save quote permissions",
            lambda: self.save(
                save_quote,
                lambda: self.window.service.save_quote_rule(
                    self.quote, self.allow_quotes.get_active()
                ),
                lambda gate: setattr(self, "quote", gate),
                "Quote permissions saved.",
            ),
            "Save quote permissions",
        )
        self.body.append(save_quote)
        self.window.online_control(save_quote)
        self.restore_rows(self.quote.record.get("detachedEmbeddingUris", []), "quote")
        self.body.append(
            label(
                "Reply and quote permissions save separately. Other changes stay as entered.",
                "dim-label",
            )
        )
        self.body.append(button("", "Reload controls", self.load, "Reload controls"))

    def restore_rows(self, uris, kind):
        if not uris:
            return
        self.body.append(
            label("Hidden replies" if kind == "reply" else "Detached quotes", "heading")
        )
        for uri in uris:
            row = box(spacing=4)
            text = label(uri, "dim-label")
            text.set_selectable(True)
            row.append(text)
            restore = button(
                "",
                "Unhide reply" if kind == "reply" else "Reattach quote",
                lambda target=uri: relation(
                    self.window,
                    self.post.uri,
                    target,
                    kind,
                    False,
                    lambda gate: self.restored(gate, kind),
                ),
                "Unhide reply" if kind == "reply" else "Reattach quote",
            )
            self.window.online_control(restore)
            row.append(restore)
            self.body.append(row)

    def restored(self, gate, kind):
        if self.valid():
            mode = self.mode.get_selected() if self.thread else None
            groups = {
                name: control.get_active() for name, control in getattr(self, "groups", {}).items()
            }
            quotes = self.allow_quotes.get_active()
            if kind == "reply":
                self.thread = gate
            else:
                self.quote = gate
            self.render()
            if mode is not None:
                self.mode.set_selected(mode)
                for name, active in groups.items():
                    self.groups[name].set_active(active)
            self.allow_quotes.set_active(quotes)
