"""Deterministic in-process GUI interaction checks using invented data only."""

import os
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from gi.repository import Adw, GLib, Gtk

from .content import LabelledContent
from .conversation import Continuation, EarlierMessages, ThreadGap, ThreadPage
from .conversation_view import ConversationView
from .domain import CachedFeed, Notice, Page, Pager, Post
from .errors import UserError
from .refresh import Connection
from .service import Attachment
from .widgets import FeedView, PostRow, list_children

type SmokeStep = Callable[[], bool]


class Smoke:
    def __init__(self, app, output, scenario="full"):
        self.app, self.w = app, app.window
        self.output = Path(output).resolve()
        self.scenario = os.getenv("SKYLOOM_SMOKE_SCENARIO", scenario)
        self.failure = False
        self.steps: list[SmokeStep] = []
        self.attempts = 0

    def start(self):
        if not __debug__:
            raise RuntimeError("Run GUI smoke checks without Python optimization")
        self.output.mkdir(parents=True, exist_ok=True)
        # This demo checks native layout/controllers, not compositor activation.
        # Activity is a fixture input, like testing_auto below; physical input is separate.
        self.w.is_active = lambda: True
        self.original_animations = Gtk.Settings.get_default().get_property("gtk-enable-animations")
        Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
        if font := os.getenv("SKYLOOM_SMOKE_FONT"):
            Gtk.Settings.get_default().set_property("gtk-font-name", font)
            print(
                "SMOKE_FONT", Gtk.Settings.get_default().get_property("gtk-font-name"), flush=True
            )
        self.original_service_methods = {
            name: getattr(self.w.service, name)
            for name in (
                "feed",
                "author_feed",
                "search",
                "notifications",
                "thread",
                "cached_state",
                "cached",
                "profile",
                "sign_out",
            )
        }
        self.original_posts = list(self.w.service.posts)
        self.original_settings = {
            key: self.w.settings.get_value(key)
            for key in (
                "appearance",
                "load-images",
                "warn-labelled-content",
                "auto-refresh",
                "use-metered",
            )
        }
        self.steps = [
            self.home,
            self.navigation_hide_wide,
            self.navigation_hidden_wide,
            self.navigation_restored_wide,
            self.wide,
            self.navigation_open_narrow,
            self.navigation_opened_narrow,
            self.dark_narrow,
            self.thread,
            self.back,
            self.compose,
            self.rollback,
            self.composer_capture,
            self.save_draft,
            self.reopen_draft,
            self.publish,
            self.reply_draft,
            self.save_reply,
            self.restore_reply,
            self.verify_reply,
            self.profile,
            self.profile_expanded,
            self.profile_scrolled,
            self.profile_narrow,
            self.profile_top,
            self.profile_undo,
            self.profile_end,
            self.profile_return,
            self.profile_navigation,
            self.own_profile_card,
            self.own_profile_wide,
            self.own_profile_narrow,
            self.notifications,
            self.notifications_seen,
            self.notifications_marked,
            self.search,
            self.search_initial,
            self.search_initial_narrow,
            self.search_begin,
            self.search_loading,
            self.search_results,
            self.search_empty,
            self.search_failed,
            self.search_retried,
            self.search_cleared,
            self.overflow_open,
            self.preferences,
            self.preferences_capture,
            self.preferences_narrow,
            self.preferences_account,
            self.preferences_account_capture,
            self.about,
            self.about_capture,
            self.sign_out_preferences,
            self.sign_out_open,
            self.sign_out_cancel,
            self.sign_out_returned,
            self.sign_out_failure_confirm,
            self.sign_out_retry,
            self.media,
            self.media_description,
            self.media_scroll,
            self.close_media,
            self.labelled_content,
            self.labelled_visible,
            self.labelled_details,
            self.labelled_all_details,
            self.labelled_dark,
            self.labelled_narrow,
            self.labelled_narrow_details,
            self.labelled_preferences,
            self.labelled_warning,
            self.labelled_warning_narrow,
            self.labelled_revealed,
            self.labelled_profile,
            self.labelled_profile_revealed,
            self.post_tiles,
            self.post_tiles_narrow,
            self.quoted_tile,
            self.quoted_context,
            self.conversation_pages,
            self.conversation_retry,
            self.conversation_replies,
            self.conversation_earlier,
            self.ordered_feed,
            self.ordered_loaded,
            self.ordered_capture,
            self.ordered_narrow,
            self.ordered_refreshed,
            self.autoload_home,
            self.autoload_profile,
            self.autoload_search_posts,
            self.autoload_search_people,
            self.autoload_notifications,
            self.autoload_finish,
            self.refresh_setup,
            self.refresh_position,
            self.refresh_gates,
            self.refresh_ready,
            self.refresh_staged,
            self.refresh_shown,
            self.refresh_undone,
            self.refresh_failed,
            self.refresh_manual,
            self.refresh_cleanup,
            self.server_error,
            self.server_error_checked,
            self.cached_feed_checked,
            self.offline,
            self.offline_post,
            self.offline_draft,
            self.offline_saved,
            self.offline_drafts,
            self.offline_restored,
            self.welcome,
            self.finish,
        ]
        if self.scenario != "full":
            names = [step.__name__ for step in self.steps]
            ranges = {
                "navigation": ("navigation_hide_wide", "dark_narrow"),
                "profile": ("profile", "own_profile_narrow"),
                "search": ("notifications", "search_cleared"),
                "preferences": ("overflow_open", "sign_out_retry"),
                "labels": ("labelled_content", "labelled_profile_revealed"),
                "conversation": ("post_tiles", "ordered_refreshed"),
                "paging": ("autoload_home", "autoload_finish"),
                "refresh": ("refresh_setup", "refresh_cleanup"),
                "offline": ("server_error", "welcome"),
            }
            if self.scenario not in ranges:
                raise ValueError("Unknown smoke scenario: " + self.scenario)
            first, last = ranges[self.scenario]
            selected = self.steps[names.index(first) : names.index(last) + 1]
            if self.scenario == "profile":
                self.w.service.posts[0] = replace(
                    self.w.service.posts[0], text="A small test fixture"
                )
            if self.scenario == "preferences":
                selected.extend([self.appearance_matrix_start, self.appearance_matrix_capture])
            self.steps = [self.home, *selected, self.scenario_finish]
        GLib.timeout_add(700, self.tick)

    def tick(self):
        try:
            if not self.steps:
                return False
            step = self.steps[0]
            if step():
                self.steps.pop(0)
                self.attempts = 0
            else:
                self.attempts += 1
                if self.attempts > 20:
                    raise AssertionError("GUI step did not finish: " + step.__name__)
            return bool(self.steps)
        except Exception:  # noqa: BLE001 — fail the smoke run on any GUI assertion/callback error.
            import traceback

            self.failure = True
            self.cleanup_scenario()
            traceback.print_exc()
            self.app.quit()
            return False

    def cleanup_scenario(self):
        for name, method in self.original_service_methods.items():
            setattr(self.w.service, name, method)
        self.w.service.posts = self.original_posts
        self.w.service.offline = False
        for key, value in self.original_settings.items():
            self.w.settings.set_value(key, value)
        self.w.interactions.testing_auto = False
        Gtk.Settings.get_default().set_property("gtk-enable-animations", self.original_animations)

    def scenario_finish(self):
        if self.w.page_requests:
            return False
        self.cleanup_scenario()
        print("GUI_SMOKE_SCENARIO_PASS:", self.scenario, flush=True)
        self.app.quit()
        return True

    def appearance_matrix_start(self):
        self.appearance_cases = iter(((800, "light"), (480, "light"), (800, "dark"), (480, "dark")))
        self.appearance_current = None
        return True

    def appearance_matrix_capture(self):
        if self.appearance_current is None:
            case = next(self.appearance_cases, None)
            if case is None:
                return True
            self.appearance_current = case
            width, theme = case
            dialog = self.w.get_visible_dialog()
            if dialog:
                dialog.close()
            self.w.settings.set_string("appearance", theme)
            self.w.set_default_size(width, 820)
            self.w.preferences()
            return False
        width, theme = self.appearance_current
        dialog = self.w.get_visible_dialog()
        if self.w.get_width() != width or dialog is None:
            return False
        row = dialog.appearance
        popover = self.find_widget(row, Gtk.Popover)
        assert popover is not None
        if not popover.get_mapped():
            popover.popup()
            return False
        name = f"appearance-{width}-{theme}"
        if not self.capture(name, present=False):
            return False
        snapshot = Gtk.Snapshot.new()
        Gtk.WidgetPaintable.new(popover).snapshot(
            snapshot, popover.get_width(), popover.get_height()
        )
        node = snapshot.to_node()
        assert node is not None
        texture = self.w.get_renderer().render_texture(node, None)
        assert texture.save_to_png(str(self.output / (name + "-popover.png")))
        popover.popdown()
        dialog.close()
        self.appearance_current = None
        self.attempts = 0
        return False

    def capture(self, name, *, present=True):
        import re

        match = re.search(r"-(480|800|1280|1600)-", name)
        if match and self.w.get_width() != int(match[1]):
            self.w.set_default_size(int(match[1]), 820)
            self.w.queue_resize()
            if present:
                self.w.present()
            return False
        clock = self.w.get_frame_clock()
        frame = clock.get_frame_counter()
        if getattr(self, "capture_name", None) != name:
            self.capture_name = name
            self.capture_frame = frame
            if present:
                self.w.present()
            self.w.queue_draw()
            return False
        if frame <= self.capture_frame:
            self.w.queue_draw()
            return False
        paintable = Gtk.WidgetPaintable.new(self.w)
        snap = Gtk.Snapshot.new()
        paintable.snapshot(snap, self.w.get_width(), self.w.get_height())
        print(
            "CAPTURE",
            name,
            self.w.get_width(),
            self.w.get_height(),
            "split",
            self.w.split.get_width(),
            self.w.split.get_collapsed(),
            flush=True,
        )
        node = snap.to_node()
        if node is None:
            return False
        texture = self.w.get_renderer().render_texture(node, None)
        assert texture.save_to_png(str(self.output / (name + ".png")))
        return True

    def capture_popover(self, button, name):
        # Popovers have their own native surface and are absent from the window paintable.
        if not self.capture(name, present=False):
            return False
        content = button.get_popover()
        assert content.get_mapped()
        assert 0 < content.get_width() <= self.w.get_width()
        assert 0 < content.get_height() <= self.w.get_height()
        snap = Gtk.Snapshot.new()
        Gtk.WidgetPaintable.new(content).snapshot(snap, content.get_width(), content.get_height())
        node = snap.to_node()
        assert node is not None
        texture = self.w.get_renderer().render_texture(node, None)
        assert texture.save_to_png(str(self.output / (name + "-popover.png")))
        return True

    def home(self) -> bool:
        if not self.w.feed_views or self.w.feed_views["following"].model.get_n_items() != 6:
            return False
        self.w.set_default_size(1280, 820)
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        return True

    def wide(self) -> bool:
        if not self.capture("home-1280-light"):
            return False
        self.w.set_default_size(480, 820)
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        return True

    def navigation_hide_wide(self) -> bool:
        if self.w.get_width() != 1280:
            return False
        self.navigation_posts = tuple(self.w.pagers["following"].posts)
        self.navigation_width = self.w.feed_views["following"].scroll.get_width()
        assert self.w.split.get_show_sidebar()
        self.w.home_page.navigation_button.emit("clicked")
        return True

    def navigation_hidden_wide(self) -> bool:
        assert not self.w.split.get_show_sidebar()
        assert not self.w.split.get_sidebar().get_mapped()
        assert self.w.feed_views["following"].scroll.get_width() > self.navigation_width + 150
        assert tuple(self.w.pagers["following"].posts) == self.navigation_posts
        if getattr(self, "capture_name", None) != "navigation-hidden-1280-light":
            self.check_main_menu()
        if not self.capture("navigation-hidden-1280-light"):
            return False
        self.w.home_page.navigation_button.emit("clicked")
        return True

    def navigation_restored_wide(self) -> bool:
        assert self.w.split.get_show_sidebar()
        assert self.w.split.get_sidebar().get_mapped()
        assert self.w.home_page.navigation_button.get_active()
        assert tuple(self.w.pagers["following"].posts) == self.navigation_posts
        self.check_main_menu()
        return True

    def navigation_open_narrow(self) -> bool:
        assert self.w.split.get_collapsed()
        assert not self.w.split.get_show_sidebar()
        self.w.home_page.navigation_button.emit("clicked")
        return True

    def navigation_opened_narrow(self) -> bool:
        assert self.w.split.get_show_sidebar()
        assert self.w.split.get_sidebar().get_mapped()
        assert self.w.interactions.current_view() is None
        assert self.w.sidebar_navigation_button.get_visible()
        self.check_main_menu()
        self.w.sidebar_navigation_button.emit("clicked")
        assert not self.w.split.get_show_sidebar()
        self.w.feed_views["following"].interaction.focus()
        self.w.interactions.focus_pane()
        assert self.w.split.get_show_sidebar()
        self.w.interactions.focus_pane()
        assert not self.w.split.get_show_sidebar()
        return True

    def dark_narrow(self) -> bool:
        assert self.w.split.get_collapsed()
        if getattr(self, "capture_name", None) != "home-480-dark":
            self.check_main_menu()
        if not self.capture("home-480-dark"):
            return False
        self.w.set_default_size(800, 820)
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        adjustment = self.w.feed_views["following"].scroll.get_vadjustment()
        adjustment.set_value(100)
        self.scroll_before_thread = adjustment.get_value()
        self.w.feed_views["following"].list.emit("activate", 0)
        return True

    def thread(self) -> bool:
        page = self.w.nav.get_visible_page()
        if page.get_title() != "Conversation" or self.w.page_requests:
            return False
        if not self.capture("thread-800-light"):
            return False
        assert any(v.model.get_n_items() == 2 for v in self.w.views)
        return True

    def back(self) -> bool:
        assert self.w.nav.pop()
        assert (
            abs(
                self.w.feed_views["following"].scroll.get_vadjustment().get_value()
                - self.scroll_before_thread
            )
            < 1
        )
        p = self.w.service.posts[0]
        self.w.mutate(p, "like")
        assert self.w.feed_views["following"].model.get_item(0).post.like_uri
        return True

    def compose(self) -> bool:
        if self.w.mutations:
            return False
        self.before_failure = self.w.service.posts[0]
        self.w.service.offline = True
        self.w.mutate(self.before_failure, "repost")
        self.w.mutate(self.before_failure, "repost")  # Duplicate click must be ignored.
        assert len(self.w.mutations) == 1
        return True

    def rollback(self) -> bool:
        if self.w.mutations:
            return False
        restored = self.w.feed_views["following"].model.get_item(0).post
        assert restored == self.before_failure
        self.w.service.offline = False
        self.w.refresh_monitor.changed()
        self.w.compose()
        return True

    def composer_capture(self) -> bool:
        c = self.w.composer
        if not c.ready:
            return False
        c.buffer.set_text("A small test of a thoughtful native client. 🌤️")
        # Use prepared PNGs, exercising the same validation and rendering path as the file portal.
        from gi.repository import GdkPixbuf

        for i in range(2):
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(self.w.images.fixture_dir / "demo-landscape.svg"), 300, 160, True
            )
            path = self.output / f"fixture-{i}.png"
            pix.savev(str(path), "png", [], [])
            c.attachments.append(Attachment(str(path), f"Invented rolling hills, image {i + 1}."))
        c.render_attachments()
        c.changed()
        assert c.send_button.get_sensitive()
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        return True

    def save_draft(self) -> bool:
        if not hasattr(self, "draft_saved"):
            self.draft_saved = False
            c = self.w.composer
            self.w.worker.submit(
                self.w.service.draft_save(c.key, c.snapshot()),
                lambda _: setattr(self, "draft_saved", True),
            )
            return False
        if not self.draft_saved:
            return False
        self.w.composer.force_close()
        return True

    def reopen_draft(self) -> bool:
        if self.w.composer:
            return False
        self.w.compose(draft_key="new")
        return True

    def publish(self) -> bool:
        if not self.w.composer.ready:
            return False
        assert self.w.composer.text().startswith("A small test")
        assert len(self.w.composer.attachments) == 2

        def pictures(widget):
            for child in list_children(widget):
                if isinstance(child, Gtk.Picture):
                    yield child
                yield from pictures(child)

        previews = list(pictures(self.w.composer.get_child()))
        if not previews or any(p.get_paintable() is None for p in previews):
            return False
        if not self.capture("composer-800-dark"):
            return False
        self.w.composer.send_button.emit("clicked")
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        return True

    def reply_draft(self) -> bool:
        if self.w.composer:
            return False
        self.reply_target = self.w.service.posts[1]
        self.w.compose(reply=self.reply_target)
        return True

    def save_reply(self) -> bool:
        c = self.w.composer
        if not c.ready:
            return False
        if not hasattr(self, "reply_saved"):
            c.buffer.set_text("A reply kept with its original conversation.")
            value = c.snapshot()
            assert value["reply"]["uri"] == self.reply_target.uri
            self.reply_key = c.key
            self.reply_saved = False
            self.w.worker.submit(
                self.w.service.draft_save(c.key, value),
                lambda _: setattr(self, "reply_saved", True),
            )
            return False
        if not self.reply_saved:
            return False
        c.force_close()
        return True

    def restore_reply(self) -> bool:
        if self.w.composer:
            return False
        self.w.compose(draft_key=self.reply_key)
        return True

    def verify_reply(self) -> bool:
        c = self.w.composer
        if not c.ready:
            return False
        assert c.reply.uri == self.reply_target.uri
        assert c.text() == "A reply kept with its original conversation."
        c.force_close()
        return True

    def profile(self) -> bool:
        if self.w.composer or self.w.page_requests:
            return False
        assert self.w.service.posts[0].text.startswith("A small test")
        self.profile_service = self.w.service.profile
        self.profile_feed = self.w.service.author_feed
        self.profile_bio = (
            "\n".join(
                f"Invented profile line {i + 1:02d} — the complete biography stays readable."
                for i in range(12)
            )
            + "\nEND OF INVENTED BIOGRAPHY"
        )

        async def complete_profile(actor):
            return replace(await self.profile_service(actor), bio=self.profile_bio)

        async def complete_feed(actor, cursor=None, feed_filter="posts_no_replies"):
            page = await self.profile_feed(actor, cursor, feed_filter)
            return Page(
                tuple(
                    replace(
                        page.posts[i % len(page.posts)],
                        uri=f"at://did:example:profile/app.bsky.feed.post/{i}",
                        images=(),
                        quote=None,
                        external=None,
                    )
                    for i in range(30)
                )
            )

        self.w.service.profile = complete_profile
        self.w.service.author_feed = complete_feed
        self.w.profile(self.w.service.posts[1].author.did)
        return True

    def profile_expanded(self) -> bool:
        if self.w.page_requests:
            return False
        page = self.w.nav.get_visible_page()
        if not os.getenv("SKYLOOM_SMOKE_FONT"):
            valid_browser, browser = page.profile_browser.compute_bounds(page.profile_controls)
            valid_filter, filters = page.profile_filter.compute_bounds(page.profile_controls)
            assert valid_browser and valid_filter
            assert (
                abs(
                    browser.origin.y
                    + browser.size.height / 2
                    - filters.origin.y
                    - filters.size.height / 2
                )
                <= 2
            )
        self.profile_view, self.profile_title = page.content_view, page.profile_title
        assert self.profile_view.scroll.get_child() == self.profile_view.list
        assert self.profile_view.content_header.is_ancestor(self.profile_view.list)
        assert self.profile_view.header_visible()
        assert self.profile_title.stack.get_visible_child_name() == "expanded"
        assert self.profile_view.scroll.get_vadjustment().get_value() <= 1
        assert self.find_text_widget(page, self.profile_bio).get_lines() == -1
        if not self.capture("profile-800-light"):
            return False
        adjustment = self.profile_view.scroll.get_vadjustment()
        adjustment.set_value(self.profile_title.threshold + 80)
        return True

    def find_text_widget(self, widget, text):
        if isinstance(widget, Gtk.Label) and widget.get_text() == text:
            return widget
        for child in list_children(widget):
            if found := self.find_text_widget(child, text):
                return found
        return None

    def profile_scrolled(self) -> bool:
        assert self.profile_title.stack.get_visible_child_name() == "compact"
        if not self.capture("profile-compact-800-light"):
            return False
        self.w.set_default_size(480, 820)
        return True

    def profile_narrow(self) -> bool:
        if not self.capture("profile-compact-480-light"):
            return False
        self.profile_offset = self.profile_view.scroll.get_vadjustment().get_value()
        assert self.w.interactions.top()
        return True

    def profile_top(self) -> bool:
        assert self.profile_view.scroll.get_vadjustment().get_value() <= 1
        assert self.profile_view.header_visible()
        assert self.profile_title.stack.get_visible_child_name() == "expanded"
        assert self.w.interactions.undo()
        return True

    def profile_undo(self) -> bool:
        assert abs(self.profile_view.scroll.get_vadjustment().get_value() - self.profile_offset) < 3
        assert self.profile_title.stack.get_visible_child_name() == "compact"
        adjustment = self.profile_view.scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        return True

    def profile_end(self) -> bool:
        assert not self.profile_view.header_visible()
        assert self.profile_title.stack.get_visible_child_name() == "compact"
        self.w.interactions.top()
        return True

    def profile_return(self) -> bool:
        assert self.profile_view.header_visible()
        assert self.profile_title.stack.get_visible_child_name() == "expanded"
        self.w.service.profile = self.profile_service
        self.w.service.author_feed = self.profile_feed
        return True

    def profile_navigation(self) -> bool:
        page = self.w.nav.get_visible_page()
        assert self.w.split.get_collapsed()
        page.navigation_button.emit("clicked")
        assert self.w.split.get_show_sidebar()
        assert self.w.interactions.back()
        assert not self.w.split.get_show_sidebar()
        assert self.w.nav.get_visible_page() is page
        return True

    def own_profile_card(self) -> bool:
        self.w.go_home()
        self.own_card_verified = False
        self.w.set_default_size(800, 820)
        assert self.w.destination_buttons["profile"] is self.w.profile_button
        assert len(self.w.destination_buttons) == 5
        self.w.profile_button.emit("clicked")
        return True

    def own_profile_wide(self) -> bool:
        if self.w.get_width() != 800 or self.w.page_requests:
            return False
        page = self.w.nav.get_visible_page()
        assert page.destination == "profile"
        if not self.own_card_verified:
            if not self.w.split.get_show_sidebar():
                self.w.navigation.reveal_sidebar()
                return False
            if not self.w.profile_button.get_mapped():
                return False
            sidebar = self.w.split.get_sidebar()
            valid, card = self.w.profile_button.compute_bounds(sidebar)
            assert valid and card.origin.y > sidebar.get_height() * 0.65
            assert card.origin.y + card.size.height <= sidebar.get_height()
            browser = page.profile_browser.compute_bounds(page.profile_controls)[1]
            filters = page.profile_filter.compute_bounds(page.profile_controls)[1]
            assert (
                abs(
                    browser.origin.y
                    + browser.size.height / 2
                    - filters.origin.y
                    - filters.size.height / 2
                )
                <= 2
            )
            depth = self.w.nav.get_navigation_stack().get_n_items()
            self.w.profile_button.emit("clicked")
            assert self.w.nav.get_visible_page() is page
            assert self.w.nav.get_navigation_stack().get_n_items() == depth
            self.own_card_verified = True
        if not self.capture("own-profile-800-light"):
            return False
        self.w.set_default_size(480, 820)
        return True

    def own_profile_narrow(self) -> bool:
        if self.w.split.get_collapsed() and self.w.split.get_show_sidebar():
            self.w.navigation.reveal_content()
            return False
        if not self.capture("own-profile-480-light"):
            return False
        page = self.w.nav.get_visible_page()
        browser = page.profile_browser.compute_bounds(page.profile_controls)[1]
        filters = page.profile_filter.compute_bounds(page.profile_controls)[1]
        assert (
            abs(
                browser.origin.y
                + browser.size.height / 2
                - filters.origin.y
                - filters.size.height / 2
            )
            <= 2
        )
        page.content_view.list.grab_focus()
        self.w.interactions.focus_pane()
        assert self.w.split.get_show_sidebar()
        assert self.w.get_focus() is self.w.profile_button
        self.w.interactions.focus_pane()
        assert not self.w.split.get_show_sidebar()
        self.w.go_home()
        return True

    def notifications(self) -> bool:
        if self.w.page_requests:
            return False
        self.w.notifications()
        return True

    def search(self) -> bool:
        if self.w.page_requests:
            return False
        if not self.capture("notifications-800-light"):
            return False
        self.w.search()
        return True

    def check_search_state(self):
        view = self.w.nav.get_visible_page().content_view
        assert view.scroll.get_height() > self.w.get_height() * 0.8
        assert view.status_box.get_mapped()
        adjustment = view.scroll.get_vadjustment()
        assert abs(adjustment.get_upper() - adjustment.get_page_size()) <= 2
        for widget in (
            view.status_icon,
            view.status_title,
            view.status_description,
            view.status_action,
        ):
            if widget.get_visible():
                valid, bounds = widget.compute_bounds(view.scroll)
                assert valid and bounds.origin.y >= 0
                assert bounds.origin.y + bounds.size.height <= view.scroll.get_height()
        return view

    def search_initial(self) -> bool:
        self.check_search_state()
        return self.capture("search-initial-800-light")

    def search_initial_narrow(self) -> bool:
        if not self.capture("search-initial-480-light"):
            return False
        self.check_search_state()
        return True

    def search_begin(self) -> bool:
        import asyncio

        self.search_service = self.w.service.search

        async def slow(query, people=False, cursor=None):
            await asyncio.sleep(3)
            return await self.search_service(query, people, cursor)

        self.w.service.search = slow
        entry = self.w.nav.get_visible_page().focus_widget
        entry.set_text("software")
        entry.emit("activate")
        return True

    def search_loading(self) -> bool:
        view = self.check_search_state()
        assert view.spinner.get_mapped()
        assert view.status_title.get_text() == "Searching…"
        return self.capture("search-loading-480-light")

    def search_results(self) -> bool:
        if self.w.page_requests:
            return False
        self.w.service.search = self.search_service
        view = self.w.nav.get_visible_page().content_view
        assert view.model.get_n_items() > 0
        assert not view.status_box.get_visible()
        assert view.content_header.get_height() < 240
        if not self.capture("search-800-light"):
            return False
        view.entry.set_text("no-matches-skyloom-fixture")
        view.entry.emit("activate")
        return True

    def search_empty(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.check_search_state()
        assert view.status_title.get_text() == "No results found"
        if not self.capture("search-empty-800-light"):
            return False

        async def failure(*_args):
            raise UserError("Invented search failure")

        self.w.service.search = failure
        view.entry.set_text("software")
        view.entry.emit("activate")
        return True

    def search_failed(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.check_search_state()
        assert view.status_description.get_text() == "Invented search failure"
        assert view.status_action.get_mapped()
        if not self.capture("search-error-800-light"):
            return False
        self.w.service.search = self.search_service
        assert not view.paging.closed and not view.paging.busy
        assert view.entry.get_text() == "software"
        view.status_action.emit("clicked")
        assert view.paging.busy
        assert self.w.nav.get_visible_page() in self.w.page_requests
        return True

    def search_retried(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.w.nav.get_visible_page().content_view
        assert view.model.get_n_items() > 0, "Retry failed: " + view.paging.error
        # Clearing an in-flight search must also restore the full-height prompt.
        import asyncio

        async def slow(*_args):
            await asyncio.sleep(3)
            return Page(())

        self.w.service.search = slow
        view.entry.set_text("cancel this invented query")
        view.entry.emit("activate")
        view.entry.set_text("")
        assert not self.w.page_requests
        self.w.service.search = self.search_service
        return True

    def search_cleared(self) -> bool:
        view = self.check_search_state()
        assert view.status_title.get_text() == "Search Bluesky"
        assert view.model.get_n_items() == 0
        view.entry.set_text("software")
        view.entry.emit("activate")
        return True

    def notifications_seen(self) -> bool:
        if self.w.page_requests:
            return False
        self.notice_view = self.w.interactions.current_view()
        assert any(
            not self.notice_view.model.get_item(i).post.read
            for i in range(self.notice_view.model.get_n_items())
        )
        self.notice_mark = next(
            control
            for control in self.w.online_controls
            if control.get_tooltip_text() == "Mark all notifications as seen"
        )
        self.w.service.offline = True
        self.w.refresh_monitor.changed()
        assert not self.notice_mark.get_sensitive()
        self.w.service.offline = False
        self.w.refresh_monitor.changed()
        assert self.notice_mark.get_sensitive()
        self.notice_mark.emit("clicked")
        assert not self.notice_mark.get_sensitive()
        return True

    def notifications_marked(self) -> bool:
        if not self.notice_mark.get_sensitive():
            return False
        assert all(
            self.notice_view.model.get_item(i).post.read
            for i in range(self.notice_view.model.get_n_items())
        )
        return True

    def overflow_open(self) -> bool:
        if self.w.page_requests:
            return False
        self.check_main_menu()
        assert self.w.interactions.command("main-menu")
        return True

    def check_main_menu(self):
        page_menu = self.w.nav.get_visible_page().menu_button
        menus = (self.w.sidebar_menu, page_menu)
        assert sum(menu.get_mapped() for menu in menus) == 1
        self.overflow_menu = next(menu for menu in menus if menu.get_mapped())
        assert self.w.interactions.command("main-menu")
        assert self.overflow_menu.get_popover().get_visible()
        self.overflow_menu.popdown()

    def preferences(self) -> bool:
        popover = self.overflow_menu.get_popover()
        assert popover.get_visible()
        assert self.find_text_widget(popover, "Leave demo") is None
        assert self.find_text_widget(popover, "Sign out") is None
        assert popover.activate_action("app.preferences", None)
        dialog = self.w.get_visible_dialog()
        assert isinstance(dialog, Adw.PreferencesDialog)
        for key, title in [
            ("load-images", "Load images"),
            ("warn-labelled-content", "Warn about labelled content"),
            ("auto-refresh", "Refresh automatically"),
            ("use-metered", "Use metered connections"),
        ]:
            row = self.find_text_widget(dialog, title).get_ancestor(Adw.SwitchRow)
            previous = self.w.settings.get_boolean(key)
            row.set_active(not previous)
            assert self.w.settings.get_boolean(key) is not previous
            row.set_active(previous)
        appearance = self.find_text_widget(dialog, "Appearance").get_ancestor(Adw.ComboRow)
        previous = appearance.get_selected()
        appearance.set_selected(1)
        assert self.w.settings.get_string("appearance") == "light"
        appearance.set_selected(previous)
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        assert self.find_text_widget(dialog, "Power saver") is None
        assert self.find_text_widget(dialog, "Authentication")
        assert dialog.sign_out_row.get_title() == "Leave demo"
        assert self.app.lookup_action("sign-out") is None
        return True

    def preferences_capture(self) -> bool:
        return self.capture("preferences-800-light")

    def preferences_narrow(self) -> bool:
        return self.capture("preferences-480-light")

    def preferences_account(self) -> bool:
        self.w.get_visible_dialog().sign_out_row.grab_focus()
        return True

    def preferences_account_capture(self) -> bool:
        dialog = self.w.get_visible_dialog()
        row = dialog.sign_out_row
        valid, bounds = row.compute_bounds(dialog)
        assert valid and bounds.origin.y >= 0
        assert bounds.origin.y + bounds.size.height <= dialog.get_height()
        return self.capture("preferences-account-480-light")
        return True

    def about(self) -> bool:
        self.w.get_visible_dialog().close()
        self.check_main_menu()
        assert self.w.interactions.command("main-menu")
        assert self.overflow_menu.get_popover().activate_action("app.about", None)
        assert self.w.get_visible_dialog().get_application_name() == "Skyloom"
        assert self.w.get_visible_dialog().get_developer_name() == "Nick Richards"
        assert self.w.get_visible_dialog().get_developers() == ["Nick Richards"]
        return True

    def about_capture(self) -> bool:
        return self.capture("about-800-light")

    def sign_out_preferences(self) -> bool:
        self.w.get_visible_dialog().close()
        self.w.preferences()
        self.account_preferences = self.w.get_visible_dialog()
        self.account_preferences.sign_out_row.grab_focus()
        return True

    def sign_out_open(self) -> bool:
        self.account_preferences.sign_out_row.emit("activated")
        return True

    def sign_out_cancel(self) -> bool:
        alert = self.w.get_visible_dialog()
        assert isinstance(alert, Adw.AlertDialog)
        assert alert.get_heading() == "Leave demo?"
        cancel = self.find_text_widget(alert, "Cancel").get_ancestor(Gtk.Button)
        cancel.emit("clicked")
        assert self.w.service.account is not None
        return True

    def sign_out_returned(self) -> bool:
        assert self.w.get_visible_dialog() is self.account_preferences
        assert self.account_preferences.sign_out_row.get_sensitive()
        assert self.account_preferences.get_focus() is self.account_preferences.sign_out_row
        self.sign_out_method = self.w.service.sign_out

        async def failed():
            raise UserError("Invented sign-out failure")

        self.w.service.sign_out = failed
        self.account_preferences.sign_out_row.emit("activated")
        return True

    def sign_out_failure_confirm(self) -> bool:
        alert = self.w.get_visible_dialog()
        confirm = self.find_text_widget(alert, "Leave demo").get_ancestor(Gtk.Button)
        confirm.emit("clicked")
        assert not self.account_preferences.sign_out_row.get_sensitive()
        assert not self.account_preferences.get_can_close()
        return True

    def sign_out_retry(self) -> bool:
        if not self.account_preferences.sign_out_row.get_sensitive():
            return False
        assert self.w.get_visible_dialog() is self.account_preferences
        assert self.account_preferences.get_can_close()
        assert self.w.service.account is not None
        if self.find_text_widget(self.account_preferences, "Invented sign-out failure") is None:
            return False
        self.w.service.sign_out = self.sign_out_method
        self.account_preferences.close()
        return True

    def media(self) -> bool:
        self.w.view_media(
            replace(next(p for p in self.w.service.posts if p.images).images[0], alt="")
        )
        assert self.w.get_visible_dialog().get_title() == "Image"

        def texts(widget):
            if isinstance(widget, Gtk.Label):
                yield widget.get_text()
            for child in list_children(widget):
                yield from texts(child)

        assert "Copy description" not in list(texts(self.w.get_visible_dialog()))
        return True

    def media_description(self) -> bool:
        self.w.get_visible_dialog().close()
        self.media_alt = "\n".join(
            f"Invented description paragraph {i + 1}: the entire image description remains readable."
            for i in range(30)
        )
        self.w.view_media(
            replace(next(p for p in self.w.service.posts if p.images).images[0], alt=self.media_alt)
        )
        return True

    def media_scroll(self) -> bool:
        dialog = self.w.get_visible_dialog()
        scroll = self.find_widget(dialog, Gtk.ScrolledWindow)
        assert scroll is not None
        description = self.find_text_widget(dialog, self.media_alt)
        assert description is not None and description.get_lines() == -1
        adjustment = scroll.get_vadjustment()
        assert adjustment.get_upper() > adjustment.get_page_size()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        return True

    def close_media(self) -> bool:
        self.w.get_visible_dialog().close()
        return True

    def labelled_content(self) -> bool:
        self.w.go_home()
        _page, toolbar, _header = self.w.new_page("Labelled content")
        self.label_post = replace(
            next(p for p in self.w.service.posts if p.images),
            labels=("sexual", "graphic-media", "fixture-label", "nudity"),
        )
        self.label_view = FeedView(self.w)
        self.label_view.set_posts([self.label_post])
        toolbar.set_content(self.label_view)
        self.w.set_default_size(800, 820)
        return True

    def active_gate(self, key):
        def find(widget):
            if isinstance(widget, LabelledContent) and widget.key == key:
                return widget
            for child in list_children(widget):
                found = find(child)
                if found:
                    return found
            return None

        return find(self.w.nav.get_visible_page())

    def labelled_visible(self) -> bool:
        gate = self.active_gate(("post", self.label_post.uri))
        if gate is None:
            return False
        assert not self.w.settings.get_boolean("warn-labelled-content")
        assert gate.get_revealed()
        assert gate.revealer.get_child()
        if not self.capture("labelled-visible-800-light"):
            return False
        gate.chips[0].popup()
        return True

    def labelled_details(self) -> bool:
        gate = self.active_gate(("post", self.label_post.uri))
        assert gate.chips[0].get_popover().get_mapped()
        if not self.capture_popover(gate.chips[0], "labelled-details-800-light"):
            return False
        gate.chips[0].popdown()
        gate.chips[-1].popup()
        return True

    def labelled_all_details(self) -> bool:
        gate = self.active_gate(("post", self.label_post.uri))
        assert gate.chips[-1].get_popover().get_mapped()
        if not self.capture_popover(gate.chips[-1], "labelled-all-details-800-light"):
            return False
        gate.chips[-1].popdown()
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        return True

    def labelled_dark(self) -> bool:
        if not self.capture("labelled-visible-800-dark"):
            return False
        self.w.set_default_size(480, 820)
        return True

    def labelled_narrow(self) -> bool:
        if not self.capture("labelled-visible-480-dark"):
            return False
        gate = self.active_gate(("post", self.label_post.uri))
        gate.chips[-1].popup()
        return True

    def labelled_narrow_details(self) -> bool:
        gate = self.active_gate(("post", self.label_post.uri))
        if not self.capture_popover(gate.chips[-1], "labelled-all-details-480-dark"):
            return False

        def descendants(widget):
            yield widget
            for child in list_children(widget):
                yield from descendants(child)

        preferences = next(
            widget
            for widget in descendants(gate.chips[-1].get_popover())
            if isinstance(widget, Gtk.Button) and widget.get_label() == "Label preferences…"
        )
        preferences.emit("clicked")
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        self.w.set_default_size(800, 820)
        return True

    def labelled_preferences(self) -> bool:
        def switch(widget):
            if (
                isinstance(widget, Adw.SwitchRow)
                and widget.get_title() == "Warn about labelled content"
            ):
                return widget
            for child in list_children(widget):
                found = switch(child)
                if found:
                    return found
            return None

        control = switch(self.w.get_visible_dialog())
        assert control
        control.set_active(True)
        assert self.w.settings.get_boolean("warn-labelled-content")
        self.w.get_visible_dialog().close()
        return True

    def labelled_warning(self) -> bool:
        gate = self.active_gate(("post", self.label_post.uri))
        assert not gate.get_revealed()
        if not self.capture("labelled-hidden-800-light"):
            return False
        self.w.set_default_size(480, 820)
        return True

    def labelled_warning_narrow(self) -> bool:
        if not self.capture("labelled-hidden-480-light"):
            return False
        gate = self.active_gate(("post", self.label_post.uri))
        gate.show_button.emit("clicked")
        assert gate.get_revealed()
        self.w.set_default_size(800, 820)
        return True

    def labelled_revealed(self) -> bool:
        if not self.capture("labelled-revealed-800-light"):
            return False
        self.original_profile_post = self.w.service.posts[0]
        self.w.service.posts[0] = replace(
            self.original_profile_post,
            author=replace(self.original_profile_post.author, labels=("adult",)),
        )
        self.w.profile(self.w.service.posts[0].author.did)
        return True

    def labelled_profile(self) -> bool:
        if self.w.page_requests:
            return False
        gate = self.active_gate(("profile", self.w.service.posts[0].author.did))
        if gate is None:
            return False
        assert not gate.get_revealed()
        gate.show_button.emit("clicked")
        assert gate.revealer.get_child()
        return True

    def labelled_profile_revealed(self) -> bool:
        if not self.capture("labelled-profile-800-light"):
            return False
        self.w.service.posts[0] = self.original_profile_post
        self.w.settings.set_boolean("warn-labelled-content", False)
        self.w.go_home()
        return True

    def post_tiles(self) -> bool:
        _page, toolbar, _header = self.w.new_page("Post tiles")
        self.tile_post = next(post for post in self.w.service.posts if post.quote)
        self.tile_view = FeedView(self.w)
        self.tile_view.set_posts([self.tile_post])
        toolbar.set_content(self.tile_view)
        self.w.set_default_size(800, 820)
        return True

    def post_tiles_narrow(self) -> bool:
        if not self.capture("post-tiles-800-light"):
            return False
        self.w.set_default_size(480, 820)
        return True

    def quoted_tile(self) -> bool:
        if not self.capture("post-tiles-480-light"):
            return False
        row = self.find_widget(self.tile_view, PostRow)
        quote = row.quoted_rows[0]
        assert quote.get_margin_start() == 0 and quote.body.get_margin_start() == 16
        assert quote.alive
        assert quote.activate()
        return True

    def quoted_context(self) -> bool:
        if self.w.page_requests:
            return False
        assert self.w.nav.get_visible_page().get_title() == "Conversation"
        current = next(view for view in self.w.views if view.get_mapped())
        assert current.model.get_item(0).post.uri == self.tile_post.quote.uri
        page = self.w.nav.get_visible_page()
        stack_size = self.w.nav.get_navigation_stack().get_n_items()
        adjustment = current.scroll.get_vadjustment()
        position = adjustment.get_value()
        for _ in range(3):
            self.w.thread(self.tile_post.quote.uri)
        assert self.w.nav.get_visible_page() is page
        assert self.w.nav.get_navigation_stack().get_n_items() == stack_size
        assert current.scroll.get_vadjustment().get_value() == position
        assert self.w.nav.pop()
        self.w.go_home()
        self.w.set_default_size(800, 820)
        return True

    def conversation_pages(self) -> bool:
        self.original_thread = self.w.service.thread
        base = replace(self.w.service.posts[0], images=(), quote=None, external=None, labels=())

        def post(name, context="Earlier in this conversation"):
            return replace(
                base,
                uri="at://did:example:conversation/app.bsky.feed.post/" + name,
                text="Invented conversation message: " + name,
                context=context,
            )

        self.conversation_anchor = post("selected", "Selected post")
        self.conversation_child = post("child", "Reply")
        self.conversation_grandchild = post("grandchild", "Reply to a reply")
        self.conversation_last = post("last", "Reply to a reply")
        self.conversation_old = post("oldest")
        previous = self.conversation_old
        self.conversation_parents = []
        for i in range(20):
            parent = replace(post("parent-" + str(i)), parent=(previous.uri, previous.cid))
            self.conversation_parents.append(parent)
            previous = parent
        self.conversation_anchor = replace(
            self.conversation_anchor, parent=(previous.uri, previous.cid)
        )
        self.conversation_child = replace(
            self.conversation_child,
            parent=(self.conversation_anchor.uri, self.conversation_anchor.cid),
        )
        self.conversation_grandchild = replace(
            self.conversation_grandchild,
            parent=(self.conversation_child.uri, self.conversation_child.cid),
        )
        self.conversation_last = replace(
            self.conversation_last,
            parent=(self.conversation_grandchild.uri, self.conversation_grandchild.cid),
        )
        self.conversation_calls = []
        self.reply_attempts = 0

        async def thread(uri, *, earlier=False, replies_only=False):
            self.conversation_calls.append((uri, earlier, replies_only))
            if earlier:
                assert uri == self.conversation_old.uri
                return ThreadPage((self.conversation_old,))
            if uri == self.conversation_child.uri:
                self.reply_attempts += 1
                if self.reply_attempts == 1:
                    raise UserError("Invented temporary conversation failure. Try again.")
                return ThreadPage(
                    (self.conversation_child, self.conversation_grandchild),
                    branches=(self.conversation_grandchild.uri,),
                )
            if uri == self.conversation_grandchild.uri:
                return ThreadPage((self.conversation_grandchild, self.conversation_last))
            assert uri == self.conversation_anchor.uri
            parents = tuple(self.conversation_parents)
            return ThreadPage(
                (*parents, self.conversation_anchor, self.conversation_child),
                earlier=self.conversation_old.uri,
                branches=(self.conversation_child.uri,),
            )

        self.w.service.thread = thread
        self.w.thread(self.conversation_anchor.uri)
        return True

    def conversation_retry(self) -> bool:
        if self.w.page_requests:
            return False
        self.conversation_view = next(view for view in self.w.views if view.get_mapped())
        view = self.conversation_view
        if not view.paging.error:
            adjustment = view.scroll.get_vadjustment()
            adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))
            return False
        assert "Invented temporary" in view.paging.error
        assert any(
            view.model.get_item(i).post.uri == self.conversation_anchor.uri
            for i in range(view.model.get_n_items())
        )
        assert view.paging.request()
        return True

    def conversation_replies(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.conversation_view
        posts = [view.model.get_item(i).post for i in range(view.model.get_n_items())]
        if not any(post.uri == self.conversation_last.uri for post in posts):
            adjustment = view.scroll.get_vadjustment()
            adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))
            return False
        assert self.reply_attempts == 2
        assert not any(call[1] for call in self.conversation_calls), self.conversation_calls
        assert not view.paging.error
        if not self.capture("conversation-expanded-800-light"):
            return False
        view.scroll.get_vadjustment().set_value(0)
        return True

    def conversation_earlier(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.conversation_view
        posts = [view.model.get_item(i).post for i in range(view.model.get_n_items())]
        if any(isinstance(post, EarlierMessages) for post in posts):
            return False
        assert posts[0].uri == self.conversation_old.uri
        assert len(posts) == 25
        assert len({post.uri for post in posts}) == len(posts)
        assert isinstance(posts[-1], Post)
        assert self.conversation_calls[-1] == (self.conversation_old.uri, True, False), (
            self.conversation_calls
        )
        self.w.service.thread = self.original_thread
        self.w.go_home()
        return True

    def ordered_feed(self) -> bool:
        self.w.go_home()
        self.ordered_original = self.w.service.thread
        base = self.w.service.posts[0]

        def post(name, minute, parent=None, author=None):
            return replace(
                base,
                uri="at://did:example:ordered/app.bsky.feed.post/" + name,
                author=author
                or replace(
                    base.author,
                    did="did:example:thread-origin",
                    name="Mira Demo",
                    handle="mira.demo.invalid",
                ),
                text={
                    "root": "A conversation reads from its beginning, with each exchange kept together.",
                    "first": "This is the earlier reply branch.",
                    "grandchild": "A later reply stays beside its parent, even when another branch began earlier.",
                    "selected": "My comment on someone else’s thread opens here, with its context.",
                    "later": "This sibling branch started later.",
                }[name],
                created=f"2026-10-27T10:{minute:02d}:00Z",
                parent=(parent.uri, parent.cid) if parent else None,
                root=None,
                images=(),
                quote=None,
                labels=(),
                external=None,
                context="",
            )

        root = post("root", 0)
        first = post("first", 1, root)
        selected = post(
            "selected",
            2,
            root,
            replace(
                base.author,
                did="did:example:reply-reader",
                name="Leo Demo",
                handle="leo.demo.invalid",
            ),
        )
        later = post("later", 3, root)
        grandchild = post("grandchild", 5, first)
        self.ordered_posts = (root, first, grandchild, selected, later)
        self.ordered_calls = []

        async def thread(uri, **_kwargs):
            self.ordered_calls.append(uri)
            if uri == first.uri:
                return ThreadPage((first, grandchild))
            assert uri == selected.uri
            return ThreadPage(
                (root, later, selected, first),
                branches=(first.uri,),
                gaps=(ThreadGap("at://did:example:ordered/app.bsky.feed.post/gap", root.uri),),
            )

        self.w.service.thread = thread
        _page, toolbar, _header = self.w.new_page("Feed reply fixture")
        self.ordered_feed_view = FeedView(self.w)
        self.ordered_feed_view.set_posts([selected])
        toolbar.set_content(self.ordered_feed_view)
        self.ordered_feed_page = self.w.nav.get_visible_page()
        self.ordered_feed_view.list.emit("activate", 0)
        assert self.w.nav.get_visible_page().conversation_uri == selected.uri
        self.w.set_default_size(800, 820)
        return True

    def ordered_loaded(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.w.nav.get_visible_page().content_view
        assert isinstance(view, ConversationView)
        grandchild = self.ordered_posts[2]
        if not any(post.uri == grandchild.uri for post in view.state.posts):
            loader = next(row for row in view.rows if isinstance(row._value, Continuation))
            loader.control.emit("clicked")
            return False
        assert [p.uri for p in view.state.posts] == [p.uri for p in self.ordered_posts]
        assert view.state.anchor == self.ordered_posts[3].uri
        assert len(self.ordered_calls) == 2
        view.focus_post(view.state.anchor)
        assert view.relative("parent")
        assert view.interaction.selected().uri == self.ordered_posts[0].uri
        assert view.relative("child")
        assert view.interaction.selected().uri == self.ordered_posts[1].uri
        view.interaction.top()
        return True

    def ordered_capture(self) -> bool:
        if not self.capture("conversation-ordered-800-light"):
            return False
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        self.w.set_default_size(480, 820)
        return True

    def ordered_narrow(self) -> bool:
        if not self.capture("conversation-ordered-480-dark"):
            return False
        self.ordered_view = self.w.nav.get_visible_page().content_view
        self.ordered_view.refresh()
        return True

    def ordered_refreshed(self) -> bool:
        if self.w.page_requests:
            return False
        assert [p.uri for p in self.ordered_view.state.posts] == [p.uri for p in self.ordered_posts]
        assert len(self.ordered_calls) == 3
        page = self.w.nav.get_visible_page()
        depth = self.w.nav.get_navigation_stack().get_n_items()
        self.w.thread(self.ordered_view.state.anchor)
        assert self.w.nav.get_visible_page() is page
        assert self.w.nav.get_navigation_stack().get_n_items() == depth
        assert self.w.nav.pop()
        assert self.w.nav.get_visible_page() is self.ordered_feed_page
        self.w.service.thread = self.ordered_original
        self.app.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        self.w.go_home()
        return True

    def autoload_home(self) -> bool:
        self.w.go_home()
        # This is a two-page paging fixture, independent of earlier reading history.
        # Manual refresh now deliberately retains disjoint cached posts.
        view = self.w.feed_view()
        self.w.pagers["following"] = Pager()
        view.clear_update()
        view.set_posts([], reset=True)
        view.paging.attempted.clear()
        view.feed.gap_states.clear()
        view.feed.unseen.clear()
        self.original_methods = {
            name: getattr(self.w.service, name)
            for name in ("feed", "author_feed", "search", "notifications")
        }
        self.page_calls = {
            name: [] for name in ("home", "profile", "posts", "people", "notifications")
        }
        self.paging_base = self.w.service.posts[1]

        def post_page(name, cursor):
            self.page_calls[name].append(cursor)
            post = replace(
                self.paging_base,
                uri=self.paging_base.uri + "/" + name + ("2" if cursor else "1"),
                images=(),
                quote=None,
                external=None,
            )
            return Page((post,), None if cursor else "page-two")

        async def feed(feed="following", cursor=None):
            return post_page("home", cursor)

        async def author_feed(actor, cursor=None, feed_filter="posts_no_replies"):
            return post_page("profile", cursor)

        async def search(query, people=False, cursor=None):
            if not people:
                return post_page("posts", cursor)
            self.page_calls["people"].append(cursor)
            author = replace(
                self.paging_base.author,
                did="did:example:pager" + ("2" if cursor else "1"),
                handle="pager.demo.invalid",
            )
            return (author,), None if cursor else "page-two"

        async def notices(cursor=None):
            self.page_calls["notifications"].append(cursor)
            uri = "at://did:example:pager/like/" + ("2" if cursor else "1")
            notice = Notice(
                self.paging_base.author,
                "like",
                uri,
                self.paging_base.uri,
                False,
                self.paging_base.created,
            )
            return (notice,), None if cursor else "page-two", self.paging_base.created

        self.w.service.feed, self.w.service.author_feed = feed, author_feed
        self.w.service.search, self.w.service.notifications = search, notices
        self.w.refresh()
        return True

    def paged(self, name):
        if len(self.page_calls[name]) != 2 or self.w.page_requests:
            for view in self.w.views:
                if view.get_mapped():
                    adjustment = view.scroll.get_vadjustment()
                    adjustment.set_value(
                        max(0, adjustment.get_upper() - adjustment.get_page_size())
                    )
            return False
        assert self.page_calls[name] == [None, "page-two"]
        return True

    def autoload_profile(self) -> bool:
        if not self.paged("home"):
            return False
        view = self.w.feed_views["following"]
        assert view.model.get_n_items() == 2
        assert view.scroll.get_child() == view.list
        assert view.scroll.get_width() == view.get_width()
        self.w.profile(self.paging_base.author.did)
        return True

    def autoload_search_posts(self) -> bool:
        if not self.paged("profile"):
            return False
        self.w.search()
        self.search_entry = self.w.nav.get_visible_page().focus_widget
        self.search_entry.set_text("pager")
        self.search_entry.emit("activate")
        return True

    def find_widget(self, widget, kind):
        if isinstance(widget, kind):
            return widget
        for child in list_children(widget):
            result = self.find_widget(child, kind)
            if result:
                return result
        return None

    def autoload_search_people(self) -> bool:
        if not self.paged("posts"):
            return False
        mode = self.w.nav.get_visible_page().search_mode
        mode.set_selected(1)
        return True

    def autoload_notifications(self) -> bool:
        if not self.paged("people"):
            return False
        self.w.notifications()
        return True

    def autoload_finish(self) -> bool:
        if not self.paged("notifications"):
            return False
        for name, method in self.original_methods.items():
            setattr(self.w.service, name, method)
        self.w.go_home()
        return True

    def refresh_setup(self) -> bool:
        if self.w.page_requests:
            return False
        # Establish the capture geometry before taking any reading anchor.
        # capture() otherwise resizes the window after refresh_staged first
        # checks the anchor, invalidating pixel offsets through text reflow.
        self.w.set_default_size(800, 820)
        self.w.refresh_monitor.close()
        self.refresh_original = self.w.service.posts
        base = self.refresh_original[0]
        self.w.service.posts = [
            replace(
                base,
                uri=f"at://did:example:refresh/app.bsky.feed.post/{i}",
                text=f"Invented refresh post {i}",
                images=(),
                quote=None,
                external=None,
                labels=(),
            )
            for i in range(40)
        ]
        self.w.refresh()
        self.refresh_view = self.w.feed_views["following"]
        return True

    def refresh_position(self) -> bool:
        if self.w.page_requests or self.w.get_width() != 800 or self.w.get_height() != 820:
            return False
        self.refresh_view.interaction.move("last")
        return True

    def refresh_gates(self) -> bool:
        view = self.refresh_view
        self.refresh_before = tuple(self.w.pagers["following"].posts)
        self.refresh_objects = {
            view.model.get_item(i).post.uri: view.model.get_item(i)
            for i in range(view.model.get_n_items())
        }
        self.refresh_cursor = self.w.pagers["following"].cursor
        self.refresh_policy = self.w.interactions.policy("feed:following")
        self.refresh_policy.last_finished = time.time() - 301
        self.w.interactions.testing_auto = True
        for connection in (
            Connection(metered=True),
            Connection(power_saver=True),
            Connection(internet=False),
            Connection(available=False, internet=False),
        ):
            self.w.connection_changed(connection)
            assert not self.w.interactions.check_auto(time.time(), active=True)
            assert self.refresh_policy.last_finished < time.time() - 300
        self.w.connection_changed(Connection())
        # Clear the manual-refresh Undo and synthetic cost-policy notifications.
        # This scenario checks the actual Show control, not native toast queue timing.
        self.w.overlay.dismiss_all()
        view.after_position(settle_layout=True)
        return True

    def refresh_ready(self) -> bool:
        view = self.refresh_view
        if view.position_tick is not None or view.check_pending or self.w.page_requests:
            return False
        self.refresh_place = view.interaction.capture()
        self.refresh_offset = view.scroll.get_vadjustment().get_value()
        self.w.service.posts.insert(
            0,
            replace(self.w.service.posts[0], uri="at://did:example:refresh/app.bsky.feed.post/new"),
        )
        assert self.w.interactions.check_auto(time.time(), active=True)
        assert not self.w.interactions.check_auto(time.time(), active=True)
        return True

    def assert_reading_place(self, view, expected):
        place = view.interaction.capture()
        assert place.key == expected.key
        delta = place.offset - expected.offset
        adjustment = view.scroll.get_vadjustment()
        # A reflow below the anchor can shorten the list. Exact pixel restoration
        # then reaches the native adjustment boundary; never invent overscroll.
        value = adjustment.get_value()
        minimum = adjustment.get_lower()
        maximum = max(minimum, adjustment.get_upper() - adjustment.get_page_size())
        assert (
            abs(delta) < 3
            or (delta >= 0 and abs(value - maximum) < 1)
            or (delta <= 0 and abs(value - minimum) < 1)
        ), (
            f"Reading offset changed by {delta:.2f}px (value={value:.2f}, range={minimum:.2f}..{maximum:.2f})"
        )

    def refresh_staged(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.refresh_view
        assert tuple(self.w.pagers["following"].posts[1:]) == self.refresh_before
        assert bool(view.pending_update)
        assert view.update_notice.title == "New posts available"
        assert self.app.lookup_action("show-new").get_enabled()
        notice = self.find_text_widget(self.w.overlay, "New posts available")
        if notice is None or not notice.get_mapped():
            return False
        if view.position_tick is not None:
            return False
        self.assert_reading_place(view, self.refresh_place)
        if not self.capture("new-posts-800-light"):
            return False
        view.update_notice.toast.emit("button-clicked")
        return True

    def refresh_shown(self) -> bool:
        view = self.refresh_view
        if (
            "feed:following" in self.w.page_requests
            or view.arrival_tick is not None
            or view.position_tick is not None
        ):
            return False
        assert view.scroll.get_vadjustment().get_value() <= 1
        assert self.w.pagers["following"].cursor == self.refresh_cursor
        for i in range(view.model.get_n_items()):
            item = view.model.get_item(i)
            if item.post.uri in self.refresh_objects:
                assert item is self.refresh_objects[item.post.uri]
        assert self.w.pagers["following"].posts[0].uri.endswith("/new")
        assert not bool(self.refresh_view.pending_update)
        assert not self.app.lookup_action("show-new").get_enabled()
        if not self.capture("new-posts-shown-800-light"):
            return False
        assert self.w.interactions.undo()
        return True

    def refresh_undone(self) -> bool:
        assert tuple(self.w.pagers["following"].posts[1:]) == self.refresh_before
        if self.refresh_view.position_tick is not None:
            return False
        assert not bool(self.refresh_view.pending_update)
        self.assert_reading_place(self.refresh_view, self.refresh_place)
        self.refresh_feed = self.w.service.feed

        async def failure(*_args):
            raise UserError("Invented automatic refresh failure")

        self.w.service.feed = failure
        self.refresh_policy.last_finished = time.time() - 301
        assert self.w.interactions.check_auto(time.time(), active=True)
        self.refresh_toast = self.w.last_toast
        return True

    def refresh_failed(self) -> bool:
        if self.w.page_requests:
            return False
        assert self.refresh_policy.failures == 1
        assert not self.w.interactions.check_auto(time.time(), active=True)
        assert tuple(self.w.pagers["following"].posts[1:]) == self.refresh_before
        assert self.w.last_toast is self.refresh_toast
        assert not self.refresh_view.paging.error
        self.w.service.feed = self.refresh_feed
        self.w.connection_changed(Connection(metered=True))
        self.w.refresh()
        return True

    def refresh_manual(self) -> bool:
        if self.w.page_requests:
            return False
        assert self.refresh_policy.failures == 0
        assert self.w.pagers["following"].posts[0].uri.endswith("/new")
        assert not bool(self.refresh_view.pending_update)
        self.w.service.posts = self.refresh_original
        self.w.connection_changed(Connection())
        self.w.interactions.testing_auto = False
        self.w.refresh()
        return True

    def refresh_cleanup(self) -> bool:
        return not self.w.page_requests

    def server_error(self) -> bool:
        self.error_feed = self.w.service.feed

        async def fail(*_args):
            raise UserError("Invented server failure")

        self.w.service.feed = fail
        self.w.refresh()
        return True

    def server_error_checked(self) -> bool:
        if self.w.page_requests:
            return False
        assert not self.w.read_only
        assert self.w.feed_views["following"].model.get_n_items()
        self.w.service.feed = self.error_feed
        self.cache_original = self.w.service.cached_state

        async def cached(_feed):
            return CachedFeed(Pager([self.w.service.posts[0]]))

        async def unexpected(*_args):
            raise AssertionError("Switching to a cached feed fetched the network")

        self.w.service.cached_state = cached
        self.w.service.feed = unexpected
        self.w.set_feeds([("following", "Following"), ("cache-fixture", "Cached fixture")])
        self.w.feed_picker.set_selected(1)
        return True

    def cached_feed_checked(self) -> bool:
        if self.w.page_requests:
            return False
        assert self.w.feed_id == "cache-fixture"
        assert self.w.feed_views["cache-fixture"].model.get_n_items() == 1
        assert (
            self.w.feed_views["cache-fixture"].model.get_item(0).post.uri
            == self.w.service.posts[0].uri
        )
        self.w.service.cached_state = self.cache_original
        self.w.service.feed = self.error_feed
        self.w.feed_picker.set_selected(0)
        return True

    def offline(self) -> bool:
        if self.w.page_requests:
            return False
        if not self.capture("cached-feed-800-light"):
            return False
        self.w.go_home()
        self.w.service.offline = True
        self.w.connection_changed(Connection(available=False, internet=False))
        self.w.refresh()
        self.w.set_default_size(480, 820)
        return True

    def offline_post(self) -> bool:
        if self.w.page_requests:
            return False
        self.offline_target = self.w.feed_views["following"].model.get_item(0).post
        self.offline_thread_method = self.w.service.thread

        async def unexpected(*_args, **_kwargs):
            raise AssertionError("Opening a saved post offline attempted a network request")

        self.w.service.thread = unexpected
        self.w.thread(self.offline_target.uri)
        return True

    def offline_draft(self) -> bool:
        if self.w.page_requests:
            return False
        view = self.w.interactions.current_view()
        assert view.model.get_n_items() == 1
        saved = view.model.get_item(0).post
        assert saved.text == self.offline_target.text
        assert isinstance(view, ConversationView)
        assert saved.context == "Opened here"
        assert view.state.anchor == self.offline_target.uri
        assert view.paging.message == "Offline. Showing saved content."
        self.w.service.thread = self.offline_thread_method
        self.w.compose(reply=saved)
        return True

    def offline_saved(self) -> bool:
        c = self.w.composer
        if not c.ready:
            return False
        if not hasattr(self, "offline_saved_flag"):
            self.offline_saved_flag = False
            c.buffer.set_text("An offline reply safely kept as a draft.")
            assert not c.send_button.get_sensitive()
            self.w.worker.submit(
                self.w.service.draft_save(c.key, c.snapshot()),
                lambda _: setattr(self, "offline_saved_flag", True),
            )
            return False
        if not self.offline_saved_flag:
            return False
        c.force_close()
        self.w.drafts()
        return True

    def offline_drafts(self) -> bool:
        if self.w.page_requests or self.w.composer:
            return False
        page = self.w.nav.get_visible_page()
        rows = self.find_widget(page.get_child(), Gtk.ListBox)
        assert rows is not None
        target = next(
            row
            for row in list_children(rows)
            if isinstance(row, Adw.ActionRow) and row.get_title().startswith("An offline reply")
        )
        page.navigation_button.grab_focus()
        self.w.interactions.focus_pane()
        assert self.w.split.get_show_sidebar()
        self.w.interactions.focus_pane()
        assert not self.w.split.get_show_sidebar()
        target.emit("activated")
        return True

    def offline_restored(self) -> bool:
        c = self.w.composer
        if c is None or not c.ready:
            return False
        assert c.text() == "An offline reply safely kept as a draft."
        assert c.snapshot()["reply"]["uri"] == self.offline_target.uri
        assert not c.send_button.get_sensitive()
        c.force_close()
        self.w.go_home()
        return True

    def welcome(self) -> bool:
        if self.w.page_requests or not self.w.read_only:
            return False
        if not self.capture("offline-480-light"):
            return False
        self.w.stack.set_visible_child_name("welcome")
        self.w.set_default_size(800, 820)
        return True

    def finish(self) -> bool:
        if self.w.page_requests or not self.w.read_only:
            return False
        if not self.capture("welcome-800-light"):
            return False
        assert self.w.compose_button.get_sensitive()
        print(
            "GUI_SMOKE_PASS: feed, reaction/rollback/debounce, thread/back, draft restore, composer/images/publish, unified profile/complete bio/compact header/top/Undo/deep return, notifications/read and live connectivity controls, unified search, preferences settings/wide/narrow/authentication/sign-out confirmation/cancel/focus/failure retry, about, scrolling image descriptions, offline cached post/reply draft/save/reopen/no publish/F6, cached feed switch, server errors preserve online state, responsive light/dark, labelled posts/media/profile/reveal preferences, tile/quoted activation, ordered connected conversations/cross-author feed activation/parent-child/refresh retains depth/Back/context/earlier/deeper/retry, autoload home/profile/posts/people/notifications, automatic refresh gates/immediate insertion/Go to top/position Undo/backoff/manual metered retry"
        )
        self.cleanup_scenario()
        self.app.quit()
        return True
