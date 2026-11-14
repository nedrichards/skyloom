"""Context-aware window commands and reversible list feedback."""

from urllib.parse import quote

from gi.repository import Adw, Gdk, Gio, Gtk

from .domain import Author, Notice, Post
from .keyboard import MOVEMENT, REPEATABLE, match
from .refresh import Connection, RefreshPolicy


class Interactions:
    def __init__(self, window):
        self.window = window
        self.connection = Connection()
        self.policies = {}
        self.undo_action = None
        self.undo_toast = None
        self.held = set()
        self.testing_auto = False
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key_pressed)
        keys.connect("key-released", self.key_released)
        window.add_controller(keys)
        window.connect("notify::is-active", self.activity_changed)

    def activity_changed(self, *_args):
        if not self.window.is_active():
            self.held.clear()
            if (
                self.undo_toast is not None
                and self.undo_action is not None
                and self.undo_action[1] is not None
            ):
                self.undo_toast.dismiss()
                self.undo_toast = None

    def current_view(self, mapped=True):
        split = getattr(self.window, "split", None)
        if mapped and split and split.get_collapsed() and split.get_show_sidebar():
            return None
        page = self.window.nav.get_visible_page() if hasattr(self.window, "nav") else None
        return next(
            (
                view
                for view in reversed(self.window.views)
                if (view.get_mapped() or not mapped)
                and not view.paging.closed
                and (page is None or view.is_ancestor(page))
            ),
            None,
        )

    def destination(self):
        window = self.window
        if not hasattr(window, "nav"):
            return None
        page = window.nav.get_visible_page()
        return "home" if page == window.home_page else getattr(page, "destination", None)

    def context(self):
        window = self.window
        if window.get_visible_dialog():
            return "dialog"
        focus = window.get_focus()
        ancestor = focus
        while ancestor:
            if isinstance(ancestor, Gtk.Popover):
                return "popup"
            ancestor = ancestor.get_parent()
        current = focus
        while current:
            if getattr(current, "continuation_uri", None):
                return "control"
            if isinstance(current, Gtk.Popover):
                return "popup"
            if isinstance(current, Gtk.Editable | Gtk.TextView):
                return "text"
            if isinstance(current, Gtk.Label) and current.get_selectable():
                return "text"
            if isinstance(
                current, Gtk.DropDown | Gtk.Switch | Gtk.Range | Gtk.SpinButton | Gtk.Expander
            ):
                return "control"
            if isinstance(current, Gtk.Button | Gtk.MenuButton):
                if (
                    isinstance(current, Gtk.MenuButton)
                    and current.get_popover()
                    and current.get_popover().get_visible()
                ):
                    return "popup"
                if current.get_ancestor(Adw.HeaderBar) or current.get_ancestor(Gtk.HeaderBar):
                    return "chrome"
                return "control"
            current = current.get_parent()
        return "list" if self.current_view() else "chrome"

    def key_pressed(self, _keys, key, code, modifiers):
        binding = match(key, modifiers)
        if binding is None or binding.scope == "composer":
            return False
        identity = code or Gdk.keyval_to_lower(key)
        if identity in self.held and binding.command not in REPEATABLE:
            return True
        context = self.context()
        if binding.scope == "conversation" and (
            context != "list" or not hasattr(self.current_view(), "relative")
        ):
            return False
        if context in {"dialog", "popup"}:
            return False
        if binding.scope != "global":
            if (
                context not in {"list", "chrome"}
                and not (binding.command in {"undo", "show-new"} and context == "control")
            ) or self.current_view() is None:
                return False
            if (
                context == "chrome"
                and binding.command not in MOVEMENT
                and binding.command not in {"undo", "show-new"}
            ):
                return False
        elif binding.command == "back" and context == "text":
            return False if key == Gdk.KEY_Escape else self.back(allow_text=True)
        handled = self.command(binding.command)
        if handled:
            self.held.add(identity)
        return handled

    def key_released(self, _keys, key, code, _modifiers):
        self.held.discard(code or Gdk.keyval_to_lower(key))

    def policy(self, key):
        return self.policies.setdefault(key, RefreshPolicy())

    def update_actions(self):
        app = self.window.get_application()
        if app is None:
            return
        view = self.current_view()
        ready = self.window.service.account is not None
        modal = self.context() in {"dialog", "popup"}
        selected = view.interaction.selected() if view else None
        writable = ready and not self.window.read_only and not modal
        enabled = {
            "preferences": self.window.get_visible_dialog() is None,
            "about": self.window.get_visible_dialog() is None,
            "compose": ready and not modal,
            "manage-feeds": ready and self.window.get_visible_dialog() is None,
            "refresh": bool(view and view.refresh and not view.paging.busy and not modal),
            "top": bool(view and view.model.get_n_items() and not modal),
            "show-new": bool(view and view.pending_update and not self.window.get_visible_dialog()),
            "undo": self.undo_action is not None and not modal,
            "like": writable and isinstance(selected, Post),
            "repost": writable and isinstance(selected, Post),
            "reply": ready and not modal and isinstance(selected, Post),
            "quote": ready and not modal and isinstance(selected, Post),
            "open": bool(view and view.interaction.positions() and not modal),
            "browser": bool(self.selected_link(selected)) and not modal,
            "copy-link": bool(self.selected_link(selected)) and not modal,
            "post-menu": isinstance(selected, Post) and not modal,
        }
        for name, value in enabled.items():
            action = app.lookup_action(name)
            if action:
                action.set_enabled(value)

    def automatic_reason(self):
        return self.connection.pause_reason(self.window.settings.get_boolean("use-metered"))

    def auto_target(self):
        view = self.current_view()
        return view if view and getattr(view, "auto_refresh", None) is not None else None

    def refresh_decision(self, now, active=None):
        window = self.window
        view = self.auto_target()
        if view is None:
            return None, None
        policy = self.policy(view.auto_key)
        decision = policy.decision(
            now,
            active=window.is_active() if active is None else active,
            ready=window.service.account is not None,
            enabled=window.settings.get_boolean("auto-refresh")
            and (not window.demo or self.testing_auto),
            connection=self.connection,
            busy=bool(window.page_requests or window.mutations or view.paging.busy)
            or self.context() in {"dialog", "popup", "text"},
            allow_metered=window.settings.get_boolean("use-metered"),
        )
        return view, decision

    def check_auto(self, now, active=None):
        view, decision = self.refresh_decision(now, active)
        if decision is not None and decision.due:
            view.auto_refresh()
            return True
        return False

    def connection_changed(self, connection):
        previous = self.connection
        self.connection = connection
        reason = self.automatic_reason()
        unchanged = previous == connection and reason == getattr(self, "loading_reason", None)
        self.loading_reason = reason
        if unchanged:
            self.update_actions()
            return
        window = self.window
        connected = connection.available and connection.internet
        was_connected = previous.available and previous.internet
        if window.service.account and hasattr(window, "compose_button"):
            if not connected and not window.read_only:
                window.show_offline(True)
            elif not was_connected and connected:
                window.show_offline(False)
        if previous != connection:
            if window.service.account and window.is_active():
                if previous.available and not connection.available:
                    window.toast("You’re offline. Cached posts remain available.")
                elif not was_connected and connected:
                    window.toast("Back online. Stale feeds will refresh when active.")
                elif connection.metered and not previous.metered:
                    window.toast(
                        "Metered connection. Automatic downloads are paused."
                        if not window.settings.get_boolean("use-metered")
                        else "Metered connection. Your automatic-download preference applies."
                    )
            if hasattr(window, "connection_row"):
                window.connection_row.set_subtitle(connection.description)
        for view in window.views:
            for footer in list(view.footers):
                footer.sync()
            view.queue_check()
        self.update_actions()

    def navigate(self, destination):
        window = self.window
        if window.service.account is None:
            return False
        if self.destination() == destination:
            window.navigation.reveal_content()
            page = window.nav.get_visible_page()
            if destination == "search" and getattr(page, "focus_widget", None):
                page.content_view.focus_header(page.focus_widget)
                return True
            view = self.current_view()
            if view:
                view.interaction.focus(preserve_position=True)
            return True
        if destination == "home":
            window.go_home()
        elif destination == "profile":
            window.profile(window.service.account.did)
        else:
            getattr(window, destination)()
        return True

    def install_destination(self, widget, destination):
        armed = False

        def pressed(gesture, count, _x, _y):
            nonlocal armed
            if count == 1:
                armed = self.destination() == destination
            elif count == 2:
                if armed and self.destination() == destination:
                    gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                    self.top()
                armed = False

        gesture = Gtk.GestureClick(
            button=Gdk.BUTTON_PRIMARY, propagation_phase=Gtk.PropagationPhase.CAPTURE
        )
        gesture.connect("pressed", pressed)
        widget.add_controller(gesture)
        widget.set_tooltip_text(
            f"{destination.title()} · double-click or double-tap when active to go to the top"
        )
        return gesture

    def offer_undo(self, title, callback, view=None):
        if self.undo_toast is not None:
            self.undo_toast.dismiss()
        self.undo_action = (self.window.generation, view, callback)
        token = self.undo_action
        toast = Adw.Toast(title=title, button_label="Undo", timeout=2 if view is not None else 5)
        self.undo_toast = toast
        toast.connect(
            "button-clicked", lambda _toast: self.undo() if self.undo_action is token else None
        )
        self.window.overlay.add_toast(toast)
        self.window.last_toast = toast
        self.update_actions()
        return toast

    def undo(self):
        pending = self.undo_action
        self.undo_action = None
        if self.undo_toast is not None:
            self.undo_toast.dismiss()
            self.undo_toast = None
        self.update_actions()
        if pending is None or pending[0] != self.window.generation:
            self.window.toast("Nothing to undo.")
            return False
        _generation, view, callback = pending
        if view is not None and (view.paging.closed or self.current_view() != view):
            self.window.toast("Return to that list before undoing the jump.")
            self.undo_action = pending
            return False
        result = callback()
        if result is False:
            self.window.toast("That action can no longer be undone.")
            return False
        self.window.toast("Undoing reaction…" if result == "pending" else "Undone.")
        return True

    def offer_position_undo(self, title, view, place):
        if not view.interaction.can_restore(place):
            return False
        self.offer_undo(title, lambda: view.interaction.restore(place), view)
        return True

    def top(self):
        view = self.current_view()
        if not view or not view.model.get_n_items():
            return False
        if view.feed is not None:
            # A loaded head marker only describes an earlier snapshot. Every
            # explicit feed-top action resolves the newest page, including Home
            # double presses; the loaded window is not an authoritative top.
            self.window.refresh()
            return True
        if view.interaction.at_top():
            view.top_peek.pulse()
            return True
        place = view.interaction.top()
        self.offer_position_undo("Moved to top", view, place)
        return True

    def focus_pane(self):
        window = self.window
        focus = window.get_focus()
        buttons = getattr(window, "destination_buttons", {})
        sidebar = window.split.get_sidebar()
        in_sidebar = focus and sidebar and (focus == sidebar or focus.is_ancestor(sidebar))
        view = self.current_view()
        if in_sidebar or (
            view is not None
            and (
                self.context() == "text"
                or (
                    focus
                    and (focus.get_ancestor(Adw.HeaderBar) or focus.get_ancestor(Gtk.HeaderBar))
                )
            )
        ):
            window.navigation.reveal_content()
            view = view or self.current_view(mapped=False)
            if view:
                view.interaction.focus(preserve_position=True)
            else:
                page = window.nav.get_visible_page()
                target = getattr(page, "focus_widget", page.navigation_button)
                if target:
                    target.grab_focus()
        else:
            window.navigation.reveal_sidebar()
            buttons.get(self.destination(), next(iter(buttons.values()))).grab_focus()
        return True

    def back(self, allow_text=False):
        window = self.window
        if self.context() in {"dialog", "popup"} or (self.context() == "text" and not allow_text):
            return False
        if window.split.get_collapsed() and window.split.get_show_sidebar():
            window.navigation.reveal_content()
            window.nav.get_visible_page().navigation_button.grab_focus()
            return True
        if window.nav.pop():
            view = self.current_view()
            if view:
                view.interaction.focus(preserve_position=True)
            return True
        if window.split.get_collapsed() and not window.split.get_show_sidebar():
            window.navigation.reveal_sidebar()
            window.destination_buttons.get(self.destination(), window.side_buttons[0]).grab_focus()
            return True
        return False

    def selected_link(self, item):
        if isinstance(item, Post):
            return item.link
        if isinstance(item, Author):
            return "https://bsky.app/profile/" + quote(item.did, safe=":")
        if isinstance(item, Notice):
            uri = item.subject or item.uri
            parts = uri.removeprefix("at://").split("/")
            if len(parts) == 3 and parts[1] == "app.bsky.feed.post":
                return (
                    f"https://bsky.app/profile/{quote(parts[0], safe=':')}/post/{quote(parts[2])}"
                )
        return ""

    def command(self, command):
        window = self.window
        if command in {"quit", "close"}:
            if command == "close" and window.get_visible_dialog():
                window.get_visible_dialog().close()
                return True
            window.close()
            return True
        if command == "shortcuts":
            window.get_application().shortcuts()
            return True
        if command == "manage-feeds":
            if window.get_visible_dialog() or window.service.account is None:
                return False
            self.dismiss_main_menu()
            window.open_uri("https://bsky.app/settings/saved-feeds")
            return True
        context = self.context()
        if context == "dialog" or (context == "popup" and not self.dismiss_main_menu()):
            return False
        if command == "preferences":
            window.preferences()
            return True
        if command == "about":
            window.about()
            return True
        if command == "main-menu":
            if window.service.account is None:
                menu = getattr(window, "welcome_menu", None)
            elif window.split.get_show_sidebar():
                menu = window.sidebar_menu
            else:
                menu = getattr(window.nav.get_visible_page(), "menu_button", None)
            if menu and menu.get_mapped():
                menu.popup()
                return True
            return False
        if window.service.account is None:
            return False
        if command in {"home", "search", "notifications", "profile", "drafts"}:
            return self.navigate(command)
        if command == "compose":
            window.compose()
            return True
        if command == "back":
            return self.back()
        if command in {"focus-next", "focus-previous"}:
            return self.focus_pane()
        view = self.current_view()
        if command == "undo":
            return self.undo()
        if command == "top":
            return self.top()
        if not view:
            return False
        if command in {"parent-message", "child-message"}:
            return getattr(view, "relative", lambda _direction: False)(
                "parent" if command == "parent-message" else "child"
            )
        if command == "show-new":
            return view.apply_update()
        if command == "refresh":
            if view.refresh:
                view.refresh()
                return True
            return False
        if command in MOVEMENT:
            return view.interaction.move(command)
        if command == "open":
            if view.interaction.selected() is None:
                view.interaction.focus()
            index = view.store.get_selected()
            if index != Gtk.INVALID_LIST_POSITION:
                view.activate_item(view.list, index)
                return True
            return False
        item = view.interaction.selected()
        if command in {"browser", "copy-link"}:
            link = self.selected_link(item)
            if link:
                window.open_uri(link) if command == "browser" else window.copy(link)
                return True
            return False
        if not isinstance(item, Post):
            return False
        if command == "post-menu":
            row = next(
                (row for _y, row in view.interaction.visible_rows() if row._value.uri == item.uri),
                None,
            )
            if row and hasattr(row, "menu"):
                row.menu.popup()
                return True
        if command in {"reply", "quote"}:
            window.compose(**{command: item})
            return True
        if window.read_only:
            return False
        if command in {"like", "repost"}:
            window.mutate(item, command)
            return True
        return False

    def dismiss_main_menu(self):
        window = self.window
        page = window.nav.get_visible_page() if hasattr(window, "nav") else None
        for menu in (
            getattr(window, "welcome_menu", None),
            getattr(window, "sidebar_menu", None),
            getattr(page, "menu_button", None),
        ):
            if menu and (popover := menu.get_popover()) and popover.get_visible():
                popover.popdown()
                return True
        return False

    def menu(self):
        menu = Gio.Menu()
        reading = Gio.Menu()
        for title, action in [
            ("New post", "compose"),
            ("Refresh", "refresh"),
            ("Go to top", "top"),
            ("Show new items", "show-new"),
            ("Undo", "undo"),
        ]:
            reading.append(title, "app." + action)
        menu.append_section(None, reading)
        application = Gio.Menu()
        for title, action in [
            ("Manage feeds in Bluesky…", "manage-feeds"),
            ("Preferences", "preferences"),
            ("Keyboard shortcuts", "shortcuts"),
            ("About Skyloom", "about"),
        ]:
            application.append(title, "app." + action)
        menu.append_section(None, application)
        return menu
