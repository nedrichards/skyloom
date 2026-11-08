"""Application navigation and controllers; all widget work stays on the main thread."""

import time
from dataclasses import replace
from functools import partial
from weakref import WeakSet

from gi.repository import Adw, GLib, Gtk, Pango

from . import APP_ID, VERSION
from .composer import Composer
from .content import LabelledContent
from .conversation import Continuation, Conversation
from .conversation_view import ConversationView
from .domain import Author, Pager, Post, find_post, safe_url
from .errors import POST_UNAVAILABLE, UserError
from .feed_coordination import FeedCoordination
from .feed_state import FeedGap
from .interactions import Interactions
from .motion import Feedback
from .navigation import Navigation
from .preferences import Preferences
from .profile_header import ProfileTitle
from .reading import ReadingSession
from .records import RecordPager
from .refresh_monitor import RefreshMonitor
from .request_scope import guard
from .request_scope import submit as submit_request
from .search import SearchView
from .startup import StartupStack
from .thread_prefetch import HomeThreadPrefetch, ThreadCache
from .widgets import (
    FeedView,
    NoticeRow,
    PostRow,
    avatar,
    box,
    button,
    label,
    should_load_image,
    status,
)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Skyloom", default_width=1100, default_height=820)
        self.worker, self.service, self.images = app.worker, app.service, app.images
        self.demo, self.settings = app.demo, app.settings
        self.views, self.mutations, self.pagers, self.feed_views = [], set(), {}, {}
        self.content_gates = WeakSet()
        self.online_controls = WeakSet()
        self.revealed_labels = {}
        self.settings.connect("changed::warn-labelled-content", self.label_preference_changed)
        self.read_only = False
        self.composer = None
        self.generation = 0
        self.request = None
        self.restore_serial = 0
        self.closing = False
        self.page_requests = {}
        self.refresh_monitor = None
        self.auto_feeds = set()
        self.interactions = Interactions(self)
        self.motion = Feedback(self)
        self.images.auto_download_allowed = lambda: not self.automatic_pause_reason()
        self.feed_id = "following"
        self.connect("close-request", self.close_requested)
        self.overlay = Adw.ToastOverlay()
        self.connect("notify::focus-widget", self.sync_update_notices)
        self.connect("notify::visible-dialog", self.sync_update_notices)
        self.set_content(self.overlay)
        self.stack = StartupStack()
        self.stack.retry_button.connect("clicked", lambda *_: self.retry_session())
        self.stack.sign_in_button.connect("clicked", lambda *_: self.stack.resolve("welcome"))
        self.overlay.set_child(self.stack)
        self.connect("unrealize", self.cancel_startup)
        self.navigation = Navigation()
        self.split = self.navigation.view
        self.split.connect("notify::show-sidebar", self.view_changed)
        self.split.connect("notify::collapsed", self.view_changed)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        narrow.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(narrow)
        self.welcome()
        if self.demo:
            self.signed_in(self.service.account)
        else:
            self.retry_session()
        self.refresh_monitor = RefreshMonitor(self)

    def automatic_pause_reason(self):
        return self.interactions.automatic_reason()

    def connection_changed(self, connection):
        self.interactions.connection_changed(connection)
        self.motion.changed()
        for view in self.views:
            view.prefetch_reconsider()

    def check_auto_refresh(self, now):
        return self.interactions.check_auto(now)

    def automatic_target(self):
        return self.interactions.auto_target()

    def sync_update_notices(self, *_args):
        current = self.interactions.current_view()
        quiet = not self.is_active() or self.interactions.context() in {"dialog", "popup"}
        for view in self.views:
            if view.pending_update:
                if view is current and not quiet:
                    view.update_notice.schedule()
                else:
                    view.update_notice.unmap()

    def view_changed(self, *_args):
        self.interactions.update_actions()
        self.sync_update_notices()
        if self.refresh_monitor:
            self.refresh_monitor.changed()

    def add_menu(self, header, page=None):
        menu = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Main menu (F10)",
            menu_model=self.interactions.menu(),
        )
        header.pack_end(menu)
        if page is not None:
            page.menu_button = menu
            self.navigation.bind_menu(menu)
        else:
            self.welcome_menu = menu
        return menu

    def label_preference_changed(self, *_args):
        self.revealed_labels.clear()
        for gate in list(self.content_gates):
            gate.sync()

    def toast(self, text):
        self.last_toast = Adw.Toast(title=text, timeout=5)
        self.overlay.add_toast(self.last_toast)

    def open_uri(self, uri):
        from .domain import safe_url

        if not safe_url(uri):
            self.toast("This link cannot be opened safely.")
            return
        launch = Gtk.UriLauncher(uri=uri)

        def finished(obj, result):
            try:
                obj.launch_finish(result)
            except GLib.Error:
                self.toast("Couldn’t open the link in your browser.")

        launch.launch(self, None, finished)

    def view_media(self, media):
        dialog = Adw.Dialog(title="Image", content_width=800, content_height=640)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        if uri := safe_url(media.fullsize or media.url):
            header.pack_end(
                button("web-browser-symbolic", "Open image in browser", lambda: self.open_uri(uri))
            )
        toolbar.add_top_bar(header)
        body = box(spacing=12, margin=16)
        pic = Gtk.Picture(
            can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, vexpand=True, height_request=280
        )
        pic.set_alternative_text(media.alt if media.alt.strip() else "Image")
        body.append(pic)
        description = label(media.alt, selectable=True, visible=bool(media.alt.strip()))
        body.append(description)
        if media.alt.strip():
            body.append(
                button(
                    "edit-copy-symbolic",
                    "Copy image description",
                    lambda: (self.get_clipboard().set(media.alt), self.toast("Description copied")),
                    "Copy description",
                )
            )
        toolbar.set_content(Gtk.ScrolledWindow(child=body, hscrollbar_policy=Gtk.PolicyType.NEVER))
        dialog.set_child(toolbar)
        alive = [True]

        def loaded(pix):
            if alive[0]:
                self.images.bind(pic, pix)
                pic.set_paintable(pix)

        def failed(msg):
            if alive[0]:
                description.set_visible(True)
                description.set_label(
                    "Image unavailable. " + msg + ("\n" + media.alt if media.alt.strip() else "")
                )

        task = self.worker.submit(
            self.images.get(media.fullsize or media.url, media.local, explicit=True), loaded, failed
        )

        def closed(*_):
            alive[0] = False
            pic.set_paintable(None)
            self.images.unbind(pic)
            if task:
                task.cancel()

        dialog.connect("closed", closed)
        dialog.present(self)

    def copy(self, text):
        self.get_clipboard().set(text)
        self.toast("Link copied")

    def welcome(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.add_menu(header)
        toolbar.add_top_bar(header)
        content = box(spacing=18, margin=24)
        content.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Image(icon_name=APP_ID, pixel_size=112)
        content.append(icon)
        content.append(
            label(
                "A little closer to the conversation",
                "title-1",
                halign=Gtk.Align.CENTER,
                justify=Gtk.Justification.CENTER,
            )
        )
        content.append(
            label("A calm, native home for Bluesky.", "dim-label", halign=Gtk.Align.CENTER)
        )
        group = Adw.PreferencesGroup(
            title="Sign in with an app password",
            description="Create a dedicated app password in Bluesky settings. Enter it here; it is distinct from your account password.",
        )
        self.handle = Adw.EntryRow(title="Handle (for example, name.bsky.social)")
        self.password = Adw.PasswordEntryRow(title="App password")
        self.pds = Adw.EntryRow(title="PDS address", text="https://bsky.social")
        group.add(self.handle)
        group.add(self.password)
        advanced = Adw.ExpanderRow(title="Custom server", subtitle="For accounts on another PDS")
        advanced.add_row(self.pds)
        group.add(advanced)
        content.append(group)
        content.append(
            button(
                "web-browser-symbolic",
                "Create a dedicated Bluesky app password",
                lambda: self.open_uri("https://bsky.app/settings/app-passwords"),
                "Create an app password",
            )
        )
        self.login_button = Gtk.Button(label="Sign in")
        self.login_button.add_css_class("suggested-action")
        self.login_button.add_css_class("pill")
        self.login_button.connect("clicked", self.login)
        content.append(self.login_button)
        self.password.connect("entry-activated", self.login)
        self.login_feedback = label(
            "Your refreshable session is stored in your login keyring. Your app password is never saved.",
            "dim-label",
            selectable=True,
        )
        content.append(self.login_feedback)
        self.retry_restore = Gtk.Button(label="Retry saved session", visible=False)
        self.retry_restore.connect("clicked", lambda _: self.retry_session())
        content.append(self.retry_restore)
        clamp = Adw.Clamp(maximum_size=470, tightening_threshold=400, child=content)
        toolbar.set_content(Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.stack.add_named(toolbar, "welcome")

    def retry_session(self):
        if self.closing:
            return
        self.restore_serial += 1
        serial = self.restore_serial
        if self.request:
            self.request.cancel()
        self.stack.begin()
        self.login_button.set_sensitive(False)
        self.retry_restore.set_sensitive(False)
        self.login_feedback.set_label("Restoring session…")

        def resolved(value, callback):
            if not self.closing and serial == self.restore_serial:
                self.request = None
                callback(value)

        self.request = self.worker.submit(
            self.service.restore(),
            lambda account: resolved(account, self.restored),
            lambda message: resolved(message, self.saved_session_error),
        )

    def saved_session_error(self, message):
        self.restore_error(message, restoring=True)

    def restored(self, account):
        if self.closing:
            return
        self.login_button.set_sensitive(True)
        self.retry_restore.set_sensitive(True)
        self.retry_restore.set_visible(False)
        if account:
            self.signed_in(account)
        else:
            self.login_feedback.set_label(
                "Use a dedicated app password. Your session will be saved in your login keyring."
            )
            self.stack.resolve("welcome")

    def restore_error(self, msg, *, restoring=False):
        if self.closing:
            return
        self.login_button.set_sensitive(True)
        self.retry_restore.set_sensitive(True)
        self.login_feedback.set_label(msg)
        self.retry_restore.set_visible(True)
        if restoring:
            self.stack.show_error(msg)
        else:
            self.stack.resolve("welcome")

    def login(self, *_args):
        if not self.login_button.get_sensitive():
            return
        handle, password, pds = (
            self.handle.get_text(),
            self.password.get_text(),
            self.pds.get_text(),
        )
        if not handle.strip() or not password.strip():
            self.login_feedback.set_label("Enter your handle and a dedicated app password.")
            return
        self.password.set_text("")
        self.login_button.set_sensitive(False)
        self.login_feedback.set_label("Signing in and saving your session securely…")
        self.request = self.worker.submit(
            self.service.sign_in(handle, password, pds), self.signed_in, self.restore_error
        )

    def signed_in(self, account):
        if not account or self.closing:
            return
        self.password.set_text("")
        self.retry_restore.set_visible(False)
        self.images.use_account(account.did)
        self.feed_id = getattr(self.service, "reading_feed", "following")
        self.build_shell(account)
        self.stack.resolve("shell")
        generation = self.generation
        self.worker.submit(
            self.images.catalog(),
            lambda _: self.redisplay_media() if generation == self.generation else None,
        )
        if self.demo:
            self.refresh()
        else:
            self.load_initial_feed()
        if not self.automatic_pause_reason():
            self.load_metadata()
        elif not self.demo:
            self.feed_metadata_loaded = False
            generation = self.generation
            self.worker.submit(
                self.service.cached_feeds(),
                lambda choices: self.set_feeds(choices) if generation == self.generation else None,
                self.toast,
            )
        if self.refresh_monitor:
            self.refresh_monitor.changed()

    def build_shell(self, account):
        self.thread_cache = ThreadCache()
        self.post_positions = None
        for view in self.views:
            view.close()
        self.interactions.policies.clear()
        self.interactions.undo_action = None
        self.auto_feeds.clear()
        previous = self.stack.get_child_by_name("shell")
        if previous:
            self.stack.remove(previous)
        self.views, self.pagers, self.feed_views = [], {}, {}
        self.nav = Adw.NavigationView()
        self.nav.connect("popped", self.page_popped)
        self.nav.connect(
            "notify::visible-page",
            lambda *_: self.refresh_monitor.changed() if self.refresh_monitor else None,
        )
        self.home_toolbar = Adw.ToolbarView()
        home_header = Adw.HeaderBar()
        self.home_toolbar.add_top_bar(home_header)
        self.feed_options = getattr(self.service, "reading_choices", [("following", "Following")])
        self.feed_picker = Gtk.DropDown.new_from_strings(
            [option[1] for option in self.feed_options]
        )
        self.feed_picker.set_selected(
            next((i for i, option in enumerate(self.feed_options) if option[0] == self.feed_id), 0)
        )
        self.feed_picker.set_tooltip_text("Choose a feed")
        self.feed_picker.update_property([Gtk.AccessibleProperty.LABEL], ["Choose a feed"])
        self.feed_picker.connect("notify::selected", self.feed_changed)
        home_header.set_title_widget(self.feed_picker)
        home_toggle = self.navigation.create_toggle()
        home_header.pack_start(home_toggle)
        home_header.pack_end(button("view-refresh-symbolic", "Refresh feed (Ctrl+R)", self.refresh))
        self.compose_button = button("list-add-symbolic", "New post (Ctrl+N)", self.compose)
        home_header.pack_end(self.compose_button)
        self.home_box = box(spacing=0)
        if self.demo:
            banner = Adw.Banner(title="Demo · invented posts, no account or network")
            banner.set_revealed(True)
            self.home_box.append(banner)
        self.offline_banner = Adw.Banner(
            title="Offline · showing cached posts", button_label="Try again", revealed=False
        )
        self.offline_banner.connect("button-clicked", lambda _: self.refresh())
        self.home_box.append(self.offline_banner)
        self.feed_stack = Gtk.Stack(vexpand=True)
        self.home_box.append(self.feed_stack)
        self.home_toolbar.set_content(self.home_box)
        self.home_page = Adw.NavigationPage.new(self.home_toolbar, "Following")
        self.home_page.set_tag("home")
        self.home_page.navigation_button = home_toggle
        self.add_menu(home_header, self.home_page)
        self.nav.add(self.home_page)
        side = Adw.ToolbarView()
        side_header = Adw.HeaderBar(
            title_widget=Adw.WindowTitle(
                title="Skyloom", subtitle="Offline demo" if self.demo else "Bluesky"
            )
        )
        self.sidebar_navigation_button = self.navigation.create_toggle(overlay_only=True)
        side_header.pack_start(self.sidebar_navigation_button)
        self.sidebar_menu = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Main menu (F10)",
            menu_model=self.interactions.menu(),
        )
        side_header.pack_end(self.sidebar_menu)
        self.navigation.bind_menu(self.sidebar_menu, sidebar=True)
        side.add_top_bar(side_header)
        column = box(spacing=6, margin=12)
        account_row = box(False, 8, margin=4)
        account_row.append(avatar(account, self, 36))
        account_identity = box(spacing=2)
        account_identity.set_hexpand(True)
        account_identity.append(
            label(
                account.name,
                "heading",
                wrap=False,
                ellipsize=Pango.EllipsizeMode.END,
                max_width_chars=16,
            )
        )
        account_identity.append(
            label(
                "@" + account.handle,
                "dim-label",
                wrap=False,
                ellipsize=Pango.EllipsizeMode.END,
                max_width_chars=16,
            )
        )
        account_row.append(account_identity)
        self.side_buttons = []
        self.destination_buttons = {}
        for icon, title in [
            ("user-home-symbolic", "Home"),
            ("edit-find-symbolic", "Search"),
            ("document-edit-symbolic", "Drafts"),
            ("preferences-system-notifications-symbolic", "Notifications"),
        ]:
            destination = title.lower()
            b = button(
                icon, title, lambda destination=destination: self.interactions.navigate(destination)
            )
            self.interactions.install_destination(b, destination)
            self.destination_buttons[destination] = b
            child = box(False, 12, margin=6)
            child.append(Gtk.Image(icon_name=icon))
            name = label(title, hexpand=True)
            child.append(name)
            b.set_child(child)
            b.add_css_class("flat")
            column.append(b)
            self.side_buttons.append(b)
            if title == "Notifications":
                self.notification_label = name
        column.append(Gtk.Box(vexpand=True))
        if self.demo:
            self.offline_switch = Adw.SwitchRow(
                title="Simulate offline", subtitle="Test cached reading and errors"
            )
            self.offline_switch.connect("notify::active", self.demo_offline)
            demo_rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            demo_rows.add_css_class("boxed-list")
            demo_rows.append(self.offline_switch)
            column.append(demo_rows)
        self.profile_button = button(
            "avatar-default-symbolic", "Your profile", lambda: self.interactions.navigate("profile")
        )
        self.profile_button.set_child(account_row)
        self.profile_button.add_css_class("flat")
        self.profile_button.update_property(
            [Gtk.AccessibleProperty.LABEL], [f"Your profile: {account.name}, @{account.handle}"]
        )
        self.interactions.install_destination(self.profile_button, "profile")
        self.destination_buttons["profile"] = self.profile_button
        self.side_buttons.append(self.profile_button)
        footer = box(spacing=0, margin=12)
        footer.append(self.profile_button)
        side.add_bottom_bar(footer)
        side.set_content(column)
        self.split.set_sidebar(side)
        self.split.set_content(self.nav)
        self.split.set_show_sidebar(not self.split.get_collapsed())
        self.stack.add_named(self.split, "shell")

    def set_feeds(self, options):
        if options == self.feed_options:
            return
        selected = next((i for i, option in enumerate(options) if option[0] == self.feed_id), 0)
        with self.feed_picker.freeze_notify():
            self.feed_options = options
            self.feed_picker.set_model(Gtk.StringList.new([x[1] for x in options]))
            self.feed_picker.set_selected(selected)

    def load_metadata(self, automatic=False):
        self.feed_metadata_loaded = True
        generation = self.generation

        def failed(msg):
            if generation == self.generation:
                self.feed_metadata_loaded = False
                if not automatic:
                    self.toast(msg)

        self.worker.submit(
            self.service.feeds(),
            lambda choices: self.set_feeds(choices) if generation == self.generation else None,
            failed,
        )
        self.worker.submit(
            self.service.unread(),
            lambda count: self.unread_received(count) if generation == self.generation else None,
            failed,
        )

    def unread_received(self, count):
        self.notification_label.set_label(f"Notifications ({count})" if count else "Notifications")

    def feed_changed(self, *_args):
        index = self.feed_picker.get_selected()
        if index >= len(self.feed_options):
            return
        feed = self.feed_options[index][0]
        if self.feed_id != feed:
            previous = self.feed_views.get(self.feed_id)
            if previous and previous.reading:
                previous.reading.flush()
            self.feed_id = feed
            self.worker.submit(
                self.service.save_active_feed(feed, self.service.account), error=self.toast
            )
            self.go_home()
            self.refresh(reset=False)

    def go_home(self):
        self.nav.pop_to_tag("home")
        self.navigation.reveal_content()

    def feed_view(self):
        if self.feed_id not in self.feed_views:
            view = FeedView(self)
            self.feed_stack.add_named(view, self.feed_id)
            self.feed_views[self.feed_id] = view
            self.pagers[self.feed_id] = Pager()
            feed = self.feed_id
            view.feed = FeedCoordination(self, view, feed)
            view.reading = ReadingSession(self, view, feed)
            view.reading.ready = self.demo
            view.check_start = view.feed.autoload_gap
            prefetch = HomeThreadPrefetch(self, view, self.thread_cache)
            view.viewport_changed = prefetch.schedule
            view.prefetch_reconsider = prefetch.reconsider
            view.load_more = lambda: self.load_feed(feed, reset=False)
            view.refresh = self.refresh
            view.auto_key = "feed:" + feed
            view.auto_refresh = lambda: self.auto_refresh_feed(feed)
        self.feed_stack.set_visible_child_name(self.feed_id)
        return self.feed_views[self.feed_id]

    def load_initial_feed(self):
        feed = self.feed_id
        view = self.feed_view()
        key = "initial:" + feed
        if key in self.page_requests or "feed:" + feed in self.page_requests:
            return
        view.paging.begin("Loading cached posts…")
        generation = self.generation

        serial = view.input_serial

        async def cached():
            return await self.service.cached_state(feed)

        def ready(value):
            pager = value.pager
            policy = self.interactions.policy("feed:" + feed)
            # Restart accepts a fresh server order when network policy permits it.
            policy.restore(None)
            self.pagers[feed] = pager
            view.set_posts(pager.projected())
            view.reading.ready = True
            view.reading.latest = (pager, value.bookmark)
            if serial == view.input_serial:
                view.reading.restore(value.bookmark)
            view.reading.changed()
            view.load_more = lambda: self.load_feed(feed, reset=not bool(pager.cursor))
            view.paging.complete(pager.cursor, 0)
            if not pager.posts:
                view.paging.manual_available = True
                view.paging.message = self.automatic_pause_reason() or "Refresh to load your feed."
                view.paging.changed()
            self.sync_offline()
            if not pager.posts and not self.automatic_pause_reason():
                self.load_feed(feed, reset=True)
            if self.refresh_monitor:
                self.refresh_monitor.changed()

        def failed(msg):
            if generation == self.generation:
                view.load_more = self.refresh
                view.paging.fail(msg)

        submit_request(self, key, cached(), ready, failed)

    def auto_refresh_feed(self, feed):
        key = "feed:" + feed
        if key in self.page_requests:
            return False
        pager = self.pagers[feed]
        generation = self.generation
        policy = self.interactions.policy(key)
        baseline = {post.uri: post for post in pager.posts}
        self.auto_feeds.add(feed)

        def done(page):
            self.auto_feeds.discard(feed)
            if generation != self.generation:
                return
            policy.finished(time.time(), True)
            if not getattr(self, "feed_metadata_loaded", False):
                self.load_metadata(automatic=True)
            self.show_feed_update(feed, page, baseline, automatic=True)
            if feed == self.feed_id:
                self.sync_offline()
            self.worker.submit(
                self.service.unread(),
                lambda count: (
                    self.unread_received(count) if generation == self.generation else None
                ),
                lambda _msg: None,
            )

        def failed(_msg):
            self.auto_feeds.discard(feed)
            if generation == self.generation:
                policy.finished(time.time(), False)

        submit_request(self, key, self.service.feed(feed), done, failed)
        return True

    def show_feed_update(self, feed, page, baseline=None, *, automatic=False):
        view = self.feed_views[feed]
        pending = self.page_requests.pop("feed:" + feed, None)
        if pending:
            pending.cancel()
        previous = self.pagers[feed]
        live = {post.uri: post for post in previous.posts}
        place = view.interaction.capture()
        attempted = set(view.paging.attempted)
        if pending:
            attempted.discard(previous.cursor)
        incoming = []
        for post in page.posts:
            current = live.get(post.uri)
            before = baseline.get(post.uri) if baseline else None
            if current and (
                (
                    before is not None
                    and (current.likes, current.reposts, current.like_uri, current.repost_uri)
                    != (before.likes, before.reposts, before.like_uri, before.repost_uri)
                )
                or any(key[0] == post.uri for key in self.mutations)
            ):
                post = replace(
                    post,
                    likes=current.likes,
                    reposts=current.reposts,
                    like_uri=current.like_uri,
                    repost_uri=current.repost_uri,
                )
            incoming.append(post)
        page = replace(page, posts=tuple(incoming))
        reading = getattr(view, "reading", None)
        bookmark = reading.capture() if reading else None
        coordination = view.feed
        startup = bool(coordination and coordination.startup)
        current = previous.reconciled(
            page,
            reorder=not automatic or startup,
            anchor=bookmark.uri if bookmark else getattr(place, "key", None),
        )
        self.pagers[feed] = current
        arrivals = {post.uri for post in current.posts} - live.keys()
        if current.cursor != previous.cursor:
            view.paging.attempted.clear()
        else:
            view.paging.attempted = attempted.copy()
        view.load_more = lambda: self.load_feed(feed, reset=False)
        if automatic:
            view.set_posts(current.projected(coordination.gap_states if reading else None))
            if reading:
                reading.restore(bookmark)
                coordination.startup = False
                coordination.unseen.update(arrivals)
                coordination.unseen.intersection_update(p.uri for p in current.posts)
            if not reading:
                view.interaction.restore(place)
            count = len(coordination.unseen) if reading else len(arrivals)
            if count and arrivals:
                title = "1 new post" if count == 1 else f"{count} new posts"

                def go_to_top():
                    if reading:
                        coordination.unseen.clear()
                    self.interactions.top()

                view.offer_update(
                    title,
                    go_to_top,
                    button_label="Go to top",
                    revision=frozenset(coordination.unseen if reading else arrivals),
                )
        else:
            if reading:
                coordination.startup = False
                coordination.unseen.clear()
            view.show_latest(current.projected(), arrivals)
            self.interactions.offer_undo(
                "Latest posts shown", lambda: view.interaction.restore(place), view
            )
        view.paging.complete(current.cursor, max(1, len(arrivals)) if current.posts else 0)
        if reading:
            reading.changed()

    def load_feed_gap(self, view, before):
        reading = view.reading
        coordination = view.feed
        feed = coordination.feed
        pager = self.pagers[feed]
        cursor = pager.gaps.get(before)
        key = "feed:" + feed
        if not cursor or key in self.page_requests:
            return
        bookmark = reading.capture()
        coordination.gap_attempted.add((before, cursor))
        coordination.gap_states[before] = FeedGap(before, cursor, busy=True)
        view.set_posts(pager.projected(coordination.gap_states))
        reading.restore(bookmark)

        def failed(message):
            bookmark = reading.capture()
            coordination.gap_states[before] = FeedGap(before, cursor, error=message)
            view.set_posts(self.pagers[feed].projected(coordination.gap_states))
            reading.restore(bookmark)
            view.paging.complete(self.pagers[feed].cursor, 0)

        def loaded(page):
            current = self.pagers[feed]
            bookmark = reading.capture()
            bridged = current.bridge(before, page, anchor=bookmark.uri if bookmark else None)
            if bridged is current:
                failed("This reading window is full. Refresh to start a new window.")
                return
            if (
                before in bridged.gaps
                and (before, bridged.gaps[before]) in coordination.gap_attempted
            ):
                failed("No further progress. Try refreshing the feed.")
                return
            coordination.gap_states.pop(before, None)
            self.pagers[feed] = bridged
            view.paging.complete(bridged.cursor, len(bridged.posts) - len(current.posts))
            view.set_posts(bridged.projected(coordination.gap_states))
            reading.restore(bookmark)
            reading.changed()

        submit_request(self, key, self.feed_page(feed, cursor), loaded, failed)

    def refresh(self, reset=True):
        if not self.service.account:
            return
        self.feed_view()
        if not reset and self.pagers[self.feed_id].posts:
            self.sync_offline()
            return
        if not reset:
            self.load_initial_feed()
            return
        pending = self.page_requests.pop("initial:" + self.feed_id, None)
        if pending:
            pending.cancel()
        key = "feed:" + self.feed_id
        if self.feed_id in self.auto_feeds:
            pending = self.page_requests.pop(key, None)
            if pending:
                pending.cancel()
            self.auto_feeds.discard(self.feed_id)
        self.feed_views[self.feed_id].clear_update()
        self.load_feed(self.feed_id, reset=True)

    def load_feed(self, feed, reset):
        key = "feed:" + feed
        if key in self.page_requests:
            return
        view, pager = self.feed_views[feed], self.pagers[feed]
        cursor = None if reset else pager.cursor
        if not reset and not cursor:
            return
        view.paging.begin(
            "Refreshing…" if pager.posts else "Loading your feed…", reset=reset and not pager.posts
        )
        generation = self.generation
        baseline = {post.uri: post for post in pager.posts}

        def loaded(page):
            pager = self.pagers[feed]
            if reset:
                self.interactions.policy(key).finished(time.time(), True)
                if not getattr(self, "feed_metadata_loaded", False):
                    self.load_metadata()
            if reset and pager.posts:
                self.show_feed_update(feed, page, baseline)
                if feed == self.feed_id:
                    self.sync_offline()
                return
            bookmark = view.reading.capture()
            if reset:
                pager.merge(page, reset=True)
            else:
                pager = pager.appended(page, anchor=bookmark.uri if bookmark else None)
                self.pagers[feed] = pager
            added = view.set_posts(pager.projected(), reset=reset)
            view.reading.ready = True
            if not reset:
                view.reading.restore(bookmark)
            view.reading.changed()
            view.load_more = lambda: self.load_feed(feed, reset=False)
            view.paging.complete(
                pager.cursor,
                len(page.posts) if reset else added,
                "No posts here yet." if not pager.posts else "",
            )
            if feed == self.feed_id:
                self.sync_offline()

        def cached(page, msg):
            if generation != self.generation:
                return
            if page.posts and not pager.posts:
                pager.merge(page, reset=True)
                view.set_posts(pager.posts)
            view.load_more = lambda: self.load_feed(feed, reset=reset)
            view.paging.fail(msg)
            if feed == self.feed_id:
                self.sync_offline()

        def failed(msg):
            if generation == self.generation:
                if reset:
                    self.interactions.policy(key).finished(time.time(), False)
                submit_request(
                    self,
                    key,
                    self.service.cached(feed),
                    lambda p: cached(p, msg),
                    lambda _m: cached(type("Empty", (), {"posts": ()})(), msg),
                )

        submit_request(self, key, self.feed_page(feed, cursor), loaded, failed)

    async def feed_page(self, feed, cursor):
        connection = self.interactions.connection
        if not connection.available or not connection.internet:
            if cursor:
                page = await self.service.cached_page(feed, cursor)
                if page is not None:
                    return page
            raise UserError("These posts are not saved locally. Reconnect and try again.")
        return await self.service.feed(feed, cursor)

    def sync_offline(self):
        connection = self.interactions.connection
        self.show_offline(not connection.available or not connection.internet)

    def show_offline(self, offline):
        self.read_only = offline
        self.offline_banner.set_revealed(offline)
        self.compose_button.set_sensitive(self.service.account is not None)
        for control in self.online_controls:
            self.online_control(control)
        if self.composer:
            self.composer.update_send_sensitivity()

    def online_control(self, control, *, ready=None, busy=None):
        if ready is not None:
            control.online_ready = ready
        if busy is not None:
            control.online_busy = busy
        self.online_controls.add(control)
        control.set_sensitive(
            self.service.account is not None
            and not self.read_only
            and getattr(control, "online_ready", True)
            and not getattr(control, "online_busy", False)
        )
        return control

    def demo_offline(self, row, _param):
        self.service.offline = row.get_active()
        self.refresh()
        if self.refresh_monitor:
            self.refresh_monitor.changed()

    def new_page(self, title):
        current = self.interactions.current_view()
        if current and current.reading:
            current.reading.flush()
        self.navigation.reveal_content()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)
        page = Adw.NavigationPage.new(toolbar, title)
        page.navigation_button = self.navigation.create_toggle()
        header.pack_start(page.navigation_button)
        page.destination = title.lower() if title in {"Search", "Drafts", "Notifications"} else None
        self.add_menu(header, page)
        self.nav.push(page)
        return page, toolbar, header

    def page_popped(self, _nav, page):
        page._scope_closed = True
        future = self.page_requests.pop(page, None)
        if future:
            future.cancel()
        for view in list(self.views):
            if view.is_ancestor(page):
                view.close()
                self.views.remove(view)

    def page_load(self, page, coro, done, retry):
        def failed(msg):
            page.get_child().set_content(
                status("Couldn’t load this page", msg, "network-error-symbolic", retry)
            )

        submit_request(self, page, coro, done, failed, page=page)

    def thread(self, uri):
        current = self.nav.get_visible_page()
        if getattr(current, "conversation_uri", None) == uri:
            self.navigation.reveal_content()
            view = getattr(current, "content_view", None)
            if isinstance(view, ConversationView):
                view.focus_body()
            return
        retained = find_post(
            (
                view.model.get_item(i).post
                for view in reversed(self.views)
                for i in range(view.model.get_n_items())
            ),
            uri,
        )
        page, toolbar, header = self.new_page("Conversation")
        page.conversation_uri = uri
        state = Conversation(uri)
        older_error = ""
        received = False

        errors = {}
        active = None
        retry = None
        lookahead_requests = 0
        lookahead_anchor = None
        lookahead_forward = True
        view = ConversationView(self, state, lambda **kwargs: load(**kwargs))
        page.content_view = view
        header.pack_end(view.return_button)
        header.pack_end(view.relative_controls)
        view.post_updated = state.update_post
        view.paging_ready = False
        view.refresh = lambda: load(refresh=True)
        toolbar.set_content(view)

        def sync(*, content_changed=True):
            view.sync(
                earlier_busy=active == "earlier",
                earlier_error=older_error,
                active=active,
                errors=errors,
                content_changed=content_changed,
            )

        def load(earlier=False, refresh=False, branch=None):
            nonlocal older_error, active
            if self.read_only:
                view.paging.fail("Offline. Saved messages remain readable.")
                return False
            if page in self.page_requests or view.paging.closed:
                return False
            initial = not received
            target = (
                state.earlier
                if earlier
                else uri
                if initial or refresh
                else branch or state.next_branch
            )
            if not target:
                return False
            active = "earlier" if earlier else target
            view.paging.begin("Loading earlier messages…" if earlier else "Loading conversation…")
            sync(content_changed=not received)

            request_revision = self.thread_cache.revision

            def done(result, *, fetched_uri=target, cache_result=True):
                nonlocal older_error, state, received, active, retry
                result = self.thread_cache.reconcile(result, started=request_revision)
                if initial:
                    state = Conversation(uri)
                    view.state = state
                    view.post_updated = state.update_post
                if cache_result and (initial or refresh):
                    self.thread_cache.put(fetched_uri, result, started=request_revision)
                received = True
                active = None
                retry = None
                errors.pop(target, None)
                added = state.merge(result, fetched_uri, earlier=earlier)
                if added and not initial and view.get_mapped():
                    view.announce("Messages loaded.", Gtk.AccessibleAnnouncementPriority.MEDIUM)
                if earlier:
                    older_error = ""
                view.paging.complete(state.next_branch, added, state.message)
                sync()
                if initial:
                    if any(post.uri == uri for post in state.posts):
                        view.focus_post(uri)
                    else:
                        view.after_position()

            def failed(msg):
                nonlocal older_error, state, active, retry
                active = None
                retry = partial(load, earlier=earlier, refresh=refresh, branch=target)
                if view.get_mapped():
                    view.announce(
                        "Couldn’t load messages. Try again.",
                        Gtk.AccessibleAnnouncementPriority.MEDIUM,
                    )
                if earlier:
                    older_error = msg
                else:
                    errors[target] = msg
                if msg == POST_UNAVAILABLE:
                    state = Conversation(uri)
                    view.state = state
                    view.post_updated = state.update_post
                view.paging.fail(msg)
                sync(content_changed=initial or msg == POST_UNAVAILABLE)
                if initial:
                    view.after_position()

            cached_thread = self.thread_cache.get_snapshot(uri) if initial and not refresh else None
            if cached_thread is not None:
                done(cached_thread.page, fetched_uri=cached_thread.anchor, cache_result=False)
                return True
            submit_request(
                self,
                page,
                self.service.thread(
                    target,
                    earlier=earlier,
                    replies_only=not initial and not refresh and not earlier,
                ),
                done,
                failed,
                page=page,
            )
            return True

        def check_earlier():
            nonlocal lookahead_requests, lookahead_anchor, lookahead_forward
            if self.automatic_pause_reason():
                return False
            rows = view.interaction.visible_rows()
            anchor = next((row._value.uri for _, row in rows if isinstance(row._value, Post)), None)
            if anchor is not None and anchor != lookahead_anchor:
                previous = view.entries.get(lookahead_anchor)
                current = view.entries.get(anchor)
                if previous is not None and current is not None:
                    lookahead_forward = current[0] > previous[0]
                lookahead_anchor, lookahead_requests = anchor, 0
            adjustment = view.scroll.get_vadjustment()
            if (
                state.earlier
                and not older_error
                and not view.paging.busy
                and adjustment.get_page_size() > 0
                and adjustment.get_value() <= max(160, adjustment.get_page_size())
            ):
                if adjustment.get_value() <= 160:
                    return load(earlier=True)
                if lookahead_requests < 3 and len(state.posts) < 250:
                    loaded = load(earlier=True)
                    lookahead_requests += bool(loaded)
                    return loaded
            if not view.paging.busy:
                visible = {row._value.uri for _y, row in rows}
                for _y, row in view.interaction.visible_rows(margin=1):
                    item = row._value
                    if isinstance(item, Continuation) and item.parent not in errors:
                        if item.uri in visible:
                            return load(branch=item.parent)
                        ahead = _y >= 0 if lookahead_forward else _y < view.scroll.get_height()
                        if ahead and lookahead_requests < 3 and len(state.posts) < 250:
                            loaded = load(branch=item.parent)
                            lookahead_requests += bool(loaded)
                            return loaded
            return False

        view.check_start = check_earlier
        view.load_more = lambda: retry() if retry is not None else load()

        def cached_ready(post):
            if post is not None:
                state.posts = [
                    replace(post, context="Saved post · refresh to load the conversation")
                ]
            sync()
            connection = self.interactions.connection
            if not connection.available or not connection.internet:
                view.paging.complete(
                    None,
                    0,
                    "Offline. Showing saved content."
                    if post
                    else "This conversation is not saved on this device.",
                )
                view.paging.manual_available = True
                view.paging.changed()
                if post:
                    view.focus_post(uri)
                else:
                    view.after_position()
            else:
                load()

        def cache_failed(msg):
            view.paging.fail(msg)
            view.after_position()

        if retained is not None:
            cached_ready(retained)
        else:
            view.paging.begin("Looking for saved content…")
            submit_request(
                self, page, self.service.cached_post(uri), cached_ready, cache_failed, page=page
            )

    def mutate(self, post, kind, remember=True):
        if self.read_only or any(p == post.uri for p, _kind in self.mutations):
            return
        speculative = self.page_requests.pop("thread-prefetch", None)
        if speculative:
            speculative.cancel()
        key = (post.uri, kind)
        self.mutations.add(key)
        if kind == "like":
            optimistic = replace(
                post,
                like_uri="" if post.like_uri else "pending",
                likes=max(0, post.likes + (-1 if post.like_uri else 1)),
            )
        else:
            optimistic = replace(
                post,
                repost_uri="" if post.repost_uri else "pending",
                reposts=max(0, post.reposts + (-1 if post.repost_uri else 1)),
            )
        self.update_post(optimistic)
        generation = self.generation

        def done(result):
            self.mutations.discard(key)
            if generation == self.generation:
                self.update_post(result)
                if remember:
                    added = bool(result.like_uri if kind == "like" else result.repost_uri)
                    title = (
                        ("Liked post" if added else "Like removed")
                        if kind == "like"
                        else ("Reposted" if added else "Repost removed")
                    )
                    self.interactions.offer_undo(title, lambda: self.undo_reaction(result, kind))
                else:
                    self.toast("Reaction undone.")

        def failed(msg):
            self.mutations.discard(key)
            if generation == self.generation:
                self.update_post(post)
                self.toast(msg + " The change was undone.")

        self.worker.submit(self.service.mutate(post, kind), done, failed)

    def undo_reaction(self, expected, kind):
        if self.read_only or (expected.uri, kind) in self.mutations:
            return False
        field = "like_uri" if kind == "like" else "repost_uri"
        for view in self.views:
            for index in range(view.model.get_n_items()):
                current = view.model.get_item(index).post
                if (
                    isinstance(current, Post)
                    and current.uri == expected.uri
                    and getattr(current, field) != getattr(expected, field)
                ):
                    return False
        self.mutate(expected, kind, remember=False)
        return "pending"

    def update_post(self, post):
        self.thread_cache.update_post(post)
        for pager in self.pagers.values():
            pager.posts = [post if p.uri == post.uri else p for p in pager.posts]
        for view in self.views:
            view.update_post(post)

    def compose(self, reply=None, quote=None, draft_key=None):
        if not self.service.account:
            return
        if self.composer:
            self.composer.present(self)
            return
        self.composer = Composer(self, reply, quote, draft_key)
        self.composer.present(self)

    def drafts(self):
        self.go_home()
        page, toolbar, _header = self.new_page("Drafts")

        def load():
            toolbar.set_content(status("Loading drafts…", ""))

            def done(values):
                body = box(spacing=12, margin=16)
                if not values:
                    body.append(
                        status(
                            "Room for a new thought",
                            "Unfinished posts are kept here on this device.",
                            "document-edit-symbolic",
                        )
                    )
                else:
                    rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
                    rows.add_css_class("boxed-list")
                    for key, draft in values:
                        title = draft.get("text", "").strip()[:100] or "Image post"
                        row = Adw.ActionRow(
                            use_markup=False,
                            title=title,
                            subtitle="Reply"
                            if draft.get("reply")
                            else "Quote"
                            if draft.get("quote")
                            else "New post",
                            activatable=True,
                        )
                        row.connect("activated", lambda _r, k=key: self.compose(draft_key=k))
                        rows.append(row)
                    body.append(rows)
                toolbar.set_content(
                    Gtk.ScrolledWindow(
                        child=Adw.Clamp(maximum_size=760, child=body),
                        hscrollbar_policy=Gtk.PolicyType.NEVER,
                    )
                )

            self.page_load(page, self.service.drafts(), done, load)

        load()

    def profile(self, actor):
        page, toolbar, header = self.new_page("Profile")
        page.destination = "profile" if actor == self.service.account.did else None
        state = {
            "author": None,
            "pager": Pager(),
            "filter": "posts_no_replies",
        }

        def load():
            toolbar.set_content(status("Loading profile…", ""))

            def done(author):
                state["author"] = author
                render()

            self.page_load(page, self.service.profile(actor), done, load)

        def render():
            pending = self.page_requests.pop(page, None)
            if pending:
                pending.cancel()
            author = state["author"]
            previous_view = state.get("view")
            if previous_view in self.views:
                previous_view.close()
                self.views.remove(previous_view)
            intro = box(spacing=12, margin=24)
            identity = box(spacing=12)
            portrait = avatar(author, self, 72)
            portrait.set_halign(Gtk.Align.START)
            identity.append(portrait)
            identity.append(label(author.name, "title-1"))
            identity.append(label("@" + author.handle, "dim-label", selectable=True))
            intro.append(identity)

            def biography():
                content = box(spacing=12)
                if author.banner and should_load_image(self, author.banner):
                    banner = Gtk.Picture(
                        content_fit=Gtk.ContentFit.COVER, can_shrink=True, height_request=120
                    )
                    banner.set_alternative_text("Profile banner")
                    content.append(banner)
                    self.worker.submit(
                        self.images.get(author.banner),
                        guard(self, page, lambda pix: banner.set_paintable(pix)),
                        guard(self, page, lambda _: banner.set_visible(False)),
                    )
                if author.bio.strip():
                    content.append(label(author.bio, selectable=True))
                return content

            if author.labels:
                intro.append(
                    LabelledContent(self, ("profile", author.did), author.labels, biography)
                )
            else:
                intro.append(biography())
            statistics = []
            for value, title in [
                (author.followers, "followers"),
                (author.following_count, "following"),
                (author.posts_count, "posts"),
            ]:
                if value is not None:
                    statistics.append(f"{value:,} {title}")
            if statistics:
                intro.append(label(" · ".join(statistics), "dim-label"))
            controls = Adw.WrapBox(child_spacing=6, line_spacing=6)
            if author.did != self.service.account.did:
                follow = button(
                    "",
                    "Unfollow" if author.following else "Follow",
                    lambda: do_follow(follow),
                    "Following" if author.following else "Follow",
                )
                follow.add_css_class("suggested-action" if not author.following else "flat")
                self.online_control(follow)
                controls.append(follow)
                controls.append(
                    self.online_control(
                        button(
                            "",
                            "Mute or unmute this account",
                            lambda: moderation("mute"),
                            "Unmute" if author.muted else "Mute",
                        )
                    )
                )
                controls.append(
                    self.online_control(
                        button(
                            "",
                            "Block or unblock this account",
                            lambda: moderation("block"),
                            "Unblock" if author.blocking else "Block",
                        )
                    )
                )
            browser = button(
                "web-browser-symbolic",
                "Open profile / report in Bluesky",
                lambda: self.open_uri("https://bsky.app/profile/" + author.did),
            )
            controls.append(browser)
            filters = Gtk.DropDown.new_from_strings(["Posts", "Posts and replies", "Media"])
            options = ["posts_no_replies", "posts_with_replies", "posts_with_media"]
            filters.set_selected(options.index(state["filter"]))
            filters.set_tooltip_text("Profile post filter")

            def filtered(row, _ps):
                state["filter"] = options[row.get_selected()]
                more(True)

            state["filters"] = filters
            filters.connect("notify::selected", filtered)
            controls.append(filters)
            intro.append(controls)
            page.profile_controls = controls
            page.profile_filter = filters
            page.profile_browser = browser
            view = FeedView(self)
            view.set_header(intro)
            view.load_more = lambda: more(False)
            view.refresh = lambda: more(True)
            state["view"] = view
            page.content_view = view
            page.profile_title = ProfileTitle(header, view, identity, author)
            toolbar.set_content(view)
            more(True)

        def more(reset):
            if page in self.page_requests:
                return
            view = state["view"]
            view.paging.begin("Loading posts…", reset=reset)
            state["filters"].set_sensitive(False)

            def done(result):
                filters = state.get("filters")
                if filters:
                    filters.set_sensitive(True)
                pager = state["pager"]
                pager.merge(result, reset=reset)
                added = view.set_posts(pager.posts, reset=reset)
                view.load_more = lambda: more(False)
                view.paging.complete(
                    pager.cursor,
                    len(result.posts) if reset else added,
                    "No posts here yet." if not pager.posts else "",
                )

            async def request():
                return await self.service.author_feed(
                    actor, None if reset else state["pager"].cursor, state["filter"]
                )

            def failed(msg):
                state["filters"].set_sensitive(True)
                view.load_more = lambda: more(reset)
                view.paging.fail(msg)

            submit_request(self, page, request(), done, failed, page=page)

        def do_follow(b):
            if self.read_only or getattr(b, "online_busy", False):
                return
            self.online_control(b, busy=True)
            original = state["author"]
            b.set_label("Follow" if original.following else "Following")

            def done(a):
                state["author"] = a
                b.set_label("Following" if a.following else "Follow")
                b.set_tooltip_text("Unfollow" if a.following else "Follow")
                self.online_control(b, busy=False)

            self.worker.submit(
                self.service.follow(state["author"]),
                guard(self, page, done),
                guard(
                    self,
                    page,
                    lambda msg: (
                        b.set_label("Following" if original.following else "Follow"),
                        self.online_control(b, busy=False),
                        self.toast(msg),
                    ),
                ),
            )

        def moderation(kind):
            if self.read_only:
                return
            author = state["author"]
            alert = Adw.AlertDialog(
                heading=f"Change {kind} for {author.name}?",
                body="This changes how you interact with this account on Bluesky. Blocking is public; muting is private.",
            )
            alert.add_response("cancel", "Cancel")
            alert.add_response("apply", "Apply")
            alert.set_response_appearance("apply", Adw.ResponseAppearance.DESTRUCTIVE)

            def response(_alert, value):
                if value == "apply" and not self.read_only:

                    def done(a):
                        state["author"] = a
                        render()
                        self.refresh()

                    self.worker.submit(
                        self.service.moderate(author, kind),
                        guard(self, page, done),
                        guard(self, page, self.toast),
                    )

            alert.connect("response", response)
            alert.present(self)

        load()

    def search(self):
        self.go_home()
        page, toolbar, _header = self.new_page("Search")
        state = {
            "serial": 0,
            "pager": Pager(),
            "people_pager": RecordPager(lambda author: author.did),
            "query": "",
            "people": False,
        }

        def author_row(author):
            row = Adw.ActionRow(
                use_markup=False,
                title=author.name,
                subtitle="@" + author.handle,
                activatable=True,
                margin_start=16,
                margin_end=16,
            )
            row.add_prefix(avatar(author, self))
            row.connect("activated", lambda _: self.profile(author.did))
            rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            rows.append(row)
            return rows

        view = SearchView(
            self,
            render=lambda value: (
                author_row(value) if isinstance(value, Author) else PostRow(value, self)
            ),
        )
        entry, mode = view.entry, view.mode
        page.focus_widget, page.search_mode = entry, mode
        view.refresh = lambda: run(True)
        state["view"] = view
        page.content_view = view
        toolbar.set_content(view)

        def clear():
            state["serial"] += 1
            request = self.page_requests.pop(page, None)
            if request:
                request.cancel()
            state.update(
                query="", pager=Pager(), people_pager=RecordPager(lambda author: author.did)
            )
            view.search_started = False
            view.set_items([], view.key, reset=True)
            view.paging.complete(None, 0)
            view.focus_header(entry)

        def run(reset=True):
            if reset:
                query = entry.get_text().strip()
                if not query:
                    clear()
                    return
                view.search_started = True
                view.model.remove_all()
                state.update(
                    query=query,
                    people=mode.get_selected() == 1,
                    pager=Pager(),
                    people_pager=RecordPager(lambda author: author.did),
                )
            elif not (state["people_pager"] if state["people"] else state["pager"]).cursor:
                return
            state["serial"] += 1
            serial = state["serial"]
            results = state["people_pager"] if state["people"] else state["pager"]
            cursor = results.cursor
            view.paging.begin("Searching…", reset=reset)

            def done(value):
                if serial != state["serial"]:
                    return
                if state["people"]:
                    authors, next_cursor = value
                    results.merge(authors, next_cursor, reset=reset)
                    added = view.set_items(results.items, lambda author: author.did, reset=reset)
                else:
                    state["pager"].merge(value, reset=reset)
                    added = view.set_posts(state["pager"].posts, reset=reset)
                view.load_more = lambda: run(False)
                view.paging.complete(
                    results.cursor,
                    view.model.get_n_items() if reset else added,
                    "No results found." if view.model.get_n_items() == 0 else "",
                )

            def failed(msg):
                view.load_more = lambda: run(reset)
                view.paging.fail(msg)

            submit_request(
                self,
                page,
                self.service.search(state["query"], state["people"], None if reset else cursor),
                done,
                failed,
                page=page,
            )

        entry.connect("activate", lambda *_: run())
        entry.connect("changed", lambda *_: clear() if not entry.get_text().strip() else None)
        mode.connect("notify::selected", lambda *_: run())
        view.focus_header(entry)

    def notifications(self):
        self.go_home()
        page, toolbar, header = self.new_page("Notifications")
        state = {
            "automatic": False,
        }

        def notice_key(notice):
            return notice.uri, notice.author.did, notice.reason, notice.indexed_at

        records = RecordPager(notice_key)

        view = FeedView(
            self, render=lambda notice: NoticeRow(notice, self), update=NoticeRow.update_notice
        )
        view.refresh = lambda: load()
        view.auto_key = "notifications"
        view.auto_refresh = lambda: load(automatic=True)
        toolbar.set_content(view)

        def apply(value, reset):
            if not page.get_parent() or view.paging.closed:
                return
            notices, next_cursor, timestamp = value
            records.merge(notices, next_cursor, reset=reset)
            view.clear_update()
            added = view.set_items(records.items, notice_key, reset=reset)
            view.load_more = lambda: load(False)
            view.paging.complete(
                records.cursor,
                view.model.get_n_items() if reset else added,
                "You’re all caught up." if not records.items else "",
            )

            def seen():
                if self.read_only or getattr(mark, "online_busy", False):
                    return
                self.online_control(mark, busy=True)
                keys = {notice_key(n) for n in records.items}
                generation = self.generation

                def marked(_):
                    self.online_control(mark, busy=False)
                    if generation != self.generation or not page.get_parent():
                        return
                    # The fixed read marker preserves layout, so keep the user's
                    # current scroll/focus instead of starting a corrective scroll.
                    records.items = [
                        replace(n, read=True) if notice_key(n) in keys else n for n in records.items
                    ]
                    view.set_items(records.items, notice_key)
                    self.toast("Notifications marked as seen")
                    self.worker.submit(
                        self.service.unread(),
                        lambda count: (
                            self.unread_received(count) if generation == self.generation else None
                        ),
                        self.toast,
                    )

                self.worker.submit(
                    self.service.mark_seen(timestamp),
                    guard(self, page, marked),
                    guard(
                        self,
                        page,
                        lambda msg: (self.online_control(mark, busy=False), self.toast(msg)),
                    ),
                )

            self.online_control(mark, ready=True)
            state["mark_seen"] = seen

        def load(reset=True, automatic=False):
            if page in self.page_requests:
                if not automatic and state["automatic"]:
                    old = self.page_requests.pop(page, None)
                    if old:
                        old.cancel()
                else:
                    return False
            if not reset and not records.cursor:
                return False
            state["automatic"] = automatic
            cursor = records.cursor
            if not automatic:
                view.paging.begin("Loading notifications…", reset=reset)
            policy = self.interactions.policy(view.auto_key)

            def done(value):
                if reset:
                    policy.finished(time.time(), True)
                if automatic:
                    notices = value[0]
                    known = {notice_key(n) for n in records.items}
                    count = sum(notice_key(n) not in known for n in notices)
                    if list(notices) != records.items[: len(notices)]:
                        title = (
                            "1 new notification"
                            if count == 1
                            else f"{count} new notifications"
                            if count
                            else "Notifications updated"
                        )
                        view.offer_update(
                            title,
                            lambda: apply(value, True),
                            revision=frozenset(notice_key(n) for n in notices),
                        )
                else:
                    apply(value, reset)

            def failed(msg):
                if reset:
                    policy.finished(time.time(), False)
                if not automatic:
                    view.load_more = lambda: load(reset)
                    view.paging.fail(msg)

            submit_request(
                self,
                page,
                self.service.notifications(None if reset else cursor),
                done,
                failed,
                page=page,
            )
            return True

        mark = button(
            "object-select-symbolic",
            "Mark all notifications as seen",
            lambda: state.get("mark_seen", lambda: None)(),
        )
        self.online_control(mark, ready=False)
        header.pack_end(mark)
        header.pack_end(button("view-refresh-symbolic", "Refresh notifications", lambda: load()))
        load()

    def preferences(self):
        Preferences(self).present(self)

    def redisplay_media(self, *_args):
        for view in self.views:
            place = view.interaction.capture()
            count = view.model.get_n_items()
            if count:
                view.model.items_changed(0, count, count)
                if place and view.get_mapped():
                    view.interaction.restore(place)

    def about(self):
        about = Adw.AboutDialog(
            application_name="Skyloom",
            application_icon=APP_ID,
            version=VERSION,
            developer_name="Nick Richards",
            developers=["Nick Richards"],
            license_type=Gtk.License.GPL_3_0,
            comments="A native client for Bluesky. Independent and not affiliated with Bluesky.",
        )
        about.present(self)

    def sign_out(self, preferences):
        if self.composer:
            self.composer.close()
            return
        alert = Adw.AlertDialog(
            heading="Leave demo?" if self.demo else "Sign out?",
            body="Demo drafts and cached content will be removed."
            if self.demo
            else "This removes your saved session, drafts and cached content from this device.",
        )
        alert.add_response("cancel", "Cancel")
        alert.add_response("signout", "Leave demo" if self.demo else "Sign out")
        alert.set_response_appearance("signout", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_default_response("cancel")
        alert.set_close_response("cancel")

        def response(_a, value):
            if value != "signout":
                return
            self.generation += 1
            for request in self.page_requests.values():
                if request:
                    request.cancel()
            self.page_requests.clear()
            self.mutations.clear()
            preferences.sign_out_row.set_sensitive(False)
            preferences.set_can_close(False)

            def done(value):
                preferences.set_can_close(True)
                preferences.close()
                self.signed_out(value)

            def failed(message):
                preferences.set_can_close(True)
                preferences.sign_out_row.set_sensitive(True)
                preferences.add_toast(Adw.Toast(title=message))

            self.worker.submit(self.service.sign_out(), done, failed)

        alert.connect("response", response)
        alert.present(preferences)

    def signed_out(self, _value):
        self.thread_cache.clear()
        self.post_positions = None
        self.images.use_account(None)
        for view in self.views:
            view.close()
        self.interactions.policies.clear()
        self.interactions.undo_action = None
        self.auto_feeds.clear()
        if self.refresh_monitor:
            self.refresh_monitor.changed()
        if self.demo:
            self.destroy()
            return
        self.stack.set_visible_child_name("welcome")
        self.login_button.set_sensitive(True)
        self.login_feedback.set_label("Signed out. Use a dedicated app password to sign in again.")
        self.handle.set_text("")
        self.images.cache.clear()
        self.revealed_labels.clear()
        shell = self.stack.get_child_by_name("shell")
        if shell:
            self.stack.remove(shell)
        self.split.set_sidebar(None)
        self.split.set_content(None)
        self.views, self.pagers, self.feed_views = [], {}, {}

    def close_requested(self, *_args):
        if self.composer:
            self.composer.close()
            return True
        for view in self.feed_views.values():
            if view.reading:
                view.reading.flush()
        self.cancel_startup()
        return False

    def cancel_startup(self, *_args):
        if self.closing:
            return
        self.closing = True
        self.restore_serial += 1
        if self.request:
            self.request.cancel()
            self.request = None
        self.stack.close()
