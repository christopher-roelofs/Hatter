import struct
import unittest
from inspect_format import FormatError
from link_package_methods import declarations, resolve_import, resolve_component, method_list, class_array


def word(value):
    return struct.pack('>I', value)


class PackageMethodsTests(unittest.TestCase):
    def test_nonidentity_import_range_and_kind_separation(self):
        entry = {'kind': 'class', 'raw_component_word': 9000, 'raw_range_word': 2,
                 'count': 3, 'name': {'text_latin1': 'SystemInternal'}}
        interfaces = {'SystemInternal': {('class', 3): ['UnlinkedClassWithInstances']}}
        result = resolve_import([entry], 'class', 9001, interfaces)
        self.assertEqual(result['interface_offset'], 3)
        self.assertEqual(result['sdk_declared_names'], ['UnlinkedClassWithInstances'])
        for kind, selector in [('operation', 9001), ('class', 8999), ('class', 9003)]:
            self.assertEqual(resolve_import([entry], kind, selector, interfaces)['status'], 'not-imported')
        self.assertEqual(resolve_import([entry, entry], 'class', 9001, interfaces)['status'], 'ambiguous-import')

    def test_declarations_preserve_conditional_alternatives_and_ignore_comments(self):
        name, entries = declarations('''define interface Test;
        // class Wrong = 1;
        class Right = 1;
        #ifdef X
        operation First = 4;
        #else
        operation Second = 4;
        #endif
        class operation Create = 2;
        ''')
        self.assertEqual(name, 'Test')
        self.assertEqual(entries[('class', 0)], ['Right'])
        self.assertEqual(entries[('operation', 3)], ['First', 'Second'])
        self.assertEqual(entries[('class-operation', 1)], ['Create'])

    def test_method_layout_low20_selector_and_native_threshold(self):
        # Body starts after unrelated bytes; list at +4, two-byte displacement.
        data = b'xxxx' + b'\0\0\0\4' + b'\x80\x02\0\2' + b'xx'
        data += word(0x41a00123) + word(7) + word(0x40000456) + word(8)
        result = method_list(data, {'offset': 4, 'length': len(data) - 4})
        self.assertEqual(result[0]['operation_selector'], 0x123)
        self.assertTrue(result[0]['native'])
        self.assertFalse(result[1]['native'])
        self.assertEqual(result[0]['record']['offset'], 14)

    def test_local_component_range_and_import_overlap(self):
        local = [{'kind': 'operation', 'selector_start': 5000, 'count': 2}]
        result = resolve_component([], local, 'operation', 5001, {})
        self.assertEqual(result['status'], 'package-defined')
        self.assertEqual(result['range_offset'], 1)
        self.assertEqual(resolve_component([], local, 'operation', 5002, {})['status'], 'not-imported')
        imported = [{'kind': 'operation', 'raw_component_word': 5000, 'raw_range_word': 0,
                     'count': 1, 'name': {'text_latin1': 'X'}}]
        self.assertEqual(resolve_component(imported, local, 'operation', 5000, {})['status'], 'ambiguous-component')

    def test_separate_class_and_intrinsic_list_offsets(self):
        data = bytearray(40)
        struct.pack_into('>HH', data, 6, 24, 12)
        struct.pack_into('>HHII', data, 12, 1, 0, 0x41000001, 3)
        struct.pack_into('>HHII', data, 24, 1, 0, 0x41000002, 4)
        body = {'offset': 0, 'length': len(data)}
        self.assertEqual(method_list(data, body), [])
        self.assertEqual(method_list(data, body, 8)[0]['raw_value'], 3)
        self.assertEqual(method_list(data, body, 6)[0]['raw_value'], 4)

    @staticmethod
    def class_array_fixture():
        data = bytearray(0x98)
        for offset, value in [(0x64, 200), (0x8c, 7000), (0x94, 2)]:
            struct.pack_into('>I', data, offset, value)
        objects = [{'raw_class_selector': 9000, 'body': {'offset': 0, 'length': len(data)}}, {}, {}]
        package = {'records': [{'heap': {'objects': objects}}],
                   'heap_selectors': {'objects': [{'selector': 200, 'heap_object_index': 2},
                                                  {'selector': 208, 'heap_object_index': 1}]}}
        imports = [{'kind': 'class', 'raw_component_word': 9000, 'raw_range_word': 7,
                    'count': 1, 'name': {'text_latin1': 'SystemInternal'}}]
        definitions = [{'kind': 'class', 'selector_start': 7000, 'count': 2}]
        interfaces = {'SystemInternal': {('class', 7): ['CodePackageCluster']}}
        return data, package, imports, definitions, interfaces

    def test_class_array_uses_locator_map_and_local_range(self):
        result = class_array(*self.class_array_fixture())
        self.assertEqual(result[2]['selector'], 7000)
        self.assertEqual(result[1]['selector'], 7001)
        self.assertEqual(result[1]['locator_selector'], 208)

    def test_class_array_missing_locator_and_invalid_range(self):
        for offset, value in [(0x64, 999), (0x8c, 6999), (0x94, 99)]:
            data, *args = self.class_array_fixture()
            struct.pack_into('>I', data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                class_array(data, *args)

    def test_method_list_bounds_and_empty_list(self):
        self.assertEqual(method_list(bytes(4), {'offset': 0, 'length': 4}), [])
        for data in [b'x', b'\0\0\xff\xff', b'\0\0\0\4\x00\xff\0\0']:
            with self.subTest(data=data.hex()), self.assertRaises(FormatError):
                method_list(data, {'offset': 0, 'length': len(data)})


if __name__ == '__main__':
    unittest.main()
