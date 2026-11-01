"""Invented-data prefetch budgets, shared cache and cancellation ownership."""

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_conversation import node

from skyloom.conversation import ThreadPage, thread_from
from skyloom.domain import post_from
from skyloom.thread_prefetch import HomeThreadPrefetch, ThreadCache


class ThreadCacheTests(unittest.TestCase):
    def test_budget_deduplication_expiry_and_bounded_retention(self):
        clock = Mock()
        cache = ThreadCache(clock=clock)
        post = post_from(node("root")["post"])
        clock.return_value = 1000
        self.assertTrue(cache.claim(post.uri))
        self.assertFalse(cache.claim(post.uri))
        for i in range(5):
            self.assertTrue(cache.claim(str(i)))
        self.assertFalse(cache.claim("over-budget"))
        for i in range(40):
            cached = replace(post, uri=f"at://invented/cache/{i}")
            cache.put(cached.uri, ThreadPage((cached,)))
        self.assertEqual(len(cache.pages), 32)
        self.assertEqual(cache.get(cached.uri).posts, (cached,))
        clock.return_value = 1130
        self.assertIsNone(cache.get(cached.uri))
        self.assertFalse(cache.claim(post.uri))
        self.assertTrue(cache.claim("new"))
        clock.return_value = 1400
        self.assertTrue(cache.claim(post.uri))

    def test_ancestry_only_posts_do_not_supply_cached_reply_coverage(self):
        cache = ThreadCache()
        root_node = node("root", reply_count=2)
        child_node = node("child", root_node)
        page = thread_from(child_node)
        root_uri = root_node["post"]["uri"]
        child_uri = child_node["post"]["uri"]
        cache.put(child_uri, page)
        self.assertIn(root_uri, cache.get_snapshot(child_uri).uris)
        self.assertIs(cache.get(child_uri), page)
        self.assertIsNone(cache.get_snapshot(root_uri))
        self.assertIsNone(cache.get(root_uri))

    def test_snapshot_retains_fetch_anchor_and_expires_without_renewing_on_read(self):
        clock = Mock(return_value=1000)
        cache = ThreadCache(clock=clock)
        root_node = node("root", reply_count=1)
        root = post_from(root_node["post"])
        child = post_from(node("child", root_node, reply_count=1)["post"])
        page = ThreadPage((root, child), branches=(child.uri,))
        cache.put(root.uri, page)
        clock.return_value = 1110
        snapshot = cache.get_snapshot(child.uri)
        self.assertEqual(snapshot.anchor, root.uri)
        self.assertEqual(snapshot.created, 1000)
        self.assertIs(snapshot.page, page)
        self.assertIs(cache.get(child.uri), page)
        self.assertEqual(len(cache.pages), 1)
        clock.return_value = 1121
        self.assertIsNone(cache.get_snapshot(root.uri))
        self.assertIsNone(cache.get(child.uri))

    def test_local_reactions_survive_late_thread_response_without_hiding_new_content(self):
        clock = Mock(return_value=1000)
        cache = ThreadCache(clock=clock)
        root = post_from(node("root")["post"])
        cache.put(root.uri, ThreadPage((root,)))
        clock.return_value = 1050
        latest = replace(
            root,
            likes=9,
            like_uri="at://invented/like",
            reposts=4,
            repost_uri="at://invented/repost",
        )
        cache.update_post(latest)
        snapshot = cache.get_snapshot(root.uri)
        self.assertEqual(snapshot.created, 1000)
        self.assertEqual(snapshot.page.posts[0], latest)
        late = replace(root, text="New server content", replies=5)
        clock.return_value = 1060
        cache.put(root.uri, ThreadPage((late,)))
        reconciled = cache.get(root.uri).posts[0]
        self.assertEqual(reconciled.text, late.text)
        self.assertEqual(reconciled.replies, 5)
        self.assertEqual((reconciled.likes, reconciled.like_uri), (latest.likes, latest.like_uri))
        self.assertEqual(
            (reconciled.reposts, reconciled.repost_uri), (latest.reposts, latest.repost_uri)
        )
        self.assertEqual(cache.get_snapshot(root.uri).created, 1060)

    def test_reaction_before_prefetch_completion_is_applied_to_first_snapshot(self):
        cache = ThreadCache()
        root = post_from(node("root")["post"])
        latest = replace(root, likes=1, like_uri="pending")
        cache.update_post(latest)
        cache.put(root.uri, ThreadPage((root,)))
        self.assertEqual(cache.get(root.uri).posts[0], latest)
        confirmed = replace(latest, like_uri="at://invented/confirmed-like")
        cache.update_post(confirmed)
        self.assertEqual(cache.reconcile(ThreadPage((root,))).posts[0], confirmed)

    def test_reaction_overlay_only_protects_requests_started_before_acknowledged_change(self):
        cache = ThreadCache()
        root = post_from(node("root")["post"])
        old_started = cache.revision
        latest = replace(root, likes=1, like_uri="at://invented/confirmed-like")
        cache.update_post(latest)
        new_started = cache.revision
        self.assertGreater(new_started, old_started)
        # A response already in flight must not undo the acknowledged local like.
        cache.put(root.uri, ThreadPage((root,)), started=old_started)
        self.assertEqual(cache.get(root.uri).posts[0], latest)
        # A later explicit refresh may observe a change made by another client.
        newer_server = replace(root, likes=4, reposts=2, repost_uri="at://invented/new-repost")
        cache.put(root.uri, ThreadPage((newer_server,)), started=new_started)
        self.assertEqual(cache.get(root.uri).posts[0], newer_server)
        self.assertEqual(cache.reconcile(ThreadPage((root,)), started=old_started).posts[0], latest)
        self.assertEqual(
            cache.reconcile(ThreadPage((newer_server,)), started=new_started).posts[0], newer_server
        )

    def test_unrelated_reaction_does_not_restore_overlay_superseded_by_newer_response(self):
        cache = ThreadCache()
        root = post_from(node("root")["post"])
        local = replace(root, likes=1, like_uri="at://invented/confirmed-like")
        cache.update_post(local)
        newer_server = replace(root, likes=4, reposts=2, repost_uri="at://invented/new-repost")
        cache.put(root.uri, ThreadPage((newer_server,)), started=cache.revision)
        unrelated = post_from(node("unrelated")["post"])
        cache.update_post(replace(unrelated, likes=1, like_uri="at://invented/another-like"))
        self.assertEqual(cache.get(root.uri).posts[0], newer_server)

    def test_pending_reaction_remains_protected_for_a_new_request(self):
        cache = ThreadCache()
        root = post_from(node("root")["post"])
        pending = replace(root, likes=1, like_uri="pending")
        cache.update_post(pending)
        started = cache.revision
        cache.put(root.uri, ThreadPage((root,)), started=started)
        self.assertEqual(cache.get(root.uri).posts[0], pending)

    def test_clear_retires_snapshots_attempts_and_reaction_overrides(self):
        cache = ThreadCache()
        root = post_from(node("root")["post"])
        cache.claim(root.uri)
        cache.put(root.uri, ThreadPage((root,)))
        cache.update_post(replace(root, likes=1, like_uri="at://invented/like"))
        cache.clear()
        self.assertIsNone(cache.get(root.uri))
        self.assertFalse(cache.pages)
        self.assertFalse(cache.attempts)
        self.assertFalse(cache.requests)
        self.assertTrue(cache.claim(root.uri))
        cache.put(root.uri, ThreadPage((root,)))
        self.assertEqual(cache.get(root.uri).posts[0], root)


class HomeThreadPrefetchTests(unittest.TestCase):
    def setUp(self):
        self.root = post_from(node("root", reply_count=1)["post"])
        self.rows = [(0, SimpleNamespace(_value=self.root))]
        self.view = SimpleNamespace(
            paging=SimpleNamespace(closed=False),
            get_mapped=lambda: True,
            connect=Mock(),
            cleanups=[],
            interaction=SimpleNamespace(visible_rows=lambda: self.rows),
        )
        self.window = SimpleNamespace(
            connect=Mock(),
            disconnect=Mock(),
            is_active=lambda: True,
            read_only=False,
            automatic_pause_reason=lambda: "",
            page_requests={},
            mutations=set(),
            service=SimpleNamespace(thread=Mock(return_value="request")),
            interactions=SimpleNamespace(current_view=lambda: self.view, context=lambda: "list"),
        )
        self.cache = ThreadCache()
        self.prefetch = HomeThreadPrefetch(self.window, self.view, self.cache)
        self.prefetch.schedule = Mock()

    def test_response_enriches_positions_and_cache_without_inserting_feed_rows(self):
        future = Mock()
        with patch("skyloom.thread_prefetch.submit", return_value=future) as submit:
            self.prefetch.run()
        self.window.service.thread.assert_called_once_with(self.root.uri)
        child = post_from(node("child", node("root"))["post"])
        page = ThreadPage((self.root, child))
        submit.call_args.args[3](page)
        self.assertEqual(self.window.post_positions.context.positions[self.root.uri], (1, 2, False))
        self.assertIs(self.cache.get(child.uri), page)
        self.assertEqual(len(self.rows), 1)
        self.assertIsNone(self.prefetch.future)
        self.prefetch.schedule.assert_called_once()

    def test_ineligible_busy_and_standalone_views_do_not_fetch(self):
        with patch("skyloom.thread_prefetch.submit") as submit:
            self.window.automatic_pause_reason = lambda: "Metered"
            self.prefetch.run()
            self.window.automatic_pause_reason = lambda: ""
            self.window.page_requests["foreground"] = Mock()
            self.prefetch.run()
            self.window.page_requests.clear()
            self.rows[:] = [(0, SimpleNamespace(_value=post_from(node("plain")["post"])))]
            self.prefetch.run()
            submit.assert_not_called()

    def test_deep_visible_reply_fetches_its_own_context_and_deduplicates_by_root(self):
        middle = post_from(node("middle", node("root"))["post"])
        deep = replace(
            post_from(node("deep", node("middle"))["post"]),
            root=(self.root.uri, self.root.cid),
            parent=(middle.uri, middle.cid),
        )
        sibling = replace(deep, uri=deep.uri + "-sibling")
        self.rows[:] = [(0, SimpleNamespace(_value=deep)), (100, SimpleNamespace(_value=sibling))]
        future = Mock()
        with patch("skyloom.thread_prefetch.submit", return_value=future) as submit:
            self.prefetch.run()
            self.window.service.thread.assert_called_once_with(deep.uri)
            self.assertEqual(set(self.cache.attempts), {self.root.uri})
            submit.call_args.args[3](ThreadPage((middle, deep)))
            self.assertEqual(self.cache.get_snapshot(deep.uri).anchor, deep.uri)
            self.prefetch.run()
            self.assertEqual(submit.call_count, 1)

    def test_pending_mutation_defers_home_dispatch_until_foreground_becomes_idle(self):
        self.window.mutations.add((self.root.uri, "like"))
        with patch("skyloom.thread_prefetch.submit") as submit:
            self.prefetch.run()
            submit.assert_not_called()
        self.window.mutations.clear()
        self.prefetch.schedule = HomeThreadPrefetch.schedule.__get__(self.prefetch)
        with patch("skyloom.thread_prefetch.GLib.timeout_add", return_value=41):
            self.prefetch.reconsider()
        self.assertEqual(self.prefetch.timer, 41)

    def test_busy_to_idle_reconsideration_arms_one_debounce_across_repeated_notifications(self):
        self.window.page_requests["foreground"] = Mock()
        self.prefetch.run()
        self.assertTrue(self.prefetch.waiting)
        self.window.page_requests.clear()
        self.prefetch.schedule = HomeThreadPrefetch.schedule.__get__(self.prefetch)
        with (
            patch("skyloom.thread_prefetch.GLib.timeout_add", return_value=41) as timeout,
            patch("skyloom.thread_prefetch.GLib.source_remove") as remove,
        ):
            for _ in range(10):
                self.prefetch.reconsider()
            timeout.assert_called_once()
            remove.assert_not_called()
            self.assertEqual(self.prefetch.timer, 41)
            self.assertFalse(self.prefetch.waiting)

    def test_unchanged_policy_reconsiderations_do_not_restart_idle_debounce(self):
        self.prefetch.schedule = HomeThreadPrefetch.schedule.__get__(self.prefetch)
        with (
            patch("skyloom.thread_prefetch.GLib.timeout_add", return_value=41) as timeout,
            patch("skyloom.thread_prefetch.GLib.source_remove") as remove,
        ):
            self.prefetch.schedule()
            for _ in range(10):
                self.prefetch.reconsider()
            timeout.assert_called_once()
            remove.assert_not_called()
            self.window.automatic_pause_reason = lambda: "Power saver"
            self.prefetch.reconsider()
            self.assertIsNone(self.prefetch.timer)
            remove.assert_called_once_with(41)
            self.window.automatic_pause_reason = lambda: ""
            self.prefetch.reconsider()
            self.assertEqual(timeout.call_count, 2)

    def test_controller_recovers_after_global_request_slot_is_cleared(self):
        future = Mock()
        with patch("skyloom.thread_prefetch.submit", return_value=future):
            self.prefetch.run()
        self.window.page_requests[self.prefetch.key] = future
        self.window.page_requests.clear()
        future.cancel()
        self.prefetch.schedule = HomeThreadPrefetch.schedule.__get__(self.prefetch)
        with patch("skyloom.thread_prefetch.GLib.timeout_add", return_value=41):
            self.prefetch.reconsider()
        self.assertIsNone(self.prefetch.future)
        self.assertEqual(self.prefetch.timer, 41)

    def test_unmap_cancels_only_its_own_request_and_failure_is_not_retried(self):
        future = Mock()
        with patch("skyloom.thread_prefetch.submit", return_value=future) as submit:
            self.prefetch.run()
            submit.call_args.args[4]("offline")
            self.prefetch.run()
            self.assertEqual(submit.call_count, 1)
        self.prefetch.future = future
        replacement = Mock()
        self.window.page_requests[self.prefetch.key] = replacement
        self.prefetch.cancel()
        future.cancel.assert_called_once()
        self.assertIs(self.window.page_requests[self.prefetch.key], replacement)
