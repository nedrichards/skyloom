"""Bounded account-private image files; all filesystem methods run on worker threads."""

import hashlib
import os
import shutil
import stat
import tempfile
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from pathlib import Path


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class ImageCache:
    def __init__(self, root, *, max_bytes=128 * 1024 * 1024, max_files=2048):
        self.root = Path(root)
        self.max_bytes, self.max_files = max_bytes, max_files
        self.io_lock, self.state_lock = threading.Lock(), threading.Lock()
        self.serial, self.tokens = 0, {}
        self.indexed_account = None
        self.entries = OrderedDict()
        self.size = 0

    def activate(self, account):
        # The GUI may call this: the state lock never encloses filesystem IO.
        with self.state_lock:
            self.serial += 1
            self.tokens[account] = self.serial
            return self.serial

    def directory(self, account):
        return self.root / digest(account)

    def path(self, account, url):
        return self.directory(account) / (digest(url) + ".image")

    def _scan(self, account):
        directory = self.directory(account)
        cutoff = time.time() - 86400
        for partial in directory.glob(".image-*"):
            if not partial.is_symlink() and partial.is_file() and partial.stat().st_mtime < cutoff:
                partial.unlink(missing_ok=True)
        files = []
        for path in directory.glob("*.image"):
            try:
                info = path.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                files.append((info.st_mtime_ns, info.st_size, path))
        files.sort()
        self.entries = OrderedDict((path, length) for _stamp, length, path in files)
        self.size = sum(self.entries.values())
        self.indexed_account = account

    def _forget(self, path):
        self.size -= self.entries.pop(path, 0)

    def _prune(self):
        while self.entries and (self.size > self.max_bytes or len(self.entries) > self.max_files):
            path = next(iter(self.entries))
            path.unlink(missing_ok=True)
            self._forget(path)
        return {path.stem for path in self.entries}

    def catalog(self, account):
        with self.io_lock:
            self.indexed_account = None
            try:
                self._scan(account)
                return self._prune()
            except OSError:
                self.indexed_account = None
                raise

    def read(self, account, url):
        with self.io_lock:
            path = self.path(account, url)
            try:
                info = path.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    if info.st_size <= 8_000_000:
                        payload = path.read_bytes()
                        os.utime(path)
                        if self.indexed_account == account and path in self.entries:
                            self.entries.move_to_end(path)
                        return payload
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                self.indexed_account = None
                raise
            if self.indexed_account == account:
                self._forget(path)
            return None

    def discard(self, account, url):
        with self.io_lock:
            path = self.path(account, url)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                self.indexed_account = None
                raise
            if self.indexed_account == account:
                self._forget(path)

    def write(self, account, token, url, payload):
        if token is None or len(payload) > min(8_000_000, self.max_bytes):
            return None
        with self.io_lock:
            with self.state_lock:
                if self.tokens.get(account) != token:
                    return None
            directory = self.directory(account)
            try:
                if self.indexed_account != account:
                    self._scan(account)
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                path = self.path(account, url)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=directory, prefix=".image-", delete=False
                    ) as file:
                        temporary = Path(file.name)
                        os.fchmod(file.fileno(), 0o600)
                        file.write(payload)
                    temporary.replace(path)
                finally:
                    if temporary:
                        temporary.unlink(missing_ok=True)
                self._forget(path)
                self.entries[path] = len(payload)
                self.size += len(payload)
                return self._prune()
            except OSError:
                self.indexed_account = None
                raise

    def clear(self, account):
        with self.io_lock:
            with self.state_lock:
                self.tokens.pop(account, None)
            if self.indexed_account == account:
                self.indexed_account = None
                self.entries.clear()
                self.size = 0
            with suppress(FileNotFoundError):
                shutil.rmtree(self.directory(account))
