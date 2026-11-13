"""Private server bookmarks through the pinned SDK, separate from reading positions."""

import re
import time
from dataclasses import dataclass, replace

from .domain import Page, Post, post_from
from .errors import UserError
from .sdk import page_items


@dataclass(frozen=True, slots=True)
class UnavailableBookmark:
    uri: str
    reason: str


@dataclass(frozen=True, slots=True)
class BookmarkPage:
    items: tuple[Post | UnavailableBookmark, ...]
    cursor: str | None = None


def bookmark_page(value):
    items = []
    for bookmark in value.get("bookmarks", []):
        subject = bookmark.get("subject") or {}
        uri = subject.get("uri", "")
        item = bookmark.get("item") or {}
        kind = item.get("$type", "")
        if not uri:
            continue
        if kind == "app.bsky.feed.defs#postView" and item.get("uri") == uri:
            items.append(replace(post_from(item), bookmarked=True))
        else:
            reason = (
                "This post is blocked."
                if kind == "app.bsky.feed.defs#blockedPost"
                else "This post is unavailable."
            )
            items.append(UnavailableBookmark(uri, reason))
    return BookmarkPage(tuple(items), value.get("cursor"))


def with_bookmark(post, uri, saved):
    if not isinstance(post, Post):
        return post
    changes = {"bookmarked": saved} if post.uri == uri else {}
    if post.quote:
        quoted = with_bookmark(post.quote, uri, saved)
        if quoted != post.quote:
            changes["quote"] = quoted
    return replace(post, **changes) if changes else post


def reconcile_bookmarks(post, changes, *, now=None):
    """Briefly retain confirmed mutations across lagging AppView responses."""
    if not isinstance(post, Post):
        return post
    now = time.monotonic() if now is None else now
    known = changes.get(post.uri)
    fields = {}
    if known and (len(known) < 3 or now < known[2]):
        fields["bookmarked"] = known[1]
    if post.quote:
        quote = reconcile_bookmarks(post.quote, changes, now=now)
        if quote != post.quote:
            fields["quote"] = quote
    return replace(post, **fields) if fields else post


class BookmarkService:
    async def bookmarks(self, cursor=None):
        async with self.authenticated():
            result = await self.client.app.bsky.bookmark.get_bookmarks(
                {"limit": 30, "cursor": cursor}
            )
            page = bookmark_page({"bookmarks": page_items(result), "cursor": result.cursor})
            posts = tuple(item for item in page.items if isinstance(item, Post))
            if not posts:
                return page
            reconciled = await self._io("reconcile_page", Page(posts))
            latest = {post.uri: post for post in reconciled.posts}
            items = []
            for item in page.items:
                post = latest.get(item.uri)
                if post and post.unavailable == "This post was deleted.":
                    item = UnavailableBookmark(item.uri, post.unavailable)
                elif post:
                    item = post
                items.append(item)
            return replace(page, items=tuple(items))

    async def bookmark(self, post, saved, *, expected_account=None):
        uri = post.uri
        if not re.fullmatch(r"at://[^/?#]+/app\.bsky\.feed\.post/[A-Za-z0-9._:~-]{1,512}", uri):
            raise UserError("This post cannot be bookmarked. Refresh and try again.")
        async with self.authenticated():
            if expected_account is not None and self.account is not expected_account:
                raise UserError("The signed-in account changed. Reopen bookmarks.")
            if saved:
                if (
                    not isinstance(post, Post)
                    or not post.cid
                    or post.unavailable == "This post was deleted."
                ):
                    raise UserError("This post is unavailable and cannot be bookmarked.")
                await self.client.app.bsky.bookmark.create_bookmark({"uri": uri, "cid": post.cid})
            else:
                await self.client.app.bsky.bookmark.delete_bookmark({"uri": uri})
            await self._io("bookmark_post", uri, saved)
        return replace(post, bookmarked=saved) if isinstance(post, Post) else post
