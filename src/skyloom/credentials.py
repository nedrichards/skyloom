"""The only persistent token boundary. No plaintext fallback."""

import threading

from . import APP_ID


class KeyringError(Exception):
    pass


class SecretStore:
    def __init__(self):
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Gio, Secret

        self.Gio = Gio
        self.pending = set()
        self.lock = threading.Lock()

        self.api = Secret
        self.schema = Secret.Schema.new(
            APP_ID, Secret.SchemaFlags.NONE, {"application": Secret.SchemaAttributeType.STRING}
        )
        self.attrs = {"application": APP_ID}

    def cancel_all(self):
        with self.lock:
            for cancellable in self.pending:
                cancellable.cancel()

    def call(self, method, *args):
        cancellable = self.Gio.Cancellable()
        with self.lock:
            self.pending.add(cancellable)
        timer = threading.Timer(20, cancellable.cancel)
        timer.daemon = True
        timer.start()
        try:
            return method(*args, cancellable)
        finally:
            timer.cancel()
            with self.lock:
                self.pending.discard(cancellable)

    def load(self):
        try:
            return self.call(self.api.password_lookup_sync, self.schema, self.attrs)
        except Exception:  # noqa: BLE001 — never expose libsecret errors or session material.
            raise KeyringError(
                "Unlock your login keyring, then try again. Skyloom cannot read its saved session."
            ) from None

    def save(self, value):
        try:
            ok = self.call(
                self.api.password_store_sync,
                self.schema,
                self.attrs,
                self.api.COLLECTION_DEFAULT,
                "Skyloom session",
                value,
            )
            if not ok:
                raise RuntimeError
        except Exception:  # noqa: BLE001 — never expose libsecret errors or session material.
            raise KeyringError(
                "Your session could not be saved securely. Unlock your keyring and sign in again."
            ) from None

    def clear(self):
        try:
            self.call(self.api.password_clear_sync, self.schema, self.attrs)
        except Exception:  # noqa: BLE001 — never expose libsecret errors or session material.
            raise KeyringError(
                "Unlock your keyring and try signing out again. The saved session could not be removed."
            ) from None
