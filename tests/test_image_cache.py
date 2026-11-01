"""Account isolation, bounded persistence and late-download invalidation."""

import os
import tempfile
import unittest
from pathlib import Path

from skyloom.image_cache import ImageCache, digest


class ImageCacheTests(unittest.TestCase):
    def test_persistence_permissions_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageCache(directory)
            token = cache.activate("alice")
            cache.write("alice", token, "https://example.invalid/image", b"pixels")
            restored = ImageCache(directory)
            self.assertEqual(restored.read("alice", "https://example.invalid/image"), b"pixels")
            self.assertIsNone(restored.read("bob", "https://example.invalid/image"))
            path = cache.path("alice", "https://example.invalid/image")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn("alice", str(path))

    def test_budget_evicts_oldest_and_read_refreshes_recency(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageCache(directory, max_bytes=10, max_files=2)
            token = cache.activate("alice")
            cache.write("alice", token, "first", b"1111")
            os.utime(cache.path("alice", "first"), ns=(1, 1))
            cache.write("alice", token, "second", b"2222")
            os.utime(cache.path("alice", "second"), ns=(2, 2))
            self.assertEqual(cache.read("alice", "first"), b"1111")
            entries = cache.write("alice", token, "third", b"3333")
            self.assertEqual(entries, {digest("first"), digest("third")})
            self.assertIsNone(cache.read("alice", "second"))
            self.assertIsNone(cache.write("alice", token, "huge", b"x" * 11))
            # The byte cap also applies when the entry count would allow a write.
            cache.write("alice", token, "large", b"x" * 9)
            self.assertEqual(cache.catalog("alice"), {digest("large")})

    def test_signout_prevents_late_downloads_from_resurrecting_files(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageCache(directory)
            old = cache.activate("alice")
            cache.write("alice", old, "image", b"old")
            cache.clear("alice")
            self.assertIsNone(cache.write("alice", old, "image", b"late"))
            self.assertFalse(cache.directory("alice").exists())
            new = cache.activate("alice")
            self.assertIsNone(cache.write("alice", old, "image", b"late"))
            cache.write("alice", new, "image", b"new")
            self.assertEqual(cache.read("alice", "image"), b"new")

    def test_catalog_drops_stale_partial_files_and_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageCache(Path(directory) / "cache")
            token = cache.activate("alice")
            cache.write("alice", token, "image", b"valid")
            partial = cache.directory("alice") / ".image-abandoned"
            partial.write_bytes(b"unfinished")
            os.utime(partial, (1, 1))
            outside = Path(directory) / "outside"
            outside.write_bytes(b"private")
            cache.path("alice", "symlink").symlink_to(outside)
            self.assertEqual(cache.catalog("alice"), {digest("image")})
            self.assertIsNone(cache.read("alice", "symlink"))
            self.assertFalse(partial.exists())
            cache.clear("alice")
            self.assertEqual(outside.read_bytes(), b"private")
