"""Bounded, account-local relationship metadata for position pills in every view."""

from collections import OrderedDict
from dataclasses import dataclass

from .conversation import chronological
from .domain import Post


@dataclass(frozen=True, slots=True)
class KnownMessage:
    uri: str
    created: str
    parent: str
    root: str
    replies: int
    incomplete: bool = False
    conversation: bool = False


class ThreadContext:
    def __init__(self, limit=2000):
        self.limit = limit
        self.messages = OrderedDict()
        self.positions = {}

    def remember(self, posts, *, incomplete=None, parents=None):
        changed = False
        for post in posts:
            if not isinstance(post, Post):
                continue
            previous = self.messages.get(post.uri)
            message = KnownMessage(
                post.uri,
                post.created,
                (parents or {}).get(
                    post.uri, post.parent[0] if post.parent else previous.parent if previous else ""
                ),
                post.root[0] if post.root else previous.root if previous else "",
                post.replies,
                previous.incomplete if incomplete is None and previous else bool(incomplete),
                incomplete is not None or bool(previous and previous.conversation),
            )
            changed |= previous != message
            self.messages[post.uri] = message
            self.messages.move_to_end(post.uri)
        while len(self.messages) > self.limit:
            self.messages.popitem(last=False)
            changed = True
        if changed:
            self.positions = self.project()
        return changed

    def project(self):
        # Parent/root references connect fragments even when the root is not loaded.
        leaders = {}

        def leader(uri):
            leaders.setdefault(uri, uri)
            root = uri
            while leaders[root] != root:
                root = leaders[root]
            while leaders[uri] != uri:
                previous = leaders[uri]
                leaders[uri] = root
                uri = previous
            return root

        for message in self.messages.values():
            for reference in (message.parent, message.root):
                if reference:
                    leaders[leader(message.uri)] = leader(reference)
        groups = {}
        for message in self.messages.values():
            groups.setdefault(leader(message.uri), []).append(message)
        positions = {}
        for messages in groups.values():
            known = {message.uri: message for message in messages}
            if len(known) < 2:
                continue
            children = {}
            for message in messages:
                children.setdefault(message.parent, []).append(message)
            for siblings in children.values():
                siblings.sort(key=chronological)
            partial = any(
                message.incomplete
                or (message.parent and message.parent not in known)
                or (message.root and message.root not in known)
                or message.replies > len(children.get(message.uri, ()))
                for message in messages
            )
            ordered, visited = [], set()
            roots = [message for message in messages if message.parent not in known]
            partial |= not roots
            # Iterative traversal also bounds malformed/cyclic graphs without recursion.
            stack = sorted(roots, key=chronological, reverse=True)
            fallback = iter(sorted(messages, key=chronological))
            while len(visited) < len(known):
                message = stack.pop() if stack else next(fallback)
                if message.uri in visited:
                    continue
                visited.add(message.uri)
                ordered.append(message)
                stack.extend(reversed(children.get(message.uri, ())))
            for index, message in enumerate(ordered, start=1):
                positions[message.uri] = (index, len(ordered), bool(partial))
        return positions
