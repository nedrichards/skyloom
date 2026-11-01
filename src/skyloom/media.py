"""Bounded image preparation and downloads, run off the GTK thread."""

import asyncio
import hashlib
import os
import threading
import weakref
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import gi
import httpx

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GdkPixbuf, GLib  # noqa: E402

from .errors import UserError  # noqa: E402
from .image_cache import digest  # noqa: E402


def prepare(path, directory):
    """Re-encode to strip metadata and make a durable, bounded upload copy."""
    path, directory = Path(path), Path(directory).resolve()
    if path.stat().st_size > 12_000_000:
        raise UserError("Choose an image smaller than 12 MB.")
    info = GdkPixbuf.Pixbuf.get_file_info(str(path))
    if not info or not info[0] or info[0].get_name() not in ("jpeg", "png"):
        raise UserError("Choose a JPEG or PNG image.")
    if info[1] < 1 or info[2] < 1 or info[1] * info[2] > 30_000_000:
        raise UserError("Choose an image smaller than 30 megapixels.")
    ratio = min(1, 1600 / info[1], 1600 / info[2])
    pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
        str(path), max(1, int(info[1] * ratio)), max(1, int(info[2] * ratio)), True
    )
    # Rebuilding pixels explicitly excludes source metadata (GPS, comments and orientation tags).
    pix = pix.apply_embedded_orientation()
    clean = GdkPixbuf.Pixbuf.new_from_bytes(
        pix.read_pixel_bytes(),
        pix.get_colorspace(),
        pix.get_has_alpha(),
        8,
        pix.get_width(),
        pix.get_height(),
        pix.get_rowstride(),
    )
    ok, payload = clean.save_to_bufferv("png", [], [])
    suffix = ".png"
    if len(payload) > 1_000_000:
        ok, payload = clean.save_to_bufferv("jpeg", ["quality"], ["85"])
        suffix = ".jpg"
    if not ok or len(payload) > 1_000_000:
        raise UserError("This image remains larger than 1 MB. Resize it and try again.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / (hashlib.sha256(payload).hexdigest() + suffix)
    target.write_bytes(payload)
    os.chmod(target, 0o600)
    return str(target)


def decode(payload):
    if not payload.startswith((b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8")):
        raise UserError("Image format is not supported.")
    loader = GdkPixbuf.PixbufLoader.new()
    too_large = False

    def sized(obj, width, height):
        nonlocal too_large
        if width * height > 30_000_000:
            too_large = True
            obj.set_size(1, 1)
        elif width > 1600 or height > 1600:
            ratio = min(1600 / width, 1600 / height)
            obj.set_size(max(1, int(width * ratio)), max(1, int(height * ratio)))

    loader.connect("size-prepared", sized)
    loader.write(payload)
    loader.close()
    if too_large:
        raise UserError("Image is too large to display safely.")
    return loader.get_pixbuf()


def texture(pixbuf):
    """Share one immutable texture per decode, with no per-widget pixel copy/upload."""
    return Gdk.MemoryTexture.new(
        pixbuf.get_width(),
        pixbuf.get_height(),
        Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8,
        pixbuf.read_pixel_bytes(),
        pixbuf.get_rowstride(),
    )


def decode_texture(payload):
    return texture(decode(payload))


def local_texture(path):
    return texture(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 800, 440, True))


def texture_bytes(paintable):
    """Conservative RGBA pixel storage estimate, excluding renderer/decoder overhead."""
    return max(0, paintable.get_width()) * max(0, paintable.get_height()) * 4


class Images:
    def __init__(
        self, fixture_dir, disk=None, *, max_cache_bytes=48 * 1024 * 1024, max_cache_entries=32
    ):
        self.fixture_dir = Path(fixture_dir)
        self.cache = OrderedDict()
        self.max_cache_bytes = max_cache_bytes
        self.max_cache_entries = max_cache_entries
        # Cache insertion happens on the async worker; bindings belong to GTK's thread.
        # Lock only bookkeeping and immutable texture dimensions, never filesystem IO.
        self._cache_lock = threading.RLock()
        self._bindings = weakref.WeakKeyDictionary()
        self._peak_resident_bytes = 0
        self.sem = asyncio.Semaphore(4)
        self.inflight = {}
        self.auto_download_allowed = lambda: True
        self.disk, self.account, self.token = disk, None, None
        self.disk_entries = set()
        self.generation = 0
        self.disk_error = False

    def use_account(self, account):
        with self._cache_lock:
            self.generation += 1
            self.account = account
            self.cache.clear()
            self.disk_entries.clear()
            self.disk_error = False
            self.token = self.disk.activate(account) if self.disk and account else None
            # Existing native consumers still own their paintables until released.
            # Keep them in the residency total across account invalidation.

    def _cached(self, key):
        with self._cache_lock:
            paintable = self.cache.get(key)
            if paintable is not None:
                self.cache.move_to_end(key)
            return paintable

    def _trim_locked(self):
        size = sum(texture_bytes(paintable) for paintable in self.cache.values())
        while self.cache and (
            size > self.max_cache_bytes or len(self.cache) > self.max_cache_entries
        ):
            _key, paintable = self.cache.popitem(last=False)
            size -= texture_bytes(paintable)

    def _remember(self, generation, key, paintable):
        with self._cache_lock:
            if generation != self.generation:
                return
            self.cache[key] = paintable
            self.cache.move_to_end(key)
            self._trim_locked()
            self._residency_locked()

    def trim(self):
        """Apply current decoded-cache budgets; native bindings are released by their owner."""
        with self._cache_lock:
            self._trim_locked()
            return self._residency_locked()

    def drop_cached(self, paintable):
        """Remove one decoded texture from the cache without disturbing visible consumers."""
        with self._cache_lock:
            keys = [key for key, value in self.cache.items() if value is paintable]
            for key in keys:
                self.cache.pop(key)
            return bool(keys)

    def bind(self, consumer, paintable):
        """Track a native consumer's texture until unbind or consumer destruction."""
        with self._cache_lock:
            self._bindings[consumer] = paintable
            self._residency_locked()

    def unbind(self, consumer):
        with self._cache_lock:
            self._bindings.pop(consumer, None)

    def _residency_locked(self):
        cached = {id(value): value for value in self.cache.values()}
        bound = {id(value): value for value in self._bindings.values()}
        combined = cached | bound
        resident_bytes = sum(texture_bytes(value) for value in combined.values())
        self._peak_resident_bytes = max(self._peak_resident_bytes, resident_bytes)
        return {
            "cache_textures": len(cached),
            "cache_bytes": sum(texture_bytes(value) for value in cached.values()),
            "bound_consumers": len(self._bindings),
            "bound_textures": len(bound),
            "bound_bytes": sum(texture_bytes(value) for value in bound.values()),
            "resident_textures": len(combined),
            "resident_bytes": resident_bytes,
            "peak_resident_bytes": self._peak_resident_bytes,
            "cache_budget_bytes": self.max_cache_bytes,
        }

    def residency(self):
        """Unique tracked texture identities, estimated RGBA bytes; not process RSS.

        Native bindings may legitimately add visible textures beyond the decoded LRU
        budget. The view must release offscreen bindings to bound that second owner.
        Temporary decoder buffers and renderer copies are outside these estimates.
        """
        with self._cache_lock:
            return self._residency_locked()

    async def catalog(self):
        generation, account = self.generation, self.account
        if self.disk and account:
            try:
                entries = await asyncio.to_thread(self.disk.catalog, account)
            except OSError:
                self.disk_error = True
                return
            if generation == self.generation:
                self.disk_entries = entries

    def has_cached(self, url, local=False):
        with self._cache_lock:
            return (url, local) in self.cache or (not local and digest(url) in self.disk_entries)

    async def get(self, url, local=False, *, explicit=False):
        cache_key = (url, local)
        cached = self._cached(cache_key)
        if cached is not None:
            return cached
        with self._cache_lock:
            context = (self.generation, self.account, self.token)
        key = (context[0], url, local, explicit)
        pending = self.inflight.get(key)
        if pending is None:
            task = asyncio.create_task(
                self._get(
                    url,
                    local,
                    explicit=explicit,
                    context=context,
                )
            )
            # Retrieve failures even if the final waiter is cancelled on the same turn.
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            pending = [task, 0]
            self.inflight[key] = pending
        pending[1] += 1
        try:
            return await asyncio.shield(pending[0])
        finally:
            pending[1] -= 1
            if pending[1] == 0:
                self.inflight.pop(key, None)
                if not pending[0].done():
                    pending[0].cancel()

    async def _get(self, url, local, *, explicit, context):
        generation, account, token = context
        key = (url, local)
        cached = self._cached(key) if generation == self.generation else None
        if cached is not None:
            return cached
        async with self.sem:
            cached = self._cached(key) if generation == self.generation else None
            if cached is not None:
                return cached
            if not local and self.disk and account:
                try:
                    payload = await asyncio.to_thread(self.disk.read, account, url)
                    if payload is not None:
                        pix = await asyncio.to_thread(decode_texture, payload)
                        self._remember(generation, key, pix)
                        return pix
                except OSError, UserError, GLib.Error:
                    self.disk_error = True
                    try:
                        await asyncio.to_thread(self.disk.discard, account, url)
                    except OSError:
                        self.disk_error = True
                    self.disk_entries.discard(digest(url))
            if not local and not explicit and not self.auto_download_allowed():
                raise UserError("Automatic image downloads are paused. Open the image to load it.")
            if local:
                path = Path(url)
                if not path.is_absolute():
                    path = self.fixture_dir / (url + ".svg")
                if path.suffix == ".svg" and path.parent == self.fixture_dir:
                    pix = await asyncio.to_thread(local_texture, path)
                else:
                    payload = await asyncio.to_thread(path.read_bytes)
                    pix = await asyncio.to_thread(decode_texture, payload)
            else:
                u = urlparse(url)
                # No arbitrary remote fetches from untrusted embedded URLs or private network hosts.
                if u.scheme != "https" or u.hostname != "cdn.bsky.app" or u.port not in (None, 443):
                    raise UserError("Open this image externally to view it.")
                async with (
                    httpx.AsyncClient(timeout=15, follow_redirects=False) as client,
                    client.stream("GET", url) as response,
                ):
                    response.raise_for_status()
                    parts, size = [], 0
                    async for part in response.aiter_bytes():
                        size += len(part)
                        if size > 8_000_000:
                            raise UserError("Image download is too large.")
                        parts.append(part)
                    payload = b"".join(parts)
                    pix = await asyncio.to_thread(decode_texture, payload)
                    if self.disk and account:
                        try:
                            entries = await asyncio.to_thread(
                                self.disk.write, account, token, url, payload
                            )
                        except OSError:
                            self.disk_error = True
                        else:
                            if entries is not None and generation == self.generation:
                                self.disk_entries = entries
            self._remember(generation, key, pix)
            return pix
