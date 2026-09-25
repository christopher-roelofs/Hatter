import unittest
from inspect_format import decode_abbreviated_classes, FormatError
from build_frozen import abbreviated_classes


class AbbreviatedClassTests(unittest.TestCase):
    def test_nibble_order_and_odd_padding(self):
        data = bytes.fromhex('0000000103de4f5800000000')
        result = decode_abbreviated_classes(data, 0, len(data))
        e = result['entries'][0]
        self.assertEqual(e['raw_format_nibbles'], [13, 14, 4])
        self.assertEqual(e['padding_hex'], '58')

    def test_roundtrip_preserves_unused_nibble_and_padding(self):
        data = bytes.fromhex('0000000103de4f5800000000')
        entries = decode_abbreviated_classes(data, 0, len(data))['entries']
        self.assertEqual(abbreviated_classes(entries), data)

    def test_empty_fixed_part_and_multiple_classes(self):
        data = abbreviated_classes([{'class_selector': 1, 'raw_format_nibbles': []},
                                    {'class_selector': 2, 'raw_format_nibbles': [1, 2, 3, 4]}])
        self.assertEqual([e['format_count'] for e in decode_abbreviated_classes(data, 0, len(data))['entries']], [0, 4])

    def test_count_limit(self):
        data = abbreviated_classes([{'class_selector': 1, 'raw_format_nibbles': [14] * 255}])
        self.assertEqual(decode_abbreviated_classes(data, 0, len(data))['entries'][0]['format_count'], 255)
        for entry in ({'class_selector': 0, 'raw_format_nibbles': []},
                      {'class_selector': 1, 'raw_format_nibbles': [16]},
                      {'class_selector': 1, 'raw_format_nibbles': [1] * 256}):
            with self.assertRaises(FormatError):
                abbreviated_classes([entry])

    def test_truncation_and_trailing_bytes(self):
        data = abbreviated_classes([{'class_selector': 1, 'raw_format_nibbles': [1, 2, 3]}])
        for n in range(len(data)):
            with self.assertRaises(FormatError):
                decode_abbreviated_classes(data[:n], 0, n)
        with self.assertRaises(FormatError):
            decode_abbreviated_classes(data + b'x', 0, len(data) + 1)


if __name__ == '__main__':
    unittest.main()
