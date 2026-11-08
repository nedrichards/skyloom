"""Plain posts retain escaping and Unicode without facet-offset preparation."""

import unittest

from skyloom.richtext import markup


class PlainMarkupTests(unittest.TestCase):
    def test_plain_unicode_and_markup_characters_are_escaped(self):
        text = "🌤️ <tag a=\"quoted\"> & 'apostrophe'\n👩🏽‍💻 e\u0301"
        expected = "🌤️ &lt;tag a=&quot;quoted&quot;&gt; &amp; &#x27;apostrophe&#x27;\n👩🏽‍💻 e\u0301"
        self.assertEqual(markup(text), expected)
        self.assertEqual(markup(text, []), expected)
        self.assertEqual(markup(text, ()), expected)
        self.assertEqual(markup(""), "")
