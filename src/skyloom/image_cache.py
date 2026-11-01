"""Bounded account-private image files; all filesystem methods run on worker threads."""

import hashlib
import os
import shutil
import tempfile
import threading
import time
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

    def _prune(self, account):
        directory = self.directory(account)
        for partial in directory.glob(".image-*"):
            if (
                not partial.is_symlink()
                and partial.is_file()
                and partial.stat().st_mtime < time.time() - 86400
            ):
                partial.unlink(missing_ok=True)
        files = []
        for path in directory.glob("*.image"):
            if not path.is_symlink() and path.is_file():
                info = path.stat()
                files.append((info.st_mtime_ns, info.st_size, path))
        files.sort()
        size = sum(item[1] for item in files)
        while files and (size > self.max_bytes or len(files) > self.max_files):
            _stamp, length, path = files.pop(0)
            path.unlink(missing_ok=True)
            size -= length
        return {path.stem for _stamp, _size, path in files}

    def catalog(self, account):
        with self.io_lock:
            return self._prune(account)

    def read(self, account, url):
        with self.io_lock:
            path = self.path(account, url)
            if path.is_symlink() or not path.is_file():
                return None
            if path.stat().st_size > 8_000_000:
                path.unlink()
                return None
            payload = path.read_bytes()
            path.touch()
            return payload

    def discard(self, account, url):
        with self.io_lock:
            self.path(account, url).unlink(missing_ok=True)

    def write(self, account, token, url, payload):
        if token is None or len(payload) > min(8_000_000, self.max_bytes):
            return None
        with self.io_lock:
            with self.state_lock:
                if self.tokens.get(account) != token:
                    return None
            directory = self.directory(account)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=directory, prefix=".image-", delete=False
                ) as file:
                    temporary = Path(file.name)
                    os.fchmod(file.fileno(), 0o600)
                    file.write(payload)
                temporary.replace(self.path(account, url))
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
            return self._prune(account)

    def clear(self, account):
        with self.io_lock:
            with self.state_lock:
                self.tokens.pop(account, None)
            with suppress(FileNotFoundError):
                shutil.rmtree(self.directory(account))
