"""SDK adapter. One instance and all its calls belong to the async worker loop."""

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from atproto import models
from atproto_client.exceptions import AtProtocolError

from .bookmark_service import BookmarkService
from .confirmed import at_or_before
from .conversation import ThreadPage, thread_from
from .credentials import KeyringError, SecretStore
from .domain import (
    Media,
    Notice,
    Page,
    Post,
    Video,
    author_from,
    deleted_post,
    feed_from,
    post_from,
)
from .errors import POST_UNAVAILABLE, UserError
from .network import new_client
from .profile_service import ProfileService
from .richtext import facets_for, validate
from .sdk import model_data as data
from .sdk import page_items
from .storage import Storage
from .thread_service import ThreadService

# Never let third-party diagnostics print HTTP headers, response bodies or session material.
for _name in ("atproto", "atproto_client", "httpx", "httpcore"):
    logger = logging.getLogger(_name)
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    logger.disabled = True


@dataclass(frozen=True, slots=True)
class Attachment:
    path: str
    alt: str


_CURRENT_ACCOUNT = object()


class Service(BookmarkService, ProfileService, ThreadService):
    def __init__(self, client=None, secrets=None, storage=None, client_factory=new_client):
        self.client_factory = client_factory
        self.client = client or self.client_factory()
        self.secrets = secrets
        self.storage = storage or Storage()
        self.account = None
        self.lock = asyncio.Lock()
        self.draft_lock = asyncio.Lock()
        self.persist_error = None
        self._storage_lease = None
        self.client.on_session_change(self._session_changed)

    def _published_head(self, page, actor, feed_filter="posts_with_replies"):
        known = {post.uri for post in page.posts}
        additions = tuple(
            self.confirmed().post(post)
            for post in reversed(self.confirmed().published())
            if post.author.did == actor
            and post.uri not in known
            and not (feed_filter == "posts_no_replies" and post.parent)
            and not (feed_filter == "posts_with_media" and not (post.images or post.video))
        )
        return replace(page, posts=(additions + page.posts)[:250])

    def _io(self, operation, *args, account=None):
        did = account or self.account.did
        lease = getattr(self, "_storage_lease", None)
        token = lease[1] if lease and lease[0] == did else self.storage.token(did)
        return asyncio.to_thread(self.storage.run, did, token, operation, *args)

    def _local(self, operation, *args, account=_CURRENT_ACCOUNT, serial=False):
        # Capture the owner when the awaitable is requested, not when a queued
        # coroutine eventually starts after a different account has signed in.
        owner = self.account if account is _CURRENT_ACCOUNT else account
        if owner is not None:
            did = owner.did
            lease = getattr(self, "_storage_lease", None)
            token = lease[1] if lease and lease[0] == did else self.storage.token(did)

        async def execute():
            if owner is None or self.account is not owner:
                return None
            value = await asyncio.to_thread(self.storage.run, did, token, operation, *args)
            if self.account is not owner:
                return None
            if operation in ("cached", "cached_page") and value is not None:
                return self.confirmed().page(value)
            if operation == "cached_post" and value is not None:
                return self.confirmed().post(value)
            if operation == "cached_state" and value is not None:
                return replace(
                    value,
                    pager=replace(
                        value.pager, posts=[self.confirmed().post(p) for p in value.pager.posts]
                    ),
                )
            return value

        async def serialized():
            async with self.draft_lock:
                return await execute()

        return serialized() if serial else execute()

    async def _secure_io(self, operation, *args):
        # Keep the surrounding SDK lock until the blocking keyring call stops.
        # Cancellation of its awaiter cannot cancel a running filesystem thread.
        task = asyncio.create_task(asyncio.to_thread(operation, *args))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            # A failed rotated-session save must still reach _session_changed's
            # persistence recovery state even when its original request was cancelled.
            error = None if task.cancelled() else task.exception()
            if error is not None:
                raise error
            raise asyncio.CancelledError
        return task.result()

    async def close(self):
        if self.secrets is not None and hasattr(self.secrets, "cancel_all"):
            self.secrets.cancel_all()
        await self.client.request.close()

    def keyring(self):
        if self.secrets is None:
            self.secrets = SecretStore()
        return self.secrets

    async def _session_changed(self, event, session):
        # Runs on every import/create/refresh; exceptions abort rather than falsely claiming persistence.
        try:
            await self._secure_io(self.keyring().save, session.export())
            self.persist_error = None
        except KeyringError as exc:
            self.persist_error = exc
            raise

    async def sign_in(self, handle, app_password, pds="https://bsky.social"):
        from urllib.parse import urlparse

        u = urlparse(pds)
        if (
            u.scheme != "https"
            or not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
        ):
            raise UserError("Enter an HTTPS PDS address without credentials or query parameters.")
        async with self.lock:
            if getattr(self.client.request, "retry_at", 0) > time.monotonic():
                raise UserError(
                    "Bluesky is limiting sign-in attempts. Wait a few minutes, then try again."
                )
            await self.client.request.close()
            self.client = self.client_factory(base_url=pds.rstrip("/"))
            self.client.on_session_change(self._session_changed)
            # Discovery is performed by the configured PDS (bsky.social for Bluesky accounts).
            try:
                profile = await self.client.login(handle.strip().lstrip("@"), app_password)
            finally:
                app_password = ""
            if profile is None:
                raise UserError("This server does not provide a Bluesky profile.")
            self.account = author_from(data(profile))
            self.reading_feed = "following"
            self.reading_choices = [("following", "Following")]
            self._storage_lease = (
                self.account.did,
                await asyncio.to_thread(self.storage.activate, self.account.did),
            )
            await self._io("put", "identity", data(profile))
            return self.account

    async def restore(self):
        async with self.lock:
            value = await self._secure_io(self.keyring().load)
            if not value:
                return None
            await self.client.login(session_string=value, fetch_bsky_profile=False)
            session = self.client._session
            self._storage_lease = (
                session.did,
                await asyncio.to_thread(self.storage.activate, session.did),
            )
            try:
                profile = await self.client.get_profile(session.did)
                self.client.me = profile
                identity = data(profile)
                await self._io("put", "identity", identity, account=session.did)
            except AtProtocolError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (400, 401, 403):
                    raise
                identity = await self._io(
                    "get",
                    "identity",
                    {"did": session.did, "handle": session.handle},
                    account=session.did,
                )
                self.client.me = models.AppBskyActorDefs.ProfileViewDetailed(**identity)
            self.account = author_from(identity)
            self.reading_choices = [
                tuple(option)
                for option in await self._io(
                    "get", "feed-options", [("following", "Following")], account=session.did
                )
            ]
            selected = await self._io("get", "reading:feed", "following", account=session.did)
            self.reading_feed = (
                selected
                if any(option[0] == selected for option in self.reading_choices)
                else "following"
            )
            return self.account

    async def sign_out(self):
        async with self.lock:
            account = self.account
            # Clear keyring first; if it fails keep account context so the user can retry.
            await self._secure_io(self.keyring().clear)
            try:
                # deleteSession expects refresh JWT, whereas the default SDK request uses access JWT.
                session = self.client._session
                await self.client.com.atproto.server.delete_session(
                    headers={"Authorization": f"Bearer {session.refresh_jwt}"},
                    ignore_session_check=True,
                )
            except Exception:  # noqa: BLE001, S110 — offline sign-out succeeds; errors may contain tokens.
                pass  # Local sign-out still succeeds offline. No sensitive details logged.
            if account:
                lease = getattr(self, "_storage_lease", None)
                token = (
                    lease[1]
                    if lease and lease[0] == account.did
                    else self.storage.token(account.did)
                )
                await asyncio.to_thread(self.storage.clear, account.did, token)
            self.account = None
            self._confirmed = None
            getattr(self, "_gate_overrides", {}).clear()
            await self.client.request.close()
            self.client = self.client_factory()
            self.client.on_session_change(self._session_changed)

    @asynccontextmanager
    async def authenticated(self):
        async with self.lock:
            if self.persist_error:
                # A failed refresh write must be retried before using the rotated token again.
                await self._session_changed(None, self.client._session)
            if not self.account:
                raise UserError("Sign in to continue.")
            yield

    async def feed(self, feed="following", cursor=None):
        async with self.authenticated():
            if feed == "following":
                result = await self.client.get_timeline(cursor=cursor, limit=30)
            else:
                result = await self.client.app.bsky.feed.get_feed(
                    {"feed": feed, "cursor": cursor, "limit": 30}
                )
            page = await self._io(
                "reconcile_page", feed_from({"feed": page_items(result), "cursor": result.cursor})
            )
            page = self.confirmed().page(page)
            if cursor is None and feed == "following":
                page = self._published_head(page, self.account.did)
            if self.account:
                await self._io("cache", feed, page, cursor)
            return page

    def cached(self, feed):
        return self._local("cached", feed)

    def cached_state(self, feed):
        return self._local("cached_state", feed)

    def cached_page(self, feed, cursor):
        return self._local("cached_page", feed, cursor)

    def save_feed_state(self, feed, pager, bookmark, account):
        return self._local("checkpoint", feed, pager, bookmark, account=account)

    def save_active_feed(self, feed, account):
        return self._local("put", "reading:feed", feed, account=account)

    def cached_post(self, uri):
        return self._local("cached_post", uri)

    async def feeds(self):
        async with self.authenticated():
            prefs = data(await self.client.app.bsky.actor.get_preferences()).get("preferences", [])
            uris = []
            for pref in prefs:
                if pref.get("$type", "").endswith("#savedFeedsPrefV2"):
                    uris.extend(
                        x["value"]
                        for x in pref.get("items", [])
                        if x.get("pinned") and x.get("type") == "feed"
                    )
                elif pref.get("$type", "").endswith("#savedFeedsPref"):
                    uris.extend(pref.get("pinned", []))
            uris = list(dict.fromkeys(uris))[:24]
            if not uris:
                await self._io("put", "feed-options", [("following", "Following")])
                return [("following", "Following")]
            response = data(await self.client.app.bsky.feed.get_feed_generators({"feeds": uris}))
            options = [("following", "Following")] + [
                (x["uri"], x.get("displayName", "Custom feed")) for x in response.get("feeds", [])
            ]
            await self._io("put", "feed-options", options)
            return options

    def cached_feeds(self):
        return self._local("get", "feed-options", [("following", "Following")])

    async def thread(self, uri, *, earlier=False, replies_only=False):
        async with self.authenticated():
            published = self.confirmed().published()
            own = next((post for post in published if post.uri == uri), None)
            try:
                node = data(
                    await self.client.get_post_thread(
                        uri, depth=0 if earlier else 2, parent_height=0 if replies_only else 20
                    )
                )["thread"]
            except AtProtocolError as exc:
                if (
                    own is None
                    or getattr(getattr(exc, "response", None), "status_code", None) != 404
                ):
                    raise
                node = {}
            if "post" not in node:
                if (
                    own is None
                    or node.get("blocked")
                    or node.get("$type", "").endswith("#blockedPost")
                ):
                    raise UserError(POST_UNAVAILABLE)
                page = ThreadPage((replace(own, context="Selected post"),))
            else:
                page = thread_from(node, include_replies=not earlier)
            if not earlier:
                known = {post.uri for post in page.posts}
                added = tuple(
                    post
                    for post in published
                    if post.uri not in known and post.parent and post.parent[0] in known
                )
                page = replace(
                    page,
                    posts=page.posts + added,
                    edges=page.edges + tuple((p.uri, p.parent[0]) for p in added),
                )
            return self.apply_gate_controls(
                self.confirmed().page(await self._io("reconcile_page", page))
            )

    async def profile(self, actor):
        async with self.authenticated():
            return self.confirmed().author(author_from(data(await self.client.get_profile(actor))))

    async def author_feed(self, actor, cursor=None, feed_filter="posts_no_replies"):
        async with self.authenticated():
            result = await self.client.get_author_feed(
                actor, cursor=cursor, filter=feed_filter, limit=30
            )
            page = feed_from({"feed": page_items(result), "cursor": result.cursor})
            page = self.confirmed().page(await self._io("reconcile_page", page))
            if cursor is None:
                page = self._published_head(page, actor, feed_filter)
            return page

    async def mutate(self, post, kind):
        async with self.authenticated():
            if post.unavailable == "This post was deleted." or kind not in ("like", "repost"):
                raise UserError("This post action is not supported.")
            field, count = ("like_uri", "likes") if kind == "like" else ("repost_uri", "reposts")
            if getattr(post, field):
                await self._delete_record(getattr(post, field), "app.bsky.feed." + kind, post.uri)
                changes = {field: "", count: max(0, getattr(post, count) - 1)}
            else:
                method = self.client.like if kind == "like" else self.client.repost
                result = await method(post.uri, post.cid)
                changes = {field: result.uri, count: getattr(post, count) + 1}
            self.confirmed().remember("post", post.uri, **changes)
            return replace(post, **changes)

    async def delete_post(self, post, *, expected_account=None):
        async with self.authenticated():
            if expected_account is not None and self.account is not expected_account:
                raise UserError("The signed-in account changed. Reopen the post.")
            prefix = f"at://{self.account.did}/app.bsky.feed.post/"
            rkey = post.uri.removeprefix(prefix)
            if (
                post.author.did != self.account.did
                or not post.uri.startswith(prefix)
                or not re.fullmatch(r"[A-Za-z0-9._:~-]{1,512}", rkey)
                or rkey in (".", "..")
                or not post.cid
            ):
                raise UserError("Only your own posts can be deleted.")
            params = {"repo": self.account.did, "collection": "app.bsky.feed.post", "rkey": rkey}
            try:
                record = data(await self.client.com.atproto.repo.get_record(params))
            except AtProtocolError as exc:
                if getattr(getattr(exc, "response", None), "status_code", None) != 404:
                    raise
            else:
                if (
                    record.get("uri") != post.uri
                    or record.get("cid") != post.cid
                    or record.get("value", {}).get("$type") != "app.bsky.feed.post"
                ):
                    raise UserError("This post has changed. Refresh it before deleting.")
                await self.client.com.atproto.repo.delete_record({**params, "swapRecord": post.cid})
            self.confirmed().forget("published", post.uri)
            self.confirmed().forget("post", post.uri)
            await self._io("delete_post", post.uri)
            return deleted_post(post)

    async def _delete_record(self, value, collection, subject):
        # Viewer fields are untrusted AppView data. Never let them select a
        # repository or collection for an authenticated destructive request.
        prefix = f"at://{self.account.did}/{collection}/"
        rkey = value.removeprefix(prefix) if isinstance(value, str) else ""
        if (
            not isinstance(value, str)
            or not value.startswith(prefix)
            or not re.fullmatch(r"[A-Za-z0-9._:~-]{1,512}", rkey)
            or rkey in (".", "..")
        ):
            raise UserError("This saved action is invalid. Refresh the content and try again.")
        params = {"repo": self.account.did, "collection": collection, "rkey": rkey}
        try:
            record = data(await self.client.com.atproto.repo.get_record(params))
        except AtProtocolError as exc:
            if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                return  # Already removed: keep undo actions idempotent.
            raise
        content = record.get("value")
        actual = content.get("subject") if isinstance(content, dict) else None
        if collection in ("app.bsky.feed.like", "app.bsky.feed.repost"):
            actual = actual.get("uri") if isinstance(actual, dict) else None
        if (
            record.get("uri") != value
            or not record.get("cid")
            or not isinstance(content, dict)
            or content.get("$type") != collection
            or actual != subject
        ):
            raise UserError("This saved action has changed. Refresh the content and try again.")
        # Reject a concurrent replacement between verification and deletion.
        await self.client.com.atproto.repo.delete_record({**params, "swapRecord": record["cid"]})

    async def follow(self, author):
        async with self.authenticated():
            if author.following:
                await self._delete_record(author.following, "app.bsky.graph.follow", author.did)
                following = ""
            else:
                following = (await self.client.follow(author.did)).uri
            self.confirmed().remember("author", author.did, following=following)
            return replace(author, following=following)

    async def moderate(self, author, kind):
        async with self.authenticated():
            if kind == "mute":
                method = (
                    self.client.app.bsky.graph.unmute_actor
                    if author.muted
                    else self.client.app.bsky.graph.mute_actor
                )
                await method({"actor": author.did})
                changes = {"muted": not author.muted}
            elif kind == "block":
                if author.blocking:
                    await self._delete_record(author.blocking, "app.bsky.graph.block", author.did)
                    blocking = ""
                else:
                    result = await self.client.app.bsky.graph.block.create(
                        self.account.did,
                        models.AppBskyGraphBlock.Record(
                            subject=author.did, created_at=self.client.get_current_time_iso()
                        ),
                    )
                    blocking = result.uri
                changes = {"blocking": blocking}
            else:
                raise UserError("This account action is not supported.")
            self.confirmed().remember("author", author.did, **changes)
            return replace(author, **changes)

    async def search(self, query, people=False, cursor=None):
        async with self.authenticated():
            if people:
                result = await self.client.app.bsky.actor.search_actors(
                    {"q": query, "limit": 30, "cursor": cursor}
                )
                return tuple(
                    self.confirmed().author(a) for a in page_items(result, author_from)
                ), result.cursor
            result = await self.client.app.bsky.feed.search_posts(
                {"q": query, "limit": 30, "cursor": cursor}
            )
            return self.confirmed().page(
                await self._io("reconcile_page", Page(page_items(result, post_from), result.cursor))
            )

    async def notifications(self, cursor=None):
        async with self.authenticated():
            result = await self.client.app.bsky.notification.list_notifications(
                {"limit": 40, "cursor": cursor}
            )
            items = tuple(
                Notice(
                    self.confirmed().author(author_from(data(item.author))),
                    item.reason,
                    item.uri,
                    item.reason_subject or "",
                    item.is_read,
                    item.indexed_at,
                )
                for item in result.get_page_items()
            )
            seen = self.confirmed().fields("notification", "seen").get("timestamp")
            if seen:
                items = tuple(
                    replace(n, read=True) if at_or_before(n.indexed_at, seen) else n for n in items
                )
            return items, result.cursor, self.client.get_current_time_iso()

    async def mark_seen(self, timestamp):
        async with self.authenticated():
            previous = self.confirmed().fields("notification", "seen").get("timestamp")
            if previous and at_or_before(timestamp, previous):
                timestamp = previous
            await self.client.app.bsky.notification.update_seen({"seenAt": timestamp})
            self.confirmed().remember("notification", "seen", timestamp=timestamp)

    async def unread(self):
        async with self.authenticated():
            timestamp = self.confirmed().fields("notification", "seen").get("timestamp")
            params = models.AppBskyNotificationGetUnreadCount.Params(seen_at=timestamp)
            return (await self.client.app.bsky.notification.get_unread_count(params)).count

    def drafts(self):
        return self._local("drafts")

    def draft_get(self, key):
        return self._local("get", "draft:" + key, {})

    def draft_save(self, key, value):
        return self._local("put", "draft:" + key, value, serial=True)

    async def send(
        self, text, attachments=(), reply=None, quote=None, *, video=None, expected_account=None
    ):
        error = validate(text, attachments, video)
        if error:
            raise UserError(error)
        async with self.authenticated():
            if expected_account is not None and self.account is not expected_account:
                raise UserError("The signed-in account changed. Reopen the composer.")

            async def resolve(handle):
                return (
                    await self.client.com.atproto.identity.resolve_handle({"handle": handle})
                ).did

            facets = [
                models.AppBskyRichtextFacet.Main(**x) for x in await facets_for(text, resolve)
            ]
            reply_ref = None
            if reply:
                root_uri, root_cid = reply.root or (reply.uri, reply.cid)
                reply_ref = models.AppBskyFeedPost.ReplyRef(
                    root={"uri": root_uri, "cid": root_cid},
                    parent={"uri": reply.uri, "cid": reply.cid},
                )
            embed = None
            if attachments:
                images = []
                for a in attachments:
                    try:
                        payload = await asyncio.to_thread(Path(a.path).read_bytes)
                    except OSError:
                        raise UserError(
                            "An image is no longer available. Remove it and attach it again."
                        ) from None
                    if len(payload) > 1_000_000 or not payload.startswith(
                        (b"\x89PNG", b"\xff\xd8\xff")
                    ):
                        raise UserError(
                            "An image is invalid or larger than 1 MB. Remove it and attach it again."
                        )
                    blob = (await self.client.upload_blob(payload)).blob
                    images.append(models.AppBskyEmbedImages.Image(alt=a.alt, image=blob))
                embed = models.AppBskyEmbedImages.Main(images=images)
            if video is not None:
                from .video_upload import upload_video

                embed = await upload_video(self, video)
            if quote:
                record = models.AppBskyEmbedRecord.Main(record={"uri": quote.uri, "cid": quote.cid})
                embed = (
                    models.AppBskyEmbedRecordWithMedia.Main(record=record, media=embed)
                    if embed
                    else record
                )
            # No automatic retry: a timeout can occur after the server creates the post.
            created = self.client.get_current_time_iso()
            result = await self.client.send_post(
                text, reply_to=reply_ref, embed=embed, facets=facets, langs=["en"]
            )
            published = Post(
                result.uri,
                result.cid,
                self.confirmed().author(self.account),
                text,
                created,
                facets=tuple(data(facet) for facet in facets),
                images=tuple(Media(a.path, a.alt, local=True) for a in attachments),
                video=Video(
                    video.path, video.alt, width=video.width, height=video.height, local=True
                )
                if video
                else None,
                quote=quote,
                parent=(reply.uri, reply.cid) if reply else None,
                root=(reply.root or (reply.uri, reply.cid)) if reply else None,
            )
            self.confirmed().remember("published", result.uri, post=published)
            return result
