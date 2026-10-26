import unittest

from directories import DirectoryMap


class ResolveTests(unittest.TestCase):
    def test_bare_path_is_exact_match_only(self):
        m = DirectoryMap.parse({'/a/b': '/x/b'})
        self.assertEqual(m.to_hub('/a/b'), '/x/b')
        self.assertEqual(m.to_local('/x/b'), '/a/b')
        self.assertIsNone(m.to_hub('/a/b/c'))
        self.assertIsNone(m.to_hub('/a'))

    def test_single_star_one_segment(self):
        m = DirectoryMap.parse({'/home/foo/*': '/home/bar/*'})
        self.assertEqual(m.to_hub('/home/foo/proj'), '/home/bar/proj')
        self.assertEqual(m.to_local('/home/bar/proj'), '/home/foo/proj')
        self.assertIsNone(m.to_hub('/home/foo'))
        self.assertIsNone(m.to_hub('/home/foo/a/b'))

    def test_double_star_one_or_more_segments(self):
        m = DirectoryMap.parse({'/home/foo/**': '/home/bar/**'})
        self.assertEqual(m.to_hub('/home/foo/a/b/c'), '/home/bar/a/b/c')
        self.assertEqual(m.to_local('/home/bar/a'), '/home/foo/a')
        self.assertIsNone(m.to_hub('/home/foo'))

    def test_wildcard_in_the_middle(self):
        m = DirectoryMap.parse({'/srv/*/repo': '/workspace/*/repo'})
        self.assertEqual(m.to_hub('/srv/acme/repo'), '/workspace/acme/repo')
        self.assertEqual(m.to_local('/workspace/acme/repo'), '/srv/acme/repo')
        self.assertIsNone(m.to_hub('/srv/acme/other'))

    def test_mixed_wildcards_keep_order(self):
        m = DirectoryMap.parse({'/a/*/b/**': '/x/*/y/**'})
        self.assertEqual(m.to_hub('/a/one/b/t/u'), '/x/one/y/t/u')

    def test_first_match_wins(self):
        m = DirectoryMap.parse({'/a/special': '/hub/one', '/a/*': '/hub/two/*'})
        self.assertEqual(m.to_hub('/a/special'), '/hub/one')
        self.assertEqual(m.to_hub('/a/other'), '/hub/two/other')

    def test_trailing_slash_is_normalized(self):
        m = DirectoryMap.parse({'/a/*/': '/b/*/'})
        self.assertEqual(m.to_hub('/a/p/'), '/b/p')

    def test_regex_metacharacters_are_literal(self):
        m = DirectoryMap.parse({'/a.b/*': '/x+y/*'})
        self.assertEqual(m.to_hub('/a.b/p'), '/x+y/p')
        self.assertIsNone(m.to_hub('/aXb/p'))

    def test_tilde_expanded_locally_only(self):
        m = DirectoryMap.parse({'~/code/*': '/hub/code/*'})
        self.assertNotIn('~', m.to_local('/hub/code/p'))
        with self.assertRaises(ValueError):
            DirectoryMap.parse({'/a': '~/a'})

    def test_empty_map(self):
        self.assertIsNone(DirectoryMap.parse({}).to_hub('/a'))


class ValidationTests(unittest.TestCase):
    def assertRejected(self, raw):
        with self.assertRaises(ValueError):
            DirectoryMap.parse(raw)

    def test_wildcard_mismatch(self):
        self.assertRejected({'/a/*': '/b/**'})
        self.assertRejected({'/a/*': '/b'})
        self.assertRejected({'/a': '/b/*'})

    def test_relative_or_empty(self):
        self.assertRejected({'a/b': '/x'})
        self.assertRejected({'/a': 'x'})
        self.assertRejected({'/': '/x'})
        self.assertRejected({'/a//b': '/x'})

    def test_partial_segment_wildcard(self):
        self.assertRejected({'/a/foo*': '/b/foo*'})

    def test_multiple_double_stars(self):
        self.assertRejected({'/a/**/b/**': '/x/**/y/**'})

    def test_overlapping_rules(self):
        self.assertRejected({'/a/*': '/b/*', '/a/*/': '/d/*'})
        self.assertRejected({'/a/*': '/b/*', '/c/*': '/b/*'})
        self.assertRejected({'/a/*': '/b/*', '/a/**': '/c/**'})


if __name__ == '__main__':
    unittest.main()
