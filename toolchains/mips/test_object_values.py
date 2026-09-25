import unittest
from inspect_format import FormatError
from build_object_values import fixed_body, object_list, read_object_list, decode_object_list
from build_object_values import plain_text, read_plain_text


def layout(*fields, size=4):
    return {'fixed_storage_bytes': size, 'fields': [
        {'name': n, 'type': t, 'bit_offset': o, 'bit_width': w, 'word_format': f}
        for n, t, o, w, f in fields]}


class ObjectValueTests(unittest.TestCase):
    def test_text_golden_ascii_and_unicode(self):
        self.assertEqual(plain_text('About EmptyPackage\n'), b'About EmptyPackage\n')
        self.assertEqual(plain_text('\u20180'), bytes.fromhex('81201830'))
        self.assertEqual(read_plain_text(bytes.fromhex('81201830')), '\u20180')
        self.assertEqual(plain_text(''), b'')

    def test_text_chunk_boundaries(self):
        for count in (1, 63, 64, 127, 65536):
            value = '\u3042' * count + ' ASCII\x00\x7f' + '\u00e9'
            self.assertEqual(read_plain_text(plain_text(value)), value)
        self.assertEqual(plain_text('\u3042' * 64), b'\xbf' + b'\x30\x42' * 63 + b'\x81\x30\x42')

    def test_text_extended_count(self):
        self.assertEqual(read_plain_text(b'\x80\x00\x40' + b'\x30\x42' * 64), '\u3042' * 64)

    def test_text_rejects_unsupported_and_truncated(self):
        for value in ('\U0001f600', '\ud800', 42):
            with self.assertRaises(FormatError):
                plain_text(value)
        for data in (b'\x80', b'\x80\x00', b'\x80\x00\x00', b'\x81\x20', b'\xc0', b'\xff', b'\x81\xd8\x00'):
            with self.assertRaises(FormatError):
                read_plain_text(data)

    def test_boolean_msb_numbering_and_halfword(self):
        l = layout(('a', 'Boolean', 0, 1, 0), ('b', 'Boolean', 7, 1, 0),
                   ('c', 'Boolean', 8, 1, 0), ('short', 'UnsignedShort', 16, 16, 3))
        self.assertEqual(fixed_body(l, {'a': True, 'b': True, 'c': True, 'short': 0x1234}), bytes.fromhex('81801234'))

    def test_dot_signed_raw_units(self):
        l = layout(('point', 'Dot', 0, 64, 4), size=8)
        self.assertEqual(fixed_body(l, {'point': [1, -8]}), bytes.fromhex('00000001fffffff8'))

    def test_references_are_explicit_encoded_words(self):
        l = layout(('ref', 'Object', 0, 32, 13))
        self.assertEqual(fixed_body(l, {'ref': 0x10001fe4}), bytes.fromhex('10001fe4'))

    def test_runtime_pointer_must_be_null(self):
        l = layout(('ptr', 'VolumeRosterPointer', 0, 32, 8))
        self.assertEqual(fixed_body(l, {'ptr': 0}), bytes(4))
        with self.assertRaises(FormatError):
            fixed_body(l, {'ptr': 12})

    def test_missing_unknown_and_bad_values(self):
        l = layout(('n', 'Unsigned', 0, 32, 4))
        for values in ({}, {'n': 0, 'extra': 1}, {'n': -1}, {'n': True}):
            with self.assertRaises(FormatError):
                fixed_body(l, values)

    def test_list_golden_and_empty(self):
        self.assertEqual(object_list([0x10001fe4, 12]), bytes.fromhex('0d00000210001fe40000000c'))
        self.assertEqual(read_object_list(object_list([])), [])

    def test_bad_list_and_selector_rejected(self):
        for data in (b'\x00', bytes.fromhex('0d000001'), bytes.fromhex('0f000000')):
            with self.assertRaises(FormatError):
                read_object_list(data)
        with self.assertRaises(FormatError):
            object_list([-1])

    def test_weak_reference_format_preserved(self):
        data = bytes.fromhex('0e0000010000000c')
        decoded = decode_object_list(data)
        self.assertEqual(decoded['word_format'], 14)
        self.assertEqual(object_list(**decoded), data)

    def test_empty_body_has_no_asserted_reference_format(self):
        self.assertIsNone(decode_object_list(b'')['word_format'])
        self.assertEqual(object_list([], omit_empty_header=True), b'')
        with self.assertRaises(FormatError):
            object_list([12], omit_empty_header=True)


if __name__ == '__main__':
    unittest.main()
