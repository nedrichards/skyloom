"""Account-scoped local data. Call from worker, never store credentials here."""

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .bookmark_service import reconcile_bookmarks, with_bookmark
from .domain import (
    Author,
    CachedFeed,
    Media,
    Page,
    Pager,
    Post,
    find_post,
    reconcile_deleted,
)
from .feed_state import Bookmark
from .image_cache import ImageCache


def post_restore(d):
    return Post(
        **{
            **d,
            "author": Author(**{**d["author"], "labels": tuple(d["author"].get("labels", []))}),
            "labels": tuple(d.get("labels", [])),
            "facets": tuple(d.get("facets", [])),
            "external": tuple(d["external"]) if d.get("external") else None,
            "images": tuple(Media(**i) for i in d["images"]),
            "quote": post_restore(d["quote"]) if d.get("quote") else None,
            "root": tuple(d["root"]) if d.get("root") else None,
            "parent": tuple(d["parent"]) if d.get("parent") else None,
        }
    )


class Storage:
    def __init__(self, base=None):
        self.base = Path(
            base or Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "skyloom"
        )
        cache_root = (
            self.base / "cache"
            if base is not None
            else Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "skyloom"
        )
        self.images = ImageCache(cache_root)
        self.archive_feed_limit = 10000
        self.archive_limit = 50000
        self.archive_max_age = 30 * 86400
        self._last_cleanup = {}
        self._archived = 0
        self._state_lock = threading.Lock()
        self._io_locks = {}
        self._epochs = {}
        self._initialized = set()
        self._windows = OrderedDict()
        self._bookmark_changes = OrderedDict()

    def _io_lock(self, account):
        with self._state_lock:
            return self._io_locks.setdefault(account, threading.RLock())

    def token(self, account):
        with self._state_lock:
            return self._epochs.get(account, 0)

    def activate(self, account):
        with self._io_lock(account):
            with self._state_lock:
                token = self._epochs.get(account, 0) + 1
                self._epochs[account] = token
            self._forget_windows(account)
            return token

    def run(self, account, token, operation, *args):
        """Validate ownership inside the same IO lock used by clear, even after cancellation."""
        with self._io_lock(account):
            if token != self.token(account):
                return None
            return getattr(self, operation)(account, *args)

    def _forget_windows(self, account):
        for key in tuple(self._windows):
            if key[0] == account:
                self._windows.pop(key)

    def _remember_window(self, account, feed, posts):
        key = (account, feed)
        self._windows[key] = tuple(posts)
        self._windows.move_to_end(key)
        while len(self._windows) > 12:
            self._windows.popitem(last=False)

    @contextmanager
    def connect(self, account):
        with self._io_lock(account):
            self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
            name = hashlib.sha256(account.encode()).hexdigest() + ".db"
            path = self.base / name
            initialize = account not in self._initialized or not path.exists()
            db = sqlite3.connect(path)
            try:
                os.chmod(path, 0o600)
                if initialize:
                    db.executescript("""
                        CREATE TABLE IF NOT EXISTS deleted_posts (uri TEXT PRIMARY KEY);
                        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS feed_posts (
                            feed TEXT NOT NULL, uri TEXT NOT NULL, value TEXT NOT NULL,
                            touched REAL NOT NULL, PRIMARY KEY(feed, uri));
                        CREATE INDEX IF NOT EXISTS feed_posts_age ON feed_posts(touched);
                        CREATE INDEX IF NOT EXISTS feed_posts_feed_age ON feed_posts(feed, touched);
                        CREATE INDEX IF NOT EXISTS feed_posts_uri_age ON feed_posts(uri, touched DESC);
                        CREATE TABLE IF NOT EXISTS feed_pages (
                            feed TEXT NOT NULL, cursor TEXT NOT NULL, value TEXT NOT NULL,
                            touched REAL NOT NULL, PRIMARY KEY(feed, cursor));
                        CREATE TABLE IF NOT EXISTS feed_protected (
                            feed TEXT NOT NULL, uri TEXT NOT NULL, PRIMARY KEY(feed, uri));
                        CREATE TABLE IF NOT EXISTS feed_bookmarks (
                            feed TEXT PRIMARY KEY, value TEXT NOT NULL);
                    """)
                    self._initialized.add(account)
                with db:
                    yield db
            finally:
                db.close()

    def get(self, account, key, default=None):
        with self.connect(account) as db:
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, account, key, value):
        with self.connect(account) as db:
            if key.startswith("draft:") and not value:
                db.execute("DELETE FROM state WHERE key=?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))
            # Keep only 12 recent feed caches; draft entries are retained.
            db.execute(
                "DELETE FROM state WHERE key LIKE 'feed:%' AND rowid NOT IN (SELECT rowid FROM state WHERE key LIKE 'feed:%' ORDER BY rowid DESC LIMIT 12)"
            )

    def _feed_value(self, db, feed):
        row = db.execute("SELECT value FROM state WHERE key=?", ("feed:" + feed,)).fetchone()
        value = json.loads(row[0]) if row else {}
        return value if isinstance(value, dict) else {"posts": value}

    def _write_feed(self, db, feed, value):
        db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", ("feed:" + feed, json.dumps(value)))
        db.execute("""DELETE FROM state WHERE key LIKE 'feed:%' AND rowid NOT IN
            (SELECT rowid FROM state WHERE key LIKE 'feed:%' ORDER BY rowid DESC LIMIT 12)""")

    def reconcile_page(self, account, page):
        with self.connect(account) as db:
            deleted = {row[0] for row in db.execute("SELECT uri FROM deleted_posts")}
        changes = self._bookmark_overrides(account)
        posts = tuple(
            reconcile_bookmarks(reconcile_deleted(p, deleted), changes) for p in page.posts
        )
        from dataclasses import replace

        return replace(page, posts=posts)

    def delete_post(self, account, uri):
        with self.connect(account) as db:
            db.execute("INSERT OR IGNORE INTO deleted_posts VALUES (?)", (uri,))
            for rowid, raw in db.execute("SELECT rowid,value FROM feed_posts").fetchall():
                post = post_restore(json.loads(raw))
                updated = reconcile_deleted(post, {uri})
                if updated != post:
                    db.execute(
                        "UPDATE feed_posts SET value=? WHERE rowid=?",
                        (json.dumps(asdict(updated)), rowid),
                    )
            for key, raw in db.execute(
                "SELECT key,value FROM state WHERE key LIKE 'feed:%'"
            ).fetchall():
                value = json.loads(raw)
                posts = value.get("posts") if isinstance(value, dict) else value
                if isinstance(posts, list):
                    updated = [asdict(reconcile_deleted(post_restore(p), {uri})) for p in posts]
                    if isinstance(value, dict):
                        value["posts"] = updated
                    else:
                        value = updated
                    db.execute("UPDATE state SET value=? WHERE key=?", (json.dumps(value), key))
        self._forget_windows(account)

    def _bookmark_overrides(self, account):
        now = time.monotonic()
        return {
            uri: value
            for (did, uri), value in self._bookmark_changes.items()
            if did == account and now < value[2]
        }

    def bookmark_post(self, account, uri, saved):
        self._bookmark_changes[(account, uri)] = (0, saved, time.monotonic() + 120)
        self._bookmark_changes.move_to_end((account, uri))
        while len(self._bookmark_changes) > 2000:
            self._bookmark_changes.popitem(last=False)
        with self.connect(account) as db:
            for rowid, raw in db.execute("SELECT rowid,value FROM feed_posts").fetchall():
                post = post_restore(json.loads(raw))
                updated = with_bookmark(post, uri, saved)
                if updated != post:
                    db.execute(
                        "UPDATE feed_posts SET value=? WHERE rowid=?",
                        (json.dumps(asdict(updated)), rowid),
                    )
            for table, query in (
                ("state", "SELECT rowid,value FROM state WHERE key LIKE 'feed:%'"),
                ("feed_pages", "SELECT rowid,value FROM feed_pages"),
            ):
                for rowid, raw in db.execute(query).fetchall():
                    value = json.loads(raw)
                    posts = value.get("posts") if isinstance(value, dict) else value
                    if not isinstance(posts, list):
                        continue
                    updated = [asdict(with_bookmark(post_restore(p), uri, saved)) for p in posts]
                    if isinstance(value, dict):
                        value["posts"] = updated
                    else:
                        value = updated
                    if table == "state":
                        db.execute(
                            "UPDATE state SET value=? WHERE rowid=?", (json.dumps(value), rowid)
                        )
                    else:
                        db.execute(
                            "UPDATE feed_pages SET value=? WHERE rowid=?",
                            (json.dumps(value), rowid),
                        )
        self._forget_windows(account)

    def _archive(self, db, feed, posts, *, checkpoint=False, overwrite=True):
        now = time.time()
        values = {}
        deleted = {row[0] for row in db.execute("SELECT uri FROM deleted_posts")}
        for post in posts:
            current = reconcile_deleted(post, deleted)
            visited = set()
            while current is not None and current.uri not in visited:
                visited.add(current.uri)
                values.setdefault(current.uri, json.dumps(asdict(current)))
                current = current.quote
        db.executemany(
            """INSERT INTO feed_posts VALUES (?,?,?,?) ON CONFLICT(feed,uri)
            DO UPDATE SET value=excluded.value, touched=excluded.touched
            WHERE ? AND (NOT ? OR feed_posts.value != excluded.value)""",
            ((feed, uri, value, now, overwrite, checkpoint) for uri, value in values.items()),
        )
        if not checkpoint:
            self._archived += len(values)

    def _cleanup(self, db, account, *, force=False):
        now = time.time()
        if not force and self._archived < 512 and now - self._last_cleanup.get(account, 0) < 3600:
            return
        self._last_cleanup[account], self._archived = now, 0
        # Rebuild protection transactionally from the bounded saved reading windows.
        db.execute("DELETE FROM feed_protected")
        for key, raw in db.execute(
            "SELECT key,value FROM state WHERE key LIKE 'feed:%'"
        ).fetchall():
            value = json.loads(raw)
            uris = value.get("window", {}).get("uris", ()) if isinstance(value, dict) else ()
            db.executemany(
                "INSERT OR IGNORE INTO feed_protected VALUES (?,?)", ((key[5:], u) for u in uris)
            )
        db.execute(
            """DELETE FROM feed_posts WHERE touched<? AND NOT EXISTS
            (SELECT 1 FROM feed_protected p WHERE p.feed=feed_posts.feed AND p.uri=feed_posts.uri)""",
            (now - self.archive_max_age,),
        )
        feeds = [row[0] for row in db.execute("SELECT DISTINCT feed FROM feed_posts")]
        for feed in feeds:
            db.execute(
                """DELETE FROM feed_posts WHERE feed=? AND NOT EXISTS
                (SELECT 1 FROM feed_protected p WHERE p.feed=feed_posts.feed AND p.uri=feed_posts.uri) AND rowid NOT IN
                (SELECT rowid FROM feed_posts WHERE feed=? ORDER BY touched DESC, rowid DESC LIMIT ?)""",
                (feed, feed, self.archive_feed_limit),
            )
        db.execute(
            """DELETE FROM feed_posts WHERE NOT EXISTS
            (SELECT 1 FROM feed_protected p WHERE p.feed=feed_posts.feed AND p.uri=feed_posts.uri) AND rowid NOT IN
            (SELECT rowid FROM feed_posts ORDER BY touched DESC, rowid DESC LIMIT ?)""",
            (self.archive_limit,),
        )
        db.execute("DELETE FROM feed_pages WHERE touched<?", (now - self.archive_max_age,))
        for feed in feeds:
            db.execute(
                """DELETE FROM feed_pages WHERE feed=? AND rowid NOT IN
                (SELECT rowid FROM feed_pages WHERE feed=? ORDER BY touched DESC LIMIT 1000)""",
                (feed, feed),
            )

    def cleanup(self, account):
        with self.connect(account) as db:
            self._cleanup(db, account, force=True)

    def _save_bookmark(self, db, feed, bookmark):
        if bookmark is not None:
            db.execute(
                """INSERT INTO feed_bookmarks VALUES (?,?) ON CONFLICT(feed)
                DO UPDATE SET value=excluded.value WHERE value != excluded.value""",
                (feed, json.dumps(asdict(bookmark))),
            )

    def _bookmark(self, db, feed, value):
        row = db.execute("SELECT value FROM feed_bookmarks WHERE feed=?", (feed,)).fetchone()
        return Bookmark.parse(json.loads(row[0]) if row else value.get("bookmark"))

    def _records(self, db, feed, uris):
        posts = []
        for uri in uris:
            row = db.execute(
                "SELECT value FROM feed_posts WHERE feed=? AND uri=?", (feed, uri)
            ).fetchone()
            if row is None:
                return None
            posts.append(post_restore(json.loads(row[0])))
        return posts

    def _head_page(self, db, feed, value):
        if "head" in value:
            head = value["head"]
            posts = self._records(db, feed, head.get("uris", ()))
            return Page(
                tuple(posts or ()), head.get("cursor") if posts is not None else None, cached=True
            )
        # Legacy full payloads remain readable; new snapshots keep URI references only.
        return Page(
            tuple(post_restore(p) for p in value.get("posts", ())), value.get("cursor"), cached=True
        )

    def _migrate_feed(self, db, feed, value):
        if "posts" in value:
            posts = tuple(post_restore(p) for p in value.pop("posts"))
            self._archive(db, feed, posts, checkpoint=True, overwrite=False)
            value["head"] = {"uris": [p.uri for p in posts], "cursor": value.pop("cursor", None)}
        if "bookmark" in value:
            self._save_bookmark(db, feed, Bookmark.parse(value.pop("bookmark")))
        value.pop("refreshed", None)
        value["version"] = 3

    def cache(self, account, feed, page, cursor=None):
        page = self.reconcile_page(account, page)
        with self.connect(account) as db:
            self._archive(db, feed, page.posts)
            db.execute(
                "INSERT OR REPLACE INTO feed_pages VALUES (?,?,?,?)",
                (
                    feed,
                    cursor or "",
                    json.dumps({"uris": [p.uri for p in page.posts], "cursor": page.cursor}),
                    time.time(),
                ),
            )
            if cursor is None:
                value = self._feed_value(db, feed)
                self._migrate_feed(db, feed, value)
                value["head"] = {"uris": [p.uri for p in page.posts], "cursor": page.cursor}
                self._write_feed(db, feed, value)
            self._cleanup(db, account)
        key = (account, feed)
        if key in self._windows:
            incoming = {p.uri: p for p in page.posts}
            self._remember_window(
                account, feed, (incoming.get(p.uri, p) for p in self._windows[key])
            )

    def checkpoint(self, account, feed, pager, bookmark):
        if len(pager.posts) > 250:
            raise ValueError("Reading windows must contain at most 250 posts")
        changes = self._bookmark_overrides(account)
        posts = tuple(reconcile_bookmarks(p, changes) for p in pager.posts)
        with self.connect(account) as db:
            value = self._feed_value(db, feed)
            original = value.copy()
            self._migrate_feed(db, feed, value)
            previous = self._windows.get((account, feed))
            # Immutable DTO equality detects actual content changes without JSON encoding.
            known = {p.uri: p for p in previous or ()}
            changed = [p for p in posts if known.get(p.uri) != p]
            if changed:
                self._archive(db, feed, changed, checkpoint=True)
            old_uris = set(value.get("window", {}).get("uris", ()))
            window = {
                "uris": [p.uri for p in posts],
                "cursor": pager.cursor,
                "starts": pager.page_starts,
                "gaps": pager.gaps,
            }
            value["window"] = window
            if value != original:
                self._write_feed(db, feed, value)
            new_uris = set(window["uris"])
            if old_uris != new_uris:
                db.executemany(
                    "DELETE FROM feed_protected WHERE feed=? AND uri=?",
                    ((feed, uri) for uri in old_uris - new_uris),
                )
                db.executemany(
                    "INSERT OR IGNORE INTO feed_protected VALUES (?,?)",
                    ((feed, uri) for uri in new_uris - old_uris),
                )
            self._save_bookmark(db, feed, bookmark)
            if changed or old_uris != new_uris:
                self._cleanup(db, account)
        self._remember_window(account, feed, posts)

    def cached_page(self, account, feed, cursor):
        with self.connect(account) as db:
            row = db.execute(
                "SELECT value FROM feed_pages WHERE feed=? AND cursor=?", (feed, cursor or "")
            ).fetchone()
            if not row:
                return None
            value = json.loads(row[0])
            posts = self._records(db, feed, value["uris"])
            return (
                Page(tuple(posts), value.get("cursor"), cached=True) if posts is not None else None
            )

    def cached_state(self, account, feed):
        with self.connect(account) as db:
            self._cleanup(db, account)
            value = self._feed_value(db, feed)
            window = value.get("window")
            bookmark = self._bookmark(db, feed, value)
            posts = self._records(db, feed, window.get("uris", ())[:250]) if window else None
            if posts:
                pager = Pager(
                    posts=posts,
                    cursor=window.get("cursor"),
                    page_starts=window.get("starts", {}),
                    gaps=window.get("gaps", {}),
                )
            else:
                page = self._head_page(db, feed, value)
                pager = Pager()
                pager.merge(page, reset=True)
                posts = pager.posts
        self._remember_window(account, feed, posts)
        return CachedFeed(pager, bookmark.resolve(posts) if bookmark else None)

    def cached(self, account, feed):
        with self.connect(account) as db:
            return self._head_page(db, feed, self._feed_value(db, feed))

    def cached_post(self, account, uri):
        with self.connect(account) as db:
            row = db.execute(
                "SELECT value FROM feed_posts WHERE uri=? ORDER BY touched DESC LIMIT 1", (uri,)
            ).fetchone()
            if row:
                return post_restore(json.loads(row[0]))
            rows = db.execute(
                "SELECT value FROM state WHERE key LIKE 'feed:%' ORDER BY rowid DESC LIMIT 12"
            ).fetchall()
        for (raw,) in rows:
            value = json.loads(raw)
            posts = value if isinstance(value, list) else value.get("posts", ())
            if post := find_post((post_restore(p) for p in posts), uri):
                return post
        return None

    def drafts(self, account):
        with self.connect(account) as db:
            rows = db.execute(
                "SELECT key, value FROM state WHERE key LIKE 'draft:%' AND value <> '{}' ORDER BY rowid DESC LIMIT 100"
            ).fetchall()
            return [(key[6:], value) for key, raw in rows if (value := json.loads(raw))]

    def prepare_image(self, account, path):
        # Called through run(): preparation and sign-out share the account IO
        # lock, and a queued operation cannot recreate files after invalidation.
        from .media import prepare

        directory = self.base / (hashlib.sha256(account.encode()).hexdigest() + "-images")
        return prepare(path, directory)

    def clear(self, account, token=None):
        with self._io_lock(account):
            if token is not None and token != self.token(account):
                return
            with self._state_lock:
                self._epochs[account] = self._epochs.get(account, 0) + 1
            self._forget_windows(account)
            self.images.clear(account)
            path = self.base / (hashlib.sha256(account.encode()).hexdigest() + ".db")
            if path.exists():
                with self.connect(account) as db:
                    db.execute("PRAGMA secure_delete=ON")
                    db.execute("DELETE FROM state")
                    db.execute("DELETE FROM feed_posts")
                    db.execute("DELETE FROM feed_pages")
                    db.execute("DELETE FROM feed_protected")
                    db.execute("DELETE FROM feed_bookmarks")
                    db.execute("DELETE FROM deleted_posts")
                path.unlink(missing_ok=True)
            for key in tuple(self._bookmark_changes):
                if key[0] == account:
                    self._bookmark_changes.pop(key)
            self._initialized.discard(account)
            self._last_cleanup.pop(account, None)
            shutil.rmtree(
                self.base / (hashlib.sha256(account.encode()).hexdigest() + "-images"),
                ignore_errors=True,
            )
