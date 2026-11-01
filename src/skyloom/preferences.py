"""Application preferences with account actions kept at the bottom."""

from gi.repository import Adw, Gio, Gtk


class Preferences(Adw.PreferencesDialog):
    def __init__(self, window):
        super().__init__(title="Preferences")
        page = Adw.PreferencesPage()
        reading = Adw.PreferencesGroup(title="Reading")
        appearance = Adw.ComboRow(
            title="Appearance", model=Gtk.StringList.new(["System", "Light", "Dark"])
        )
        appearance.add_css_class("appearance-selector")
        self.appearance = appearance
        values = ["system", "light", "dark"]
        appearance.set_selected(values.index(window.settings.get_string("appearance")))
        appearance.connect(
            "notify::selected",
            lambda row, _ps: window.settings.set_string("appearance", values[row.get_selected()]),
        )
        reading.add(appearance)
        images = self.switch(window, "load-images", "Load images")
        images.connect("notify::active", window.redisplay_media)
        reading.add(images)
        reading.add(self.switch(window, "warn-labelled-content", "Warn about labelled content"))
        page.add(reading)

        updates = Adw.PreferencesGroup(title="Updates")
        updates.add(
            self.switch(
                window, "auto-refresh", "Refresh automatically", "Every five minutes while active"
            )
        )
        updates.add(
            self.switch(
                window,
                "use-metered",
                "Use metered connections",
                "Allow automatic refresh, paging and images",
            )
        )
        window.connection_row = Adw.ActionRow(
            use_markup=False,
            title="Connection",
            subtitle=window.interactions.connection.description,
        )
        updates.add(window.connection_row)
        page.add(updates)

        storage = Adw.PreferencesGroup(
            title="Storage",
            description="Saved posts, drafts and images are removed when you sign out.",
        )
        storage.add(
            Adw.ActionRow(
                use_markup=False,
                title="Image cache",
                subtitle="Storage unavailable · images can still load online"
                if window.images.disk_error
                else "Up to 128 MiB · available offline",
            )
        )
        page.add(storage)

        authentication = Adw.PreferencesGroup(title="Authentication")
        if account := window.service.account:
            authentication.add(
                Adw.ActionRow(use_markup=False, title="Account", subtitle="@" + account.handle)
            )
        authentication.add(
            Adw.ActionRow(
                use_markup=False,
                title="Sign-in method",
                subtitle="Offline demo"
                if window.demo
                else "App password · session saved in your login keyring",
            )
        )
        if account:
            self.sign_out_row = Adw.ButtonRow(
                title="Leave demo" if window.demo else "Sign out",
                start_icon_name="system-log-out-symbolic",
            )
            self.sign_out_row.add_css_class("destructive-action")
            self.sign_out_row.connect("activated", lambda _row: window.sign_out(self))
            authentication.add(self.sign_out_row)
        page.add(authentication)
        self.add(page)

    @staticmethod
    def switch(window, key, title, subtitle=""):
        row = Adw.SwitchRow(title=title, subtitle=subtitle)
        window.settings.bind(key, row, "active", Gio.SettingsBindFlags.DEFAULT)
        return row
