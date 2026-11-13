"""Immutable view data and defensive lexicon mapping; no GTK or network imports."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

from .feed_state import Bookmark, FeedGap


@dataclass(frozen=True, slots=True)
class Author:
    did: str
    handle: str
    name: str
    avatar: str = ""
    bio: str = ""
    followers: int | None = None
    following_count: int | None = None
    posts_count: int | None = None
    following: str = ""
    muted: bool = False
    blocking: str = ""
    labels: tuple[str, ...] = ()
    banner: str = ""


@dataclass(frozen=True, slots=True)
class Media:
    url: str
    alt: str
    fullsize: str = ""
    local: bool = False


@dataclass(frozen=True, slots=True)
class Video:
    playlist: str
    alt: str = ""
    thumbnail: str = ""
    width: int = 0
    height: int = 0
    local: bool = False


@dataclass(frozen=True, slots=True)
class Post:
    uri: str
    cid: str
    author: Author
    text: str
    created: str
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    like_uri: str = ""
    repost_uri: str = ""
    facets: tuple[dict, ...] = ()
    images: tuple[Media, ...] = ()
    quote: Post | None = None
    external: tuple[str, str, str] | None = None
    labels: tuple[str, ...] = ()
    context: str = ""
    root: tuple[str, str] | None = None
    unavailable: str = ""
    parent: tuple[str, str] | None = None
    bookmarked: bool = False
    reply_disabled: bool = False
    embedding_disabled: bool = False
    video: Video | None = None

    @property
    def link(self):
        return f"https://bsky.app/profile/{quote(self.author.did, safe=':')}/post/{quote(self.uri.rsplit('/', 1)[-1])}"


@dataclass(frozen=True, slots=True)
class Page:
    posts: tuple[Post, ...]
    cursor: str | None = None
    cached: bool = False


@dataclass(frozen=True, slots=True)
class Notice:
    author: Author
    reason: str
    uri: str
    subject: str
    read: bool
    indexed_at: str


def unique_posts(posts, known=()):
    """Keep the first occurrence of each incoming URI in server order."""
    seen = set(known)
    result = []
    for post in posts:
        if post.uri not in seen:
            seen.add(post.uri)
            result.append(post)
    return result


def retained_metadata(posts, values):
    keys = {post.uri for post in posts}
    return {key: value for key, value in values.items() if key in keys}


@dataclass
class Pager:
    """Bounded window, de-duplication and repeated-cursor protection."""

    posts: list[Post] = field(default_factory=list)
    cursor: str | None = None
    seen_cursors: set[str] = field(default_factory=set)
    page_starts: dict[str, str | None] = field(default_factory=dict)
    gaps: dict[str, str | None] = field(default_factory=dict)

    def projected(self, states=None):
        states = states or {}
        result = []
        for post in self.posts:
            if post.uri in self.gaps:
                result.append(states.get(post.uri, FeedGap(post.uri, self.gaps[post.uri])))
            result.append(post)
        return result

    def reconciled(self, page, *, reorder=False, anchor=None):
        """Retain omissions as history; absence from a head page is not deletion."""
        head = unique_posts(page.posts)[:250]
        if not self.posts:
            result = Pager()
            result.merge(Page(tuple(head), page.cursor), reset=True)
            return result
        known = {p.uri for p in self.posts}
        incoming = {p.uri: p for p in head}
        combined = (
            head + [p for p in self.posts if p.uri not in incoming]
            if reorder
            else [p for p in head if p.uri not in known]
            + [incoming.get(p.uri, p) for p in self.posts]
        )
        starts = self.page_starts.copy()
        if head:
            starts[head[0].uri] = None
        gaps = self.gaps.copy()
        if head and not known.intersection(incoming):
            gaps[self.posts[0].uri] = page.cursor
        # The cursor always belongs to the retained tail, never to a prepended head.
        cursor = self.cursor
        if len(combined) > 250:
            anchor_index = next((i for i, p in enumerate(combined) if p.uri == anchor), 0)
            boundaries = [
                (i, starts[p.uri]) for i, p in enumerate(combined[:251]) if starts.get(p.uri)
            ]
            if anchor_index < 250 and boundaries:
                end, cursor = boundaries[-1]
                # Retain a partial page when necessary; re-fetch from its real boundary.
                end = max(end, anchor_index + 1)
                combined = combined[:end]
            else:
                prefix = combined[: min(30, max(0, len(combined) - 220))]
                start = max(len(prefix), min(anchor_index, len(combined) - (250 - len(prefix))))
                end = start + 250 - len(prefix)
                suffix = combined[start:end]
                if end < len(combined):
                    cursor = next(
                        (starts[p.uri] for p in reversed(combined[: end + 1]) if starts.get(p.uri)),
                        page.cursor,
                    )
                if suffix and prefix:
                    gaps[suffix[0].uri] = page.cursor
                combined = prefix + suffix
        return Pager(
            combined,
            cursor,
            set(self.seen_cursors) if cursor == self.cursor else set(),
            retained_metadata(combined, starts),
            retained_metadata(combined, gaps),
        )

    def appended(self, page, *, anchor=None):
        added = unique_posts(page.posts, (p.uri for p in self.posts))
        combined = self.posts + added
        anchor_index = next((i for i, p in enumerate(combined) if p.uri == anchor), len(combined))
        start = min(max(0, len(combined) - 250), anchor_index)
        end = start + 250
        retained = combined[start:end]
        starts = self.page_starts.copy()
        if added:
            starts[added[0].uri] = self.cursor
        cursor = self.cursor if end < len(combined) else page.cursor
        # A partial retained page must be fetched again from its actual request cursor.
        seen = set(self.seen_cursors)
        if end < len(combined):
            seen.discard(cursor)
        elif cursor in seen:
            cursor = None
        elif cursor:
            seen.add(cursor)
        return Pager(
            retained,
            cursor,
            seen,
            retained_metadata(retained, starts),
            retained_metadata(retained, self.gaps),
        )

    def bridge(self, before, page, *, anchor=None):
        """Fill one known gap, stopping at a verified overlap or an exhausted cursor."""
        if before not in self.gaps:
            return self
        index = next(i for i, p in enumerate(self.posts) if p.uri == before)
        prefix, suffix = self.posts[:index], self.posts[index:]
        suffix_keys = {p.uri for p in suffix}
        prefix_keys = {p.uri for p in prefix}
        overlap = any(p.uri in suffix_keys for p in page.posts)
        added = unique_posts(page.posts, prefix_keys | suffix_keys)
        gaps = self.gaps.copy()
        if overlap:
            gaps.pop(before)
        else:
            gaps[before] = page.cursor
        starts = self.page_starts.copy()
        if added:
            starts[added[0].uri] = self.gaps[before]
        combined = prefix + added + suffix
        cursor = self.cursor
        seen = set(self.seen_cursors)
        if len(combined) > 250:
            anchor_index = next((i for i, p in enumerate(combined) if p.uri == anchor), 0)
            if anchor_index >= 250:
                return self
            # Keep the reader and the newly connected segment. Rewind the omitted
            # tail to a real cursor; pages already archived can be replayed offline.
            cursor = next(
                (starts[p.uri] for p in reversed(combined[:251]) if starts.get(p.uri)),
                self.gaps[before],
            )
            seen.clear()
            combined = combined[:250]
        return Pager(
            combined,
            cursor,
            seen,
            retained_metadata(combined, starts),
            retained_metadata(combined, gaps),
        )

    def merge(self, page: Page, reset=False):
        start = None if reset else self.cursor
        if reset:
            self.posts.clear()
            self.seen_cursors.clear()
            self.page_starts.clear()
            self.gaps.clear()
        added = unique_posts(page.posts, (p.uri for p in self.posts))
        if added:
            self.page_starts[added[0].uri] = start
        self.posts.extend(added)
        self.posts = self.posts[-250:]
        self.page_starts = retained_metadata(self.posts, self.page_starts)
        self.gaps = retained_metadata(self.posts, self.gaps)
        self.cursor = page.cursor if page.cursor not in self.seen_cursors else None
        if page.cursor:
            self.seen_cursors.add(page.cursor)


@dataclass(frozen=True, slots=True)
class CachedFeed:
    pager: Pager
    bookmark: Bookmark | None = None


def deleted_post(post):
    """Retain identity and thread edges, never the deleted record's content."""
    return replace(
        post,
        text="",
        facets=(),
        images=(),
        quote=None,
        external=None,
        video=None,
        labels=(),
        likes=0,
        reposts=0,
        replies=0,
        like_uri="",
        repost_uri="",
        unavailable="This post was deleted.",
        reply_disabled=True,
        embedding_disabled=True,
    )


def reconcile_deleted(post, deleted):
    if not isinstance(post, Post):
        return post
    if post.uri in deleted:
        return deleted_post(post)
    if post.quote:
        quote = reconcile_deleted(post.quote, deleted)
        if quote != post.quote:
            return replace(post, quote=quote)
    return post


def find_post(posts, uri):
    """Find a retained post or quoted record without revisiting quote cycles."""
    visited = set()
    for post in posts:
        while isinstance(post, Post) and post.uri not in visited:
            if post.uri == uri:
                return post
            visited.add(post.uri)
            post = post.quote
    return None


def safe_url(value: str) -> str:
    try:
        u = urlparse(value)
        return (
            value
            if u.scheme in ("https", "http") and u.hostname and not u.username and not u.password
            else ""
        )
    except ValueError:
        return ""


def safe_https_url(value: str) -> str:
    value = safe_url(value)
    return value if value.startswith("https://") else ""


def author_from(d: dict) -> Author:
    viewer = d.get("viewer") or {}
    return Author(
        did=d.get("did", ""),
        handle=d.get("handle", "Unknown account"),
        name=d.get("displayName") or d.get("display_name") or d.get("handle", "Unknown account"),
        avatar=safe_url(d.get("avatar", "")),
        bio=d.get("description", d.get("bio", "")),
        followers=d.get("followersCount"),
        following_count=d.get("followsCount"),
        posts_count=d.get("postsCount"),
        following=viewer.get("following", ""),
        muted=viewer.get("muted", False),
        blocking=viewer.get("blocking", ""),
        labels=tuple(x.get("val", "labelled") for x in d.get("labels", [])),
        banner=safe_url(d.get("banner", "")),
    )


def post_from(d: dict, depth=0) -> Post:
    rec = d.get("record") or {}
    viewer = d.get("viewer") or {}
    embed = d.get("embed") or {}
    images, quoted, external, unavailable, video = [], None, None, "", None
    kind = embed.get("$type", "")
    media = embed.get("media", embed)
    images.extend(
        Media(safe_url(im.get("thumb", "")), im.get("alt", ""), safe_url(im.get("fullsize", "")))
        for im in media.get("images", [])[:4]
    )
    if "external" in media:
        e = media["external"]
        external = (safe_url(e.get("uri", "")), e.get("title", "Link"), e.get("description", ""))
    if "video" in kind or "video" in media.get("$type", ""):
        playlist = safe_https_url(media.get("playlist", ""))
        if playlist:
            ratio = media.get("aspectRatio") or {}
            width, height = ratio.get("width", 0), ratio.get("height", 0)
            video = Video(
                playlist,
                media.get("alt", ""),
                safe_https_url(media.get("thumbnail", "")),
                width if isinstance(width, int) and 0 < width <= 100000 else 0,
                height if isinstance(height, int) and 0 < height <= 100000 else 0,
            )
        else:
            unavailable = "This video is unavailable."
    if "record" in embed and depth < 2:
        q = embed["record"]
        if "record" in q:
            q = q["record"]
        if "author" in q and "value" in q:
            quoted = post_from({**q, "record": q["value"]}, depth + 1)
        else:
            unavailable = "Quoted post is unavailable."
    reply = rec.get("reply") or {}
    root = reply.get("root")
    labels = tuple(x.get("val", "labelled") for x in d.get("labels", []))
    return Post(
        uri=d.get("uri", ""),
        cid=d.get("cid", ""),
        author=author_from(d.get("author") or {}),
        text=rec.get("text", ""),
        created=rec.get("createdAt", d.get("indexedAt", "")),
        likes=d.get("likeCount", 0),
        reposts=d.get("repostCount", 0),
        replies=d.get("replyCount", 0),
        like_uri=viewer.get("like", ""),
        repost_uri=viewer.get("repost", ""),
        bookmarked=viewer.get("bookmarked", False),
        reply_disabled=viewer.get("replyDisabled", False),
        embedding_disabled=viewer.get("embeddingDisabled", False),
        facets=tuple(rec.get("facets") or []),
        images=tuple(images),
        quote=quoted,
        external=external,
        video=video,
        labels=labels,
        root=(root["uri"], root["cid"]) if root else None,
        unavailable=unavailable,
        parent=(reply["parent"]["uri"], reply["parent"]["cid"]) if reply.get("parent") else None,
    )


def feed_from(d: dict) -> Page:
    posts = []
    for item in d.get("feed", []):
        if "post" not in item:
            continue
        p = post_from(item["post"])
        reason = item.get("reason") or {}
        if "by" in reason:
            p = replace(p, context=f"Reposted by {author_from(reason['by']).name}")
        elif item.get("reply") or p.parent or p.root:
            p = replace(p, context="In a conversation")
        posts.append(p)
    return Page(tuple(posts), d.get("cursor"))


def relative_time(value: str, now=None) -> str:
    try:
        dt = datetime.fromisoformat(value)
        seconds = max(0, int(((now or datetime.now(UTC)) - dt).total_seconds()))
        if seconds < 60:
            return "Just now"
        if seconds < 3600:
            return f"{seconds // 60} min"
        if seconds < 86400:
            return f"{seconds // 3600} h"
        return dt.astimezone().strftime("%d %b")
    except ValueError, TypeError:
        return ""
