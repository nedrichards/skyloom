"""Identity and liveness ownership for completions already queued to the UI loop."""


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
    previous = window.page_requests.pop(key, None)
    if previous:
        previous.cancel()
    future = None

    def finish(callback, value):
        if key not in window.page_requests or window.page_requests[key] is not future:
            return
        window.page_requests.pop(key)
        callback(value)

    success = guard(window, page, done)
    error = guard(window, page, failed)
    future = window.worker.submit(
        coro, lambda value: finish(success, value), lambda value: finish(error, value)
    )
    window.page_requests[key] = future
    return future
