import unittest
from build_native_package import build
from inspect_format import inspect, FormatError
from link_package_methods import SDK, declarations, link_package


class NativePackageTests(unittest.TestCase):
    def test_method_linkage(self):
        raw, manifest = build(bytes.fromhex('03e0000824020001'))
        parsed = inspect(raw)['packages'][0]
        interfaces = {}
        for name in ('PublicInterface.cdef', 'InternalInterface.cdef'):
            key, entries = declarations((SDK / 'Interfaces/DefFiles/Interfaces' / name).read_text())
            interfaces[key] = entries
        linked = link_package(raw, parsed, interfaces)
        self.assertEqual(len(linked), 1)
        method = linked[0]['methods'][0]
        self.assertEqual(method['operation']['sdk_declared_names'], ['CanGoTo'])
        self.assertEqual(method['function']['function_id'], 3)
        self.assertEqual(method['function']['code_offset'], 0)
        self.assertEqual(method['function']['entry_preview']['prefix_hex'], '03e0000824020001')
        self.assertEqual(len(parsed['heap_selectors']['objects']), 19)
        offsets = next(a['function_offsets'] for a in parsed['records'] if 'function_offsets' in a)
        self.assertEqual([e['code_offset'] for e in offsets['entries']], [None, None, 0])
        self.assertEqual(manifest['superclass'], 'SoftwarePackageContents')

    def test_unknown_code_rejected(self):
        with self.assertRaises(FormatError):
            build(bytes(8))


if __name__ == '__main__':
    unittest.main()
