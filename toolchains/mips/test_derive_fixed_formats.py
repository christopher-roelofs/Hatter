import unittest
from inspect_format import FormatError
from derive_fixed_formats import derive


def cls(size, fields=(), parents=(), base='Object'):
    return {'layout': {'fixed_storage_bytes': size, 'inherits_from': [{'name_latin1': x} for x in parents],
                       'field_access_base': {'name_latin1': base}},
            'members': {'fields': list(fields)}}


def field(name, kind, offset, flags=0):
    return {'name_latin1': name, 'type_name_latin1': kind,
            'fixed_bit_offset': offset, 'raw_flags_byte': flags}


class FixedFormatTests(unittest.TestCase):
    def test_scalar_boolean_and_object_strength(self):
        classes = {'Object': cls(0), 'Test': cls(16, [field('bits', 'Boolean', 0),
                   field('number', 'Unsigned', 32), field('strong', 'Object', 64),
                   field('weak', 'Object', 96, 128)])}
        self.assertEqual(derive('Test', classes)['raw_format_nibbles'], [0, 4, 13, 14])

    def test_explicit_mixin_placement_required(self):
        classes = {'Mix': cls(4, [field('x', 'Signed', 0)], base='Mix'),
                   'Test': cls(8, parents=['Mix'])}
        with self.assertRaises(FormatError):
            derive('Test', classes)
        result = derive('Test', classes, {'Mix': 4})
        self.assertEqual(result['raw_format_nibbles'], [0, 4])
        self.assertEqual(result['unassigned_words'], [0])

    def test_inherited_fields_not_duplicated(self):
        classes = {'Base': cls(4, [field('x', 'Unsigned', 0)]),
                   'Left': cls(4, parents=['Base']), 'Right': cls(4, parents=['Base']),
                   'Test': cls(4, parents=['Left', 'Right'])}
        self.assertEqual(len(derive('Test', classes)['fields']), 1)

    def test_unsupported_type_flags_and_bounds(self):
        for f in (field('x', 'Dot', 0), field('x', 'Unsigned', 0, 64),
                  field('x', 'Unsigned', 32), field('x', 'Unsigned', 1)):
            with self.assertRaises(FormatError):
                derive('Test', {'Test': cls(4, [f])})

    def test_conflicting_formats_rejected(self):
        with self.assertRaises(FormatError):
            derive('Test', {'Test': cls(4, [field('x', 'Unsigned', 0), field('y', 'Boolean', 0)])})

    def test_dot_occupies_two_integer_words(self):
        self.assertEqual(derive('Test', {'Test': cls(8, [field('point', 'Dot', 0)])})['raw_format_nibbles'], [4, 4])

    def test_halfword_with_boolean_bytes(self):
        result = derive('Test', {'Test': cls(4, [field('flag', 'Boolean', 0),
                                               field('type', 'UnsignedShort', 16)])})
        self.assertEqual(result['raw_format_nibbles'], [3])

    def test_two_halfwords_combine(self):
        result = derive('Test', {'Test': cls(4, [field('a', 'UnsignedShort', 0),
                                               field('b', 'UnsignedShort', 16)])})
        self.assertEqual(result['raw_format_nibbles'], [1])

    def test_pointer_and_component_formats(self):
        types = ['VolumeRosterPointer', 'MethodCodeAddress', 'ClassNumber',
                 'OperationNumber', 'ClassOperationNumber', 'IntrinsicNumber']
        result = derive('Test', {'Test': cls(24, [field(str(i), t, i * 32) for i, t in enumerate(types)])})
        self.assertEqual(result['raw_format_nibbles'], [8, 8, 9, 10, 11, 12])

    def test_same_format_overlap_still_rejected(self):
        with self.assertRaises(FormatError):
            derive('Test', {'Test': cls(8, [field('point', 'Dot', 0), field('x', 'Signed', 32)])})

    def test_misaligned_halfword_rejected(self):
        with self.assertRaises(FormatError):
            derive('Test', {'Test': cls(4, [field('x', 'UnsignedShort', 8)])})


if __name__ == '__main__':
    unittest.main()
