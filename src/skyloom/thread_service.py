"""Owned thread/post gates, preserving fields belonging to other clients."""

import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from atproto_client.exceptions import AtProtocolError

from .conversation import ThreadGap
from .errors import UserError
from .sdk import model_data

THREAD = "app.bsky.feed.threadgate"
POST = "app.bsky.feed.postgate"
RULES = {name: THREAD + "#" + name + "Rule" for name in ("mention", "follower", "following")}
DISABLE = POST + "#disableRule"


def post_parts(uri):
    match = re.fullmatch(r"at://([^/?#]+)/app\.bsky\.feed\.post/([A-Za-z0-9._:~-]{1,512})", uri)
    if not match or match[2] in (".", ".."):
        raise UserError("This post address is invalid. Refresh and try again.")
    return match[1], match[2]


@dataclass(frozen=True, slots=True)
class Gate:
    owner: str
    collection: str
    rkey: str
    cid: str
    record_json: str
    account: object = field(default=None, repr=False, compare=False)

    @property
    def record(self):
        return json.loads(self.record_json)


def reply_rules(gate, mode, groups):
    record = gate.record
    if mode == "everyone":
        record.pop("allow", None)
    elif mode == "nobody":
        record["allow"] = []
    elif mode == "groups":
        if any(name not in RULES for name in groups):
            raise UserError("This reply group is not supported.")
        preserved = [r for r in record.get("allow", []) if r.get("$type") not in RULES.values()]
        record["allow"] = preserved + [{"$type": RULES[name]} for name in dict.fromkeys(groups)]
        if len(record["allow"]) > 5:
            raise UserError(
                "Bluesky allows at most five reply rules. Existing list rules are preserved."
            )
    else:
        raise UserError("Choose who can reply.")
    return record


class ThreadService:
    async def _owned_post(self, uri, *, root=False):
        owner, rkey = post_parts(uri)
        if owner != self.account.did:
            raise UserError("Only the author can change these controls.")
        result = model_data(
            await self.client.com.atproto.repo.get_record(
                {"repo": owner, "collection": "app.bsky.feed.post", "rkey": rkey}
            )
        )
        record = result.get("value")
        if (
            result.get("uri") != uri
            or not isinstance(record, dict)
            or record.get("$type") != "app.bsky.feed.post"
            or (root and record.get("reply"))
        ):
            raise UserError("These controls require your original thread post.")
        return record

    async def _gate(self, uri, collection):
        owner, rkey = post_parts(uri)
        if owner != self.account.did or collection not in (THREAD, POST):
            raise UserError("Only the author can change these controls.")
        try:
            result = model_data(
                await self.client.com.atproto.repo.get_record(
                    {"repo": owner, "collection": collection, "rkey": rkey}
                )
            )
        except AtProtocolError as exc:
            if getattr(getattr(exc, "response", None), "status_code", None) != 404:
                raise
            record = {"$type": collection, "post": uri, "createdAt": datetime.now(UTC).isoformat()}
            return Gate(owner, collection, rkey, "", json.dumps(record), self.account)
        record = result.get("value")
        if (
            result.get("uri") != f"at://{owner}/{collection}/{rkey}"
            or not result.get("cid")
            or not isinstance(record, dict)
            or record.get("$type") != collection
            or record.get("post") != uri
        ):
            raise UserError("These controls have changed. Reload and try again.")
        return Gate(owner, collection, rkey, result["cid"], json.dumps(record), self.account)

    async def _write_gate(self, gate, record):
        if (
            gate.owner != self.account.did
            or gate.collection not in (THREAD, POST)
            or (gate.account is not None and gate.account is not self.account)
        ):
            raise UserError("The signed-in account changed. Reopen these controls.")
        uri = f"at://{gate.owner}/app.bsky.feed.post/{gate.rkey}"
        if record.get("$type") != gate.collection or record.get("post") != uri:
            raise UserError("These controls are invalid. Reopen them.")
        await self._owned_post(uri, root=gate.collection == THREAD)
        params = {
            "repo": gate.owner,
            "collection": gate.collection,
            "rkey": gate.rkey,
            "record": record,
        }
        if gate.cid:
            result = await self.client.com.atproto.repo.put_record(
                {**params, "swapRecord": gate.cid}
            )
        else:
            # A competing creator must fail; nullable swapRecord is omitted by this SDK.
            result = await self.client.com.atproto.repo.create_record(params)
        result = model_data(result)
        overrides = getattr(self, "_gate_overrides", OrderedDict())
        self._gate_overrides = overrides
        overrides[(gate.owner, uri, gate.collection)] = record
        overrides.move_to_end((gate.owner, uri, gate.collection))
        while len(overrides) > 256:
            overrides.popitem(last=False)
        return Gate(
            gate.owner, gate.collection, gate.rkey, result["cid"], json.dumps(record), self.account
        )

    def apply_gate_controls(self, page):
        hidden = set()
        for (owner, _uri, collection), record in getattr(self, "_gate_overrides", {}).items():
            if owner == self.account.did and collection == THREAD:
                hidden.update(record.get("hiddenReplies", []))
        # A directly opened hidden message remains accessible; only child branches hide.
        selected = next((post.uri for post in page.posts if post.context == "Selected post"), "")
        hidden.difference_update(
            post.uri
            for post in page.posts
            if post.uri == selected or post.context == "Earlier in this conversation"
        )
        parents = dict(page.edges)
        while True:
            descendants = {post.uri for post in page.posts if parents.get(post.uri) in hidden}
            if descendants.issubset(hidden):
                break
            hidden.update(descendants)
        omitted = {post.uri for post in page.posts if post.uri in hidden}
        gaps = page.gaps + tuple(
            ThreadGap(uri, parents.get(uri, ""), "hidden")
            for uri in omitted
            if parents.get(uri) not in hidden
        )
        return replace(page, posts=tuple(p for p in page.posts if p.uri not in hidden), gaps=gaps)

    async def thread_controls(self, uri, *, replies=True, expected_account=None):
        async with self.authenticated():
            if expected_account is not None and self.account is not expected_account:
                raise UserError("The signed-in account changed. Reopen these controls.")
            await self._owned_post(uri, root=replies)
            thread = await self._gate(uri, THREAD) if replies else None
            return thread, await self._gate(uri, POST)

    async def save_reply_rules(self, gate, mode, groups):
        async with self.authenticated():
            if gate.collection != THREAD:
                raise UserError("These reply controls are invalid.")
            return await self._write_gate(gate, reply_rules(gate, mode, groups))

    async def save_quote_rule(self, gate, allowed):
        async with self.authenticated():
            if gate.collection != POST:
                raise UserError("These quote controls are invalid.")
            record = gate.record
            rules = [r for r in record.get("embeddingRules", []) if r.get("$type") != DISABLE]
            if not allowed:
                rules.append({"$type": DISABLE})
            if len(rules) > 5:
                raise UserError("Bluesky allows at most five quote rules.")
            record["embeddingRules"] = rules
            return await self._write_gate(gate, record)

    async def _visible_post(self, uri):
        # AppView routes foreign repositories; our PDS need not host this author.
        result = model_data(await self.client.app.bsky.feed.get_posts({"uris": [uri]}))
        posts = result.get("posts", [])
        if len(posts) != 1 or posts[0].get("uri") != uri:
            raise UserError("This post is unavailable. Refresh and try again.")
        return posts[0].get("record") or {}

    async def hidden_reply(self, root_uri, reply_uri, hidden, *, expected_account=None):
        async with self.authenticated():
            if expected_account is not None and self.account is not expected_account:
                raise UserError("The signed-in account changed. Reopen these controls.")
            await self._owned_post(root_uri, root=True)
            post_parts(reply_uri)
            if hidden:
                record = await self._visible_post(reply_uri)
                if (
                    record.get("$type") != "app.bsky.feed.post"
                    or record.get("reply", {}).get("root", {}).get("uri") != root_uri
                ):
                    raise UserError("This post is not a reply in your thread.")
            gate = await self._gate(root_uri, THREAD)
            record = gate.record
            values = [uri for uri in record.get("hiddenReplies", []) if uri != reply_uri]
            if hidden:
                values.append(reply_uri)
            if len(values) > 300:
                raise UserError("This thread already has 300 hidden replies.")
            record["hiddenReplies"] = values
            return await self._write_gate(gate, record)

    async def detached_quote(self, original_uri, quote_uri, detached, *, expected_account=None):
        async with self.authenticated():
            if expected_account is not None and self.account is not expected_account:
                raise UserError("The signed-in account changed. Reopen these controls.")
            await self._owned_post(original_uri)
            post_parts(quote_uri)
            if detached:
                record = await self._visible_post(quote_uri)
                embed = record.get("embed") or {}
                if embed.get("$type") == "app.bsky.embed.recordWithMedia":
                    embed = embed.get("record") or {}
                if (
                    record.get("$type") != "app.bsky.feed.post"
                    or embed.get("record", {}).get("uri") != original_uri
                ):
                    raise UserError("This post does not quote your post.")
            gate = await self._gate(original_uri, POST)
            record = gate.record
            values = [uri for uri in record.get("detachedEmbeddingUris", []) if uri != quote_uri]
            if detached:
                values.append(quote_uri)
            if len(values) > 50:
                raise UserError("This post already has 50 detached quotes.")
            record["detachedEmbeddingUris"] = values
            return await self._write_gate(gate, record)


class DemoThreadService(ThreadService):
    async def thread_controls(self, uri, *, replies=True, expected_account=None):
        await self.pause()
        if expected_account is not None and self.account is not expected_account:
            raise UserError("The signed-in account changed. Reopen these controls.")
        owner, key = post_parts(uri)
        if owner != self.account.did:
            raise UserError("Only the author can change these controls.")
        gates = getattr(self, "demo_gates", {})
        self.demo_gates = gates

        def gate(collection):
            return gates.get(
                (uri, collection),
                Gate(
                    owner,
                    collection,
                    key,
                    "",
                    json.dumps(
                        {"$type": collection, "post": uri, "createdAt": "2026-11-13T12:00:00Z"}
                    ),
                    self.account,
                ),
            )

        return gate(THREAD) if replies else None, gate(POST)

    async def _demo_save(self, gate, record):
        await self.pause()
        if gate.owner != self.account.did or (
            gate.account is not None and gate.account is not self.account
        ):
            raise UserError("The signed-in account changed.")
        uri = record["post"]
        current = self.demo_gates.get((uri, gate.collection))
        if current and current.cid != gate.cid:
            raise UserError("These controls have changed. Reload and try again.")
        updated = Gate(gate.owner, gate.collection, gate.rkey, gate.cid + "1", json.dumps(record))
        self.demo_gates[(uri, gate.collection)] = updated
        self._gate_overrides = {
            (self.account.did, key[0], key[1]): value.record
            for key, value in self.demo_gates.items()
        }
        return updated

    async def save_reply_rules(self, gate, mode, groups):
        return await self._demo_save(gate, reply_rules(gate, mode, groups))

    async def save_quote_rule(self, gate, allowed):
        record = gate.record
        record["embeddingRules"] = [] if allowed else [{"$type": DISABLE}]
        return await self._demo_save(gate, record)

    async def hidden_reply(self, root_uri, reply_uri, hidden, *, expected_account=None):
        gate, _quote = await self.thread_controls(root_uri, expected_account=expected_account)
        record = gate.record
        record["hiddenReplies"] = [u for u in record.get("hiddenReplies", []) if u != reply_uri] + (
            [reply_uri] if hidden else []
        )
        return await self._demo_save(gate, record)

    async def detached_quote(self, original_uri, quote_uri, detached, *, expected_account=None):
        _thread, gate = await self.thread_controls(
            original_uri, replies=False, expected_account=expected_account
        )
        record = gate.record
        record["detachedEmbeddingUris"] = [
            u for u in record.get("detachedEmbeddingUris", []) if u != quote_uri
        ] + ([quote_uri] if detached else [])
        return await self._demo_save(gate, record)
