"""Run under GNOME 51 for worker/main-thread and image contracts."""

import asyncio
import tempfile
import threading
import unittest
from contextvars import ContextVar
from pathlib import Path

try:
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    RUNTIME = True
except ImportError, ValueError, AttributeError:
    RUNTIME = False


@unittest.skipUnless(RUNTIME, "GNOME 51 GI runtime required")
class WorkerTests(unittest.TestCase):
    def test_thread_context_is_explicit_and_requests_keep_their_context(self):
        from skyloom.worker import Worker

        marker = ContextVar("synthetic-worker-test", default="empty")

        class ObservedWorker(Worker):
            def _run(self):
                self.initial_context = marker.get()
                super()._run()

        token = marker.set("caller")
        worker = ObservedWorker()
        try:

            async def inspect():
                return marker.get(), asyncio.get_running_loop()

            # Submission deliberately propagates the per-request context; the base thread is empty.
            request = worker.submit(inspect())
            value, loop = request.result(timeout=3)
            self.assertEqual(worker.initial_context, "empty")
            self.assertEqual(value, "caller")
            self.assertIs(loop, worker.loop)
        finally:
            worker.close()
            marker.reset(token)
        self.assertTrue(worker.loop.is_closed())

    def test_failures_are_sanitized_before_main_thread_dispatch(self):
        from skyloom.worker import Worker

        worker = Worker()
        owner = threading.get_ident()
        result = []
        loop = GLib.MainLoop()

        async def fail():
            raise RuntimeError("synthetic secret-shaped diagnostic must not reach UI")

        def failed(text):
            result.append((text, threading.get_ident()))
            loop.quit()

        worker.submit(fail(), error=failed)
        deadline = GLib.timeout_add(3000, lambda: (loop.quit(), False)[1])
        try:
            loop.run()
        finally:
            GLib.source_remove(deadline)
            worker.close()
        self.assertTrue(result)
        self.assertNotIn("secret-shaped", result[0][0])
        self.assertEqual(result[0][1], owner)

    def test_dispatch_cancellation_and_shutdown(self):
        from skyloom.worker import Worker

        worker = Worker()
        owner = threading.get_ident()
        result = []
        loop = GLib.MainLoop()

        async def work():
            return threading.get_ident()

        def done(thread):
            result.append((thread, threading.get_ident()))
            loop.quit()

        worker.submit(work(), done)
        deadline = GLib.timeout_add(3000, lambda: (loop.quit(), False)[1])
        loop.run()
        GLib.source_remove(deadline)
        self.assertTrue(result)
        self.assertNotEqual(result[0][0], owner)
        self.assertEqual(result[0][1], owner)

        async def wait():
            await asyncio.sleep(60)

        cancelled = worker.submit(wait(), lambda _: self.fail("Cancelled completion reached UI"))
        cancelled.cancel()
        worker.close()
        self.assertFalse(worker.thread.is_alive())

    def test_bounded_queue(self):
        from skyloom.worker import Worker

        worker = Worker()

        async def pending():
            await asyncio.Event().wait()

        try:
            for _ in range(32):
                worker.submit(pending())
            self.assertIsNone(worker.submit(pending()))
            self.assertLessEqual(len(worker.pending), 32)
        finally:
            worker.close()
        self.assertFalse(worker.thread.is_alive())


@unittest.skipUnless(RUNTIME, "GNOME 51 GI runtime required")
class ImageTests(unittest.TestCase):
    def test_late_image_picker_and_preparation_cannot_follow_signout(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from skyloom.composer import Composer
        from skyloom.domain import Author
        from skyloom.storage import Storage

        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(directory)
            account = Author("did:example:picker", "picker.invalid", "Invented picker")
            storage.activate(account.did)
            service = SimpleNamespace(account=account, storage=storage)
            callbacks, requests = [], []
            dialog = SimpleNamespace(
                set_filters=lambda _: None,
                open=lambda _window, _cancel, callback: callbacks.append(callback),
                open_finish=lambda _: SimpleNamespace(get_path=lambda: "unused-fixture.png"),
            )
            owner = SimpleNamespace(
                window=SimpleNamespace(
                    service=service,
                    worker=SimpleNamespace(submit=lambda *args: requests.append(args)),
                ),
                closed=False,
                add=SimpleNamespace(set_sensitive=lambda _: None),
                attachments=[],
                render_attachments=lambda: self.fail("Stale preparation changed the composer"),
                changed=lambda: self.fail("Stale preparation changed the draft"),
            )
            with patch("skyloom.composer.Gtk.FileDialog", return_value=dialog):
                Composer.choose_image(owner)
                owner.closed = True
                callbacks.pop()(dialog, None)
                self.assertFalse(requests)
                owner.closed = False
                Composer.choose_image(owner)
                callbacks.pop()(dialog, None)
            self.assertEqual(len(requests), 1)
            work, ready, _failed = requests[0]
            storage.clear(account.did)
            service.account = None
            result = asyncio.run(work)
            self.assertIsNone(result)
            ready(result)
            ready("old-account-result.png")
            self.assertFalse(owner.attachments)
            self.assertFalse(list(storage.base.glob("*-images")))

    def test_signout_waits_for_running_preparation_and_rejects_queued_copies(self):
        from unittest.mock import patch

        from skyloom.media import prepare
        from skyloom.storage import Storage

        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory) / "private")
            account = "did:example:preparation"
            token = storage.activate(account)
            source = Path(directory) / "source.png"
            pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 8, 8)
            pix.fill(0x3584E4FF)
            pix.savev(str(source), "png", [], [])
            entered, release, clearing, cleared = (threading.Event() for _ in range(4))
            results = []

            def delayed(path, target):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Invented preparation gate was not released")
                return prepare(path, target)

            def make():
                results.append(storage.run(account, token, "prepare_image", source))

            def clear():
                clearing.set()
                storage.clear(account)
                cleared.set()

            with patch("skyloom.media.prepare", delayed):
                worker = threading.Thread(target=make)
                worker.start()
                try:
                    self.assertTrue(entered.wait(3))
                    cleanup = threading.Thread(target=clear)
                    cleanup.start()
                    self.assertTrue(clearing.wait(3))
                    self.assertFalse(cleared.wait(0.05))
                finally:
                    release.set()
                    worker.join(5)
                    if clearing.is_set():
                        cleanup.join(5)
            self.assertTrue(cleared.is_set())
            self.assertEqual(len(results), 1)
            self.assertFalse(Path(results[0]).exists())
            self.assertIsNone(storage.run(account, token, "prepare_image", source))
            self.assertFalse(list(storage.base.glob("*-images")))
            self.assertTrue(source.exists())

    def test_images_survive_restart_offline_and_corruption_recovers_online(self):
        from unittest.mock import patch

        import httpx

        from skyloom.image_cache import ImageCache
        from skyloom.media import Images

        pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 8, 8)
        pix.fill(0x3584E4FF)
        _ok, payload = pix.save_to_bufferv("png", [], [])
        calls = []

        def response(request):
            calls.append(str(request.url))
            return httpx.Response(200, content=payload)

        client_type = httpx.AsyncClient

        async def exercise(directory):
            disk = ImageCache(Path(directory) / "cache")
            images = Images(directory, disk)
            images.use_account("alice")
            url = "https://cdn.bsky.app/img/fixture.png"
            await images.get(url)
            restored = Images(directory, ImageCache(disk.root))
            restored.use_account("alice")
            restored.auto_download_allowed = lambda: False
            await restored.catalog()
            self.assertTrue(restored.has_cached(url))
            self.assertEqual((await restored.get(url)).get_width(), 8)
            self.assertEqual(len(calls), 1)
            restored.use_account("bob")
            await restored.catalog()
            self.assertFalse(restored.has_cached(url))
            disk.path("alice", url).write_bytes(b"broken")
            restored.use_account("alice")
            restored.auto_download_allowed = lambda: True
            self.assertEqual((await restored.get(url)).get_width(), 8)
            self.assertTrue(restored.disk_error)
            self.assertEqual(len(calls), 2)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "skyloom.media.httpx.AsyncClient",
                lambda **kwargs: client_type(transport=httpx.MockTransport(response), **kwargs),
            ),
        ):
            asyncio.run(exercise(directory))

    def test_shared_image_work_and_textures_survive_one_waiter_cancel(self):
        from unittest.mock import patch

        import httpx

        from skyloom.media import Images

        pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 8, 8)
        pix.fill(0x3584E4FF)
        _ok, payload = pix.save_to_bufferv("png", [], [])
        client_type = httpx.AsyncClient

        async def exercise():
            started, release = asyncio.Event(), asyncio.Event()
            calls = []

            async def response(request):
                calls.append(request.url.path)
                started.set()
                await release.wait()
                return httpx.Response(200, content=payload)

            with patch(
                "skyloom.media.httpx.AsyncClient",
                lambda **kw: client_type(transport=httpx.MockTransport(response), **kw),
            ):
                images = Images(".")
                url = "https://cdn.bsky.app/img/shared-fixture.png"
                tasks = [asyncio.create_task(images.get(url)) for _ in range(12)]
                await asyncio.wait_for(started.wait(), 1)
                tasks[0].cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await tasks[0]
                release.set()
                textures = await asyncio.gather(*tasks[1:])
                self.assertTrue(all(image is textures[0] for image in textures))
                self.assertIs(await images.get(url), textures[0])
                self.assertEqual(len(calls), 1)
                self.assertEqual(textures[0].get_width(), 8)
                self.assertFalse(images.inflight)
                release.clear()
                started.clear()
                tasks = [asyncio.create_task(images.get(url + "-cancel")) for _ in range(2)]
                await asyncio.wait_for(started.wait(), 1)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(0)
                self.assertFalse(images.inflight)
                self.assertNotIn((url + "-cancel", False), images.cache)
                started.clear()
                old = asyncio.create_task(images.get(url + "-account"))
                await asyncio.wait_for(started.wait(), 1)
                images.use_account("another-invented-account")
                release.set()
                previous = await old
                self.assertNotIn((url + "-account", False), images.cache)
                current = await images.get(url + "-account")
                self.assertIsNot(current, previous)
                self.assertFalse(images.inflight)

        asyncio.run(exercise())

    def test_paused_downloads_allow_explicit_viewing_and_cached_or_local_images(self):
        from unittest.mock import patch

        import httpx

        from skyloom.errors import UserError
        from skyloom.media import Images

        pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 8, 8)
        pix.fill(0x3584E4FF)
        _ok, payload = pix.save_to_bufferv("png", [], [])
        calls = []

        def response(request):
            calls.append(request.url.path)
            return httpx.Response(200, content=payload)

        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(response)

        async def exercise(directory):
            images = Images(directory)
            images.auto_download_allowed = lambda: False
            url = "https://cdn.bsky.app/img/fixture.png"
            with self.assertRaises(UserError):
                await images.get(url)
            self.assertFalse(calls)
            viewed = await images.get(url, explicit=True)
            self.assertEqual(viewed.get_width(), 8)
            self.assertIs(await images.get(url), viewed)
            local = Path(directory) / "fixture.png"
            local.write_bytes(payload)
            self.assertEqual((await images.get(str(local), local=True)).get_width(), 8)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "skyloom.media.httpx.AsyncClient",
                lambda **kwargs: client_type(transport=transport, **kwargs),
            ),
        ):
            asyncio.run(exercise(directory))
        self.assertEqual(calls, ["/img/fixture.png"])

    def test_boottime_timer_dispatches_once_and_closes_without_sleeping_hardware(self):
        import os

        from skyloom.refresh_monitor import RefreshMonitor

        monitor = RefreshMonitor.__new__(RefreshMonitor)
        from types import SimpleNamespace

        monitor.fd = monitor.source = monitor.queued = None
        monitor.window = SimpleNamespace(worker=SimpleNamespace(after_dispatch=None))
        monitor.closed = False
        monitor.signals = []
        calls = []
        loop = GLib.MainLoop()

        def changed():
            calls.append(True)
            monitor.stop_timer()
            loop.quit()

        monitor.changed = changed
        monitor.start_timer()
        self.assertIsNotNone(monitor.fd, "The supported runtime should provide BOOTTIME timerfd")
        fd = monitor.fd
        os.timerfd_settime(fd, initial=0.01)
        deadline = GLib.timeout_add(1000, lambda: (loop.quit(), False)[1])
        try:
            loop.run()
        finally:
            GLib.source_remove(deadline)
            monitor.close()
        self.assertEqual(calls, [True])
        self.assertIsNone(monitor.source)
        self.assertIsNone(monitor.fd)
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_preparation_strips_metadata_and_bounds(self):
        from skyloom.errors import UserError
        from skyloom.media import decode, prepare

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 64, 64)
            pix.fill(0x3584E4FF)
            pix.savev(str(path), "png", ["tEXt::Comment"], ["TEST-ONLY-METADATA"])
            self.assertIn(b"TEST-ONLY-METADATA", path.read_bytes())
            target = Path(prepare(str(path), Path(directory) / "prepared"))
            self.assertNotIn(b"TEST-ONLY-METADATA", target.read_bytes())
            self.assertLessEqual(target.stat().st_size, 1_000_000)
            self.assertEqual(decode(target.read_bytes()).get_width(), 64)
            bad = Path(directory) / "bad.svg"
            bad.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
            with self.assertRaises(UserError):
                prepare(str(bad), Path(directory) / "prepared")
            with self.assertRaises(UserError):
                decode(b"unsupported")
