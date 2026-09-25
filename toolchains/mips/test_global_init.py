import unittest
from inspect_format import FormatError, decode_bnum, decode_global_init


class GlobalInitTests(unittest.TestCase):
    def test_bnum_signed_widths_and_skipped_upper_word(self):
        cases = [(b'\xef', 239), (b'\xf1\x23', 291), (b'\xf7\xff', -1),
                 (b'\xf8\x80\x00', -32768), (b'\xf9\xff\xff\xfe', -2),
                 (b'\xfa\x12\x34\x56\x78', 0x12345678),
                 (b'\xfbABCD\xff\xff\xff\xfd', -3)]
        for data, expected in cases:
            self.assertEqual(decode_bnum(data, 0, len(data)), (expected, len(data)))
            for size in range(len(data)):
                with self.assertRaises(FormatError):
                    decode_bnum(data[:size], 0, size)
        with self.assertRaises(FormatError):
            decode_bnum(b'\xfc', 0, 1)

    def test_global_literals_skip_embedded_stop_and_extended_counts(self):
        data = bytes(8) + b'\xd1\x03A\x00B\x25\x12\x34\x00xx'
        result = decode_global_init(data, 0, len(data))
        self.assertEqual(result['status'], 'decoded-global-init-boundaries')
        self.assertEqual(result['instructions'][0]['count'], 3)
        self.assertEqual(result['instructions'][1]['kind'], 'repeat-halfword')
        self.assertEqual(result['trailing_bytes']['length'], 2)

    def test_global_relative_operands_and_partial_instruction(self):
        data = bytes(8) + b'\x29\x05\xf8\x01\x00\x1e\xff\xff'
        result = decode_global_init(data, 0, len(data))
        self.assertEqual(result['instructions'][0]['bnum_operands'], [5, 256])
        self.assertEqual(result['status'], 'partial-global-init')
        self.assertEqual(result['opaque_remainder']['offset'], 13)

    def test_resolution_name_reuse_delta_and_pass_reset(self):
        # Full name ABC, then replace its last character, then reuse the name.
        data = bytes(8) + b'\x1c\x40\x03ABC\x1c\x40\xc1\x01D\x1c\x00\x01\x1c\x00\x00'
        result = decode_global_init(data, 0, len(data))
        ins = result['instructions']
        self.assertEqual(ins[0]['entries'][0]['state']['interface_latin1'], 'ABC')
        self.assertEqual(ins[1]['entries'][0]['state']['interface_latin1'], 'ABD')
        self.assertEqual(ins[2]['entries'][0]['state']['interface_latin1'], 'ABD')
        self.assertNotIn('interface_latin1', ins[4]['entries'][0]['state'])

    def test_resolution_repeated_index_and_destination_delta(self):
        data = bytes(8) + b'\x2c\x20\xfe\x05\xfe\x08\x1d\x00\xf7\xff\x00'
        result = decode_global_init(data, 0, len(data))
        entries = result['instructions'][0]['entries']
        self.assertEqual([e['state']['raw_index'] for e in entries], [5, 8])
        last = result['instructions'][1]['entries'][0]
        self.assertEqual(last['state']['raw_index'], 9)
        self.assertEqual(last['destination_delta'], -1)

    def test_resolution_truncated_names_and_mask_operands(self):
        for suffix in [b'\x1c', b'\x1c\x40\x05abc', b'\x1c\x80',
                       b'\x1c\x20\xff\x01', b'\x1c\x01\x23',
                       b'\x1c\x40\x81']:
            data = bytes(8) + suffix
            with self.subTest(suffix=suffix.hex()), self.assertRaises(FormatError):
                decode_global_init(data, 0, len(data))

    def test_global_invalid_and_truncated_scripts(self):
        for suffix in [b'', b'\x03', b'\xd1', b'\xf1\xff\xff\xff\xff', b'\x17ab']:
            data = bytes(8) + suffix
            with self.subTest(suffix=suffix), self.assertRaises(FormatError):
                decode_global_init(data, 0, len(data))
        with self.assertRaises(FormatError):
            decode_global_init(bytes(7), 0, 7)


if __name__ == '__main__':
    unittest.main()
