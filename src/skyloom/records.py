"""Bounded cursor bookkeeping for record lists without feed ordering semantics."""


class RecordPager:
    def __init__(self, key, limit=200):
        self.key, self.limit = key, limit
        self.items = []
        self.cursor = None
        self.seen = set()

    def merge(self, items, cursor, *, reset=False):
        if reset:
            self.items.clear()
            self.seen.clear()
        known = {self.key(item) for item in self.items}
        added = [
            item for item in items if self.key(item) not in known and not known.add(self.key(item))
        ]
        self.items = (self.items + added)[-self.limit :]
        self.cursor = cursor if cursor not in self.seen else None
        if cursor:
            self.seen.add(cursor)
        return len(added)
