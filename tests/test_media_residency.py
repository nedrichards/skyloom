"""Decoded-cache and consumer residency contracts, with invented texture dimensions."""

import gc
import unittest

from skyloom.media import Images


class Texture:
    def __init__(self, width=10, height=10):
        self.width, self.height = width, height

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height


class Consumer:
    pass


class MediaResidencyTests(unittest.TestCase):
    def test_byte_budget_evicts_lru_independently_of_entry_limit(self):
        images = Images(".", max_cache_bytes=800, max_cache_entries=32)
        textures = [Texture() for _ in range(4)]
        for index in range(3):
            images._remember(images.generation, (str(index), False), textures[index])
        self.assertEqual(list(images.cache), [("1", False), ("2", False)])
        self.assertIs(images._cached(("1", False)), textures[1])
        images._remember(images.generation, ("3", False), textures[3])
        self.assertEqual(list(images.cache), [("1", False), ("3", False)])
        self.assertEqual(images.residency()["cache_bytes"], 800)
        images.max_cache_entries = 1
        images.trim()
        self.assertEqual(list(images.cache), [("3", False)])

    def test_bound_consumers_remain_counted_after_cache_eviction(self):
        images = Images(".", max_cache_bytes=400)
        first, second = Texture(), Texture()
        one, two = Consumer(), Consumer()
        images._remember(images.generation, ("one", False), first)
        images.bind(one, first)
        images.bind(two, first)
        self.assertEqual(images.residency()["resident_bytes"], 400)
        self.assertEqual(images.residency()["bound_consumers"], 2)
        images._remember(images.generation, ("two", False), second)
        stats = images.residency()
        self.assertEqual(stats["cache_bytes"], 400)
        self.assertEqual(stats["bound_bytes"], 400)
        self.assertEqual(stats["resident_bytes"], 800)
        images.unbind(one)
        self.assertEqual(images.residency()["bound_textures"], 1)
        images.unbind(two)
        self.assertEqual(images.residency()["resident_bytes"], 400)
        self.assertEqual(images.residency()["peak_resident_bytes"], 800)

    def test_consumers_are_weak_and_oversized_textures_are_not_cached(self):
        images = Images(".", max_cache_bytes=100)
        picture, texture = Consumer(), Texture()
        images._remember(images.generation, ("large", False), texture)
        self.assertFalse(images.cache)
        images.bind(picture, texture)
        self.assertEqual(images.residency()["resident_bytes"], 400)
        del picture
        gc.collect()
        self.assertEqual(images.residency()["bound_consumers"], 0)
        self.assertEqual(images.residency()["resident_bytes"], 0)

    def test_account_change_rejects_stale_cache_but_tracks_existing_consumers(self):
        images = Images(".")
        picture, texture = Consumer(), Texture()
        generation = images.generation
        images._remember(generation, ("invented", False), texture)
        images.bind(picture, texture)
        images.use_account("did:example:other")
        images._remember(generation, ("stale", False), Texture())
        self.assertFalse(images.cache)
        self.assertEqual(images.residency()["bound_bytes"], 400)
        images.unbind(picture)
        self.assertEqual(images.residency()["resident_bytes"], 0)

    def test_dropping_cache_does_not_remove_a_visible_binding(self):
        images = Images(".")
        picture, texture = Consumer(), Texture()
        images._remember(images.generation, ("invented", False), texture)
        images.bind(picture, texture)
        self.assertTrue(images.drop_cached(texture))
        self.assertFalse(images.drop_cached(texture))
        self.assertEqual(images.residency()["cache_bytes"], 0)
        self.assertEqual(images.residency()["bound_bytes"], 400)
