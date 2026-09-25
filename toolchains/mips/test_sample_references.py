import unittest
from build_object_values import pixel_units
from inspect_format import FormatError
from link_package_methods import resolve_import
from build_empty_objects import construct
from build_object_values import read_object_list, read_plain_text
from build_object_names import read_names


class SampleReferenceTests(unittest.TestCase):
    def test_sample_scene_and_object_graph(self):
        bodies, imports, formats, manifest = construct()
        # Viewable prefix: null superview, origin <0,-8>, size <480,256>.
        self.assertEqual(bodies['packageScene'][:20], bytes.fromhex(
            '00000000 00000000 fffff800 0001e000 00010000'))
        self.assertEqual(len(bodies['packageScene']), 72)
        self.assertEqual(bodies['contents'][16], 0x80)
        self.assertEqual(bodies['packageScene'][48:52], bytes.fromhex('00040000'))
        self.assertEqual(read_object_list(bodies['installationList']), [0x10000014, 28])
        self.assertEqual(read_object_list(bodies['helpForObjects']), [28, 44])
        self.assertEqual(read_plain_text(bodies['packageSceneInfo']),
                         'About EmptyPackage\nEmptyPackage is ... empty')
        self.assertEqual(int.from_bytes(bodies['contents'][20:24], 'big'), 20)
        self.assertEqual(int.from_bytes(bodies['contents'][36:40], 'big'), 36)
        self.assertEqual(len(manifest['references']), 37)
        self.assertEqual(read_names(bodies['nameLookup'], bodies['nameTextHeap'], 5),
                         ['EmptyPackage', None, 'EmptyPackage', None, None])
        self.assertEqual(bodies['nameDictionary'].hex(), '000000340000003c0000000c00000005')

    def test_pixel_literals(self):
        self.assertEqual([pixel_units(x) for x in ('0.0', '-8.0', '480.0', '256.0')],
                         [0, -2048, 122880, 65536])
        self.assertEqual(pixel_units('0.00390625'), 1)
        self.assertEqual(pixel_units('-8388608'), -2147483648)
        self.assertEqual(pixel_units('8388607.99609375'), 2147483647)

    def test_pixels_reject_rounding_and_overflow(self):
        for x in ('0.1', '8388608', '-8388608.00390625', 'nan', '1/2', True, 1.5):
            with self.assertRaises(FormatError):
                pixel_units(x)

    def test_imported_locator_stride_and_range(self):
        entries = [{'kind': 'locator', 'raw_component_word': 0x10000004,
                    'raw_range_word': 10, 'count': 3, 'name': {'text_latin1': 'Example'}}]
        interfaces = {'Example': {('locator', 12): ['last']}}
        result = resolve_import(entries, 'locator', 0x10000014, interfaces)
        self.assertEqual(result['sdk_declared_names'], ['last'])
        self.assertEqual(result['interface_offset'], 12)
        for bad in (0x10000003, 0x10000005, 0x1000001c):
            self.assertEqual(resolve_import(entries, 'locator', bad, interfaces)['status'], 'not-imported')


if __name__ == '__main__':
    unittest.main()
