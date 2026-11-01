"""Real X11 input in a uniquely titled, demo-only regression window."""

import asyncio
import os
import subprocess
import sys
import traceback
from dataclasses import replace
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, Gtk


class KeyboardSmoke:
    def __init__(self, app):
        self.app, self.window = app, app.window
        self.failure = False
        self.waiting = False
        self.quiet = 0
        self.attempts = 0
        self.input_events = 0
        self.down_seen = False
        self.native_held = set()
        tracker = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        tracker.connect("key-pressed", self.observe_input)
        self.window.add_controller(tracker)
        self.title = f"Skyloom Keyboard Regression {os.getpid()}"
        self.driver = Path(os.environ["SKYLOOM_KEYBOARD_DRIVER"]).resolve(strict=True)
        self.steps = [
            lambda: self.send("Return", mode="release"),
            self.setup,
            self.header_down,
            self.first_selected,
            self.second_selected,
            self.page_selected,
            self.last_selected,
            self.held_opened,
            self.back,
            self.back_restored,
            self.top,
            self.undo_top,
            self.pane,
            self.pane_return,
            self.search,
            self.search_type,
            self.search_preserved,
            self.search_back,
            self.help,
            self.help_closed,
            self.menu,
            self.menu_closed,
            self.reply,
            self.reply_type,
            self.editor_undo,
            self.editor_preserved,
            self.close_editor,
            self.notifications,
            self.notice_select,
            self.notice_not_seen,
            self.narrow,
            self.narrow_pane,
            self.narrow_return,
            self.finish,
        ]

    def start(self):
        if not self.app.demo or not __debug__:
            raise RuntimeError("Keyboard regression requires unoptimized --demo")
        self.window.set_title(self.title)
        self.window.set_default_size(1280, 820)
        Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
        self.window.refresh_monitor.close()
        GLib.timeout_add(150, self.tick)

    def fail(self, text):
        self.failure = True
        print("KEYBOARD_INPUT_FAILURE:", text, flush=True)
        self.stop()

    def stop(self):
        held = tuple(self.native_held)
        self.native_held.clear()
        if not held:
            self.app.quit()
            return
        self.waiting = True

        async def release():
            for key in held:
                await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, str(self.driver), self.title, key, "release"],
                    check=False,
                    capture_output=True,
                    timeout=5,
                )

        self.window.worker.submit(
            release(), lambda _value: self.app.quit(), lambda _error: self.app.quit()
        )

    def send(self, key, *modifiers, mode="key", wait=2):
        self.waiting = True
        if mode == "press":
            self.native_held.add(key)

        async def deliver():
            # Fixed interpreter and explicitly selected local test driver; no shell or real account.
            await asyncio.to_thread(
                subprocess.run,
                [sys.executable, str(self.driver), self.title, key, mode, *modifiers],
                check=True,
                capture_output=True,
                timeout=5,
            )

        def delivered(_value):
            if mode == "release":
                self.native_held.discard(key)
            self.waiting, self.quiet = False, wait

        self.window.worker.submit(deliver(), delivered, self.fail)
        return True

    def tick(self):
        if self.waiting:
            return True
        if self.quiet:
            self.quiet -= 1
            return True
        try:
            if not self.steps:
                return False
            if self.steps[0]():
                self.steps.pop(0)
                self.attempts = 0
            else:
                self.attempts += 1
                if self.attempts > 50:
                    raise AssertionError(
                        "Native input step did not complete: " + self.steps[0].__name__
                    )
            return bool(self.steps)
        except Exception:  # noqa: BLE001 — fail the isolated fixture run on every GUI/input error.
            self.failure = True
            traceback.print_exc()
            self.stop()
            return False

    def check(self, condition, message):
        if not condition:
            raise AssertionError(message)

    def observe_input(self, _keys, key, _code, _modifiers):
        # Counts only; this isolated --demo harness never records text or account input.
        self.input_events += 1
        if key == Gdk.KEY_Down:
            self.down_seen = True
            self.down_context = self.window.interactions.context()
        return False

    def setup(self):
        if self.window.page_requests:
            return False
        original = self.window.service.posts
        self.window.go_home()
        base = original[0]
        self.window.service.posts = [
            replace(
                base,
                uri=original[i].uri
                if i < len(original)
                else f"at://did:example:keyboard/app.bsky.feed.post/{i}",
                text=f"Invented keyboard post {i}",
                images=(),
                quote=None,
                external=None,
                labels=(),
            )
            for i in range(40)
        ]
        self.window.refresh()
        self.view = self.window.feed_views["following"]
        return self.send("none", mode="focus")

    def header_down(self):
        if self.window.page_requests or not self.window.is_active():
            return False
        self.window.compose_button.grab_focus()
        self.header_before = self.view.store.get_selected()
        return self.send("Down")

    def first_selected(self):
        self.check(
            self.view.store.get_selected() == 0,
            f"Down from header did not select/focus the first post: before={self.header_before}, after={self.view.store.get_selected()}, delivered={self.down_seen}, context={getattr(self, 'down_context', 'none')}, events={self.input_events}",
        )
        self.check(
            self.window.nav.get_visible_page() == self.window.home_page,
            f"Movement changed page: {self.window.nav.get_visible_page().get_title()}; expected {self.window.home_page.get_title()}; stack={self.window.nav.get_navigation_stack().get_n_items()}",
        )
        return self.send("j")

    def second_selected(self):
        self.check(self.view.store.get_selected() == 1, "J did not select the next post")
        return self.send("Page_Down")

    def page_selected(self):
        self.check(self.view.scroll.get_vadjustment().get_value() > 0, "Page Down did not scroll")
        return self.send("End")

    def last_selected(self):
        self.check(self.view.store.get_selected() == 39, "End selected a footer or wrong row")
        self.before_open = self.view.scroll.get_vadjustment().get_value()
        return self.send("Return", mode="press", wait=8)

    def held_opened(self):
        if self.window.page_requests:
            return False
        self.check(
            self.window.nav.get_visible_page().get_title() == "Conversation",
            "Enter did not open the selected post",
        )
        self.check(
            self.window.nav.get_navigation_stack().get_n_items() == 2,
            "Held Enter opened more than one page",
        )
        return self.send("Return", mode="release")

    def back(self):
        return self.send("Left", "Alt_L")

    def back_restored(self):
        self.check(
            self.window.nav.get_visible_page() == self.window.home_page, "Alt+Left did not return"
        )
        self.check(
            abs(self.view.scroll.get_vadjustment().get_value() - self.before_open) < 3,
            "Back lost the source list position",
        )
        return self.send("Home", "Control_L")

    def top(self):
        self.check(
            self.view.scroll.get_vadjustment().get_value() <= 1, "Go to top did not scroll to top"
        )
        self.check(
            self.window.last_toast.get_button_label() == "Undo", "Top feedback has no Undo action"
        )
        return self.send("u", wait=4)

    def undo_top(self):
        self.check(
            abs(self.view.scroll.get_vadjustment().get_value() - self.before_open) < 3,
            "Undo did not restore the reading position",
        )
        return self.send("F6")

    def pane(self):
        focus = self.window.get_focus()
        self.check(
            any(
                focus == b or (focus and focus.is_ancestor(b))
                for b in self.window.destination_buttons.values()
            ),
            "F6 did not focus navigation",
        )
        return self.send("F6", "Shift_L")

    def pane_return(self):
        focus = self.window.get_focus()
        self.check(
            focus is not None and focus.is_ancestor(self.view),
            "Shift+F6 did not return to the list",
        )
        return self.send("2", "Control_L")

    def search(self):
        self.check(
            self.window.nav.get_visible_page().get_title() == "Search", "Ctrl+2 did not open search"
        )
        self.search_entry = self.window.nav.get_visible_page().focus_widget
        return self.send("j")

    def search_type(self):
        return self.send("k")

    def search_preserved(self):
        self.check(self.search_entry.get_text() == "jk", "Single-key shortcuts stole search typing")
        return self.send("Left", "Alt_L")

    def search_back(self):
        self.check(
            self.window.nav.get_visible_page() == self.window.home_page,
            "Alt+Left from an entry did not go back",
        )
        return self.send("F1")

    def help(self):
        self.check(
            isinstance(self.window.get_visible_dialog(), Adw.ShortcutsDialog),
            "F1 did not open native shortcut help",
        )
        return self.send("Escape")

    def help_closed(self):
        self.check(
            self.window.get_visible_dialog() is None, "Escape was stolen from the shortcut dialog"
        )
        return self.send("F10")

    def menu(self):
        self.check(
            self.window.home_page.menu_button.get_popover().get_visible(),
            "F10 did not open the main menu",
        )
        return self.send("Escape")

    def menu_closed(self):
        self.check(
            not self.window.home_page.menu_button.get_popover().get_visible(),
            "Escape did not close the menu",
        )
        self.view.interaction.focus()
        return self.send("r")

    def reply(self):
        if self.window.composer is None or not self.window.composer.ready:
            return False
        self.check(self.window.composer.reply is not None, "R did not open a reply")
        return self.send("j")

    def reply_type(self):
        return self.send("k")

    def editor_undo(self):
        self.check(self.window.composer.text() == "jk", "List shortcuts stole composer typing")
        return self.send("z", "Control_L")

    def editor_preserved(self):
        self.check(
            len(self.window.composer.text()) < 2, "Ctrl+Z did not reach the native text editor"
        )
        self.window.composer.buffer.set_text("")
        self.window.composer.close()
        return True

    def close_editor(self):
        if self.window.get_visible_dialog():
            return False
        return self.send("3", "Control_L")

    def notifications(self):
        if self.window.page_requests:
            return False
        self.check(
            self.window.nav.get_visible_page().get_title() == "Notifications",
            "Ctrl+3 did not open notifications",
        )
        self.notices = self.window.interactions.current_view()
        self.window.nav.get_visible_page().menu_button.grab_focus()
        return self.send("Down")

    def notice_select(self):
        self.check(self.notices.store.get_selected() == 0, "Notification list did not receive Down")
        return self.send("j")

    def notice_not_seen(self):
        self.check(not self.window.service.seen, "Keyboard movement marked notifications seen")
        return self.send("1", "Control_L")

    def narrow(self):
        self.window.set_default_size(480, 820)
        self.window.split.set_collapsed(True)
        self.view.interaction.focus()
        return self.send("F6")

    def narrow_pane(self):
        self.check(self.window.split.get_show_sidebar(), "F6 did not reveal narrow navigation")
        return self.send("F6")

    def narrow_return(self):
        self.check(not self.window.split.get_show_sidebar(), "F6 did not return to narrow content")
        return True

    def finish(self):
        print(
            "PHYSICAL_KEYBOARD_PASS: header/list J/K/arrows/pages, held Enter, Back position, top/Undo, panes, destinations, typing/editor Undo, help/menu Escape, notifications, wide/narrow",
            flush=True,
        )
        self.stop()
        return True
