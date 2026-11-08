"""Event-driven paging state. No timers, automatic retries or concurrent requests."""


class AutoPager:
    def __init__(self, load, changed=lambda: None):
        self.load, self.changed = load, changed
        self.busy = False
        self.cursor = None
        self.error = ""
        self.message = ""
        self.auto = False
        self.attempted = set()
        self.closed = False
        self.manual_available = False

    def begin(self, message="Loading…", reset=False):
        self.manual_available = False
        self.busy, self.error, self.message = True, "", message
        if reset:
            self.attempted.clear()
        self.changed()

    def complete(self, cursor, added, message=""):
        self.manual_available = False
        self.busy, self.error, self.message = False, "", message
        self.cursor = cursor
        # Empty/duplicate pages can still be traversed manually, but cannot spin.
        self.auto = bool(cursor) and added > 0 and cursor not in self.attempted
        self.changed()

    def fail(self, message):
        self.busy, self.auto = False, False
        self.error, self.message = message, ""
        self.changed()

    def request(self, automatic=False):
        if self.closed or self.busy or (automatic and (not self.auto or not self.cursor)):
            return False
        if not automatic and not (self.cursor or self.error or self.manual_available):
            return False
        if automatic and self.cursor in self.attempted:
            return False
        if self.cursor:
            self.attempted.add(self.cursor)
        self.auto, self.busy = False, True
        self.error, self.message = "", "Loading…"
        self.changed()
        self.load()
        return True

    def near_end(self, value, upper, page_size):
        if page_size > 0 and upper - value - page_size <= max(480, page_size * 2):
            return self.request(automatic=True)
        return False
