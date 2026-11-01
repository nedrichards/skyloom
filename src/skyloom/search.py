"""Search fields, results and viewport-filling states share one native scroller."""

from gi.repository import Gtk

from .widgets import FeedView, box, label


class SearchView(FeedView):
    def __init__(self, window, render=None):
        super().__init__(window, render)
        self.search_started = False
        self.entry = Gtk.SearchEntry(placeholder_text="Search Bluesky", hexpand=True)
        self.entry.update_property([Gtk.AccessibleProperty.LABEL], ["Search posts or people"])
        self.mode = Gtk.DropDown.new_from_strings(["Posts", "People"])
        self.mode.set_tooltip_text("Search type")
        fields = box(spacing=12, margin=16)
        fields.append(self.entry)
        fields.append(self.mode)
        self.status_box = box(spacing=12, margin=32)
        self.status_box.set_vexpand(True)
        self.status_box.set_valign(Gtk.Align.CENTER)
        self.status_icon = Gtk.Image(icon_name="edit-find-symbolic", pixel_size=64)
        self.spinner = Gtk.Spinner(width_request=64, height_request=64)
        self.status_box.append(self.status_icon)
        self.status_box.append(self.spinner)
        self.status_title = label("", "title-1", xalign=0.5, justify=Gtk.Justification.CENTER)
        self.status_description = label(
            "", "dim-label", xalign=0.5, justify=Gtk.Justification.CENTER
        )
        self.status_box.append(self.status_title)
        self.status_box.append(self.status_description)
        self.status_action = Gtk.Button(halign=Gtk.Align.CENTER)
        self.status_action.add_css_class("suggested-action")
        self.status_action.connect("clicked", lambda _button: self.paging.request())
        self.status_box.append(self.status_action)
        fields.append(self.status_box)
        self.set_header(fields)
        self.paging_changed()

    def paging_changed(self):
        self.status_active = self.model.get_n_items() == 0
        self.status_box.set_visible(self.status_active)
        self.fill_header = self.status_active
        self.fit_header()
        state = self.paging
        busy = self.status_active and state.busy
        self.spinner.set_visible(busy)
        self.spinner.set_spinning(busy)
        self.status_icon.set_visible(not busy)
        self.status_icon.set_from_icon_name(
            "network-error-symbolic" if state.error else "edit-find-symbolic"
        )
        if state.busy:
            title, description = "Searching…", ""
        elif state.error:
            title, description = "Couldn’t search", state.error
        elif self.search_started:
            title, description = (
                ("No results on this page", "Load more or try another search.")
                if state.cursor
                else ("No results found", "Try another search.")
            )
        else:
            title, description = "Search Bluesky", "Find posts and people."
        self.status_title.set_label(title)
        self.status_description.set_label(description)
        self.status_description.set_visible(bool(description))
        self.status_action.set_label("Try again" if state.error else "Load more")
        self.status_action.set_visible(
            self.status_active and not state.busy and bool(state.error or state.cursor)
        )
        super().paging_changed()

    def close(self):
        self.spinner.set_spinning(False)
        super().close()
