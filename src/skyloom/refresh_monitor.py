"""Native network/power notifications and an active-window-only, suspend-aware timer."""

import math
import os
import time
from datetime import UTC, datetime

from gi.repository import Gio, GLib, GLibUnix

from .refresh import Connection, ResumeClock


class RefreshMonitor:
    def __init__(self, window):
        self.window = window
        self.network = Gio.NetworkMonitor.get_default()
        self.power = Gio.PowerProfileMonitor.dup_default()
        self.fd = self.source = self.queued = None
        self.timer_key = None
        self.closed = False
        self.test_connection = None
        self.clock = ResumeClock(time.clock_gettime(time.CLOCK_BOOTTIME), time.monotonic())
        self.signals = [
            (self.network, self.network.connect("notify", self.changed)),
            (self.power, self.power.connect("notify::power-saver-enabled", self.changed)),
            (window, window.connect("notify::is-active", self.activated)),
            (window, window.connect("notify::visible-dialog", self.changed)),
            (window, window.connect("notify::focus-widget", self.queue)),
            (window.settings, window.settings.connect("changed::auto-refresh", self.changed)),
            (window.settings, window.settings.connect("changed::use-metered", self.changed)),
        ]
        window.worker.after_dispatch = self.queue
        self.timestamp_fd = None
        try:
            self.timestamp_fd = os.timerfd_create(
                time.CLOCK_BOOTTIME, flags=os.TFD_CLOEXEC | os.TFD_NONBLOCK
            )
            os.timerfd_settime(self.timestamp_fd, initial=60, interval=60)
            self.timestamp_source = GLibUnix.fd_add_full(
                GLib.PRIORITY_DEFAULT,
                self.timestamp_fd,
                GLib.IOCondition.IN,
                self.timestamp_tick,
                None,
            )
        except OSError:
            if self.timestamp_fd is not None:
                os.close(self.timestamp_fd)
                self.timestamp_fd = None
            self.timestamp_source = GLib.timeout_add_seconds(60, self.timestamp_tick)
        self.changed()

    def activated(self, *_args):
        if self.window.is_active():
            self.refresh_timestamps()
        self.changed()

    def refresh_timestamps(self):
        now = datetime.now(UTC)
        for row in tuple(getattr(self.window, "timestamp_rows", ())):
            if row.alive and row.get_mapped():
                row.refresh_timestamp(now)

    def timestamp_tick(self, *_args):
        if self.timestamp_fd is not None:
            try:
                os.read(self.timestamp_fd, 8)
            except BlockingIOError:
                return True
        self.refresh_timestamps()
        return True

    def queue(self, *_args):
        if self.closed or self.queued is not None:
            return

        def dispatch():
            self.queued = None
            self.changed()
            return False

        self.queued = GLib.idle_add(dispatch)

    def connection(self):
        if self.test_connection is not None:
            return self.test_connection
        if self.window.demo:
            return Connection(
                available=not self.window.service.offline, internet=not self.window.service.offline
            )
        return Connection(
            available=self.network.get_network_available(),
            internet=self.network.get_connectivity() == Gio.NetworkConnectivity.FULL,
            metered=self.network.get_network_metered(),
            power_saver=self.power.get_power_saver_enabled(),
        )

    def changed(self, *_args):
        if self.closed:
            return
        boot, awake = time.clock_gettime(time.CLOCK_BOOTTIME), time.monotonic()
        resumed = self.clock.update(boot, awake)
        if resumed:
            self.refresh_timestamps()
        if resumed:
            for policy in self.window.interactions.policies.values():
                policy.last_finished = policy.last_success
                policy.failures = 0
        connection = self.connection()
        self.window.connection_changed(connection)
        now = time.time()
        target, decision = self.window.interactions.refresh_decision(now)
        if target is None or not decision.eligible:
            self.stop_timer()
            return
        if decision.due:
            self.check()
            # A refresh can become busy synchronously. Reuse the exact same policy
            # decision after dispatch rather than maintaining a second set of gates.
            target, decision = self.window.interactions.refresh_decision(time.time())
        if target is None or not decision.eligible:
            self.stop_timer()
            return
        policy = self.window.interactions.policy(target.auto_key)
        key = (target.auto_key, policy.last_finished, policy.interval)
        if self.source is None or self.timer_key != key:
            self.stop_timer()
            self.start_timer(max(1, decision.delay), key)

    def check(self):
        if not self.closed:
            self.window.check_auto_refresh(time.time())

    def start_timer(self, seconds=60, key=None):
        self.timer_key = key
        try:
            self.fd = os.timerfd_create(time.CLOCK_BOOTTIME, flags=os.TFD_CLOEXEC | os.TFD_NONBLOCK)
            # One deadline; BOOTTIME expires across suspend without waking hardware.
            os.timerfd_settime(self.fd, initial=seconds, interval=0)
            self.source = GLibUnix.fd_add_full(
                GLib.PRIORITY_DEFAULT, self.fd, GLib.IOCondition.IN, self.tick, None
            )
        except OSError:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            self.source = GLib.timeout_add_seconds(max(1, math.ceil(seconds)), self.tick)

    def tick(self, *_args):
        if self.fd is not None:
            try:
                os.read(self.fd, 8)
            except BlockingIOError:
                return True
        self.stop_timer()
        self.changed()
        return False

    def stop_timer(self):
        self.timer_key = None
        if self.source is not None:
            GLib.source_remove(self.source)
            self.source = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timestamp_source is not None:
            GLib.source_remove(self.timestamp_source)
            self.timestamp_source = None
        if self.timestamp_fd is not None:
            os.close(self.timestamp_fd)
            self.timestamp_fd = None
        self.stop_timer()
        if self.queued is not None:
            GLib.source_remove(self.queued)
            self.queued = None
        if self.window.worker.after_dispatch == self.queue:
            self.window.worker.after_dispatch = lambda: None
        for obj, signal in self.signals:
            obj.disconnect(signal)
        self.signals.clear()
