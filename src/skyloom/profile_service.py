"""Own-profile record editing without discarding fields owned by other clients."""

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path

from atproto_client.exceptions import AtProtocolError

from .domain import author_from
from .errors import UserError
from .richtext import counts
from .sdk import model_data, page_items

COLLECTION = "app.bsky.actor.profile"


def validate_profile(name, description):
    for text, title, graphemes, size in (
        (name, "Names", 64, 640),
        (description, "Descriptions", 256, 2560),
    ):
        n, length = counts(text)
        if n > graphemes or length > size:
            return f"{title} allow {graphemes} characters and {size} UTF-8 bytes."
    return ""


@dataclass(frozen=True, slots=True)
class EditableProfile:
    did: str
    cid: str
    record_json: str
    account: object = field(default=None, repr=False, compare=False)

    @property
    def record(self):
        return json.loads(self.record_json)


class ProfileService:
    async def follow_people(self, actor, kind, cursor=None):
        if kind not in ("followers", "following"):
            raise UserError("This people list is not supported.")
        async with self.authenticated():
            method = (
                self.client.app.bsky.graph.get_followers
                if kind == "followers"
                else self.client.app.bsky.graph.get_follows
            )
            result = await method({"actor": actor, "limit": 30, "cursor": cursor})
            return page_items(result, author_from), result.cursor

    async def editable_profile(self):
        async with self.authenticated():
            did = self.account.did
            try:
                result = model_data(
                    await self.client.com.atproto.repo.get_record(
                        {"repo": did, "collection": COLLECTION, "rkey": "self"}
                    )
                )
            except AtProtocolError as exc:
                if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                    return EditableProfile(did, "", json.dumps({"$type": COLLECTION}), self.account)
                raise
            record = result.get("value")
            if (
                result.get("uri") != f"at://{did}/{COLLECTION}/self"
                or not result.get("cid")
                or not isinstance(record, dict)
                or record.get("$type") != COLLECTION
            ):
                raise UserError("This profile record is invalid. Reload it and try again.")
            return EditableProfile(did, result["cid"], json.dumps(record), self.account)

    async def update_profile(self, original, name, description, avatar=None, banner=None):
        """None keeps an image, an empty path removes it, a prepared path replaces it."""
        if error := validate_profile(name, description):
            raise UserError(error)
        async with self.authenticated():
            if original.did != self.account.did or (
                original.account is not None and original.account is not self.account
            ):
                raise UserError("The signed-in account changed. Reopen the profile editor.")
            record = original.record
            if record.get("$type") != COLLECTION:
                raise UserError("This profile record is invalid. Reload it and try again.")
            record.update(displayName=name, description=description)
            for field, path in (("avatar", avatar), ("banner", banner)):
                if path is None:
                    continue
                if not path:
                    record.pop(field, None)
                    continue

                def read_image(path=path):
                    try:
                        with Path(path).open("rb") as source:
                            payload = source.read(1_000_001)
                    except OSError:
                        raise UserError(
                            "An image is no longer available. Choose it again."
                        ) from None
                    if len(payload) > 1_000_000 or not payload.startswith(
                        (b"\x89PNG", b"\xff\xd8\xff")
                    ):
                        raise UserError("Choose a JPEG or PNG image smaller than 1 MB.")
                    return payload

                record[field] = model_data(
                    (await self.client.upload_blob(await asyncio.to_thread(read_image))).blob
                )
            params = {
                "repo": original.did,
                "collection": COLLECTION,
                "rkey": "self",
                "record": record,
            }
            # createRecord rejects an existing key; putRecord rejects a changed CID.
            # Do not retry either mutation after an ambiguous connection failure.
            try:
                if original.cid:
                    await self.client.com.atproto.repo.put_record(
                        {**params, "swapRecord": original.cid}
                    )
                else:
                    await self.client.com.atproto.repo.create_record(params)
            except AtProtocolError as exc:
                error = getattr(
                    getattr(getattr(exc, "response", None), "content", None), "error", None
                )
                if error in ("InvalidSwap", "RecordAlreadyExists"):
                    raise UserError(
                        "Your profile changed in another client. Copy any edits you want to keep, then reopen the editor to load the latest profile."
                    ) from None
                raise
            # A successful write must not become a reported failure because a
            # subsequent AppView read failed (or has not indexed the write yet).
            author = self.account
            with suppress(AtProtocolError):
                author = author_from(model_data(await self.client.get_profile(original.did)))
            return replace(
                author,
                name=name or author.handle,
                bio=description,
                avatar="" if avatar == "" else author.avatar,
                banner="" if banner == "" else author.banner,
            )
