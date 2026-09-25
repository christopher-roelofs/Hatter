import unittest

from inspect_format import FormatError, decode_global_init
from validate_global_init import validate


def audit(body, size=16, code_size=32):
    data = size.to_bytes(4, 'big') + bytes(4) + body + b'\x00'
    return validate(data, decode_global_init(data, 0, len(data)), code_size)


class GlobalWriteTests(unittest.TestCase):
    def test_literal_then_add_globals_base(self):
        result = audit(b'\x16\x00\x00\x00\x03\x02\x1f\x02')
        self.assertEqual(result['relative_targets'][0]['offset'], 5)
        self.assertEqual(result['outside_target_count'], 0)

    def test_symbolic_existing_word_stays_unknown(self):
        result = audit(b'\x19\x00\x02\x1f\x02')
        self.assertIsNone(result['relative_targets'][1]['offset'])
        self.assertEqual(result['unresolved_target_count'], 1)

    def test_one_past_and_outside_are_advisory(self):
        result = audit(b'\x2a\x20\xfa\xbd\xcd\xcd\xcd')
        self.assertTrue(result['relative_targets'][0]['within_extent_or_one_past'])
        self.assertEqual(result['relative_targets'][1]['offset'], -1110585907)
        self.assertEqual(result['outside_target_count'], 1)

    def test_reset_and_resolution_destination_delta(self):
        result = audit(b'\x1d\x01\x11\x04\x18\x01\x1c\x00')
        self.assertEqual([(w['destination_offset'], w['length']) for w in result['write_spans']],
                         [(0, 8), (12, 1), (0, 4)])

    def test_rewind_and_signed_add_wrap(self):
        result = audit(b'\x16\xff\xff\xff\xff\x43\x1f\x01')
        self.assertEqual(result['relative_targets'][0]['offset'], 0)

    def test_bounds_alignment_and_expansion_rejected(self):
        for body in (b'\x12\x19\x00', b'\xd2\x10\x18',
                     b'\x13\x18', b'\xf8\xff\xff\xff\xff'):
            with self.subTest(body=body.hex()), self.assertRaises(FormatError):
                audit(body)

    def test_unsupported_resolution_and_partial_script_rejected(self):
        with self.assertRaises(FormatError):
            audit(b'\x1c\x01\x02')
        with self.assertRaises(FormatError):
            audit(b'\x1e')


if __name__ == '__main__':
    unittest.main()
