"""A bounded async worker; completion always dispatched on GTK's main thread."""

import asyncio
import concurrent.futures
import threading
from contextvars import Context

from gi.repository import GLib

from .errors import message


class Worker:
    def __init__(self):
        self.loop = asyncio.EventLoop()
        self.closed = False
        self.cleanup = None
        self.after_dispatch = lambda: None
        self.pending = set()
        self.thread = threading.Thread(
            target=self._run, name="skyloom-network", daemon=True, context=Context()
        )
        self.thread.start()

    def _run(self):
        try:
            self.loop.run_forever()
            self.loop.run_until_complete(self._shutdown())
        finally:
            self.loop.close()

    async def _shutdown(self):
        # Even an empty gather must execute inside the running loop on Python 3.14.
        pending = asyncio.all_tasks() - {asyncio.current_task()}
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        try:
            if self.cleanup is not None:
                await self.cleanup
        finally:
            await self.loop.shutdown_asyncgens()
            await self.loop.shutdown_default_executor()

    def submit(self, coro, done=lambda _x: None, error=lambda _x: None):
        if self.closed or len(self.pending) >= 32:
            coro.close()
            if not self.closed:
                GLib.idle_add(
                    self.dispatch,
                    error,
                    "Skyloom is busy loading content. Wait a moment, then try again.",
                )
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self.pending.add(future)

        def finished(f):
            self.pending.discard(f)
            if self.closed or f.cancelled():
                return
            try:
                result = f.result()
                callback, value = done, result
            except asyncio.CancelledError, concurrent.futures.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 — sanitize every SDK failure before GTK dispatch.
                callback, value = error, message(exc)

            GLib.idle_add(self.dispatch, callback, value)

        future.add_done_callback(finished)
        return future

    def dispatch(self, callback, value):
        if not self.closed:
            try:
                callback(value)
            finally:
                self.after_dispatch()
        return False

    def close(self, cleanup=None):
        self.cleanup = cleanup
        self.closed = True
        for future in tuple(self.pending):
            future.cancel()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)
