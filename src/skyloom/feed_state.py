"""Serializable reading identities and bounded feed reconciliation, independent of GTK."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bookmark:
    uri: str
    offset: float = 0
    selected: str | None = None
    neighbours: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("uri"), str):
            return None
        offset = value.get("offset", 0)
        if not isinstance(offset, int | float) or not math.isfinite(offset):
            offset = 0
        return cls(
            value["uri"],
            max(-10000, min(float(offset), 10000)),
            value.get("selected") if isinstance(value.get("selected"), str) else None,
            tuple(x for x in (value.get("neighbours") or ())[:8] if isinstance(x, str))
            if isinstance(value.get("neighbours", ()), list | tuple)
            else (),
        )

    def resolve(self, posts):
        keys = {p.uri for p in posts}
        if self.uri in keys:
            return self
        for key in self.neighbours:
            if key in keys:
                return Bookmark(key, 0, self.selected if self.selected in keys else None)
        return None


@dataclass(frozen=True, slots=True)
class FeedGap:
    before: str
    cursor: str | None
    busy: bool = False
    error: str = ""

    @property
    def uri(self):
        return "gap:" + self.before
