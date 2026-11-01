"""One shortcut registry for native actions, dispatch, shortcut help and tooltips."""

from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True, slots=True)
class Binding:
    command: str
    title: str
    keys: tuple[str, ...]
    section: str = "General"
    scope: str = "global"


BINDINGS = (
    Binding("compose", "New post", ("<Control>n",)),
    Binding("refresh", "Refresh the current list", ("<Control>r", "F5")),
    Binding("search", "Search posts or people", ("<Control>k", "<Control>f")),
    Binding("preferences", "Preferences", ("<Control>comma",)),
    Binding(
        "shortcuts", "Keyboard shortcuts", ("F1", "<Control>question", "<Control><Shift>slash")
    ),
    Binding("close", "Close window", ("<Control>w",)),
    Binding("quit", "Quit Skyloom", ("<Control>q",)),
    Binding("back", "Go back or show navigation", ("Escape", "<Alt>Left"), "Navigation"),
    Binding("focus-next", "Focus the next pane", ("F6",), "Navigation"),
    Binding("focus-previous", "Focus the previous pane", ("<Shift>F6",), "Navigation"),
    Binding("home", "Home", ("<Control>1",), "Navigation"),
    Binding("search", "Search", ("<Control>2",), "Navigation"),
    Binding("notifications", "Notifications", ("<Control>3",), "Navigation"),
    Binding("profile", "Your profile", ("<Control>4",), "Navigation"),
    Binding("drafts", "Drafts", ("<Control>5",), "Navigation"),
    Binding("main-menu", "Open the main menu", ("F10",), "Navigation"),
    Binding("top", "Jump to the top, with Undo", ("<Control>Home",), "Lists", "list"),
    Binding("show-new", "Show new items", ("<Control><Shift>Home",), "Lists", "list"),
    Binding("next", "Select the next item", ("Down", "j"), "Lists", "list"),
    Binding("previous", "Select the previous item", ("Up", "k"), "Lists", "list"),
    Binding("first", "Select the first item", ("Home",), "Lists", "list"),
    Binding("last", "Select the last loaded item", ("End",), "Lists", "list"),
    Binding("page-down", "Move one page down", ("Page_Down", "space"), "Lists", "list"),
    Binding("page-up", "Move one page up", ("Page_Up", "<Shift>space"), "Lists", "list"),
    Binding("open", "Open the selected item", ("Return", "KP_Enter"), "Lists", "list"),
    Binding(
        "parent-message", "Select parent message", ("<Alt>Up",), "Conversations", "conversation"
    ),
    Binding("child-message", "Select first reply", ("<Alt>Down",), "Conversations", "conversation"),
    Binding("compose", "New post", ("n",), "Posts", "post"),
    Binding("reply", "Reply to the selected post", ("r",), "Posts", "post"),
    Binding("quote", "Quote the selected post", ("q",), "Posts", "post"),
    Binding("like", "Like or unlike the selected post", ("l",), "Posts", "post"),
    Binding("repost", "Repost or undo repost", ("<Shift>r",), "Posts", "post"),
    Binding("browser", "Open the selected item in Bluesky", ("b",), "Posts", "post"),
    Binding("copy-link", "Copy the selected item’s link", ("<Control><Shift>c",), "Posts", "post"),
    Binding("post-menu", "Open the selected post’s menu", ("m",), "Posts", "post"),
    Binding("undo", "Undo the last jump or reaction", ("u", "<Control>z"), "Lists", "list"),
    Binding(
        "publish",
        "Publish from the composer",
        ("<Control>Return", "<Control>KP_Enter"),
        "Composer",
        "composer",
    ),
)
MOVEMENT = frozenset({"next", "previous", "first", "last", "page-down", "page-up", "top"})
REPEATABLE = MOVEMENT - {"top"}


@cache
def parsed():
    from gi.repository import Gtk

    result = []
    for binding in BINDINGS:
        for accelerator in binding.keys:
            valid, key, modifiers = Gtk.accelerator_parse(accelerator)
            if not valid:
                raise ValueError(f"Invalid shortcut: {accelerator}")
            result.append((key, int(modifiers), binding))
    return tuple(result)


def match(key, modifiers, scope=None):
    from gi.repository import Gdk

    keep = (
        Gdk.ModifierType.SHIFT_MASK
        | Gdk.ModifierType.CONTROL_MASK
        | Gdk.ModifierType.ALT_MASK
        | Gdk.ModifierType.SUPER_MASK
        | Gdk.ModifierType.HYPER_MASK
        | Gdk.ModifierType.META_MASK
    )
    modifiers = int(modifiers & keep)
    key = Gdk.keyval_to_lower(key)
    if key == Gdk.KEY_question:
        modifiers &= ~int(Gdk.ModifierType.SHIFT_MASK)
    return next(
        (
            b
            for k, m, b in parsed()
            if k == key and m == modifiers and (scope is None or b.scope == scope)
        ),
        None,
    )


def accelerators(command):
    # Native dialogs and popovers own Escape/F6/F10; the context router handles them.
    if command in {"back", "focus-next", "focus-previous", "main-menu"}:
        return []
    return [key for b in BINDINGS if b.command == command and b.scope == "global" for key in b.keys]


def hint(command):
    from gi.repository import Gtk

    binding = next((b for b in BINDINGS if b.command == command), None)
    if binding is None:
        return ""
    _valid, key, modifiers = Gtk.accelerator_parse(binding.keys[0])
    return Gtk.accelerator_get_label(key, modifiers)


def shortcuts_dialog(window):
    from gi.repository import Adw

    dialog = Adw.ShortcutsDialog()
    sections = {}
    for binding in BINDINGS:
        if binding.section not in sections:
            sections[binding.section] = Adw.ShortcutsSection.new(binding.section)
            dialog.add(sections[binding.section])
        for accelerator in binding.keys:
            item = Adw.ShortcutsItem.new(binding.title, accelerator)
            if binding.scope in {"list", "post"}:
                item.set_subtitle("Outside text fields, dialogs and focused controls")
            sections[binding.section].add(item)
    dialog.present(window)
    return dialog
