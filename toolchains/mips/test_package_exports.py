import struct
import unittest
from inspect_format import FormatError
from package_exports import decode_entries, resolve_local


def decode(slots, names=b'\x05@Test'):
    entries = struct.pack('>I', len(slots)) + b''.join(struct.pack('>4I', *s) for s in slots)
    data = entries + bytes(8) + names
    return decode_entries(data, {'offset': 0, 'length': len(entries)},
                          {'offset': len(entries), 'length': 8 + len(names)})


class ExportTests(unittest.TestCase):
    def test_name_kind_count_and_deleted_slot(self):
        entries = decode([(0, 0x02000000, 1, 50), (0x80000000, 0xffffffff, 0, 0)])
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]['name'], entries[0]['kind'], entries[0]['selector_start']), ('@Test', 'class', 50))
        self.assertTrue(entries[0]['local'])

    def test_bad_layout_name_and_kind(self):
        for slot, name in [((0, 0x020000ff, 1, 2), b'\x01X'),
                           ((0, 0x02000000, 1, 2), b'\xffX'),
                           ((0, 0x06000000, 1, 2), b'\x01X')]:
            with self.assertRaises(FormatError):
                decode([slot], name)
        with self.assertRaises(FormatError):
            decode_entries(bytes(12), {'offset': 0, 'length': 5}, {'offset': 4, 'length': 8})

    def test_locator_stride_and_range(self):
        exports = decode([(0, 0x01000000, 3, 12)])
        source = {'component_kind': 'locator', 'interface': '@Test', 'index': 2, 'required_count': 1}
        self.assertEqual(resolve_local(source, exports)['selector'], 28)
        self.assertEqual(resolve_local({**source, 'required_count': 2}, exports)['status'], 'local-export-range-mismatch')

    def test_duplicate_and_missing_names_not_guessed(self):
        exports = decode([(0, 0x02000000, 1, 50)])
        source = {'component_kind': 'class', 'interface': '@Test', 'index': 0, 'required_count': 1}
        self.assertEqual(resolve_local(source, exports * 2)['status'], 'ambiguous-local-export')
        self.assertEqual(resolve_local(source, [])['status'], 'missing-local-export')


if __name__ == '__main__':
    unittest.main()
