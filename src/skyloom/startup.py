"""Neutral startup until session lookup resolves, with delayed native feedback."""

from gi.repository import Adw, GLib, Gtk


class StartupStack(Gtk.Stack):
    def __init__(self):
        super().__init__(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=150,
        )
        self.loading_source = None
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Skyloom")))
        self.spinner = Gtk.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.append(self.spinner)
        content.append(Gtk.Label(label="Opening Skyloom…", css_classes=["dim-label"]))
        self.loading = Gtk.Revealer(
            child=content,
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            transition_duration=150,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        toolbar.set_content(self.loading)
        self.add_named(toolbar, "pending")
        recovery = Adw.ToolbarView()
        recovery.add_top_bar(Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Skyloom")))
        self.error_page = Adw.StatusPage(
            title="Couldn’t restore your session", icon_name="dialog-error-symbolic"
        )
        actions = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self.retry_button = Gtk.Button(label="Try again", css_classes=["suggested-action"])
        self.sign_in_button = Gtk.Button(label="Sign in")
        actions.append(self.retry_button)
        actions.append(self.sign_in_button)
        self.error_page.set_child(actions)
        recovery.set_content(self.error_page)
        self.add_named(recovery, "recovery")

    def begin(self):
        self.close()
        self.set_visible_child_name("pending")
        self.loading_source = GLib.timeout_add(200, self.show_loading)

    def show_loading(self):
        self.loading_source = None
        if self.get_visible_child_name() == "pending":
            self.spinner.set_spinning(True)
            self.loading.set_reveal_child(True)
        return False

    def resolve(self, page):
        self.close()
        self.set_visible_child_name(page)

    def show_error(self, message):
        self.error_page.set_description(message)
        self.resolve("recovery")

    def close(self):
        if self.loading_source is not None:
            GLib.source_remove(self.loading_source)
            self.loading_source = None
        self.spinner.set_spinning(False)
        self.loading.set_reveal_child(False)
