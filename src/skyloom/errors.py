"""Never display exception strings: SDK errors can contain credentials or post data."""

import sqlite3

from .credentials import KeyringError

POST_UNAVAILABLE = "This post is deleted, blocked or unavailable."


class UserError(Exception):
    pass


def message(exc):
    if isinstance(exc, sqlite3.DatabaseError):
        return "Skyloom couldn’t read its local data. Your drafts have not been deleted. Back up the application data before attempting recovery."
    if isinstance(exc, (UserError, KeyringError)):
        return str(exc)
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (400, 401):
        return "Your session or sign-in details could not be accepted. Try signing in with a dedicated app password."
    if status == 403:
        return "This action is not permitted for your account or app password."
    if status == 429:
        return "Bluesky is limiting requests. Wait a few minutes, then try again."
    if status == 404:
        return "This content is no longer available."
    return (
        "Couldn’t reach the service or complete this action. Check your connection and try again."
    )
