import unittest
from build_object_names import name_tables, read_names, name_dictionary
from inspect_format import FormatError


class ObjectNamesTests(unittest.TestCase):
    def test_golden_names_and_duplicate(self):
        lookup, text = name_tables(['A', None, 'A', '\u3042'])
        self.assertEqual(lookup.hex(), '0000ffff00020004')
        self.assertEqual(text.hex(), '00000000000100410001004100013042')
        self.assertEqual(read_names(lookup, text, 4), ['A', None, 'A', '\u3042'])

    def test_invalid_names(self):
        for name in ('', '\ud800', '\U0001f600', 'x' * 16384):
            with self.assertRaises(FormatError):
                name_tables([name])

    def test_reject_bad_offsets_and_headers(self):
        lookup, text = name_tables(['AB'])
        for l, t, n in [(b'\x00\x01', text, 1), (lookup, text[:-1], 1),
                        (lookup, b'\0\0\0\1' + text[4:], 1), (lookup, text, 2),
                        (lookup, bytes(4) + b'\x40\x01\x00A', 1)]:
            with self.assertRaises(FormatError):
                read_names(l, t, n)

    def test_dictionary_golden_and_range(self):
        self.assertEqual(name_dictionary(52, 60, 12, 5).hex(), '000000340000003c0000000c00000005')
        with self.assertRaises(FormatError):
            name_dictionary(52, 60, 13, 5)


if __name__ == '__main__':
    unittest.main()
