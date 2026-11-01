"""Compact label explanations and lazy disclosure shared by posts and profiles."""

from dataclasses import dataclass

from gi.repository import Adw, Gtk, Pango

# Standard global meanings, not labeller-specific definitions or severity decisions.
# Unknown/custom values remain available verbatim rather than acquiring invented meanings.
STANDARD_LABELS = {
    "porn": ("Adult content", "Explicit sexual imagery or activity.", "image-x-generic-symbolic"),
    "sexual": (
        "Sexually suggestive",
        "Sexually suggestive themes or imagery.",
        "image-x-generic-symbolic",
    ),
    "nudity": (
        "Non-sexual nudity",
        "Nudity without explicit sexual activity.",
        "image-x-generic-symbolic",
    ),
    "graphic-media": (
        "Graphic media",
        "Graphic violence or potentially disturbing imagery.",
        "dialog-warning-symbolic",
    ),
    "bot": ("Automated account", "An account marked as automated.", "system-run-symbolic"),
    "!warn": ("Content warning", "A general content warning.", "dialog-warning-symbolic"),
    "!hide": (
        "Restricted content",
        "A service restriction marker. Availability also depends on the service.",
        "dialog-warning-symbolic",
    ),
    "!no-unauthenticated": (
        "Sign-in restriction",
        "A marker for content that requires sign-in on supporting services.",
        "dialog-information-symbolic",
    ),
}


@dataclass(frozen=True, slots=True)
class ContentLabel:
    value: str
    title: str
    description: str
    icon: str
    scopes: tuple[str, ...]


def describe_labels(labels, author_labels=(), *, profile=False):
    """Merge duplicate values while preserving the origins actually returned by our model."""
    scopes = {}
    for values, scope in (
        (labels, "On this profile" if profile else "On this post"),
        (author_labels, "On the author"),
    ):
        for value in values:
            if value:
                origins = scopes.setdefault(value, [])
                if scope not in origins:
                    origins.append(scope)
    result = []
    for value, origins in scopes.items():
        title, description, icon = STANDARD_LABELS.get(
            value,
            (
                value.replace("-", " ").replace("_", " ").capitalize(),
                "No definition was supplied for this label. Its meaning depends on the labeller.",
                "dialog-information-symbolic",
            ),
        )
        result.append(ContentLabel(value, title, description, icon, tuple(origins)))
    return tuple(result)


def text(value, css=None):
    widget = Gtk.Label(label=value, xalign=0, wrap=True, max_width_chars=36)
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        widget.add_css_class(css)
    return widget


class LabelledContent(Gtk.Box):
    def __init__(self, window, key, labels, build, *, author_labels=()):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.window, self.key, self.build = window, key, build
        self.labels = describe_labels(labels, author_labels, profile=key[0] == "profile")
        self.chips = []
        bar = Gtk.Box(spacing=6)
        # Natural-width controls, without focusable grid cells around the chips.
        flow = Adw.WrapBox(child_spacing=6, line_spacing=6, hexpand=True)
        flow.add_css_class("content-labels")
        for item in self.labels[:3]:
            flow.append(self.chip(item.title, item.icon, (item,)))
        if len(self.labels) > 3:
            flow.append(
                self.chip(
                    f"+{len(self.labels) - 3}",
                    "view-more-symbolic",
                    self.labels,
                    tooltip=f"All {len(self.labels)} content labels",
                )
            )
        bar.append(flow)
        self.hide_button = Gtk.Button(
            icon_name="view-conceal-symbolic",
            tooltip_text="Hide labelled content",
            valign=Gtk.Align.START,
        )
        self.hide_button.add_css_class("flat")
        self.hide_button.update_property([Gtk.AccessibleProperty.LABEL], ["Hide labelled content"])
        self.hide_button.connect("clicked", lambda _: self.set_revealed(False))
        bar.append(self.hide_button)
        self.append(bar)

        self.notice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.notice.add_css_class("content-label-notice")
        heading = Gtk.Box(spacing=10)
        heading.append(Gtk.Image(icon_name="view-conceal-symbolic", pixel_size=24))
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        words.append(text("Content hidden", "heading"))
        words.append(text("You can show it here without changing your preferences.", "dim-label"))
        heading.append(words)
        self.notice.append(heading)
        self.show_button = Gtk.Button(label="Show content", halign=Gtk.Align.START)
        self.show_button.add_css_class("pill")
        self.show_button.connect("clicked", lambda _: self.set_revealed(True))
        self.notice.append(self.show_button)
        self.append(self.notice)
        self.revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration=150
        )
        self.append(self.revealer)
        window.content_gates.add(self)
        self.sync()

    def chip(self, title, icon, items, *, tooltip=None):
        chip = Gtk.MenuButton(
            tooltip_text=tooltip or f"About {title}",
            valign=Gtk.Align.START,
            halign=Gtk.Align.START,
        )
        chip.focus_key = ("content-label", self.key, tuple(item.value for item in items))
        chip.add_css_class("content-label-chip")
        chip.set_always_show_arrow(False)
        body = Gtk.Box(spacing=6)
        body.append(Gtk.Image(icon_name=icon, pixel_size=16))
        caption = Gtk.Label(label=title, ellipsize=Pango.EllipsizeMode.END, max_width_chars=22)
        body.append(caption)
        chip.set_child(body)
        chip.update_property([Gtk.AccessibleProperty.LABEL], [tooltip or f"About {title}"])
        chip.set_create_popup_func(lambda button: button.set_popover(self.details(items)))
        self.chips.append(chip)
        return chip

    def details(self, items):
        popover = Gtk.Popover()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_size_request(280, -1)
        for edge in ("top", "bottom", "start", "end"):
            getattr(body, "set_margin_" + edge)(12)
        entries = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for item in items:
            entry = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            heading = Gtk.Box(spacing=8)
            heading.append(Gtk.Image(icon_name=item.icon, pixel_size=20))
            title = text(item.title, "heading")
            title.set_hexpand(True)
            heading.append(title)
            entry.append(heading)
            entry.append(text(" · ".join(item.scopes), "caption"))
            entry.append(text(item.description))
            raw = text(item.value, "monospace")
            raw.set_selectable(True)
            raw.set_tooltip_text("Original label value")
            entry.append(raw)
            copy = Gtk.Button(label="Copy label", halign=Gtk.Align.START)
            copy.add_css_class("flat")
            copy.connect("clicked", lambda _, value=item.value: self.copy_label(value))
            entry.append(copy)
            entries.append(entry)
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
            max_content_height=360,
            child=entries,
        )
        body.append(scroll)
        body.append(Gtk.Separator())
        note = text("Visibility is your choice in Skyloom.", "dim-label")
        body.append(note)
        preferences = Gtk.Button(label="Label preferences…")
        preferences.connect("clicked", lambda _: self.open_preferences(popover))
        body.append(preferences)
        popover.set_child(body)
        return popover

    def copy_label(self, value):
        self.get_clipboard().set(value)
        self.window.toast("Label copied")

    def open_preferences(self, popover):
        popover.popdown()
        self.window.preferences()

    def get_revealed(self):
        return self.revealer.get_reveal_child()

    def set_revealed(self, revealed):
        focused = self.hide_button.has_focus() or self.show_button.has_focus()
        states = self.window.revealed_labels
        states[self.key] = revealed
        if len(states) > 1024:
            del states[next(iter(states))]
        for gate in tuple(self.window.content_gates):
            if gate.key == self.key:
                gate.sync()
        if focused:
            (self.hide_button if revealed else self.show_button).grab_focus()

    def sync(self):
        revealed = self.window.revealed_labels.get(
            self.key, not self.window.settings.get_boolean("warn-labelled-content")
        )
        if revealed and self.revealer.get_child() is None:
            self.revealer.set_child(self.build())
        self.revealer.set_reveal_child(revealed)
        self.hide_button.set_visible(revealed)
        self.notice.set_visible(not revealed)
