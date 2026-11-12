"""Transient feed ordering, arrivals and gap traversal, separate from checkpoints."""

from .feed_state import FeedGap


class FeedCoordination:
    def __init__(self, window, view, feed):
        self.window, self.view, self.feed = window, view, feed
        self.startup = True
        self.unseen = set()
        self.gap_states = {}
        self.gap_attempted = set()

    def autoload_gap(self):
        if len(self.gap_attempted) >= 8:
            return False
        for _y, row in self.view.interaction.visible_rows():
            gap = row._value
            if (
                isinstance(gap, FeedGap)
                and gap.cursor
                # A leading gap has no retained head to bridge from. Leave it
                # manual; Go to top fetches the actual newest page instead.
                and gap.before != self.window.pagers[self.feed].posts[0].uri
                and not gap.busy
                and not gap.error
                and (gap.before, gap.cursor) not in self.gap_attempted
            ):
                self.window.load_feed_gap(self.view, gap.before)
                return True
        return False
