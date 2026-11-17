"""Identity and liveness ownership for completions already queued to the UI loop."""

from concurrent.futures import Future


def guard(window, page, callback):
    generation = window.generation
    content = getattr(page, "content_view", None)
    account = getattr(getattr(window, "service", None), "account", None)

    def guarded(*args):
        if (
            window.generation == generation
            and getattr(getattr(window, "service", None), "account", None) is account
            and not getattr(window, "closing", False)
            and (page is None or (not getattr(page, "_scope_closed", False) and page.get_parent()))
            and (
                content is None
                or (getattr(page, "content_view", None) is content and not content.paging.closed)
            )
        ):
            return callback(*args)
        return None

    return guarded


def submit(window, key, coro, done, failed, *, page=None):
    # Speculative reads yield the serialised service connection to foreground work.
    if key != "thread-prefetch":
        speculative = window.page_requests.pop("thread-prefetch", None)
        if speculative:
            speculative.cancel()
    previous = window.page_requests.pop(key, None)
    if previous:
        previous.cancel()
    request = None

    def finish(callback, value):
        if window.page_requests.get(key) is not request:
            return
        window.page_requests.pop(key)
        callback(value)

    success = guard(window, page, done)
    error = guard(window, page, failed)
    future = window.worker.submit(
        coro, lambda value: finish(success, value), lambda value: finish(error, value)
    )
    # The worker queues its rejection before returning None. Track that queued
    # completion with its own cancellable identity too.
    request = future if future is not None else Future()
    window.page_requests[key] = request
    return future
