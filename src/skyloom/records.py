"""Bounded cursor bookkeeping for record lists without feed ordering semantics."""


class RecordPager:
    def __init__(self, key, limit=200):
        self.key, self.limit = key, limit
        self.items = []
        self.cursor = None
        self.seen = set()

    def merge(self, items, cursor, *, reset=False, anchor=None):
        request_cursor = None if reset else self.cursor
        if reset:
            self.items.clear()
            self.seen.clear()
        known = {self.key(item) for item in self.items}
        added = [
            item for item in items if self.key(item) not in known and not known.add(self.key(item))
        ]
        combined = self.items + added
        anchor_index = next(
            (i for i, item in enumerate(combined) if self.key(item) == anchor), len(combined)
        )
        start = min(max(0, len(combined) - self.limit), anchor_index)
        end = start + self.limit
        self.items = combined[start:end]
        if end < len(combined):
            # Retain the reader and refetch an omitted page from its real cursor.
            self.cursor = request_cursor
            self.seen.discard(request_cursor)
        else:
            self.cursor = cursor if cursor not in self.seen else None
            if cursor:
                self.seen.add(cursor)
        retained = {self.key(item) for item in self.items}
        return sum(self.key(item) in retained for item in added)
