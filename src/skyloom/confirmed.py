"""Short-lived, session-owned facts confirmed by successful writes, never retries."""

import time
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime


class ConfirmedChanges:
    def __init__(self, owner, clock=time.monotonic, ttl=120, limit=2000):
        self.owner, self.clock, self.ttl, self.limit = owner, clock, ttl, limit
        self.values = OrderedDict()

    def remember(self, kind, key, **fields):
        self.prune()
        entry = (kind, key)
        values = self.values.setdefault(entry, {})
        for name, value in fields.items():
            values[name] = (self.clock() + self.ttl, value)
        self.values.move_to_end(entry)
        while len(self.values) > self.limit:
            self.values.popitem(last=False)

    def forget(self, kind, key):
        self.values.pop((kind, key), None)

    def prune(self):
        now = self.clock()
        for key in tuple(self.values):
            self._fields(key, now)

    def _fields(self, key, now):
        fields = self.values.get(key, {})
        for name, (expires, _) in tuple(fields.items()):
            if expires <= now:
                del fields[name]
        if not fields:
            self.values.pop(key, None)
        return {name: value for name, (_, value) in fields.items()}

    def fields(self, kind, key):
        return self._fields((kind, key), self.clock())

    def apply(self, kind, key, record):
        changes = {
            name: value
            for name, value in self.fields(kind, key).items()
            if getattr(record, name) != value
        }
        return replace(record, **changes) if changes else record

    def author(self, author):
        return self.apply("author", author.did, author)

    def post(self, post):
        changes = {"author": self.author(post.author)}
        if post.quote:
            changes["quote"] = self.post(post.quote)
        # A server tombstone must never regain counters or interaction controls.
        if not post.unavailable:
            changes.update(self.fields("post", post.uri))
        changes = {name: value for name, value in changes.items() if getattr(post, name) != value}
        return replace(post, **changes) if changes else post

    def page(self, page):
        return replace(page, posts=tuple(self.post(post) for post in page.posts))

    def published(self):
        self.prune()
        return tuple(
            fields["post"][1] for (kind, _), fields in self.values.items() if kind == "published"
        )


def at_or_before(value, cutoff):
    try:
        return datetime.fromisoformat(value) <= datetime.fromisoformat(cutoff)
    except ValueError, TypeError:
        return False


class ConfirmedState:
    def confirmed(self):
        changes = getattr(self, "_confirmed", None)
        owner = getattr(self, "account", None)
        if changes is None or changes.owner is not owner:
            changes = self._confirmed = ConfirmedChanges(owner)
        return changes
