"""Real native sidebar visibility/allocation, independent of account data."""

import asyncio
import unittest
from types import SimpleNamespace

from gtk_support import DISPLAY, settle

if DISPLAY:
    from gi.repository import Adw, GLib, Gtk


@unittest.skipUnless(DISPLAY, "GNOME GTK display required")
class NavigationTests(unittest.TestCase):
    def pump(self):
        self.assertTrue(settle(self.window), "Native navigation window did not finish rendering")

    def setUp(self):
        from skyloom.navigation import Navigation

        settings = Gtk.Settings.get_default()
        animations = settings.get_property("gtk-enable-animations")
        settings.set_property("gtk-enable-animations", False)
        self.addCleanup(settings.set_property, "gtk-enable-animations", animations)
        self.navigation = Navigation()
        self.split = self.navigation.view
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.append(Gtk.Button(label="Invented destination"))
        self.content = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.header = header
        self.toggle = self.navigation.create_toggle()
        header.pack_start(self.toggle)
        self.content.add_top_bar(header)
        self.content.set_content(Gtk.Label(label="Invented content stays mounted"))
        self.split.set_sidebar(self.sidebar)
        self.navigation.set_content(self.content)
        self.window = Adw.Window(
            default_width=800, default_height=500, content=self.navigation.root
        )
        self.addCleanup(self.window.destroy)
        self.window.present()
        self.pump()

    def test_wide_button_hides_and_restores_sidebar_and_reallocates_content(self):
        before = self.content.get_width()
        self.assertTrue(self.split.get_show_sidebar())
        self.assertEqual(self.toggle.get_tooltip_text(), "Hide navigation")
        self.toggle.emit("clicked")
        self.pump()
        self.assertFalse(self.split.get_show_sidebar())
        self.assertFalse(self.sidebar.get_mapped())
        self.assertGreater(self.content.get_width(), before + 150)
        self.assertEqual(self.toggle.get_tooltip_text(), "Show navigation")
        self.assertIs(self.split.get_content().child, self.content)
        self.toggle.emit("clicked")
        self.pump()
        self.assertTrue(self.sidebar.get_mapped())
        self.assertTrue(self.toggle.get_active())
        self.assertAlmostEqual(self.content.get_width(), before, delta=2)

    def test_narrow_button_uses_overlay_and_destination_closes_it(self):
        self.window.set_default_size(480, 500)
        self.split.set_collapsed(True)
        self.pump()
        self.assertFalse(self.split.get_show_sidebar())
        width = self.content.get_width()
        self.toggle.emit("clicked")
        self.pump()
        self.assertTrue(self.sidebar.get_mapped())
        self.assertTrue(self.toggle.get_active())
        self.assertAlmostEqual(self.content.get_width(), width, delta=2)
        self.navigation.reveal_content()
        self.pump()
        self.assertFalse(self.split.get_show_sidebar())
        self.assertFalse(self.toggle.get_active())

    def animation_settings(self, enabled=True, reduced=None):
        settings = Gtk.Settings.get_default()
        for name in ("gtk-enable-animations", "gtk-interface-reduced-motion"):
            self.addCleanup(settings.set_property, name, settings.get_property(name))
        settings.set_property("gtk-enable-animations", enabled)
        settings.set_property(
            "gtk-interface-reduced-motion",
            Gtk.ReducedMotion.NO_PREFERENCE if reduced is None else reduced,
        )

    def test_breakpoint_resize_slides_sidebar_out_over_live_content(self):
        self.animation_settings()
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        narrow.add_setter(self.split, "collapsed", True)
        self.window.add_breakpoint(narrow)
        self.sidebar.get_first_child().grab_focus()
        samples = []
        content_samples = []

        def frame(*_args):
            valid, bounds = self.sidebar.compute_bounds(self.split)
            slide = self.navigation.sidebar_slide
            if slide.image is not None:
                valid_content, content_bounds = self.content.compute_bounds(self.split)
                if valid_content:
                    content_samples.append((slide.offset, content_bounds.origin.x))
            if valid and self.sidebar.get_mapped():
                valid_content, content_bounds = self.content.compute_bounds(self.split)
                samples.append((bounds.origin.x, bounds.size.width))

            return True

        tick = self.window.add_tick_callback(frame)
        try:
            self.window.set_default_size(480, 500)
            self.assertTrue(
                settle(
                    self.window,
                    900,
                    lambda: (
                        not self.sidebar.get_mapped()
                        and self.navigation.sidebar_slide.image is None
                    ),
                )
            )
        finally:
            self.window.remove_tick_callback(tick)
        self.assertTrue(self.split.get_collapsed())
        self.assertFalse(self.split.get_show_sidebar())
        self.assertTrue(
            any(sidebar_x < -2 and 2 < content_x < 200 for sidebar_x, content_x in content_samples),
            "Content and sidebar must move together during collapse",
        )
        self.assertTrue(
            any(-160 < x < -60 and content_x > 2 for x, content_x in content_samples),
            "The rendered sidebar must remain visible through the shared transition",
        )
        self.assertTrue(
            any(-width + 2 < x < -2 for x, width in samples),
            "Resizing must render an intermediate sidebar position before unmapping it",
        )
        self.assertIs(self.split.get_content().child, self.content)
        self.assertAlmostEqual(self.content.get_width(), self.split.get_width(), delta=2)
        self.assertEqual(self.toggle.get_tooltip_text(), "Show navigation")
        focus = self.window.get_focus()
        self.assertFalse(focus and (focus is self.sidebar or focus.is_ancestor(self.sidebar)))

    def test_collapse_animation_can_reverse_without_losing_sidebar_or_content(self):
        self.animation_settings()
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        narrow.add_setter(self.split, "collapsed", True)
        self.window.add_breakpoint(narrow)
        self.window.set_default_size(480, 500)

        def reverse():
            self.window.set_default_size(800, 500)
            return False

        GLib.timeout_add(40, reverse)
        self.assertTrue(settle(self.window, 700))
        self.assertFalse(self.split.get_collapsed())
        self.assertTrue(self.split.get_show_sidebar())
        self.assertTrue(self.sidebar.get_mapped())
        self.assertIs(self.split.get_content().child, self.content)
        self.assertTrue(self.toggle.get_active())
        self.assertIsNone(self.navigation.visibility_tick)
        self.assertIsNone(self.navigation.sidebar_slide.image)

    def test_collapse_skips_animation_when_motion_is_disabled(self):
        for enabled, reduced in (
            (False, Gtk.ReducedMotion.NO_PREFERENCE),
            (True, Gtk.ReducedMotion.REDUCE),
        ):
            with self.subTest(enabled=enabled, reduced=reduced):
                self.animation_settings(enabled, reduced)
                self.split.set_collapsed(True)
                self.assertFalse(self.sidebar.get_mapped())
                self.assertIsNone(self.navigation.sidebar_slide.image)
                self.assertFalse(self.toggle.get_active())
                self.split.set_collapsed(False)
                self.assertTrue(self.sidebar.get_mapped())
                self.assertTrue(self.toggle.get_active())

    def test_all_page_toggles_follow_native_visibility_changes(self):
        other = self.navigation.create_toggle(overlay_only=True)
        self.assertFalse(other.get_visible())
        self.split.set_show_sidebar(False)
        self.assertFalse(self.toggle.get_active())
        self.assertFalse(other.get_active())
        other.emit("clicked")
        self.assertTrue(self.toggle.get_active())
        self.assertTrue(self.split.get_show_sidebar())
        self.split.set_collapsed(True)
        self.assertTrue(other.get_visible())
        self.assertFalse(other.get_active())
        self.split.set_collapsed(False)
        self.assertFalse(other.get_visible())
        self.assertTrue(other.get_active())

    def test_destinations_preserve_wide_hidden_preference_and_panes_can_reopen(self):
        self.split.set_show_sidebar(False)
        self.navigation.reveal_content()
        self.assertFalse(self.split.get_show_sidebar())
        self.navigation.reveal_sidebar()
        self.assertTrue(self.split.get_show_sidebar())
        self.navigation.reveal_content()
        self.assertTrue(self.split.get_show_sidebar())

    def menus(self):
        sidebar = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            popover=Gtk.Popover(child=Gtk.Label(label="Sidebar menu")),
        )
        content = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            popover=Gtk.Popover(child=Gtk.Label(label="Content menu")),
        )
        self.sidebar.append(sidebar)
        self.header.pack_end(content)
        self.navigation.bind_menu(sidebar, sidebar=True)
        self.navigation.bind_menu(content)
        self.pump()
        return sidebar, content

    def test_only_one_overflow_menu_survives_hide_show_and_resizing(self):
        sidebar, content = self.menus()
        for collapsed, shown in [
            (False, True),
            (False, False),
            (False, True),
            (True, False),
            (True, True),
            (False, True),
        ]:
            with self.subTest(collapsed=collapsed, shown=shown):
                self.split.set_collapsed(collapsed)
                self.split.set_show_sidebar(shown)
                self.pump()
                self.assertEqual(sidebar.get_mapped(), shown)
                self.assertEqual(content.get_mapped(), not shown)
                self.assertEqual(sum(menu.get_mapped() for menu in (sidebar, content)), 1)
        later = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.navigation.bind_menu(later)
        self.assertFalse(later.get_visible(), "New content pages must also hide their menu")

    def test_f10_targets_the_visible_menu_and_hidden_popovers_close(self):
        from skyloom.interactions import Interactions

        sidebar, content = self.menus()
        router = Interactions.__new__(Interactions)
        router.window = SimpleNamespace(
            service=SimpleNamespace(account=object()),
            split=self.split,
            sidebar_menu=sidebar,
            nav=SimpleNamespace(get_visible_page=lambda: SimpleNamespace(menu_button=content)),
        )
        router.context = lambda: "chrome"
        for collapsed in (False, True):
            self.split.set_collapsed(collapsed)
            for shown in (True, False, True):
                with self.subTest(collapsed=collapsed, shown=shown):
                    self.split.set_show_sidebar(shown)
                    self.pump()
                    active, hidden = (sidebar, content) if shown else (content, sidebar)
                    self.assertFalse(hidden.get_popover().get_visible())
                    self.assertTrue(router.command("main-menu"))
                    self.assertTrue(active.get_popover().get_visible())
            sidebar.popdown()

    def test_repeated_conversation_activation_preserves_page_requests_and_back_stack(self):
        from skyloom.window import Window

        nav = Adw.NavigationView()
        home = Adw.NavigationPage.new(Gtk.Box(), "Home fixture")
        nav.add(home)
        self.content.set_content(nav)
        requests, cancelled = [], []

        async def cached_post(uri):
            return None

        def submit(coro, *_args):
            requests.append(coro)
            coro.close()
            return SimpleNamespace(cancel=lambda: cancelled.append(True))

        fixture = SimpleNamespace(
            nav=nav,
            interactions=SimpleNamespace(current_view=lambda: None),
            navigation=self.navigation,
            views=[],
            page_requests={},
            generation=0,
            read_only=False,
            service=SimpleNamespace(cached_post=cached_post),
            worker=SimpleNamespace(submit=submit),
            add_menu=lambda *_args: None,
        )
        fixture.new_page = lambda title: Window.new_page(fixture, title)
        nav.connect("popped", lambda view, page: Window.page_popped(fixture, view, page))
        first_uri, other_uri = "at://invented/post/one", "at://invented/post/two"
        try:
            Window.thread(fixture, first_uri)
            first = nav.get_visible_page()
            pending = fixture.page_requests[first]
            # Repeat before the first cache/network result, as with rapid clicks or held Enter.
            for _ in range(3):
                Window.thread(fixture, first_uri)
            self.assertIs(nav.get_visible_page(), first)
            self.assertIs(fixture.page_requests[first], pending)
            self.assertEqual(len(requests), 1)
            self.assertEqual(len(fixture.views), 1)
            self.assertEqual(nav.get_navigation_stack().get_n_items(), 2)
            Window.thread(fixture, other_uri)
            second = nav.get_visible_page()
            Window.thread(fixture, other_uri)
            self.assertIs(nav.get_visible_page(), second)
            self.assertEqual(len(requests), 2)
            self.assertEqual(nav.get_navigation_stack().get_n_items(), 3)
            self.assertTrue(nav.pop())
            self.assertIs(nav.get_visible_page(), first)
            Window.thread(fixture, first_uri)
            self.assertEqual(len(requests), 2)
            self.assertEqual(nav.get_navigation_stack().get_n_items(), 2)
            self.assertTrue(nav.pop())
            self.assertIs(nav.get_visible_page(), home)
            Window.thread(fixture, first_uri)
            self.assertIsNot(nav.get_visible_page(), first)
            self.assertEqual(len(requests), 3)
            self.assertEqual(nav.get_navigation_stack().get_n_items(), 2)
        finally:
            for view in fixture.views:
                view.close()
            for request in fixture.page_requests.values():
                request.cancel()

    def test_feed_metadata_retains_selection_without_reloading(self):
        from skyloom.window import Window

        options = [("following", "Following"), ("pinned", "Pinned")]
        picker = Gtk.DropDown.new_from_strings([item[1] for item in options])
        picker.set_selected(1)
        events, saved = [], []

        async def save(feed, account):
            saved.append((feed, account))

        fixture = SimpleNamespace(
            feed_views={},
            worker=SimpleNamespace(submit=lambda task, **_: asyncio.run(task)),
            service=SimpleNamespace(account="invented-account", save_active_feed=save),
            toast=lambda _message: None,
            feed_options=options,
            feed_picker=picker,
            feed_id="pinned",
            go_home=lambda: events.append("home"),
            refresh=lambda **_: events.append("reload"),
        )
        picker.connect("notify::selected", lambda *_: Window.feed_changed(fixture))
        updated = [("following", "Following"), ("another", "Another"), ("pinned", "Renamed")]
        Window.set_feeds(fixture, updated)
        self.assertEqual(picker.get_selected(), 2)
        self.assertEqual(fixture.feed_id, "pinned")
        self.assertFalse(events)
        model = picker.get_model()
        Window.set_feeds(fixture, updated)
        self.assertIs(picker.get_model(), model)
        self.assertFalse(events)
        Window.set_feeds(fixture, [("following", "Following")])
        self.assertEqual(fixture.feed_id, "following")
        self.assertEqual(events, ["home", "reload"])
        self.assertEqual(saved, [("following", "invented-account")])
