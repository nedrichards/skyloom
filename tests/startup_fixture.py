"""Native window fixture with temporary demo data and synthetic session restore."""

import time
from pathlib import Path

from gtk_support import DISPLAY

if DISPLAY:
    from gi.repository import Adw, Gio, GLib, Gtk


class StartupFixture:
    count = 0

    def setUp(self):
        from skyloom import APP_ID
        from skyloom.demo import DemoService
        from skyloom.media import Images
        from skyloom.worker import Worker

        StartupFixture.count += 1
        self.app = Adw.Application(
            application_id=f"{APP_ID}.StartupFixture{StartupFixture.count}",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.assertTrue(self.app.register(None))
        self.app.demo = False
        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        self.app.settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        self.app.settings.set_boolean("auto-refresh", False)
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        self.app.service = DemoService(fixtures / "demo-feed.json")
        self.app.service.cached_feeds = self.app.service.feeds
        self.account = self.app.service.account
        self.app.service.account = None
        self.app.worker = Worker()
        self.app.images = Images(fixtures, self.app.service.storage.images)
        self.window = None
        self.frames = []
        settings = Gtk.Settings.get_default()
        animations = settings.get_property("gtk-enable-animations")
        settings.set_property("gtk-enable-animations", True)
        self.addCleanup(settings.set_property, "gtk-enable-animations", animations)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.window:
            self.window.cancel_startup()
            self.window.refresh_monitor.close()
            for view in self.window.views:
                view.close()
            self.window.destroy()
        self.app.worker.close(self.app.service.close())

    def open(self, restore):
        from skyloom.window import Window

        self.app.service.restore = restore
        self.window = Window(self.app)
        self.window.set_title("Skyloom startup fixture")

        def frame(*_args):
            self.frames.append(
                (
                    self.window.stack.get_visible_child_name(),
                    self.window.stack.spinner.get_spinning(),
                )
            )
            return True

        self.window.add_tick_callback(frame)
        self.window.present()

    def wait(self, predicate, timeout=2):
        started = time.monotonic()
        loop = GLib.MainLoop()
        success = False

        def check():
            nonlocal success
            success = bool(predicate())
            if success or time.monotonic() - started >= timeout:
                loop.quit()
                return False
            return True

        GLib.timeout_add(10, check)
        loop.run()
        self.assertTrue(success, "Startup state did not settle before its deadline")

    async def restored_account(self):
        self.app.service.account = self.account
        return self.account
