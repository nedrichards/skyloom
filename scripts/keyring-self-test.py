#!/usr/bin/env python3
"""Use an isolated dummy entry; never read the application's actual account session."""

from skyloom.credentials import SecretStore

store = SecretStore()
store.attrs = {"application": "com.nedrichards.Skyloom.Validation"}
try:
    store.save("invalid-test-only-value")
    if store.load() != "invalid-test-only-value":
        raise RuntimeError("Dummy keyring entry did not round-trip")
    store.clear()
    if store.load() is not None:
        raise RuntimeError("Dummy keyring entry was not removed")
    print("KEYRING_SELF_TEST_PASS: isolated dummy value stored, read and removed")
finally:
    store.clear()
