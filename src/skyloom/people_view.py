"""Paged followers and follows reuse the native virtualised people rows."""

from .records import RecordPager
from .request_scope import submit
from .widgets import AuthorRow, FeedView


def open_people(window, author, kind):
    title = "Followers" if kind == "followers" else "Following"
    page, toolbar, _header = window.new_page(f"{title} · {author.name}")
    pager = RecordPager(lambda value: value.did)
    view = FeedView(
        window,
        recycle_record=lambda value, row: (
            row.bind_author(value) if row else AuthorRow(value, window)
        ),
    )
    page.content_view = view
    toolbar.set_content(view)

    def more(reset=False):
        if page in window.page_requests or (not reset and not pager.cursor):
            return
        view.paging.begin(f"Loading {title.lower()}…", reset=reset)

        def done(result):
            authors, cursor = result
            place = view.interaction.capture()
            pager.merge(authors, cursor, reset=reset, anchor=place.key if place else None)
            added = view.set_items(pager.items, lambda value: value.did, reset=reset)
            view.load_more = lambda: more(False)
            view.paging.complete(
                pager.cursor,
                len(authors) if reset else added,
                f"No {title.lower()} yet." if not pager.items else "",
            )

        def failed(msg):
            view.load_more = lambda: more(reset)
            view.paging.fail(msg)

        submit(
            window,
            page,
            window.service.follow_people(author.did, kind, None if reset else pager.cursor),
            done,
            failed,
            page=page,
        )

    view.refresh = lambda: more(True)
    view.load_more = lambda: more(True)
    more(True)
    return page
