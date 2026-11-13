"""Bounded conversation snapshots and incremental branch/ancestor merging, without GTK."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from .domain import Post, post_from


def chronological(post):
    try:
        value = datetime.fromisoformat(post.created)
        if value.tzinfo is None:
            raise ValueError
        return (0, value.astimezone(UTC), post.uri)
    except ValueError, TypeError, OverflowError:
        return (1, datetime.max.replace(tzinfo=UTC), post.uri)


@dataclass(frozen=True, slots=True)
class ThreadGap:
    uri: str
    parent: str = ""
    kind: str = "unavailable"


@dataclass(frozen=True, slots=True)
class ThreadPosition:
    parent: str = ""
    depth: int = 0
    opened: bool = False
    branch_start: bool = False


@dataclass(frozen=True, slots=True)
class Continuation:
    parent: str
    busy: bool = False
    error: str = ""

    @property
    def uri(self):
        return "skyloom:continue:" + self.parent


@dataclass(frozen=True, slots=True)
class ThreadPage:
    posts: tuple[Post, ...]
    earlier: str = ""
    branches: tuple[str, ...] = ()
    unavailable: bool = False
    truncated: bool = False
    edges: tuple[tuple[str, str], ...] = ()
    gaps: tuple[ThreadGap, ...] = ()


@dataclass(frozen=True, slots=True)
class EarlierMessages:
    busy: bool = False
    error: str = ""
    uri: str = "skyloom:earlier-messages"


def thread_from(node: dict, include_replies=True) -> ThreadPage:
    ancestors, current, visited = [], node, set()
    unavailable = False
    edges, gaps = [], []
    hidden = set()
    while current and "post" in current and len(ancestors) < 21:
        gate = current["post"].get("threadgate") or {}
        hidden.update((gate.get("record") or {}).get("hiddenReplies", []))
        post = post_from(current["post"])
        if post.uri in visited:
            break
        visited.add(post.uri)
        ancestors.append(post)
        if post.parent:
            edges.append((post.uri, post.parent[0]))
        current = current.get("parent")
    if current and "post" not in current:
        unavailable = True
        if current.get("uri"):
            gaps.append(
                ThreadGap(
                    current["uri"], kind="blocked" if current.get("blocked") else "unavailable"
                )
            )
    ancestors.reverse()
    earliest = ancestors[0]
    earlier = earliest.parent[0] if earliest.parent and not current else ""
    if earlier in visited:
        earlier = ""
    posts = [replace(p, context="Earlier in this conversation") for p in ancestors[:-1]]
    posts.append(replace(ancestors[-1], context="Selected post"))
    branches = []
    truncated = False

    def descend(item, level=0):
        nonlocal unavailable, truncated
        children = item.get("replies") or []
        if children and item["post"].get("replyCount", 0) > len(children):
            unavailable = True
        if not children and item["post"].get("replyCount", 0) > 0:
            branches.append(item["post"]["uri"])
        children = sorted(
            children,
            key=lambda child: (
                chronological(post_from(child["post"]))
                if "post" in child
                else (1, datetime.max.replace(tzinfo=UTC), child.get("uri", ""))
            ),
        )
        for child in children:
            if "post" not in child:
                unavailable = True
                if child.get("uri"):
                    gaps.append(
                        ThreadGap(
                            child["uri"],
                            item["post"]["uri"],
                            "blocked" if child.get("blocked") else "unavailable",
                        )
                    )
                continue
            post = post_from(child["post"])
            if post.uri in hidden:
                gaps.append(ThreadGap(post.uri, item["post"]["uri"], "hidden"))
                continue
            if post.uri in visited:
                continue
            if len(posts) >= 250 or level >= 8:
                truncated = True
                return
            visited.add(post.uri)
            edges.append((post.uri, item["post"]["uri"]))
            posts.append(replace(post, context="Reply" if level == 0 else "Reply to a reply"))
            descend(child, level + 1)

    if include_replies:
        descend(node)
    return ThreadPage(
        tuple(posts), earlier, tuple(branches), unavailable, truncated, tuple(edges), tuple(gaps)
    )


@dataclass
class Conversation:
    anchor: str
    posts: list[Post] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    fetched: set[str] = field(default_factory=set)
    ancestors_fetched: set[str] = field(default_factory=set)
    earlier: str = ""
    unavailable: bool = False
    limited: bool = False
    parents: dict[str, str] = field(default_factory=dict)
    gaps: dict[str, ThreadGap] = field(default_factory=dict)
    positions: dict[str, ThreadPosition] = field(default_factory=dict)
    sort_keys: dict = field(default_factory=dict)
    overrides: dict[str, Post] = field(default_factory=dict)

    def merge(self, page: ThreadPage, uri: str, earlier=False) -> int:
        initial = not self.posts
        existing = {post.uri: post for post in self.posts}
        added = []
        for post in page.posts:
            if post.uri not in existing:
                added.append(post)
                existing[post.uri] = post
        for post in page.posts:
            if post.parent:
                self.parents.setdefault(post.uri, post.parent[0])
            self.sort_keys.setdefault(post.uri, chronological(post))
        for child, parent in page.edges:
            self.parents[child] = parent
        capacity = max(0, 250 - len(self.posts))
        self.limited |= page.truncated or len(added) > capacity
        # Retain the messages nearest the selected post when loading distant ancestors.
        added = added[-capacity:] if earlier and capacity else added[:capacity]
        if earlier:
            self.posts[:0] = added
            self.ancestors_fetched.add(uri)
        else:
            self.fetched.add(uri)
            index = next(
                (i + 1 for i, post in enumerate(self.posts) if post.uri == uri), len(self.posts)
            )
            self.posts[index:index] = added
        updates = {}
        for post in page.posts:
            latest = self.overrides.get(post.uri)
            updates[post.uri] = (
                replace(
                    post,
                    likes=latest.likes,
                    reposts=latest.reposts,
                    like_uri=latest.like_uri,
                    repost_uri=latest.repost_uri,
                )
                if latest
                else post
            )
        self.posts = [
            replace(updates[p.uri], context=p.context) if p.uri in updates else p
            for p in self.posts
        ]
        hidden = {gap.uri for gap in page.gaps if gap.kind == "hidden"}
        # Previously loaded descendants must not bypass a newly hidden branch.
        changed = True
        while changed:
            descendants = {uri for uri, parent in self.parents.items() if parent in hidden}
            changed = not descendants.issubset(hidden)
            hidden.update(descendants)
        self.posts = [
            post for post in self.posts if post.uri not in hidden or post.uri == self.anchor
        ]
        present = {post.uri for post in self.posts}
        for gap in page.gaps:
            if len(self.gaps) < 250 and gap.uri not in present:
                self.gaps[gap.uri] = gap
                if gap.parent:
                    self.parents[gap.uri] = gap.parent
        for key in present:
            self.gaps.pop(key, None)
        self.reorder()
        if initial or earlier:
            self.earlier = page.earlier if page.earlier not in self.ancestors_fetched else ""
        self.branches = [branch for branch in self.branches if branch != uri]
        present = {post.uri for post in self.posts}
        for branch in page.branches:
            if branch in present and branch not in self.fetched and branch not in self.branches:
                self.branches.append(branch)
        self.unavailable |= page.unavailable or (not earlier and uri in page.branches)
        if len(self.posts) >= 250:
            self.limited = True
        if self.limited:
            self.branches.clear()
            self.earlier = ""
        return len(added)

    def reorder(self):
        nodes = {post.uri: post for post in self.posts} | self.gaps
        children = {}
        for key in nodes:
            parent = self.parents.get(key, "")
            children.setdefault(parent if parent in nodes and parent != key else "", []).append(key)
        fallback = (1, datetime.max.replace(tzinfo=UTC), "")

        def ordered(keys):
            return sorted(keys, key=lambda key: self.sort_keys.get(key, (*fallback[:2], key)))

        visited, result = set(), []
        self.positions.clear()

        def visit(key, depth=0, branch=False):
            if key in visited:
                return
            visited.add(key)
            self.positions[key] = ThreadPosition(
                self.parents.get(key, ""), depth, key == self.anchor, branch
            )
            result.append(nodes[key])
            for index, child in enumerate(ordered(children.get(key, []))):
                visit(child, depth + 1, index > 0)

        for key in ordered(children.get("", [])):
            visit(key)
        for key in ordered(nodes):
            visit(key)
        self.posts = [node for node in result if isinstance(node, Post)]
        self.rows = result
        self.parents = {key: value for key, value in self.parents.items() if key in nodes}
        self.sort_keys = {key: value for key, value in self.sort_keys.items() if key in nodes}

    def project(self):
        self.reorder()
        rows, path = [], []
        for node in self.rows:
            depth = self.positions[node.uri].depth
            while path and self.positions[path[-1].uri].depth >= depth:
                parent = path.pop()
                if parent.uri in self.branches:
                    rows.append(Continuation(parent.uri))
            rows.append(node)
            path.append(node)
        rows.extend(
            Continuation(parent.uri) for parent in reversed(path) if parent.uri in self.branches
        )
        return rows

    @property
    def next_branch(self):
        return self.branches[0] if self.branches else None

    def update_post(self, post):
        if any(p.uri == post.uri for p in self.posts):
            self.overrides[post.uri] = post
        self.posts = [
            replace(post, context=current.context) if current.uri == post.uri else current
            for current in self.posts
        ]

    @property
    def message(self):
        if self.limited:
            return "Open a message to keep exploring this conversation."
        if self.unavailable:
            return (
                "Some messages are unavailable in this view. Open a message to explore its replies."
            )
        return ""
