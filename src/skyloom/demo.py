"""Explicit offline backend, sharing production models and widgets."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from .bookmark_service import BookmarkPage, UnavailableBookmark
from .conversation import ThreadPage
from .domain import (
    Media,
    Notice,
    Page,
    Post,
    author_from,
    deleted_post,
    find_post,
    reconcile_deleted,
)
from .errors import UserError
from .profile_service import COLLECTION, EditableProfile, validate_profile
from .richtext import facets_for, validate
from .storage import Storage
from .thread_service import DemoThreadService


class DemoService(DemoThreadService):
    def __init__(self, fixture):
        self.fixture = json.loads(Path(fixture).read_text(encoding="utf-8"))
        self.account = author_from(self.fixture["demo_account"])
        self.directory = TemporaryDirectory(prefix="skyloom-demo-")
        self.storage = Storage(Path(self.directory.name))
        self.storage_token = self.storage.activate(self.account.did)
        self.draft_lock = asyncio.Lock()
        self.offline = False
        self.posts = []
        self.seen = False
        for d in self.fixture["posts"]:
            viewer = d["viewer"]
            images, external = [], None
            for e in d["embeds"]:
                images.extend(
                    Media(i["local_fixture"], i["alt"], local=True) for i in e.get("images", [])
                )
                if e["kind"] == "external":
                    external = (e["url"], e["title"], e["description"])
            p = Post(
                d["uri"],
                d["cid"],
                author_from(d["author"]),
                d["text"],
                d["created_at"],
                d["like_count"],
                d["repost_count"],
                d["reply_count"],
                "at://demo/like" if viewer["liked"] else "",
                "at://demo/repost" if viewer["reposted"] else "",
                images=tuple(images),
                external=external,
            )
            if d["id"] == "p4":
                p = replace(p, quote=self.posts[0])
            self.posts.append(p)

    async def close(self):
        if self.account:
            account, self.account = self.account, None
            await asyncio.to_thread(self.storage.clear, account.did)
        await asyncio.to_thread(self.directory.cleanup)

    async def pause(self):
        await asyncio.sleep(0.06)
        if self.offline:
            raise UserError("Demo: network disconnected. Cached posts remain readable.")

    async def feeds(self):
        return [(f["id"], f["name"]) for f in self.fixture["feeds"]]

    async def feed(self, feed="following", cursor=None):
        await self.pause()
        return await self.cached(feed)

    async def cached(self, feed):
        posts = (
            self.posts
            if feed == "following"
            else self.posts[1::2]
            if feed == "design"
            else self.posts[::2]
        )
        return Page(tuple(posts))

    async def cached_state(self, feed):
        async with self.draft_lock:
            value = await asyncio.to_thread(
                self.storage.run, self.account.did, self.storage_token, "cached_state", feed
            )
            if not value.pager.posts:
                value.pager.merge(await self.cached(feed), reset=True)
            return value

    async def cached_page(self, feed, cursor):
        return await asyncio.to_thread(
            self.storage.run, self.account.did, self.storage_token, "cached_page", feed, cursor
        )

    async def save_feed_state(self, feed, pager, bookmark, account):
        async with self.draft_lock:
            if self.account is account and account is not None:
                await asyncio.to_thread(
                    self.storage.run,
                    account.did,
                    self.storage_token,
                    "checkpoint",
                    feed,
                    pager,
                    bookmark,
                )

    async def save_active_feed(self, feed, account):
        async with self.draft_lock:
            if self.account is account and account is not None:
                await asyncio.to_thread(
                    self.storage.run, account.did, self.storage_token, "put", "reading:feed", feed
                )

    async def cached_post(self, uri):
        return find_post(self.posts, uri)

    async def thread(self, uri, *, earlier=False, replies_only=False):
        await self.pause()
        p = next((p for p in self.posts if p.uri == uri), self.posts[0])
        reply = replace(
            self.posts[2],
            uri=self.posts[2].uri + "reply",
            text="Yes — making the conversation easy to follow makes all the difference.",
            root=p.root or (p.uri, p.cid),
            parent=(p.uri, p.cid),
            context="Reply",
        )
        return self.apply_gate_controls(ThreadPage((replace(p, context="Selected post"), reply)))

    async def editable_profile(self):
        await self.pause()
        author = await self.profile(self.account.did)
        record = getattr(
            self,
            "profile_record",
            {"$type": COLLECTION, "displayName": author.name, "description": author.bio},
        )
        return EditableProfile(
            self.account.did,
            str(getattr(self, "profile_revision", 0)),
            json.dumps(record),
            self.account,
        )

    async def update_profile(
        self, original, name, description, avatar=None, banner=None, *, current=None
    ):
        await self.pause()
        if (
            original.did != self.account.did
            or (original.account is not None and original.account is not self.account)
            or original.cid != str(getattr(self, "profile_revision", 0))
        ):
            raise UserError("This profile changed. Reopen the profile editor.")
        if error := validate_profile(name, description):
            raise UserError(error)
        record = original.record
        record.update(displayName=name, description=description)
        for field, value in (("avatar", avatar), ("banner", banner)):
            if value is not None:
                record[field] = value
        self.profile_record = record
        self.profile_revision = getattr(self, "profile_revision", 0) + 1
        current = await self.profile(self.account.did)
        self.profile_override = replace(
            current,
            name=name or current.handle,
            bio=description,
            avatar=current.avatar if avatar is None else avatar,
            banner=current.banner if banner is None else banner,
            avatar_local=current.avatar_local if avatar is None else bool(avatar),
            banner_local=current.banner_local if banner is None else bool(banner),
        )
        self.posts = [
            replace(post, author=self.profile_override)
            if post.author.did == self.account.did
            else post
            for post in self.posts
        ]
        return self.profile_override

    async def follow_people(self, actor, kind, cursor=None):
        await self.pause()
        if kind not in ("followers", "following"):
            raise UserError("This people list is not supported.")
        authors = {post.author.did: post.author for post in self.posts if post.author.did != actor}
        return tuple(authors.values()) if cursor is None else (), None

    async def profile(self, actor):
        await self.pause()
        if actor == self.account.did and hasattr(self, "profile_override"):
            return self.profile_override
        a = next((p.author for p in self.posts if p.author.did == actor), self.account)
        return replace(
            a,
            bio="An invented account for exploring Skyloom. These posts stay on this computer.",
            followers=128,
            following_count=46,
            posts_count=82,
        )

    async def author_feed(self, actor, cursor=None, feed_filter="posts_no_replies"):
        await self.pause()
        return Page(tuple(p for p in self.posts if p.author.did == actor))

    async def delete_post(self, post, *, expected_account=None):
        await self.pause()
        if expected_account is not None and self.account is not expected_account:
            raise UserError("The signed-in account changed. Reopen the post.")
        if post.author.did != self.account.did:
            raise UserError("Only your own posts can be deleted.")
        self.posts = [reconcile_deleted(p, {post.uri}) for p in self.posts]
        await asyncio.to_thread(self.storage.delete_post, self.account.did, post.uri)
        return deleted_post(post)

    async def bookmarks(self, cursor=None):
        await self.pause()
        return BookmarkPage(tuple(p for p in self.posts if p.bookmarked))

    async def bookmark(self, post, saved, *, expected_account=None):
        await self.pause()
        if expected_account is not None and self.account is not expected_account:
            raise UserError("The signed-in account changed. Reopen bookmarks.")
        if isinstance(post, UnavailableBookmark):
            return post
        updated = replace(post, bookmarked=saved)
        self.posts = [updated if p.uri == post.uri else p for p in self.posts]
        return updated

    async def mutate(self, post, kind):
        await self.pause()
        if kind == "like":
            new = replace(
                post,
                like_uri="" if post.like_uri else "at://demo/like",
                likes=max(0, post.likes + (-1 if post.like_uri else 1)),
            )
        else:
            new = replace(
                post,
                repost_uri="" if post.repost_uri else "at://demo/repost",
                reposts=max(0, post.reposts + (-1 if post.repost_uri else 1)),
            )
        self.posts = [new if p.uri == new.uri else p for p in self.posts]
        return new

    async def follow(self, author):
        await self.pause()
        return replace(author, following="" if author.following else "at://demo/follow")

    async def moderate(self, author, kind):
        await self.pause()
        return (
            replace(author, muted=not author.muted)
            if kind == "mute"
            else replace(author, blocking="" if author.blocking else "at://demo/block")
        )

    async def search(self, query, people=False, cursor=None):
        await self.pause()
        if people:
            return tuple(
                p.author
                for p in self.posts
                if query.lower() in (p.author.name + p.author.handle).lower()
            ), None
        return Page(tuple(p for p in self.posts if query.lower() in p.text.lower()))

    async def notifications(self, cursor=None):
        await self.pause()
        originals = {p["id"]: p for p in self.fixture["posts"]}
        actors = {p["author"]["handle"]: author_from(p["author"]) for p in self.fixture["posts"]}
        notices = []
        for n in self.fixture["notifications"]:
            post = originals.get(n.get("post_id"))
            uri = post["uri"] if post else ""
            timestamp = post["created_at"] if post else "2026-10-25T08:15:00Z"
            notices.append(
                Notice(
                    actors[n["from"]], n["type"], uri, uri, self.seen or not n["unread"], timestamp
                )
            )
        return tuple(notices), None, datetime.now(UTC).isoformat()

    async def mark_seen(self, timestamp):
        await self.pause()
        self.seen = True

    async def unread(self):
        return 0 if self.seen else 2

    async def drafts(self):
        return await asyncio.to_thread(self.storage.drafts, self.account.did)

    async def draft_get(self, key):
        return await asyncio.to_thread(self.storage.get, self.account.did, "draft:" + key, {})

    async def draft_save(self, key, value):
        async with self.draft_lock:
            await asyncio.to_thread(self.storage.put, self.account.did, "draft:" + key, value)

    async def send(
        self, text, attachments=(), reply=None, quote=None, *, video=None, expected_account=None
    ):
        await self.pause()
        if expected_account is not None and self.account is not expected_account:
            raise UserError("The signed-in account changed. Reopen the composer.")
        if error := validate(text, attachments, video):
            raise UserError(error)

        async def resolve(handle):
            return "did:example:mention"

        p = Post(
            f"at://{self.account.did}/app.bsky.feed.post/demo-{len(self.posts)}",
            "demo-cid",
            self.account,
            text,
            datetime.now(UTC).isoformat(),
            facets=tuple(await facets_for(text, resolve)),
            images=tuple(Media(a.path, a.alt, local=True) for a in attachments),
            root=(reply.root or (reply.uri, reply.cid)) if reply else None,
            quote=quote,
            video=self.demo_video(video),
        )
        self.posts.insert(0, p)
        return SimpleNamespace(uri=p.uri, cid=p.cid)

    @staticmethod
    def demo_video(video):
        if video is None:
            return None
        from .domain import Video

        return Video(video.path, video.alt, width=video.width, height=video.height, local=True)

    async def sign_out(self):
        async with self.draft_lock:
            if self.account:
                account, self.account = self.account, None
                await asyncio.to_thread(self.storage.clear, account.did)
