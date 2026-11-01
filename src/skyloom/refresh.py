"""Network/power-aware freshness decisions; wall time includes time spent suspended."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Connection:
    available: bool = True
    internet: bool = True
    metered: bool = False
    power_saver: bool = False

    def pause_reason(self, allow_metered=False):
        if not self.available:
            return "Offline. Use the loading button to retry."
        if not self.internet:
            return "Internet access is limited. Automatic loading is paused."
        if self.power_saver:
            return "Power saver is on. Automatic loading is paused."
        if self.metered and not allow_metered:
            return "Metered connection. Use Load more to continue."
        return ""

    @property
    def description(self):
        network = (
            "Offline"
            if not self.available
            else "Limited internet access"
            if not self.internet
            else "Metered internet connection"
            if self.metered
            else "Unmetered internet connection"
        )
        return network + (" · Power saver is on" if self.power_saver else "")


@dataclass(frozen=True, slots=True)
class RefreshDecision:
    eligible: bool
    due: bool
    delay: float | None


@dataclass
class RefreshPolicy:
    last_finished: float | None = None
    last_success: float | None = None
    failures: int = 0

    def restore(self, timestamp):
        if (
            self.last_finished is None
            and isinstance(timestamp, int | float)
            and math.isfinite(timestamp)
        ):
            self.last_finished = self.last_success = float(timestamp)

    @property
    def interval(self):
        return min(300 * 2 ** max(0, min(self.failures - 1, 3)), 1800)

    def remaining(self, now):
        if self.last_finished is None or now < self.last_finished:
            return 0
        return max(0, self.last_finished + self.interval - now)

    def decision(self, now, *, active, ready, enabled, connection, busy=False, allow_metered=False):
        eligible = bool(
            active and ready and enabled and not busy and not connection.pause_reason(allow_metered)
        )
        delay = self.remaining(now) if eligible else None
        return RefreshDecision(eligible, eligible and delay == 0, delay)

    def due(self, now, **state):
        return self.decision(now, **state).due

    def finished(self, now, success):
        self.last_finished = now
        self.failures = 0 if success else self.failures + 1
        if success:
            self.last_success = now


@dataclass
class ResumeClock:
    boot: float
    awake: float

    def update(self, boot, awake):
        resumed = (boot - self.boot) - (awake - self.awake) > 30
        self.boot, self.awake = boot, awake
        return resumed
