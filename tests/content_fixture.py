"""Invented post/controller fixtures shared by native widget tests."""

from types import SimpleNamespace
from weakref import WeakSet

from gtk_support import DISPLAY

if DISPLAY:
    from gi.repository import Gio, Gtk


class ContentFixture:
    def __init__(self):
        from skyloom import APP_ID
        from skyloom.domain import Author, Media, Post

        schema = Gio.SettingsSchemaSource.get_default().lookup(APP_ID, True)
        if schema is None:
            raise RuntimeError("Skyloom settings schema is required")
        settings = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        self.requests = []

        def get(url, local=False):
            self.requests.append(url)

            async def result():
                return None

            return result()

        def submit(coro, *args, **kwargs):
            coro.close()

        self.window = SimpleNamespace(
            settings=settings,
            content_gates=WeakSet(),
            revealed_labels={},
            images=SimpleNamespace(
                get=get,
                has_cached=lambda *_args: False,
                bind=lambda *_: None,
                unbind=lambda *_: None,
            ),
            worker=SimpleNamespace(submit=submit),
            read_only=False,
            service=SimpleNamespace(
                account=Author("did:example:viewer", "viewer.invalid", "Invented viewer")
            ),
            mutations=set(),
            profile=lambda *_: None,
            open_uri=lambda *_: None,
            thread=lambda *_: None,
            compose=lambda **_: None,
            mutate=lambda *_: None,
            bookmark=lambda *_: None,
            copy=lambda *_: None,
            toast=lambda *_: None,
            preferences=lambda: None,
            view_media=lambda *_: None,
            views=[],
        )
        self.post = Post(
            "at://did:example:labelled/app.bsky.feed.post/1",
            "fixture-cid",
            Author("did:example:labelled", "labelled.invalid", "Labelled fixture"),
            "This labelled post remains readable.",
            "2026-10-27T08:00:00Z",
            labels=("sexual",),
            images=(Media("demo-landscape", "Invented landscape", local=True),),
        )

    def labels(self, widget):
        from skyloom.widgets import list_children

        result = []
        if isinstance(widget, Gtk.Label):
            result.append(widget.get_text())
        for child in list_children(widget):
            result.extend(self.labels(child))
        return result

    def walk(self, widget):
        from skyloom.widgets import list_children

        yield widget
        for child in list_children(widget):
            yield from self.walk(child)

    def pump(self, milliseconds=100):
        from gi.repository import GLib

        loop = GLib.MainLoop()
        GLib.timeout_add(milliseconds, lambda: (loop.quit(), False)[1])
        loop.run()
