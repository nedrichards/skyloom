"""UAX #29 segmentation and validated UTF-8 facets."""

import html
import re

import regex

from .domain import safe_url


def counts(text: str) -> tuple[int, int]:
    return len(regex.findall(r"\X", text)), len(text.encode("utf-8"))


def validate(text, attachments=()):
    graphemes, size = counts(text)
    if graphemes > 300 or size > 3000:
        return "Posts allow 300 characters and 3000 UTF-8 bytes."
    if not text.strip() and not attachments:
        return "Write something or add an image."
    if len(attachments) > 4:
        return "You can attach up to four images."
    if any(not a.alt.strip() for a in attachments):
        return "Add a description for each image."
    return ""


def markup(text, facets=()):
    if not facets:
        # Most rows have no facets: escaping needs neither a UTF-8 copy nor the
        # intermediate validation/sort/output containers used for byte offsets.
        return html.escape(text)
    raw = text.encode("utf-8")
    result, offset = [], 0
    valid = []
    for f in facets:
        if not isinstance(f, dict) or not isinstance(f.get("index"), dict):
            continue
        a, b = f["index"].get("byteStart"), f["index"].get("byteEnd")
        if type(a) is int and type(b) is int and isinstance(f.get("features"), (list, tuple)):
            valid.append(f)
    for facet in sorted(valid, key=lambda f: f["index"]["byteStart"]):
        try:
            start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
            if not (offset <= start < end <= len(raw)):
                continue
            before = raw[offset:start].decode("utf-8")
            label = raw[start:end].decode("utf-8")
            raw[end:].decode("utf-8")
            feature = facet["features"][0]
            kind = feature.get("$type", "")
            url = ""
            if kind.endswith("#link"):
                url = safe_url(feature.get("uri", ""))
            elif kind.endswith("#mention"):
                from urllib.parse import quote

                url = "https://bsky.app/profile/" + quote(feature.get("did", ""), safe=":")
            elif kind.endswith("#tag"):
                from urllib.parse import quote

                url = "https://bsky.app/hashtag/" + quote(feature.get("tag", ""))
            result.extend(
                (
                    html.escape(before),
                    f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
                    if url
                    else html.escape(label),
                )
            )
            offset = end
        except KeyError, IndexError, TypeError, AttributeError, UnicodeDecodeError:
            continue
    result.append(html.escape(raw[offset:].decode("utf-8")))
    return "".join(result)


async def facets_for(text, resolve):
    facets = []
    # Token boundaries avoid interpreting email addresses as mentions.
    pattern = r"https?://[^\s<>]+|(?<![\w@])@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}|(?<!\w)#[\w]+"
    for match in re.finditer(pattern, text):
        token = match.group().rstrip(".,;:!?)]}")
        if token.startswith("http"):
            if not safe_url(token):
                continue
            feature = {"$type": "app.bsky.richtext.facet#link", "uri": token}
        elif token.startswith("@"):
            did = await resolve(token[1:])
            if not did:
                continue
            feature = {"$type": "app.bsky.richtext.facet#mention", "did": did}
        else:
            if counts(token[1:])[0] > 64:
                continue
            feature = {"$type": "app.bsky.richtext.facet#tag", "tag": token[1:]}
        start = len(text[: match.start()].encode("utf-8"))
        facets.append(
            {
                "$type": "app.bsky.richtext.facet",
                "index": {"byteStart": start, "byteEnd": start + len(token.encode("utf-8"))},
                "features": [feature],
            }
        )
    return facets
