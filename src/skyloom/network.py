"""Finite timeouts and shared rate-limit cooldown, without mutation retries."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from atproto import AsyncClient
from atproto_client.exceptions import RateLimitExceededError
from atproto_client.request import AsyncRequest

from .errors import UserError


async def require_https(request):
    # HTTPX calls request hooks for every redirect hop too. The SDK can replace
    # its PDS endpoint from session/DID data, bypassing the sign-in form check.
    if request.url.scheme != "https" or request.url.userinfo:
        raise UserError("The server must use HTTPS without credentials in its address.")


class Request(AsyncRequest):
    def __init__(self, **kwargs):
        hooks = {key: list(value) for key, value in kwargs.pop("event_hooks", {}).items()}
        hooks.setdefault("request", []).append(require_https)
        super().__init__(timeout=20, event_hooks=hooks, **kwargs)
        self.retry_at = 0.0

    async def _send_request(self, method, url, **kwargs):
        if self.retry_at > time.monotonic():
            # Do not occupy a worker for arbitrary server-directed hours; fail with the same safe UI taxonomy.
            raise UserError("Bluesky is limiting requests. Wait a few minutes, then try again.")
        try:
            return await super()._send_request(method, url, **kwargs)
        except RateLimitExceededError as exc:
            headers = getattr(exc.response, "headers", {})
            value = headers.get("retry-after", "60")
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
                except ValueError, TypeError:
                    delay = 60
            self.retry_at = time.monotonic() + max(1, min(delay, 3600))
            raise


def new_client(base_url="https://bsky.social"):
    return AsyncClient(base_url=base_url, request=Request())
