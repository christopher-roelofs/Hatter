import struct
import unittest
from inspect_format import FormatError
from rom_interface_exports import trace_table


def fixture():
    data = bytearray(128)
    # Table header/body, entries header/body, names header/body.
    struct.pack_into('>2I', data, 0, 0x8010000d, 0x80000009)
    struct.pack_into('>4I', data, 8, 0x80000011, 12, 1, 1)
    struct.pack_into('>I', data, 32, 0x80000019)
    struct.pack_into('>7I', data, 48, 0x80100414, 0x80000011, 1,
                     0, 0x03000000, 2, 50)
    struct.pack_into('>2I', data, 80, 0x8000000f, 0x80000019)
    data[96:101] = b'\x04Test'
    return data


class RomExportTests(unittest.TestCase):
    def test_object_chain_and_selector(self):
        result = trace_table(fixture(), 97)
        self.assertEqual(result['table_body_offset'], 8)
        self.assertEqual(result['exports'][0]['name'], 'Test')
        self.assertEqual(result['exports'][0]['selector_start'], 50)

    def test_missing_reference_chain(self):
        data = fixture()
        struct.pack_into('>I', data, 32, 0x80000021)
        with self.assertRaises(FormatError):
            trace_table(data, 97)

    def test_active_count_mismatch(self):
        data = fixture()
        struct.pack_into('>I', data, 20, 2)
        with self.assertRaises(FormatError):
            trace_table(data, 97)

    def test_ambiguous_chain_rejected(self):
        data = fixture()
        data.extend(bytes(48))
        data[128:168] = data[:40]
        with self.assertRaises(FormatError):
            trace_table(data, 97)

    def test_name_bounds(self):
        data = fixture()
        data[96] = 255
        with self.assertRaises(FormatError):
            trace_table(data, 97)

    def test_unaligned_anchor_and_unsupported_entry_size(self):
        with self.assertRaises(FormatError):
            trace_table(fixture(), 98)
        data = fixture()
        struct.pack_into('>I', data, 12, 16)
        with self.assertRaises(FormatError):
            trace_table(data, 97)


if __name__ == '__main__':
    unittest.main()
