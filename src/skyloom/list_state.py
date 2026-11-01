"""List gesture decisions and stable scroll positions, without GTK imports."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListPlace:
    key: object
    offset: float
    selected: object = None


@dataclass
class PullRefresh:
    state: str = "idle"

    def begin(self, at_top, enabled):
        self.state = "pending" if at_top and enabled else "idle"

    def update(self, x, y):
        if self.state == "idle":
            return self.state
        if not math.isfinite(x) or not math.isfinite(y):
            self.state = "idle"
        elif self.state == "pending" and max(abs(x), abs(y)) >= 8:
            self.state = "pulling" if y > 0 and y > abs(x) else "idle"
        if self.state in {"pulling", "armed"}:
            self.state = "armed" if y >= 72 and y > abs(x) else "pulling"
        return self.state

    def finish(self, released, enabled):
        refresh = released and enabled and self.state == "armed"
        self.state = "idle"
        return refresh
