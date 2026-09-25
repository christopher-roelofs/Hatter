import unittest
from build_empty_package import assemble
from inspect_format import inspect, FormatError
from package_exports import package_exports


class EmptyPackageTests(unittest.TestCase):
    def test_complete_candidate(self):
        raw, manifest = assemble()
        decoded = inspect(raw)['packages'][0]
        self.assertEqual([a['raw_tag_byte'] for a in decoded['records']], [0x20, 0x53, 0x10, 0x60])
        self.assertEqual(len(decoded['heap_selectors']['objects']), 18)
        self.assertEqual(package_exports(raw, decoded), [])
        self.assertEqual([e['selector'] for e in decoded['heap_selectors']['objects']], list(range(4, 148, 8)))
        self.assertEqual(manifest['cluster_values']['packageContents'], 12)
        self.assertEqual(manifest['cluster_values']['pristineNameDictionary'], 68)
        self.assertEqual(raw, assemble()[0])

    def test_invalid_page_ranges(self):
        for first, last in ((-1, 0), (2, 1), (0, 2**32)):
            with self.assertRaises(FormatError):
                assemble(first, last)


if __name__ == '__main__':
    unittest.main()
