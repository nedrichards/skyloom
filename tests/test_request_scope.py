import unittest
from types import SimpleNamespace

from skyloom.request_scope import guard, submit


class RequestScopeTests(unittest.TestCase):
    def setUp(self):
        self.callbacks = []
        self.events = []
        self.alive = True
        self.window = SimpleNamespace(
            generation=0,
            page_requests={},
            service=SimpleNamespace(account=object()),
            worker=SimpleNamespace(submit=self.enqueue),
        )
        self.page = SimpleNamespace(get_parent=lambda: self.alive)

    def enqueue(self, coro, done, failed):
        coro.close()
        self.callbacks.append((done, failed))
        return SimpleNamespace(cancel=lambda: False)

    async def request(self):
        return None

    def test_queued_old_success_and_error_do_not_apply_or_remove_replacement(self):
        submit(
            self.window,
            "page",
            self.request(),
            self.events.append,
            self.events.append,
            page=self.page,
        )
        newer = submit(
            self.window,
            "page",
            self.request(),
            self.events.append,
            self.events.append,
            page=self.page,
        )
        for callback in self.callbacks[0]:
            callback("old")
        self.assertEqual(self.events, [])
        self.assertIs(self.window.page_requests["page"], newer)
        self.callbacks[1][0]("new")
        self.assertEqual(self.events, ["new"])
        self.assertNotIn("page", self.window.page_requests)

    def test_replaced_or_closed_content_is_retired_before_page_detachment(self):
        for replaced in (False, True):
            self.setUp()
            view = SimpleNamespace(paging=SimpleNamespace(closed=False))
            self.page.content_view = view
            callback = guard(self.window, self.page, self.events.append)
            if replaced:
                self.page.content_view = SimpleNamespace(paging=SimpleNamespace(closed=False))
            else:
                view.paging.closed = True
            callback("retired content")
            self.assertEqual(self.events, [])

    def test_both_completion_paths_reject_closed_page_and_changed_account_generation(self):
        for change in (
            lambda: setattr(self.page, "_scope_closed", True),
            lambda: setattr(self, "alive", False),
            lambda: setattr(self.window, "generation", 1),
            lambda: setattr(self.window.service, "account", object()),
        ):
            self.setUp()
            callback = guard(self.window, self.page, self.events.append)
            change()
            callback("stale")
            self.assertEqual(self.events, [])
