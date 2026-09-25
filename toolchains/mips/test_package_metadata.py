import unittest
from build_empty_objects import construct
from build_object_values import read_object_list
from build_package_metadata import empty_metadata, METADATA_CLASSES
from inspect_format import FormatError


class PackageMetadataTests(unittest.TestCase):
    def test_empty_tables_golden_layout(self):
        bodies, _, _, manifest = construct()
        refs = manifest['local_selectors']
        for table, entry, size, names in (('sharedTable', 'sharedEntries', 8, 'sharedObjects'),
                                           ('exports', 'exportEntries', 12, 'exportNames')):
            expected = (refs[entry].to_bytes(4, 'big') + size.to_bytes(4, 'big') + bytes(16) +
                        refs[names].to_bytes(4, 'big') + bytes.fromhex('0400000100000000'))
            self.assertEqual(bodies[table], expected)
        self.assertEqual(bodies['sharedEntries'], bytes.fromhex('0000000800000000'))
        self.assertEqual(bodies['exportEntries'], bytes(4))
        self.assertEqual(bodies['exportNames'], bytes(8))
        self.assertEqual(read_object_list(bodies['sharedObjects']), [])

    def test_empty_import_status_and_acclimatized_flag(self):
        bodies, _, _, manifest = construct()
        refs = manifest['local_selectors']
        self.assertEqual(bodies['packageData'], bytes(4) + refs['missingNames'].to_bytes(4, 'big') +
                         refs['missingIndexicals'].to_bytes(4, 'big') + bytes.fromhex('80000000'))
        self.assertEqual(bodies['missingNames'], b'')
        self.assertEqual(read_object_list(bodies['missingIndexicals']), [])

    def test_invalid_selector_maps(self):
        selectors = {name: 12 + i * 8 for i, name in enumerate(METADATA_CLASSES)}
        for bad in ({}, dict.fromkeys(selectors, 12), {**selectors, 'exports': 13}):
            with self.assertRaises(FormatError):
                empty_metadata({}, bad)


if __name__ == '__main__':
    unittest.main()
