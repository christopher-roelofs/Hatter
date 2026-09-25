import unittest
from inspect_format import FormatError, decode_bnum, decode_global_init
from build_global_init import bnum, instruction, GlobalInitBuilder, transformed_words


class BuildGlobalInitTests(unittest.TestCase):
    def test_bnum_boundaries(self):
        for value in (-2147483648, -8388609, -8388608, -32769, -32768, -1025,
                      -1024, -1, 0, 239, 240, 1023, 1024, 32767, 32768,
                      8388607, 8388608, 2147483647):
            encoded = bnum(value)
            self.assertEqual(decode_bnum(encoded, 0, len(encoded)), (value, len(encoded)))
        for value in (-2147483649, 2147483648):
            with self.assertRaises(FormatError):
                bnum(value)

    def test_counts(self):
        for n in (0, 1, 6, 7, 8, 24, 25, 255, 256, 65535, 65536, 0xffffffff):
            data = bytes(8) + instruction(2, n) + b'\0'
            self.assertEqual(decode_global_init(data, 0, len(data))['instructions'][0]['count'], n)

    def test_literal_relative_pair_and_resolution(self):
        b = GlobalInitBuilder(24, 0)
        b.literal(b'ABCD')
        b.relative_words('code', [0])
        b.relative_words('globals', [0])
        b.resolve(6, 'SystemPublic', 1, pair=True)
        b.zeros(4)
        data = b.finish(32)
        decoded = decode_global_init(data, 0, len(data))
        self.assertEqual(decoded['status'], 'decoded-global-init-boundaries')
        state = decoded['instructions'][3]['entries'][0]['state']
        self.assertEqual(state['interface_latin1'], 'SystemPublic')
        self.assertEqual(transformed_words(0x12345678, state, 0x87654321), [0x12345678, 0x87654321])

    def test_long_name_and_explicit_operand_reset(self):
        b = GlobalInitBuilder(8, 123)
        b.resolve(3, 'x' * 128, 240)
        b.resolve(2, '@Class', 0)
        data = b.finish(0)
        decoded = decode_global_init(data, 0, len(data))
        self.assertEqual(decoded['raw_second_header_word'], 123)
        self.assertEqual(decoded['instructions'][0]['entries'][0]['state']['interface_latin1'], 'x' * 128)
        self.assertEqual(decoded['instructions'][1]['entries'][0]['state']['raw_index'], 0)

    def test_bounds_alignment_and_relative_targets(self):
        b = GlobalInitBuilder(4, 0)
        b.relative_words('code', [100])
        with self.assertRaises(FormatError):
            b.finish(10)
        b = GlobalInitBuilder(4, 0)
        b.move(1)
        b.resolve(3, '@Test', 0)
        with self.assertRaises(FormatError):
            b.finish(0)

    def test_reset_destination(self):
        b = GlobalInitBuilder(4, 0)
        b.zeros(4)
        b.reset_destination()
        b.literal(b'Test')
        self.assertTrue(b.finish(0).endswith(b'Test\0'))

    def test_arithmetic_wrap_and_pair_gp_unchanged(self):
        state = {'raw_field_b4': -1, 'raw_field_bc': 2, 'raw_destination_mode': 17}
        self.assertEqual(transformed_words(3, state, 7), [0xffffffff, 7])
        with self.assertRaises(FormatError):
            transformed_words(3, state)

    def test_width_check_precedes_transform(self):
        state = {'raw_field_af': 8, 'raw_field_b4': 0}
        with self.assertRaises(FormatError):
            transformed_words(256, state)
        self.assertEqual(transformed_words(255, state), [0])
        self.assertEqual(transformed_words(0xffffffff, {'raw_field_af': 0x88}), [0xffffffff])
        with self.assertRaises(FormatError):
            transformed_words(128, {'raw_field_af': 0x88})


if __name__ == '__main__':
    unittest.main()
