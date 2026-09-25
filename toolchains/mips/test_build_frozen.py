import unittest
from build_frozen import (heap_object, heap, package, rebuild, imports,
                          defined_components, object_addressing, function_offsets)
from inspect_format import inspect, decode_heap, FormatError


class FrozenBuilderTests(unittest.TestCase):
    def test_external_name_and_padding_roundtrip(self):
        encoded = heap([heap_object(0x81000001, b'abc', name='A'.encode('utf-16-be'), body_padding=b'X')])
        p = package([(0x60, encoded)])
        self.assertEqual(rebuild(p)[0], p)
        obj = inspect(p)['packages'][0]['records'][0]['heap']['objects'][0]
        self.assertEqual(obj['external_name']['text_utf16be'], 'A')
        self.assertEqual(obj['padding_hex'], '58')

    def test_subtype_three_and_reference_records(self):
        data = heap([heap_object(0xb1000001, b'abc'), heap_object(0xc0000000, locator=12), heap_object(0x40000001)])
        self.assertEqual(len(decode_heap(data, 0, len(data))['objects']), 3)
        with self.assertRaises(FormatError):
            heap_object(0xb1000001, b'abc', name=b'\0A')

    def test_invalid_payloads(self):
        cases = [lambda: heap_object(0), lambda: heap_object(0xc0000000),
                 lambda: heap_object(0x81000001, b'a'),
                 lambda: heap_object(0x81000001, b'a', name=b'x'),
                 lambda: heap_object(0x80000001, b'a', body_padding=b'')]
        for case in cases:
            with self.assertRaises(FormatError):
                case()

    def test_new_container_with_addressed_heap(self):
        p = package([(0x20, imports([(2, 'SystemInternal', '', 1300, 0, 1)])),
                     (0x30, defined_components([(2, 1400, 1)])),
                     (0x53, object_addressing(4, 1, [(12, 1)])),
                     (0x60, heap([heap_object(0xb0000514, bytes(16)), heap_object(0xc0000000, locator=4)]))])
        parsed = inspect(p)['packages'][0]
        self.assertEqual(parsed['heap_selectors']['status'], 'linked-heap-selectors')
        self.assertEqual(rebuild(p)[0], p)

    def test_bundle_and_unknown_attribute_preserved(self):
        a = package([(0x90, b'unknown')])
        b = package([(0x60, heap([heap_object(0x40000001)]))])
        data, parsed = rebuild(a + b)
        self.assertEqual(data, a + b)
        self.assertEqual(len(parsed['packages']), 2)

    def test_function_zero_offset_and_null(self):
        p = package([(0xb0, function_offsets([0, None], 0)), (0x71, bytes(12))])
        table = inspect(p)['packages'][0]['records'][0]['function_offsets']
        self.assertEqual(table['count'], 2)

    def test_invalid_ranges_and_cross_attribute_count(self):
        with self.assertRaises(FormatError):
            imports([(2, 'SystemPublic', '', 1, 0, 0)])
        with self.assertRaises(FormatError):
            defined_components([(2, 0xffffffff, 2)])
        with self.assertRaises(FormatError):
            package([(0x53, object_addressing(4, 1, [(12, 2)])),
                     (0x60, heap([heap_object(0x40000001)]))])


if __name__ == '__main__':
    unittest.main()
