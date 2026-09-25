"""The class and operation records, held to the packages and to the SDK.

Nothing here is checked against itself. The field numbers are checked against
`NoDebug/FieldNumbers.h`, which states the number of every field in the
system; the records are rebuilt from what the decoder read and diffed against
the bytes ObjectMaker wrote. A builder that can re-emit what it reads is the
only kind worth trusting with something new.
"""
from pathlib import Path
import struct
import unittest

import class_records
from class_records import (Classes, class_list, class_record,
                           direct_dispatch_list, field_kind, field_number,
                           method_entry, operation_list, reference_masks)
from classdefs import Definitions, read
from derive_system_classes import (check_field_numbers,
                                   class_records as walk, solve)
from inspect_package import SDK_INTERFACES, inspect, load_numbers

COOKBOOK = Path(__file__).resolve().parents[2] / \
    'sdk/68k/samples/packages'
DEFFILES = SDK_INTERFACES / 'DefFiles'
PACKAGES = sorted(COOKBOOK.glob('*.pkg'))


@unittest.skipUnless(DEFFILES.is_dir(), 'SDK missing')
class FieldNumberTests(unittest.TestCase):
    """The encoding an accessor is handed to find its field."""

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)

    def test_the_sdk_states_the_number_of_every_field(self):
        """Against `FieldNumbers.h`, which is ObjectMaker's own output.

        Five classes do not come out, fifty-seven of the differences being in
        `System` alone, and they have Boolean runs this places one bit along
        from where the header does. None of them is a superclass of anything
        in the cookbook, so what is asserted is the rate rather than nothing.
        """
        agreed, differed, _ = check_field_numbers(self.defs)
        self.assertGreater(agreed, 2300)
        self.assertLess(differed, 100)

    def test_a_position_counts_from_the_class_s_own_fields(self):
        """`ClassList.reserved1` is eight bytes in and carries four."""
        self.assertEqual(
            field_number({'offset': 8, 'bit': None,
                          'kind': class_records.FIELD_KIND_HALFWORD}, 0),
            0x40040000)

    def test_a_reference_and_a_word_are_told_apart_by_the_type(self):
        """A `Pointer` is four bytes and not an object; an `ObjectList` is."""
        self.assertEqual(field_kind('Pointer', self.defs),
                         class_records.FIELD_KIND_WORD)
        self.assertEqual(field_kind('Fixed', self.defs),
                         class_records.FIELD_KIND_WORD)
        self.assertEqual(field_kind('ObjectList', self.defs),
                         class_records.FIELD_KIND_REFERENCE)
        self.assertEqual(field_kind('UnsignedShort', self.defs),
                         class_records.FIELD_KIND_HALFWORD)

    def test_a_boolean_takes_a_bit_position_rather_than_a_halfword(self):
        """`PackageBoot`-style runs: bit 0 of byte 0 is the top of the word."""
        top = field_number({'offset': 0, 'bit': 0}, 0)
        self.assertEqual(top, 0xFC000000)
        self.assertEqual(field_number({'offset': 0, 'bit': 3}, 0), 0xF0000000)
        self.assertEqual(field_number({'offset': 0, 'bit': 4}, 0), 0xEC000000)


@unittest.skipUnless(PACKAGES and DEFFILES.is_dir(), 'corpus missing')
class RoundTripTests(unittest.TestCase):
    """Every record rebuilt from the decode and diffed against the bytes."""

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        cls.decoded = {p.stem: (p.read_bytes(),
                                inspect(p.read_bytes(), cls.tables, cls.defs))
                       for p in PACKAGES}

    def payload(self, raw, entry):
        return raw[entry['offset'] + 12:entry['offset'] + entry['length']]

    def test_every_class_record_comes_back_byte_for_byte(self):
        """Forty-eight of the fifty.

        The two that do not are BizNote's `BizIndexScene` and Circuits'
        `Resistor`, whose records carry more interfaces than their
        `interfaceCount` says -- which is a limit of the decode rather than of
        this, and is already recorded as such.
        """
        same = differ = 0
        for name, (raw, decoded) in self.decoded.items():
            for entry in decoded['objects']:
                record = entry.get('class_record')
                if not record:
                    continue
                want = self.payload(raw, entry)
                flags, base, depth = struct.unpack_from('>HBB', want, 0x14)
                references, copies, total = struct.unpack_from(
                    '>III', want, 0x24)
                methods = []
                for method in record['methods']:
                    selector = int(method['selector'], 16)
                    if 'accessor' in method:
                        accessor = method['accessor']
                        methods.append(struct.pack(
                            '>IIII', selector, accessor['class_number'],
                            int(accessor['word'], 16), 0))
                    else:
                        methods.append(method_entry(
                            selector, method['code_object'],
                            method['code_offset'],
                            method.get('method_flags', 0)))
                parents = record.get('inherits_from', [])
                got = bytearray(class_record(
                    record['number'], entry['id'],
                    record.get('field_list') or 0,
                    record['instance_size'], [], parents,
                    [s['class_number'] for s in parents], methods,
                    [i['class_number'] for i in record['interfaces']],
                    {'base': base, 'depth': depth, 'copies': total}))
                # The masks and the flags are carried rather than derived here:
                # deriving them is what `reference_masks` and `class_flags` are
                # for, and they are checked against the corpus separately.
                struct.pack_into('>II', got, 0x24, references, copies)
                struct.pack_into('>H', got, 0x14, flags)
                if bytes(got) == want:
                    same += 1
                else:
                    differ += 1
        self.assertEqual((same, differ), (48, 2))

    def test_every_class_list_comes_back_byte_for_byte(self):
        seen = 0
        for name, (raw, decoded) in self.decoded.items():
            for entry in decoded['objects']:
                table = entry.get('class_list')
                if not table or not table['entries']:
                    continue
                got = class_list([
                    {'record': e['class_record'], 'own_bytes': e['own_bytes'],
                     'instance_size': e['instance_size'], 'mixin': e['mixin'],
                     'inherits_from': e['inherits_from'],
                     'name_hash': e['name_hash'],
                     'inherited_bytes': e['inherited_bytes']}
                    for e in table['entries']])
                self.assertEqual(got, self.payload(raw, entry), name)
                seen += 1
        self.assertEqual(seen, 9)

    def test_every_operation_list_comes_back_byte_for_byte(self):
        """Including the holes, and the count of slots not operations."""
        seen = 0
        for name, (raw, decoded) in self.decoded.items():
            for entry in decoded['objects']:
                table = entry.get('operation_list')
                if not table or not table['entries']:
                    continue
                live = [e for e in table['entries'] if not e.get('reserved')]
                got = operation_list(
                    [{'number': e['number'], 'record': e['operation'],
                      'kind': e['kind'], 'name_hash': e['name_hash'],
                      'flags': e['flags']} for e in live],
                    0x8000 + len(table['entries']))
                self.assertEqual(got, self.payload(raw, entry), name)
                seen += 1
        self.assertEqual(seen, 9)

    def test_a_direct_dispatch_list_is_a_bare_run_of_numbers(self):
        seen = 0
        for name, (raw, decoded) in self.decoded.items():
            for entry in decoded['objects']:
                if entry.get('class_name') != 'DirectDispatchList':
                    continue
                want = self.payload(raw, entry)
                numbers = struct.unpack(f'>{len(want) // 4}I', want)
                self.assertEqual(direct_dispatch_list(numbers), want, name)
                seen += 1
        self.assertGreaterEqual(seen, 9)


@unittest.skipUnless(PACKAGES and DEFFILES.is_dir(), 'corpus missing')
class DerivedValueTests(unittest.TestCase):
    """The numbers a record carries that are sums over what it inherits."""

    @classmethod
    def setUpClass(cls):
        defs = Definitions(DEFFILES, SDK_INTERFACES)
        tables = load_numbers()
        cls.by_name = {name: number
                       for number, name in tables['class'].items()}
        cls.rows = [row for _, local in walk(defs, tables)
                    for row in local.values()]

    def test_the_corpus_settles_the_system_classes_it_builds_on(self):
        system, disagree = solve(self.rows, self.by_name)
        self.assertGreaterEqual(len(system), 26)
        # Hanoi's Ring and Pole, whose only parent is another class of the
        # same package; Spreadsheet's CellEditorWindow, which has two parents
        # nothing else in the corpus mentions; and BizNote's BizIndexScene
        # and Circuits' Resistor, whose records carry more interfaces than
        # their interfaceCount admits to.
        self.assertEqual({row['name'] for row, _ in disagree},
                         {'Ring', 'Pole', 'CellEditorWindow',
                          'BizIndexScene', 'Resistor'})

    def test_what_was_derived_is_what_is_shipped(self):
        """`system_classes.json` against a fresh derivation."""
        system, _ = solve(self.rows, self.by_name)
        shipped = Classes().known
        self.assertTrue(shipped, 'system_classes.json is missing')
        for name, value in system.items():
            self.assertEqual(shipped.get(name), value, name)

    def test_class_flags_are_the_bits_the_corpus_explains(self):
        """0x04 where a class adds no fields, 0x0A00 where it has no parent."""
        unexplained = []
        for row in self.rows:
            want = class_records.CLASS_FLAGS
            if not row['reference_mask'] and not row['copy_mask'] \
                    and row['flags'] & class_records.FLAG_NO_OWN_FIELDS:
                want |= class_records.FLAG_NO_OWN_FIELDS
            if not row['parents']:
                want |= class_records.FLAG_NO_IMPLEMENTATION_PARENT
            if row['flags'] & ~want:
                unexplained.append(f'{row["package"]}:{row["name"]}')
        # ChartTool and five of Circuits' components carry 0x20, BizNote's
        # BizDrawerStack 0x10 and BarChart's BarChartForm 0x4000, and nothing
        # in the corpus says what any of the three select.
        self.assertLessEqual(len(unexplained), 9)

    def test_a_no_copy_field_is_in_one_mask_and_not_the_other(self):
        """BarChart's `drawingData`, the only `noCopy` in the corpus."""
        fields = [{'offset': 0, 'kind': class_records.FIELD_KIND_REFERENCE},
                  {'offset': 4, 'kind': class_records.FIELD_KIND_REFERENCE,
                   'no_copy': True}]
        self.assertEqual(reference_masks(fields), (0b11, 0b01))


if __name__ == '__main__':
    unittest.main()


def _have_clang():
    import shutil
    return (shutil.which('clang-18') and shutil.which('llvm-objdump-18')
            and shutil.which('m68k-linux-gnu-ld'))


@unittest.skipUnless(_have_clang(), 'clang-18 missing')
class DispatchTests(unittest.TestCase):
    """That a call to Magic Cap can be compiled here at all.

    The SDK's headers declare the system's twelve and a half thousand
    operations as four instruction words to paste at the call site, which no
    compiler here speaks. What is asserted is that clang can be made to emit
    those same words, because that is what the nine examples that still need
    a `Code` object are waiting on.
    """

    def test_clang_emits_the_words_the_sdk_states(self):
        import dispatch
        code, wanted = dispatch.probe()
        for want in wanted:
            self.assertIn(want, code)

    def test_a_call_is_the_selector_and_the_vector(self):
        import dispatch
        self.assertEqual(dispatch.call(0x8004),
                         [0x343C, 0x8004, 0x4EAD, 0xFFFA])
        self.assertEqual(dispatch.call(0x064D, dispatch.INHERITED),
                         [0x343C, 0x064D, 0x4EAD, 0xFFDA])

    def test_the_probe_matches_what_counter_carries(self):
        """Counter's own `Code` object has these eight bytes twice over."""
        import dispatch
        code, _ = dispatch.probe()
        counter = bytes.fromhex('2f03' '343c8004' '4eadfffa')
        self.assertIn(counter[2:], code)


@unittest.skipUnless(_have_clang() and PACKAGES, 'clang-18 or corpus missing')
class CompileTests(unittest.TestCase):
    """The examples' own C, compiled here, against what CodeWarrior made.

    The bytes differ and are meant to. The dispatches are what has to agree:
    which selector goes through which A5 vector is the whole of what a
    package does, and if those match then the rewritten headers are carrying
    the SDK's own instruction words through unchanged.
    """

    EXAMPLES = ('Counter', 'Hanoi', 'Spreadsheet')
    SOURCES = Path(__file__).resolve().parents[2] / \
        'sdk/68k/samples/projects'

    def test_every_dispatch_is_the_one_the_package_carries(self):
        from compile_example import compare
        for name in self.EXAMPLES:
            with self.subTest(example=name):
                ours, stock = compare(self.SOURCES / name,
                                      COOKBOOK / f'{name}.pkg')
                self.assertTrue(stock, f'{name} has no code to compare with')
                self.assertEqual(ours, stock)

    def test_the_headers_leave_nothing_it_cannot_compile(self):
        """Every inline-code declaration rewritten, bar the variadic ones."""
        import magic_headers
        text = magic_headers.normalise(magic_headers.OPERATIONS)
        rewritten, count, omitted = magic_headers.convert(
            text, magic_headers.struct_types([text]))
        self.assertGreater(count, 12000)
        self.assertNotIn('={0x', rewritten)
        self.assertLess(len(omitted), 40)

    def test_an_argument_is_pushed_as_a_long_and_popped_by_the_caller(self):
        import magic_headers
        one = magic_headers.rewrite('void', 'F', [('ObjectID', 'self')],
                                    [0x343C, 0x8001, 0x4EAD, 0xFFFA], False)
        self.assertIn('move.l %[a0],-(%%sp)', one)
        self.assertIn('0x343c,0x8001,0x4ead,0xfffa,0x584f', one)
        three = magic_headers.rewrite(
            'void', 'G', [('ObjectID', 'a'), ('Boolean', 'b'),
                          ('Boolean', 'c')],
            [0x343C, 0x801E, 0x4EAD, 0xFFFA], False)
        # Three longs come back off with `lea 12(a7),a7`.
        self.assertIn('0x4fef,0x000c', three)


    def test_the_linked_code_has_nothing_left_to_relocate(self):
        """Which is what a package's `Code` is: no fixup table anywhere.

        A compiler leaves references behind -- a string in `.rodata`, a jump
        table, a call between two of the package's own procedures -- and they
        are resolved by the link, because a Magic Cap package has no way to
        resolve them later. Circuits is the one with all three.
        """
        from compile_example import code
        for name in ('Counter', 'Circuits'):
            with self.subTest(example=name):
                blob, left, procedures = code(self.SOURCES / name)
                self.assertEqual(left, 0)
                self.assertGreater(len(blob), 200)
                self.assertIn('main', procedures)

    def test_the_packages_use_the_cpu32_multiply_and_divide(self):
        """Which is why this compiles for the 68020 and not the 68000.

        The 68000 has no 32-bit `mulu.l` or `divu.l`; BarChart's compiled
        code has four and two of them, so CodeWarrior was building for the
        CPU32 core the MC68349 has. Without it a divide becomes a call to
        `__udivsi3`, which is a relocation into a library that is not there.
        """
        import struct
        from inspect_package import (CODE_CLASS, decode_header, find_cluster,
                                     walk_objects)
        data, _ = find_cluster((COOKBOOK / 'BarChart.pkg').read_bytes())
        header = decode_header(data)
        wide = 0
        for entry in walk_objects(data, header['heap_end']):
            if entry['class_number'] != CODE_CLASS:
                continue
            body = entry['payload']
            code = data[body['offset']:body['offset'] + body['length']]
            for at in range(0, len(code) - 1, 2):
                if 0x4C00 <= struct.unpack_from('>H', code, at)[0] <= 0x4C7F:
                    wide += 1
        self.assertGreaterEqual(wide, 6)
