import struct
import unittest
from inspect_format import FormatError, SALT, inspect, decode_imports, decode_class_layout, decode_class_members, decode_operation_signature


def word(n):
    return struct.pack('>I', n)


def frozen(payload=b'abcd'):
    return SALT + word(152) + word(0x71000000 | len(payload)) + payload + word(0)


class ContainerTests(unittest.TestCase):
    def test_bundle_preserves_absolute_offsets(self):
        first = frozen()
        result = inspect(first + frozen(b'12345678'))
        self.assertEqual(len(result['packages']), 2)
        second = result['packages'][1]
        self.assertEqual(second['offset'], len(first))
        self.assertEqual(second['records'][0]['payload']['offset'], len(first) + 16)
        self.assertEqual(sum(x['length'] for x in result['packages']), result['bytes'])

    def test_unknown_tag_remains_opaque(self):
        data = SALT + word(152) + word(0xef000003) + b'xyz' + word(0)
        record = inspect(data)['packages'][0]['records'][0]
        self.assertEqual(record['raw_tag_byte'], 0xef)
        self.assertEqual(record['payload']['prefix_hex'], '78797a')

    def test_all_truncated_frozen_prefixes_rejected(self):
        data = frozen()
        for n in range(len(data)):
            with self.subTest(length=n), self.assertRaises(FormatError):
                inspect(data[:n])

    def test_oversized_length_rejected(self):
        with self.assertRaises(FormatError):
            inspect(SALT + word(152) + word(0x71ffffff) + word(0))

    def test_trailing_bytes_not_discarded(self):
        with self.assertRaises(FormatError):
            inspect(frozen() + b'garbage')

    def test_unknown_version_rejected(self):
        with self.assertRaises(FormatError):
            inspect(SALT + word(153) + word(0))

    @staticmethod
    def xfile():
        # Two section tags; aligned offsets relative to byte 4.
        return word(121) + struct.pack('>HHH', 2, 1, 99) + b'\0\0' + word(16) + word(20) + b'ABCD' + b'EFG'

    def test_xfile_relative_offsets_and_unaligned_eof(self):
        result = inspect(self.xfile())
        self.assertEqual([(s['offset'], s['length']) for s in result['sections']], [(20, 4), (24, 3)])
        self.assertEqual(result['architecture'], 'undetermined')

    def test_xfile_invalid_directories(self):
        for offset, value in [(12, 0), (16, 15), (16, 99999)]:
            data = bytearray(self.xfile())
            data[offset:offset + 4] = word(value)
            with self.subTest(offset=offset, value=value), self.assertRaises(FormatError):
                inspect(data)

    def test_xfile_short_directory(self):
        with self.assertRaises(FormatError):
            inspect(word(121) + b'\xff\xff')

    def test_named_record_and_invalid_name_length(self):
        data = (word(121) + struct.pack('>HH', 1, 12) + word(8)
                + word(1) + word(16) + word(6) + b'System' + b'opaque')
        record = inspect(data)['sections'][0]['named_records'][0]
        self.assertEqual(record['name_latin1'], 'System')
        self.assertEqual(record['opaque_tail']['length'], 6)
        broken = bytearray(data)
        broken[20:24] = word(999)
        with self.assertRaises(FormatError):
            inspect(broken)

    @staticmethod
    def one_section(tag, payload):
        return word(121) + struct.pack('>HH', 1, tag) + word(8) + payload

    def test_class_and_operation_prefixes(self):
        for tag, key in [(13, 'class_number'), (16, 'operation_number')]:
            payload = word(1) + word(16) + word(2) + word(3) + b'Foo' + word(167) + b'unknown'
            record = inspect(self.one_section(tag, payload))['sections'][0]['named_records'][0]
            self.assertEqual(record['raw_kind'], 2)
            self.assertEqual(record[key], 167)
            self.assertEqual(record['opaque_tail']['length'], 7)

    def test_class_number_cannot_cross_record_boundary(self):
        payload = word(1) + word(16) + word(2) + word(3) + b'Foo' + b'xx'
        with self.assertRaises(FormatError):
            inspect(self.one_section(13, payload))

    def test_dependency_paths_and_padding(self):
        payload = word(2) + word(3) + b'a.x' + word(4) + b'b.cx' + b'\0'
        section = inspect(self.one_section(19, payload))['sections'][0]
        self.assertEqual([x['path_latin1'] for x in section['dependency_paths']], ['a.x', 'b.cx'])
        self.assertEqual(section['padding']['length'], 1)
        with self.assertRaises(FormatError):
            inspect(self.one_section(19, payload[:-1] + b'x'))

    def test_dependency_count_and_length_bounds(self):
        for payload in [word(0xffffffff), word(1) + word(999), word(0) + bytes(4)]:
            with self.assertRaises(FormatError):
                inspect(self.one_section(19, payload))

    @staticmethod
    def layout_fixture(words):
        data = b''.join(word(x) for x in words)
        record = {'raw_kind': 2, 'opaque_tail': {'offset': 0, 'length': len(data)}}
        classes = [{'name_latin1': 'Object', 'class_number': 1},
                   {'name_latin1': 'HasDate', 'class_number': 10}]
        return data, record, classes

    def test_layout_distinguishes_mixins_and_inheritance(self):
        fixture = self.layout_fixture([1, 0, 1, 24, 0, 8, 1, 1, 1, 2])
        result = decode_class_layout(*fixture)
        self.assertEqual(result['fixed_offset_bytes'], 16)
        self.assertEqual(result['mixes_in_with'][0]['name_latin1'], 'Object')
        self.assertEqual(result['inherits_from'][0]['name_latin1'], 'HasDate')

    def test_layout_rejects_invalid_sizes_and_references(self):
        for words in ([1, 0, 1, 4, 0, 8, 0, 0],
                      [1, 0, 3, 8, 0, 4, 0, 0],
                      [1, 0, 1, 8, 0, 4, 1, 0, 0],
                      [1, 0, 1, 8, 0, 4, 999]):
            with self.assertRaises(FormatError):
                decode_class_layout(*self.layout_fixture(words))

    def test_layout_unknown_prefix_is_not_guessed(self):
        result = decode_class_layout(*self.layout_fixture([2, 947]))
        self.assertEqual(result['status'], 'unsupported-definition-prefix')

    @staticmethod
    def member_fixture():
        data = bytearray(96)
        def put(offset, value):
            data[offset:offset + 4] = word(value)
        put(42, 44)  # field table: base 8 + relative 44 = 52
        put(46, 68)  # method table: base 8 + relative 68 = 76
        put(52, 1)
        put(56, 8)
        put(60, 1)
        data[64] = ord('f')
        put(65, 1)  # type index; deliberately unaligned
        put(69, 3)  # bit offset within class leaf
        put(76, 1)
        put(80, 8)
        put(84, 1)  # operation index
        record = {'opaque_tail': {'offset': 0}, 'layout': {
            'status': 'decoded-observed-prefix-1', 'fixed_offset_bytes': 4,
            'remaining_opaque_tail': {'offset': 32, 'length': 64}}}
        return data, record, [{'name_latin1': 'Boolean'}], [
            {'name_latin1': 'Draw', 'operation_number': 42}]

    def test_field_bits_type_and_method_resolution(self):
        result = decode_class_members(*self.member_fixture())
        self.assertEqual(result['fields'][0]['fixed_bit_offset'], 35)
        self.assertEqual(result['fields'][0]['type_name_latin1'], 'Boolean')
        self.assertEqual(result['methods'][0]['name_latin1'], 'Draw')
        self.assertEqual(result['methods'][0]['operation_number'], 42)

    def test_member_offsets_counts_and_references_checked(self):
        for offset, value in [(42, 999), (52, 999), (60, 999), (65, 0), (84, 2), (46, 50)]:
            data, *args = self.member_fixture()
            data[offset:offset + 4] = word(value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                decode_class_members(data, *args)

    def test_member_prefix_list_count_checked(self):
        data, *args = self.member_fixture()
        data[32:36] = word(999)
        with self.assertRaises(FormatError):
            decode_class_members(data, *args)

    @staticmethod
    def signature_fixture():
        # Prefix, kind, byte modifier, unaligned return index, byte modifier,
        # parameter count, then a packed parameter with an output modifier.
        data = bytearray(word(1) + word(7) + b'\0' + word(0) + b'\0' + word(1)
                         + word(3) + b'box' + word(1) + b'\x80')
        record = {'raw_kind': 2, 'opaque_tail': {'offset': 0, 'length': len(data)}}
        return data, record, [{'name_latin1': 'Box', 'raw_kind': 6}]

    def test_signature_return_parameter_and_modifier(self):
        result = decode_operation_signature(*self.signature_fixture())
        self.assertEqual(result['return_type']['name_latin1'], 'void')
        self.assertEqual(result['parameters'][0]['type']['name_latin1'], 'Box')
        self.assertEqual(result['parameters'][0]['raw_flags_byte'], 128)

    def test_signature_bad_counts_names_and_types(self):
        for offset, value in [(9, 2), (14, 999), (18, 999), (25, 0)]:
            data, *args = self.signature_fixture()
            data[offset:offset + 4] = word(value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                decode_operation_signature(data, *args)

    def test_signature_padding_and_reference_variants(self):
        data, record, types = self.signature_fixture()
        data.append(1)
        record['opaque_tail']['length'] += 1
        with self.assertRaises(FormatError):
            decode_operation_signature(data, record, types)
        record['raw_kind'] = 1
        self.assertEqual(decode_operation_signature(data, record, types)['status'],
                         'reference-record-not-decoded')

    def test_accessor_bindings_resolve_field(self):
        for kind, label in [(1, 'getter'), (2, 'setter'), (3, 'text-getter'),
                            (4, 'text-setter'), (5, 'shared-setter')]:
            data, *args = self.member_fixture()
            data[88:92] = word(kind)
            data[92:96] = word(1)
            binding = decode_class_members(data, *args)['methods'][0]['binding']
            self.assertEqual(binding['kind'], label)
            self.assertEqual(binding['field_name_latin1'], 'f')
            self.assertEqual(binding['fixed_bit_offset'], 35)

    def test_accessor_invalid_field_rejected_unknown_kind_preserved(self):
        data, *args = self.member_fixture()
        data[88:92] = word(1)
        data[92:96] = word(2)
        with self.assertRaises(FormatError):
            decode_class_members(data, *args)
        data[88:92] = word(99)
        binding = decode_class_members(data, *args)['methods'][0]['binding']
        self.assertEqual(binding['kind'], 'unknown')

    def test_frozen_attribute_tag_and_flags_are_separate(self):
        record = inspect(frozen())['packages'][0]['records'][0]
        self.assertEqual(record['attribute_kind'], 'code')
        self.assertEqual(record['attribute_tag'], 7)
        self.assertEqual(record['raw_flags_nibble'], 1)

    @staticmethod
    def import_fixture(first=b'123456789abcdef', second=b'', kind=2, count=3):
        pair = bytes([len(first)]) + first + bytes([len(second)]) + second
        return (word(kind) + pair + b'\xa5' * (-len(pair) % 4)
                + word(123) + word(456) + word(count) + word(0))

    def test_import_paired_pascal_alignment(self):
        for first, second in [(b'123456789abcdef', b''), (b'ab', b'xyz'),
                              (b'', b''), (b'\xff', b'z')]:
            data = self.import_fixture(first, second)
            entry = decode_imports(data, 0, len(data))['entries'][0]
            self.assertEqual(entry['name']['hex'], first.hex())
            self.assertEqual(entry['secondary_name']['hex'], second.hex())
            self.assertEqual(entry['raw_component_word'], 123)
            self.assertEqual(entry['raw_range_word'], 456)
            self.assertEqual(entry['count'], 3)

    def test_import_kind_mask_and_categories(self):
        for kind, label in enumerate(['locator', 'class', 'operation',
                                      'class-operation', 'intrinsic'], 1):
            data = self.import_fixture(kind=0x100 | kind)
            self.assertEqual(decode_imports(data, 0, len(data))['entries'][0]['kind'], label)
        data = word(0x100)
        self.assertEqual(decode_imports(data, 0, 4)['raw_terminator'], 0x100)

    def test_import_truncations_and_bad_ranges(self):
        data = self.import_fixture()
        for size in range(len(data)):
            with self.subTest(size=size), self.assertRaises(FormatError):
                decode_imports(data[:size], 0, size)
        for kind, count in [(6, 1), (2, 0), (2, 5001)]:
            data = self.import_fixture(kind=kind, count=count)
            with self.assertRaises(FormatError):
                decode_imports(data, 0, len(data))
        data = self.import_fixture() + word(0)
        with self.assertRaises(FormatError):
            decode_imports(data, 0, len(data))

    def test_import_integration_absolute_offsets_and_unknown_flags(self):
        payload = self.import_fixture()
        data = SALT + word(152) + word(0x20000000 | len(payload)) + payload + word(0)
        result = inspect(frozen() + data)['packages'][1]['records'][0]
        self.assertEqual(result['imports']['entries'][0]['record']['offset'], len(frozen()) + 16)
        unknown = SALT + word(152) + word(0x21000001) + b'x' + word(0)
        self.assertNotIn('imports', inspect(unknown)['packages'][0]['records'][0])

    def test_function_offsets_one_based_null_and_trailer(self):
        payload = word(3) + word(0xffffffff) + word(0) + word(100) + word(99)
        data = SALT + word(152) + word(0xb0000000 | len(payload)) + payload + word(0)
        table = inspect(data)['packages'][0]['records'][0]['function_offsets']
        self.assertEqual([e['function_id'] for e in table['entries']], [1, 2, 3])
        self.assertEqual([e['code_offset'] for e in table['entries']], [None, 0, 100])
        self.assertEqual(table['raw_trailing_word'], 99)

    def test_function_offsets_bad_count_and_short_payload(self):
        for payload in [b'', word(0), word(999) + word(0), word(0) + word(0) + word(0)]:
            data = SALT + word(152) + word(0xb0000000 | len(payload)) + payload + word(0)
            with self.assertRaises(FormatError):
                inspect(data)

    @staticmethod
    def linked_code_fixture(offset=4, code_tag=0x71):
        code = word(0x12345678) + bytes.fromhex('27bdffe803e0000800000000')
        table = word(2) + word(0xffffffff) + word(offset) + word(0)
        return (SALT + word(152) + word((code_tag << 24) | len(code)) + code
                + word(0xb0000000 | len(table)) + table + word(0))

    def test_function_code_base_and_bundle_positions(self):
        first = frozen()
        result = inspect(first + self.linked_code_fixture())['packages'][1]['function_code']
        self.assertEqual(result['code_base_file_offset'], len(first) + 20)
        self.assertEqual(result['raw_leading_word'], 0x12345678)
        self.assertEqual(result['entries'][0]['status'], 'null-method')
        entry = result['entries'][1]
        self.assertEqual(entry['file_offset'], len(first) + 24)
        self.assertEqual(entry['entry_preview']['prefix_hex'], '03e0000800000000')
        zero = inspect(self.linked_code_fixture(0))['packages'][0]['function_code']
        self.assertEqual(zero['entries'][1]['file_offset'], 20)

    def test_function_code_rejects_outside_and_unaligned_offsets(self):
        for offset in [1, 12, 0xfffffffc]:
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                inspect(self.linked_code_fixture(offset))

    def test_function_code_unknown_variant_stays_unlinked(self):
        result = inspect(self.linked_code_fixture(code_tag=0x72))['packages'][0]['function_code']
        self.assertEqual(result['status'], 'unsupported-code-attribute-combination')

    @staticmethod
    def heap_fixture(payload, tag=0x60):
        return SALT + word(152) + word((tag << 24) | len(payload)) + payload + word(0)

    def test_heap_body_padding_reference_and_bundle_positions(self):
        payload = word(0xb0000517) + word(3) + b'abcX' + word(0xf0000000) + word(42) + word(0)
        first = frozen()
        heap = inspect(first + self.heap_fixture(payload))['packages'][1]['records'][0]['heap']
        self.assertEqual(len(heap['objects']), 2)
        obj = heap['objects'][0]
        self.assertEqual(obj['raw_class_selector'], 0x517)
        self.assertEqual(obj['body']['offset'], len(first) + 24)
        self.assertEqual(obj['body']['length'], 3)
        self.assertEqual(obj['padding_hex'], '58')
        self.assertEqual(heap['objects'][1]['raw_locator_selector'], 42)

    def test_heap_name_subtype_controls_external_name(self):
        external = word(0x81000001) + word(1) + b'\x00\x01\x00A' + b'z123' + word(0)
        obj = inspect(self.heap_fixture(external))['packages'][0]['records'][0]['heap']['objects'][0]
        self.assertEqual(obj['external_name']['text_utf16be'], 'A')
        internal = word(0xb1000001) + word(4) + b'ABCD' + word(0)
        obj = inspect(self.heap_fixture(internal))['packages'][0]['records'][0]['heap']['objects'][0]
        self.assertNotIn('external_name', obj)
        self.assertEqual(obj['body']['prefix_hex'], '41424344')

    def test_heap_truncated_fields_and_invalid_terminators(self):
        for payload in [b'', word(0xb0000001), word(0xb0000001) + word(100),
                        word(0xf0000000), word(0x81000001) + word(0) + b'\xff\xff',
                        word(0) + word(0), word(1)]:
            with self.subTest(payload=payload.hex()), self.assertRaises(FormatError):
                inspect(self.heap_fixture(payload))

    def test_heap_unknown_attribute_flags_remain_opaque(self):
        record = inspect(self.heap_fixture(b'x', tag=0x62))['packages'][0]['records'][0]
        self.assertNotIn('heap', record)

    def test_defined_component_ranges_and_low_byte_kind(self):
        payload = word(0x102) + word(9000) + word(3) + word(3) + word(5000) + word(2) + word(0)
        record = inspect(self.heap_fixture(payload, tag=0x30))['packages'][0]['records'][0]
        entries = record['defined_components']['entries']
        self.assertEqual(entries[0]['kind'], 'class')
        self.assertEqual(entries[0]['selector_start'], 9000)
        self.assertEqual(entries[1]['count'], 2)

    def test_defined_components_invalid_ranges_and_truncations(self):
        for payload in [b'', word(2), word(2) + word(1), word(1) + word(1) + word(1) + word(0),
                        word(2) + word(1) + word(0) + word(0),
                        word(2) + word(0xffffffff) + word(2) + word(0), word(0) + word(0)]:
            with self.subTest(payload=payload.hex()), self.assertRaises(FormatError):
                inspect(self.heap_fixture(payload, tag=0x30))

    def test_addressing_ranges_map_heap_records(self):
        address = word(100) + word(9) + word(200) + word(2) + word(0)
        heap = word(0xf0000000) + word(0)
        heap = heap * 3 + word(0)
        data = (SALT + word(152) + word(0x53000000 | len(address)) + address
                + word(0x60000000 | len(heap)) + heap + word(0))
        package = inspect(data)['packages'][0]
        self.assertEqual([o['selector'] for o in package['heap_selectors']['objects']], [100, 200, 208])
        self.assertEqual(package['records'][0]['object_addressing']['raw_auxiliary_word'], 9)
        for count in [1, 3]:
            bad = bytearray(data)
            bad[28:32] = word(count)
            with self.assertRaises(FormatError):
                inspect(bad)

    def test_addressing_bad_range_and_terminator(self):
        for payload in [b'', word(4) + word(1),
                        word(4) + word(1) + word(12) + word(10001) + word(0),
                        word(4) + word(1) + word(0xffffffff) + word(2) + word(0),
                        word(4) + word(1) + word(0) + word(0)]:
            with self.subTest(payload=payload.hex()), self.assertRaises(FormatError):
                inspect(self.heap_fixture(payload, tag=0x53))

    def test_other_formats_rejected(self):
        with self.assertRaises(FormatError):
            inspect(b'MZ' + bytes(100))


if __name__ == '__main__':
    unittest.main()
