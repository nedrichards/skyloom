"""Application lifecycle, resources, settings and keyboard actions."""

import gettext
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, Gtk

from . import APP_ID
from .demo import DemoService
from .keyboard import BINDINGS, accelerators, shortcuts_dialog
from .media import Images
from .service import Service
from .window import Window
from .worker import Worker


class Application(Adw.Application):
    def __init__(self, demo=False, smoke=None, keyboard_test=False, smoke_scenario="full"):
        super().__init__(
            application_id=APP_ID + (".Demo" if demo else ""),
            flags=Gio.ApplicationFlags.NON_UNIQUE if demo else Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.demo, self.smoke = demo, smoke
        self.keyboard_test = keyboard_test
        self.smoke_scenario = smoke_scenario
        self.root = Path(__file__).resolve().parents[1]
        self.fixture_dir = self.root / "fixtures"
        if not self.fixture_dir.exists():
            self.fixture_dir = Path(__file__).resolve().parents[2] / "fixtures"
        self.worker = Worker()
        self.service = DemoService(self.fixture_dir / "demo-feed.json") if demo else Service()
        self.images = Images(self.fixture_dir, self.service.storage.images)
        self.window = None
        gettext.bindtextdomain("skyloom")
        gettext.textdomain("skyloom")

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.settings = Gio.Settings.new(APP_ID)
        self.settings.connect("changed::appearance", lambda *_: self.apply_appearance())
        self.apply_appearance()
        resource = self.root / "skyloom.gresource"
        if resource.exists():
            Gio.resources_register(Gio.Resource.load(str(resource)))
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_resource_path(
                "/com/nedrichards/Skyloom/icons"
            )
        provider = Gtk.CssProvider()
        if resource.exists():
            provider.load_from_resource("/com/nedrichards/Skyloom/style.css")
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        for name in dict.fromkeys(
            [binding.command for binding in BINDINGS if binding.scope != "composer"]
            + ["about", "manage-feeds"]
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect(
                "activate",
                lambda _a, _p, command=name: (
                    self.window.interactions.command(command) if self.window else None
                ),
            )
            self.add_action(action)
            self.set_accels_for_action("app." + name, accelerators(name))

    def apply_appearance(self):
        mapping = {
            "system": Adw.ColorScheme.DEFAULT,
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
        }
        self.get_style_manager().set_color_scheme(
            mapping.get(self.settings.get_string("appearance"), Adw.ColorScheme.DEFAULT)
        )

    def back(self):
        if self.window:
            self.window.interactions.back()

    def shortcuts(self):
        shortcuts_dialog(self.window)

    def do_activate(self):
        if not self.window:
            self.window = Window(self)
        self.window.present()
        if self.smoke:
            from .smoke import Smoke

            self.smoke_runner = Smoke(self, self.smoke, self.smoke_scenario)
            self.smoke_runner.start()
            self.smoke = None
        if self.keyboard_test:
            from .keyboard_smoke import KeyboardSmoke

            self.keyboard_runner = KeyboardSmoke(self)
            self.keyboard_runner.start()
            self.keyboard_test = False

    def do_shutdown(self):
        if self.window:
            self.window.cancel_startup()
        if self.window and self.window.refresh_monitor:
            self.window.refresh_monitor.close()
        checkpoints = []
        if self.window:
            for view in self.window.feed_views.values():
                reading = view.reading
                if reading and (snapshot := reading.snapshot()):
                    checkpoints.append((reading.feed, *snapshot, reading.account))

        active_feed = (self.window.feed_id, self.service.account) if self.window else None

        async def cleanup():
            try:
                if active_feed:
                    await self.service.save_active_feed(*active_feed)
                for checkpoint in checkpoints:
                    await self.service.save_feed_state(*checkpoint)
            finally:
                await self.service.close()

        self.worker.close(cleanup())
        Adw.Application.do_shutdown(self)
