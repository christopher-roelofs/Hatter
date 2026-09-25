"""The 68k package decode, checked against the SDK's own statements.

The cookbook ships each example's ObjectMaker definitions and C beside the
package built from them, so these are not self-consistency checks: the
definitions say which classes and instances the package contains and the C
says which operations each method calls, and the decode has to agree with
both. Where the corpus is silent the decode is required to stay silent too.
"""
import struct
import unittest
from pathlib import Path

from classdefs import Definitions, LayoutError, read, read_string_table
from inspect_package import (FormatError, HEAP_START, SDK_INTERFACES,
                             decode_header, inspect, load_numbers, name_hash,
                             read_macsbug_symbol, walk_objects)

COOKBOOK = Path(__file__).resolve().parents[2] / \
    'software/68k/extracted/installable/cookbook'
PACKAGES = sorted(COOKBOOK.glob('*.pkg'))


def result_bytes(stem):
    return (COOKBOOK / f'{stem}.pkg').read_bytes()


def synthetic(objects=(), trailer=b''):
    """A package built to order, for the failures the corpus cannot show."""
    heap = b''
    for class_number, object_id, payload in objects:
        record = struct.pack('>IHHHH', 12 + len(payload), class_number,
                             0x0088, 0x0100, object_id) + payload
        heap += record
    heap += b'\0\0\0\0'
    heap_end = HEAP_START + len(heap)
    trailer = struct.pack('>I', 4 + len(trailer)) + trailer
    total = heap_end + len(trailer)
    header = bytearray(HEAP_START)
    struct.pack_into('>I', header, 0x10, total)
    struct.pack_into('>I', header, 0x14, heap_end)
    struct.pack_into('>I', header, 0x2c, len(objects))
    struct.pack_into('>I', header, 0x34, len(objects) + 1)
    return bytes(header) + heap + trailer


class SyntheticTests(unittest.TestCase):
    def test_round_trip_of_a_made_up_package(self):
        data = synthetic([(29, 7, b'\0' * 8)])
        result = inspect(data, tables=load_numbers())
        self.assertEqual(result['bytes'], len(data))
        self.assertEqual(len(result['objects']), 1)
        self.assertEqual(result['objects'][0]['id'], 7)
        self.assertEqual(result['objects'][0]['class_name'], 'ObjectList')

    def test_length_disagreeing_with_the_file_is_refused(self):
        data = bytearray(synthetic([(29, 7, b'\0' * 8)]))
        struct.pack_into('>I', data, 0x10, len(data) + 4)
        with self.assertRaises(FormatError):
            decode_header(bytes(data))

    def test_object_running_past_the_heap_is_refused(self):
        data = bytearray(synthetic([(29, 7, b'\0' * 8)]))
        struct.pack_into('>I', data, HEAP_START, 0x400)
        with self.assertRaises(FormatError):
            walk_objects(bytes(data), decode_header(bytes(data))['heap_end'])

    def test_object_shorter_than_its_header_is_refused(self):
        data = bytearray(synthetic([(29, 7, b'\0' * 8)]))
        struct.pack_into('>I', data, HEAP_START, 8)
        with self.assertRaises(FormatError):
            walk_objects(bytes(data), decode_header(bytes(data))['heap_end'])

    def test_chain_must_land_on_the_end(self):
        """A record that stops part way through the heap is a bad decode.

        Landing exactly on the end is fine and so is landing on a zero word
        four bytes short of it -- the cookbook packages have that word and
        the shipping ones do not. Anywhere else means the records were not
        being read as records.
        """
        data = bytearray(synthetic([(29, 7, b'\0' * 8)]))
        struct.pack_into('>I', data, HEAP_START, 22)    # two bytes short
        with self.assertRaises(FormatError):
            walk_objects(bytes(data), decode_header(bytes(data))['heap_end'])

    def test_a_record_reaching_the_end_exactly_is_accepted(self):
        """What the two shipping packages do, having no trailing zero word."""
        data = bytearray(synthetic([(29, 7, b'\0' * 8)]))
        struct.pack_into('>I', data, HEAP_START, 24)    # swallows the word
        walked = walk_objects(bytes(data), decode_header(bytes(data))['heap_end'])
        self.assertEqual(len(walked), 1)


class SymbolTests(unittest.TestCase):
    def test_a_name_is_read_with_its_length(self):
        data = b'\x84main'
        self.assertEqual(read_macsbug_symbol(data, 0, len(data)), ('main', 5))

    def test_high_bytes_are_not_names(self):
        """'µ' and '²' are alphanumeric to Python and are operands here."""
        self.assertIsNone(read_macsbug_symbol(b'\x83\xb5\xb2\xb5', 0, 4))

    def test_a_length_running_past_the_code_is_not_a_name(self):
        self.assertIsNone(read_macsbug_symbol(b'\x84ma', 0, 3))

    def test_a_byte_without_the_top_bit_is_not_a_name(self):
        self.assertIsNone(read_macsbug_symbol(b'\x04main', 0, 5))


@unittest.skipUnless(PACKAGES, 'cookbook packages are not in this checkout')
class CookbookTests(unittest.TestCase):
    """Every example has to decode, not just the one the decode was read off."""

    @classmethod
    def setUpClass(cls):
        cls.tables = load_numbers()
        cls.decoded = {p.stem: inspect(p.read_bytes(), cls.tables)
                       for p in PACKAGES}

    def test_all_fourteen_examples_decode(self):
        self.assertEqual(len(self.decoded), 14)

    def test_every_object_chain_covers_its_whole_heap(self):
        for name, result in self.decoded.items():
            with self.subTest(package=name):
                objects = result['objects']
                self.assertEqual(objects[0]['offset'], HEAP_START)
                for first, second in zip(objects, objects[1:]):
                    self.assertEqual(first['offset'] + first['length'],
                                     second['offset'])
                last = objects[-1]
                self.assertEqual(last['offset'] + last['length'],
                                 result['header']['heap_end'] - 4)

    def test_methods_are_only_ever_found_in_a_code_object(self):
        """Class 477 is Code in ClassNumbers.Def, and it is where methods are.

        Five of the fourteen carry none at all -- the templates are objects
        only, and Snake's bulk is a sound and its pictures -- so a package
        without code is not a package that failed to decode.
        """
        with_code = set()
        for name, result in self.decoded.items():
            with self.subTest(package=name):
                code = [o for o in result['objects'] if o['class_name'] == 'Code']
                self.assertLessEqual(len(code), 1)
                for entry in result['objects']:
                    if 'code' in entry:
                        self.assertEqual(entry['class_name'], 'Code')
                if code and 'code' in code[0]:
                    with_code.add(name)
        self.assertIn('Counter', with_code)
        self.assertEqual(len(with_code), 9)

    def test_every_package_has_a_software_package_object(self):
        """Each example's Objects.Def opens by declaring one."""
        for name, result in self.decoded.items():
            with self.subTest(package=name):
                classes = [o['class_name'] for o in result['objects']]
                self.assertEqual(classes.count('SoftwarePackage'), 1)

    def test_the_header_s_id_really_is_the_highest_one_used(self):
        for name, result in self.decoded.items():
            with self.subTest(package=name):
                highest = max(o['id'] for o in result['objects'])
                self.assertEqual(highest, result['header']['highest_object_id'])

    def test_the_word_at_0x2c_is_one_below_that_and_is_not_a_count(self):
        """Recorded because it is tempting to read it as the object count."""
        for name, result in self.decoded.items():
            with self.subTest(package=name):
                word = int(result['header']['unnamed_words']['0x2c'], 16)
                self.assertEqual(word >> 16, 0x0100)     # the same everywhere
                low = word & 0xFFFF
                self.assertEqual(low, result['header']['highest_object_id'] - 1)
                if name != 'Circuits':
                    self.assertNotEqual(low, len(result['objects']))

    def test_no_call_site_is_reported_without_a_known_load(self):
        """A call whose selector was not written in must not be given one."""
        for name, result in self.decoded.items():
            for entry in result['objects']:
                for call in entry.get('code', {}).get('calls', []):
                    with self.subTest(package=name, offset=call['offset']):
                        if call['kind'] == 'unknown-vector':
                            self.assertNotIn('name', call)


@unittest.skipUnless(PACKAGES, 'cookbook packages are not in this checkout')
class WithoutTheSdkTests(unittest.TestCase):
    """The decode is of the package, so it must not need the SDK beside it."""

    def test_code_is_still_found_when_nothing_can_be_named(self):
        data = (COOKBOOK / 'Counter.pkg').read_bytes()
        result = inspect(data, load_numbers('/nonexistent'))
        code = [o for o in result['objects'] if 'code' in o]
        self.assertEqual(len(code), 1)
        self.assertIsNone(code[0]['class_name'])
        self.assertIn('CounterScene_UpdateDisplay',
                      [m['name'] for m in code[0]['code']['methods']])


@unittest.skipUnless(PACKAGES, 'cookbook packages are not in this checkout')
class CounterAgainstItsSourceTests(unittest.TestCase):
    """Counter is the example whose every method body is short enough to read.

    Counter.Def numbers its operations ResetVisitCount 1, UpdateDisplay 2 and
    the VisitCount attribute 3 with its setter at 4; Counter.c says which of
    them each method calls, and that UpdateDisplay reaches IntToString and
    ReplaceTextWithString. All of that has to come back out of the binary.
    """

    @classmethod
    def setUpClass(cls):
        package = COOKBOOK / 'Counter.pkg'
        cls.result = inspect(package.read_bytes(), load_numbers())
        cls.code = next(o for o in cls.result['objects']
                        if o['class_name'] == 'Code')

    def methods(self):
        return {m['name']: m for m in self.code['code']['methods']}

    def calls_in(self, method_name):
        method = self.methods()[method_name]
        return [c for c in self.code['code']['calls']
                if method['offset'] <= c['offset'] < method['offset'] + method['bytes']]

    def test_the_three_methods_in_counter_c_are_all_present(self):
        self.assertEqual(set(self.methods()) - {'main'},
                         {'CounterScene_AboutToShow',
                          'CounterScene_ResetVisitCount',
                          'CounterScene_UpdateDisplay'})

    def test_about_to_show_gets_increments_sets_and_calls_the_ancestor(self):
        calls = self.calls_in('CounterScene_AboutToShow')
        self.assertEqual([(c['kind'], c.get('name')) for c in calls],
                         [('dispatch', 'package operation 3'),
                          ('dispatch', 'package operation 4'),
                          ('dispatch', 'package operation 2'),
                          ('inherited', 'AboutToShow')])

    def test_reset_sets_the_count_and_updates(self):
        calls = self.calls_in('CounterScene_ResetVisitCount')
        self.assertEqual([c.get('name') for c in calls],
                         ['package operation 4', 'package operation 2'])

    def test_update_display_converts_the_number_and_replaces_the_text(self):
        calls = self.calls_in('CounterScene_UpdateDisplay')
        self.assertEqual([(c['kind'], c.get('name')) for c in calls],
                         [('dispatch', 'package operation 3'),
                          ('intrinsic', 'IntToString'),
                          ('dispatch', 'ReplaceTextWithString')])

    def test_update_display_names_the_text_field_indexical(self):
        """Counter.c passes iiTextField, which is pushed whole as a literal."""
        method = self.methods()['CounterScene_UpdateDisplay']
        pushed = [i for i in self.code['code']['indexicals']
                  if method['offset'] <= i['offset'] < method['offset'] + method['bytes']]
        self.assertEqual([i['value'] for i in pushed], ['87832001'])

    def test_the_package_defines_one_class_with_four_operations(self):
        """CounterScene, and ObjectMaker's record per operation number."""
        classes = [o for o in self.result['objects']
                   if (o['class_name'] or '').startswith('package class')]
        self.assertEqual([o['class_name'] for o in classes], ['package class 1'])
        operations = [o for o in self.result['objects']
                      if o['class_name'] == 'MagicOperation']
        self.assertEqual(len(operations), 4)

    def test_the_instances_counter_declares_are_all_in_the_package(self):
        """Every class named by an Instance line in Objects.Def."""
        declared = {'SoftwarePackage', 'ObjectList', 'Citation', 'Telename',
                    'OctetString', 'Identifier', 'TextField', 'Text',
                    'SimpleActionButton', 'NameCard', 'AddressCard'}
        present = {o['class_name'] for o in self.result['objects']}
        self.assertEqual(declared - present, set())


DEFFILES = SDK_INTERFACES / 'DefFiles'


@unittest.skipUnless(DEFFILES.is_dir(), 'the SDK definitions are not here')
class LayoutTests(unittest.TestCase):
    """Field layouts against Counter's SoftwarePackage, whose values are stated.

    Counter's Objects.Def writes out every field of its SoftwarePackage
    instance by name -- author, installList, citation, gotoActionSelector,
    which entries are set -- so the layout is checked against a statement of
    what the object holds rather than against the bytes it was derived from.
    """

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.data = (COOKBOOK / 'Counter.pkg').read_bytes()
        result = inspect(cls.data, load_numbers(), cls.defs)
        cls.package = next(o for o in result['objects']
                           if o['class_name'] == 'SoftwarePackage')
        cls.by_name = {f['name']: f for f in cls.package['contents']['fields']}

    def test_the_ancestry_reaches_object(self):
        chain = self.defs.ancestry('SoftwarePackage')
        self.assertEqual(chain[0], 'Object')
        self.assertEqual(chain[-1], 'SoftwarePackage')
        self.assertIn('PackageRootList', chain)

    def test_a_missing_class_refuses_rather_than_approximates(self):
        with self.assertRaises(LayoutError):
            self.defs.layout('NoSuchClassExists')

    def test_the_fields_hold_what_objects_def_says(self):
        expected = {
            'length': 32,               # 32 root-list entries
            'installFlags': 'nil',
            'installParameters': 'nil',
            'installTargets': 'nil',
            'autoActivate': True,
            'persistentShadowSize': 0,
            'persistentChangesSize': 0,
            'transientSize': 0,
            'gotoActionSelector': 3,    # Objects.Def: gotoActionSelector: 3.w
            'hidden': False,
            'dontSaveData': False,
            'copyOnActivate': False,
        }
        for name, value in expected.items():
            with self.subTest(field=name):
                self.assertEqual(self.by_name[name]['value'], value)

    def test_author_and_publisher_are_the_same_address_card(self):
        """Objects.Def gives both as (AddressCard 101)."""
        self.assertEqual(self.by_name['author']['value'],
                         self.by_name['publisher']['value'])
        self.assertTrue(self.by_name['author']['value'].startswith('object '))

    def test_the_sixteen_reserved_booleans_share_two_bytes(self):
        booleans = [f for f in self.package['contents']['fields']
                    if f['name'].startswith('systemPackageReserved')]
        self.assertEqual(len(booleans), 11)
        self.assertEqual({f['offset'] for f in booleans},
                         {self.by_name['hidden']['offset'],
                          self.by_name['hidden']['offset'] + 1})
        self.assertTrue(all(f['value'] is False for f in booleans))

    def test_the_payload_is_exactly_the_fields_plus_the_entries(self):
        contents = self.package['contents']
        extra = contents['extra']
        self.assertEqual(extra['trailing_bytes'], 0)
        self.assertEqual(contents['fixed_bytes'] + extra['count'] * extra['stride'],
                         self.package['payload']['length'])

    def test_the_entries_objects_def_names_are_the_ones_that_are_set(self):
        """entry6, entry9, entry10 are lists and entry13 is iHallway."""
        elements = self.package['contents']['extra']['elements']
        set_at = {i for i, e in enumerate(elements, 1) if e != 'nil'}
        self.assertLessEqual({6, 9, 10, 13}, set_at)
        self.assertTrue(elements[12].startswith('indexical'))   # entry13
        for entry in (6, 9, 10):
            self.assertTrue(elements[entry - 1].startswith('object '))

    def test_type_sizes_come_from_the_sdk_not_from_assumption(self):
        """Dot and PixelDot are C structs in the SDK's own headers."""
        self.assertEqual(self.defs.type_sizes['Dot'], 8)
        self.assertEqual(self.defs.type_sizes['PixelDot'], 4)
        self.assertEqual(self.defs.size_of('UnsignedShort'), 2)
        self.assertEqual(self.defs.size_of('AddressCard'), 4)   # a reference
        with self.assertRaises(LayoutError):
            self.defs.size_of('NotAnyKnownType')

    def test_every_class_in_the_corpus_either_lays_out_or_says_why(self):
        resolved = 0
        for name in self.defs.classes:
            try:
                self.defs.layout(name)
                resolved += 1
            except LayoutError:
                pass
        self.assertGreater(resolved, 900)

    def test_text_objects_keep_their_bytes_rather_than_being_read_as_a_list(self):
        result = inspect(self.data, load_numbers(), self.defs)
        texts = [o for o in result['objects'] if o['class_name'] == 'Text'
                 and o['contents']['extra']]
        printable = ' '.join(t['contents']['extra'].get('printable', '')
                             for t in texts)
        self.assertIn('About Counter', printable)
        for text in texts:
            self.assertIsNone(text['contents']['extra']['elements'])


@unittest.skipUnless(DEFFILES.is_dir(), 'the SDK definitions are not here')
class ClassRecordTests(unittest.TestCase):
    """What a package says about the classes it defines.

    Counter declares one class: `Define Class CounterScene; inherits from
    Scene;` with two operations, one attribute with a generated getter and
    setter, and an override of AboutToShow. The record has to say exactly
    that.
    """

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        cls.result = inspect((COOKBOOK / 'Counter.pkg').read_bytes(),
                             cls.tables, cls.defs)
        cls.record = next(o['class_record'] for o in cls.result['objects']
                          if 'class_record' in o)

    def test_it_is_counterscene_and_it_inherits_from_scene(self):
        self.assertEqual(self.record['number'], 0x8001)
        self.assertEqual([s['class_name'] for s in self.record['inherits_from']],
                         ['Scene'])

    def test_the_five_methods_are_the_ones_counter_declares(self):
        methods = self.record['methods']
        self.assertEqual([m['name'] for m in methods],
                         ['AboutToShow', 'package operation 1',
                          'package operation 2', 'package operation 3',
                          'package operation 4'])
        # The two operations have code; the attribute's pair is generated.
        self.assertTrue(all('code_offset' in m for m in methods[:3]))
        self.assertTrue(all('accessor' in m for m in methods[3:]))

    def test_the_interfaces_are_counted_and_begin_at_object(self):
        fields = {f['name']: f for f in next(
            o['contents']['fields'] for o in self.result['objects']
            if 'class_record' in o)}
        self.assertEqual(len(self.record['interfaces']),
                         fields['interfaceCount']['raw'])
        self.assertEqual(self.record['interfaces'][0]['class_name'], 'Object')
        self.assertIn('Scene', [i['class_name'] for i in self.record['interfaces']])

    def test_the_method_table_agrees_with_the_symbols_in_the_code(self):
        """Two decodes that share nothing have to land in the same places.

        The table says where each method starts; the MacsBug symbols say what
        the method at each place is called. Counter's three real methods have
        to match both ways round, name for name.
        """
        code = next(o for o in self.result['objects']
                    if o['class_name'] == 'Code')
        start = code['payload']['offset']
        bodies = {m['offset']: m['name'] for m in code['code']['methods']}
        found = {}
        for method in self.record['methods']:
            if 'code_offset' not in method:
                continue
            found[method['name']] = bodies.get(start + method['code_offset'])
        self.assertEqual(found, {
            'AboutToShow': 'CounterScene_AboutToShow',
            'package operation 1': 'CounterScene_ResetVisitCount',
            'package operation 2': 'CounterScene_UpdateDisplay',
        })


@unittest.skipUnless(PACKAGES and DEFFILES.is_dir(), 'corpus or SDK missing')
class ClassRecordCorpusTests(unittest.TestCase):
    """The same decode over every class record in the fourteen examples."""

    @classmethod
    def setUpClass(cls):
        defs = Definitions(DEFFILES, SDK_INTERFACES)
        tables = load_numbers()
        cls.decoded = {p.stem: inspect(p.read_bytes(), tables, defs)
                       for p in PACKAGES}

    def records(self):
        for name, result in self.decoded.items():
            for entry in result['objects']:
                if 'class_record' in entry:
                    yield name, result, entry

    def test_every_class_record_names_its_methods_and_interfaces(self):
        seen = 0
        for name, _, entry in self.records():
            seen += 1
            record = entry['class_record']
            with self.subTest(package=name, number=record['number']):
                fields = {f['name']: f for f in entry['contents']['fields']}
                self.assertEqual(len(record['methods']),
                                 fields['methodCount']['raw'])
                for method in record['methods']:
                    self.assertTrue('code_offset' in method or 'accessor' in method)
        self.assertGreater(seen, 40)

    def test_the_method_table_mostly_lands_on_symbols_and_never_outside(self):
        """Where the two disagree the table is right and the scan is a guess.

        The symbols are found by pattern and the table is stated outright, so
        the table is what a builder would have to reproduce. The check here
        is that the offsets stay inside the code they name, and that the two
        agree in the large majority.
        """
        agree = total = 0
        for name, result, entry in self.records():
            code = {o['id']: o for o in result['objects']
                    if o['class_name'] == 'Code'}
            for method in entry['class_record']['methods']:
                if 'code_offset' not in method:
                    continue
                holder = code.get(method['code_object'])
                self.assertIsNotNone(holder, f'{name}: method names a non-Code object')
                with self.subTest(package=name, method=method['name']):
                    self.assertLess(method['code_offset'],
                                    holder['payload']['length'])
                bodies = {m['offset'] for m in holder.get('code', {}).get('methods', [])}
                total += 1
                agree += (holder['payload']['offset'] + method['code_offset']) in bodies
        self.assertGreater(agree / total, 0.9)

    def test_the_field_lists_chain_through_one_table_of_names(self):
        """Each class's fields are named from where the last class's ended.

        A FieldList is a StringDictionary: `length` fields whose names start
        at `firstStringEntry`. Taken in order within a package those run
        1, then 1+length, and so on with no gap and no overlap -- which is
        what says they index one table shared by the whole package rather
        than each carrying its own.
        """
        checked = 0
        for name, result in self.decoded.items():
            lists = []
            for entry in result['objects']:
                if entry['class_name'] != 'FieldList':
                    continue
                fields = {f['name']: f.get('raw')
                          for f in entry['contents']['fields']}
                lists.append((fields.get('firstStringEntry'),
                              fields.get('length')))
            expected = 1
            for first, length in sorted(lists):
                with self.subTest(package=name, first=first):
                    self.assertEqual(first, expected)
                expected = first + length
                checked += 1
        self.assertEqual(checked, 25)

    def test_every_field_list_names_its_fields_from_the_shared_table(self):
        for name, result in self.decoded.items():
            for entry in result['objects']:
                if entry['class_name'] != 'FieldList':
                    continue
                with self.subTest(package=name):
                    described = entry['fields_described']
                    self.assertTrue(described)
                    self.assertTrue(all(f['name'] for f in described))
                    self.assertTrue(all(f['type'] for f in described))

    def test_the_string_table_holds_exactly_the_fields_the_lists_count(self):
        """The chain's total and the table's length are two separate counts."""
        for name, result in self.decoded.items():
            by_id = {o['id']: o for o in result['objects']}
            lists = [o for o in result['objects'] if o['class_name'] == 'FieldList']
            if not lists:
                continue
            totals = sum(next(f['raw'] for f in o['contents']['fields']
                              if f['name'] == 'length') for o in lists)
            holder = by_id[next(f['raw'] for f in lists[0]['contents']['fields']
                                if f['name'] == 'strings')]
            with self.subTest(package=name):
                self.assertEqual(holder['class_name'], 'StringList')
                self.assertEqual(len(read_string_table(
                    result_bytes(name), holder)), totals)

    def test_the_direct_dispatch_list_is_what_the_package_overrides(self):
        """Exactly the system operations the package's classes override.

        ObjectMaker names its dispatchers -- Method, Direct, Inherited,
        Delegate, Patch, Extended -- and this is the list the direct one
        works from: an override has to be reachable without going back
        through the dispatch that found it.
        """
        import struct
        from inspect_package import find_cluster
        for name, result in self.decoded.items():
            data, _ = find_cluster(result_bytes(name))
            overridden = {int(m['selector'], 16) for entry in result['objects']
                          if 'class_record' in entry
                          for m in entry['class_record']['methods']
                          if not int(m['selector'], 16) & 0x80000000}
            listed = set()
            for entry in result['objects']:
                if entry['class_name'] != 'DirectDispatchList':
                    continue
                at, size = entry['payload']['offset'], entry['payload']['length']
                listed |= {struct.unpack_from('>I', data, at + i)[0]
                           for i in range(0, size, 4)}
            with self.subTest(package=name):
                self.assertEqual(listed, overridden)

    def test_the_class_and_operation_lists_hold_the_package_s_own_records(self):
        """What Context.Def says SetUpContextRuntime is handed.

        Both are tables whose first word is an entry count, and both hold
        references only to the package's own records -- a ClassList never
        points at anything but a Class, an OperationList at anything but a
        MagicOperation. Their shapes differ: a ClassList is four header words
        and four words an entry, an OperationList two and two. The arithmetic
        closing on every package is what says those sizes are right.

        They are sparse. BarChart's operation table has 66 entries holding
        eight references, so an entry count is not a count of operations.
        """
        import struct
        from inspect_package import find_cluster
        shape = {'ClassList': (4, 4), 'OperationList': (2, 2)}
        for name, result in self.decoded.items():
            data, _ = find_cluster(result_bytes(name))
            by_id = {o['id']: o['class_name'] for o in result['objects']}
            for listname, holds in (('ClassList', 'Class'),
                                    ('OperationList', 'MagicOperation')):
                header, per_entry = shape[listname]
                for entry in result['objects']:
                    if entry['class_name'] != listname:
                        continue
                    at, size = entry['payload']['offset'], entry['payload']['length']
                    words = [struct.unpack_from('>I', data, at + i)[0]
                             for i in range(0, size, 4)]
                    with self.subTest(package=name, list=listname):
                        self.assertEqual(len(words), header + per_entry * words[0])
                        for word in words:
                            if word >> 24 == 0xB0:
                                self.assertEqual(by_id.get(word & 0xFFFFFF), holds)

    def test_the_tag_s_high_bits_are_the_record_s_padding(self):
        """ObjectMaker computes them as (4 - (n & 3)) & 3 over the real length.

        A string table says how long its own content is -- `dataOffset` plus
        `dataSize`, from four bytes into the payload -- so the record length
        has to be twelve for the header, plus that, plus the padding. It is,
        for every string table in the corpus, which is what makes these bits
        the padding count rather than something that merely ranges 0 to 3.
        """
        checked = 0
        for name, result in self.decoded.items():
            for entry in result['objects']:
                if entry['class_name'] != 'StringList':
                    continue
                fields = {f['name']: f.get('raw')
                          for f in entry['contents']['fields']}
                content = 4 + fields['dataOffset'] + fields['dataSize']
                with self.subTest(package=name, id=entry['id']):
                    self.assertEqual(12 + content + entry['padding_bytes'],
                                     entry['length'])
                checked += 1
        self.assertGreater(checked, 20)

    def test_the_rest_of_the_tag_takes_only_the_two_values_it_writes(self):
        """`| 0x80` always, a bit 3 the writer always sets here, and bit 1."""
        seen = set()
        for result in self.decoded.values():
            for entry in result['objects']:
                seen.add(entry['tag'] & 0xFF)
        self.assertEqual(seen, {0x88, 0x8A})

    def test_a_class_inheriting_from_the_package_s_own_is_named_as_such(self):
        supers = [s['class_name'] for _, _, e in self.records()
                  for s in e['class_record']['inherits_from']]
        self.assertTrue(all(s for s in supers))       # none left blank
        self.assertTrue(any(s.startswith('package class') for s in supers))
        # Each entry is sixteen bytes, so a class with several implementation
        # parents lists several real classes rather than one and some zeroes.
        several = [e for _, _, e in self.records()
                   if len(e['class_record']['inherits_from']) > 1]
        self.assertTrue(several)
        for entry in several:
            for s in entry['class_record']['inherits_from']:
                self.assertNotEqual(s['class_name'], 'none')


SHIPPING = [Path(__file__).resolve().parents[2] / 'software/68k' / name
            for name in ('BastilleR.cap', '3PrestoPPP.cap')]
SHIPPING = [p for p in SHIPPING if p.exists()]

SOURCES = Path(__file__).resolve().parents[2] / \
    'software/68k/extracted/cookbook/Cookbook Examples'


@unittest.skipUnless(SHIPPING and DEFFILES.is_dir(), 'shipping packages missing')
class ShippingPackageTests(unittest.TestCase):
    """Software nobody in this corpus wrote, as a check on all of the above.

    Everything else here is fitted to fourteen examples built by one author in
    one run of one toolchain. These two are real third-party packages in the
    `.cap` distribution envelope, and they are what caught the object chain
    being read as though it always ended in a zero word.
    """

    @classmethod
    def setUpClass(cls):
        defs = Definitions(DEFFILES, SDK_INTERFACES)
        tables = load_numbers()
        cls.decoded = {p.stem: inspect(p.read_bytes(), tables, defs)
                       for p in SHIPPING}

    def test_both_decode_out_of_their_envelopes(self):
        for name, result in self.decoded.items():
            with self.subTest(package=name):
                self.assertGreater(result['found_at'], 0)
                self.assertGreater(len(result['objects']), 20)

    def test_the_instance_layout_holds_on_software_it_was_not_derived_from(self):
        seen = 0
        for name, result in self.decoded.items():
            for entry in result['objects']:
                record = entry.get('class_record')
                if not record:
                    continue
                seen += 1
                with self.subTest(package=name, number=record['number']):
                    self.assertNotIn('inherited_bytes_note', record)
                    self.assertEqual(record['inherited_bytes'] % 4, 0)
                    self.assertGreaterEqual(record['inherited_bytes'], 0)
        self.assertGreater(seen, 50)


def declared_fields(package):
    """Every field an example declares, in source order, from its own .Def."""
    import re
    from classdefs import read, strip_comments
    out = []
    for path in sorted((SOURCES / package).glob('*.Def')) + \
            sorted((SOURCES / package).glob('*/*.Def')):
        if path.name == 'Objects.Def':
            continue
        text = strip_comments(read(path))
        for match in re.finditer(
                r'^\s*field\s+(\w+)\s*:\s*([^;,]+?)\s*(?:,([^;]*))?;', text, re.M):
            quals = tuple(q.strip() for q in (match.group(3) or '').split(',')
                          if q.strip())
            out.append((match.group(1), match.group(2).strip(), quals))
    return out


@unittest.skipUnless(PACKAGES and SOURCES.is_dir() and DEFFILES.is_dir(),
                     'corpus, sources or SDK missing')
class FieldsAgainstTheirSourcesTests(unittest.TestCase):
    """The recovered field declarations against the ones that were compiled.

    This is the whole point of the cookbook being source and binary together:
    the names, the types and the qualifiers can be read out of the package and
    compared with what its author wrote, rather than with each other.
    """

    @classmethod
    def setUpClass(cls):
        defs = Definitions(DEFFILES, SDK_INTERFACES)
        tables = load_numbers()
        cls.decoded = {p.stem: inspect(p.read_bytes(), tables, defs)
                       for p in PACKAGES}

    def recovered(self, package):
        fields = []
        for entry in self.decoded[package]['objects']:
            record = entry.get('class_record')
            if record:
                fields += record.get('fields', [])
        return fields

    def test_the_names_and_types_match_what_was_declared(self):
        checked = 0
        equivalent = {'Object': 'reference', 'ObjectList': 'reference'}
        for package in ('Counter', 'BarChart', 'Hanoi', 'Metric', 'Positioning'):
            declared = declared_fields(package)
            recovered = {f['name']: f for f in self.recovered(package)}
            self.assertTrue(declared, f'{package} declares no fields')
            for name, type_name, quals in declared:
                with self.subTest(package=package, field=name):
                    self.assertIn(name, recovered)
                    self.assertEqual(recovered[name]['type'],
                                     equivalent.get(type_name, type_name))
                    if 'noCopy' in quals:
                        self.assertIn('noCopy', recovered[name]['flags'])
                    checked += 1
        self.assertGreater(checked, 12)

    def test_a_reference_field_points_at_the_class_it_was_declared_as(self):
        """`ringList: ObjectList` has to come back naming ObjectList."""
        recovered = {f['name']: f for f in self.recovered('Hanoi')}
        self.assertEqual(recovered['ringList']['class_name'], 'ObjectList')
        self.assertEqual(recovered['moveList']['class_name'], 'Object')

    def test_what_a_class_adds_always_leaves_whole_words_inherited(self):
        """The check on the instance layout, over every class record.

        A class's fields follow its superclass's instances, so what is left
        after taking them off `instanceSize` is the superclass's own size.
        That has to be a non-negative whole number of words, and it is, for
        all fifty.
        """
        seen = 0
        for package, result in self.decoded.items():
            for entry in result['objects']:
                record = entry.get('class_record')
                if not record:
                    continue
                seen += 1
                with self.subTest(package=package, number=record['number']):
                    self.assertNotIn('inherited_bytes_note', record)
                    self.assertGreaterEqual(record['inherited_bytes'], 0)
                    self.assertEqual(record['inherited_bytes'] % 4, 0)
        self.assertEqual(seen, 50)

    def test_two_packages_agree_on_what_a_system_class_costs(self):
        """Scene comes out at 84 from classes that know nothing of each other."""
        derived = {}
        for package, result in self.decoded.items():
            for entry in result['objects']:
                record = entry.get('class_record')
                if not record or not record['inherits_from']:
                    continue
                super_class = record['inherits_from'][0]
                if super_class['class_number'] & 0x8000:
                    continue
                derived.setdefault(super_class['class_name'], set()).add(
                    record['inherited_bytes'])
        self.assertEqual(derived['Scene'], {84})
        self.assertEqual(derived['Object'], {0})        # the root has no fields
        inconsistent = {k for k, v in derived.items() if len(v) > 1}
        # Stamp is the one that does not fit, and is left on the record.
        self.assertEqual(inconsistent, {'Stamp'})

    def test_hanoi_s_fields_sit_where_its_declarations_put_them(self):
        fields = {f['name']: f for f in self.recovered('Hanoi')}
        # Ring: three shorts end to end past MyStamp.
        self.assertEqual([fields[n]['offset'] for n in
                          ('ringNumber', 'currentPole', 'currentPosition')],
                         [0, 2, 4])
        # Pole: a short, then a reference aligned to its own width.
        self.assertEqual(fields['poleNumber']['offset'], 0)
        self.assertEqual(fields['ringList']['offset'], 4)

    def test_no_field_is_left_without_a_type_anywhere_in_the_corpus(self):
        for package in self.decoded:
            for field in self.recovered(package):
                with self.subTest(package=package, field=field['name']):
                    self.assertIsNotNone(field['type'], field['raw'])
                    self.assertNotIn('unknown_flags', field)


@unittest.skipUnless(PACKAGES and DEFFILES.is_dir(), 'corpus or SDK missing')
class RoundTripTests(unittest.TestCase):
    """Write back what was read, and diff it against the original.

    Reading a format and understanding it are different claims. This is the
    second one: everything the decode asserts about a byte has to reproduce
    that byte. A field a word out, a Boolean packed from the wrong end, a
    reference written without its tag -- none of it survives this, and none
    of it is visible from reading alone.
    """

    @classmethod
    def setUpClass(cls):
        from roundtrip import check
        cls.check = staticmethod(check)
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        cls.files = PACKAGES + SHIPPING

    def test_every_container_rebuilds_byte_for_byte(self):
        """The walk has to account for every byte between header and trailer."""
        for path in self.files:
            with self.subTest(package=path.stem):
                report = self.check(path, self.tables, self.defs)
                self.assertTrue(report['container_identical'])

    def test_no_decoded_field_writes_back_a_different_byte(self):
        for path in self.files:
            with self.subTest(package=path.stem):
                report = self.check(path, self.tables, self.defs)
                self.assertEqual(report['objects_mismatched'], [])

    def test_a_useful_share_of_the_heap_is_actually_accounted_for(self):
        """Counter is mostly structure; Snake is mostly a sound and pictures."""
        by_name = {p.stem: self.check(p, self.tables, self.defs)
                   for p in self.files}
        share = lambda r: r['payload_covered'] / r['payload_bytes']
        self.assertGreater(share(by_name['Counter']), 0.6)
        self.assertGreater(share(by_name['Template']), 0.8)
        # What is not accounted for is content, not structure.
        biggest = max(by_name['Snake']['unaccounted_by_class'].items(),
                      key=lambda kv: kv[1])[0]
        self.assertIn(biggest, ('Sound', 'Image', 'Code'))


@unittest.skipUnless(DEFFILES.is_dir() and PACKAGES, 'corpus or SDK missing')
class SystemClassSizeTests(unittest.TestCase):
    """The two routes to a system class's instance size have to agree.

    One computes it from the SDK's class definitions; the other subtracts a
    package class's own fields from the `instanceSize` its record carries.
    They share nothing, so where they agree the layout engine is right about
    a class no package in this corpus defines.
    """

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        tables = load_numbers()
        cls.derived = {}
        for path in PACKAGES + SHIPPING:
            result = inspect(path.read_bytes(), tables, cls.defs)
            for entry in result['objects']:
                record = entry.get('class_record')
                if not record or not record['inherits_from']:
                    continue
                super_class = record['inherits_from'][0]
                if super_class['class_number'] & 0x8000 or not super_class['class_name']:
                    continue
                cls.derived.setdefault(super_class['class_name'], set()).add(
                    record['inherited_bytes'])

    def test_the_definitions_and_the_binaries_agree_on_most_classes(self):
        agree = disagree = []
        agree, disagree = [], []
        for name, sizes in self.derived.items():
            if len(sizes) != 1:
                continue                      # the anomalies, checked below
            try:
                computed = self.defs.layout(name)['fixed_bytes']
            except LayoutError:
                continue
            (agree if computed == sizes.pop() else disagree).append(name)
        self.assertIn('Scene', agree)          # 84 both ways
        self.assertIn('Object', agree)         # 0 both ways, the root
        self.assertGreater(len(agree), 3 * len(disagree))

    def test_an_instance_is_all_of_its_implementation_parents(self):
        """A class's instance is every parent's instance, plus its own fields.

        Counting only the first parent left Stamp, PDUServer and Line looking
        anomalous. They are not: those classes have several implementation
        parents, and each contributes its whole instance. Circuits' Resistor
        declares no fields at all and has 76-byte instances because Stamp is
        60 and the three package classes beside it are 8, 4 and 4.
        """
        from classdefs import package_field_offsets
        tables = load_numbers()
        derived = {}
        for path in PACKAGES + SHIPPING:
            result = inspect(path.read_bytes(), tables, self.defs)
            records = {}
            for entry in result['objects']:
                record = entry.get('class_record')
                if record:
                    records[record['number']] = record
            for record in records.values():
                supers = record['inherits_from']
                if not supers or supers[0]['class_number'] & 0x8000:
                    continue
                if not supers[0].get('class_name'):
                    continue
                others, known = 0, True
                for parent in supers[1:]:
                    other = records.get(parent['class_number'])
                    if other is None:
                        known = False
                        break
                    others += other['instance_size']
                if not known:
                    continue
                _, own = package_field_offsets(record.get('fields') or [])
                derived.setdefault(supers[0]['class_name'], set()).add(
                    record['instance_size'] - own - others)
        inconsistent = {k for k, v in derived.items() if len(v) > 1}
        self.assertEqual(inconsistent, set())
        self.assertEqual(derived['Scene'], {84})
        self.assertEqual(derived['Object'], {0})
        self.assertEqual(derived['Stamp'], {60})     # what its .Def computes
        self.assertEqual(derived['Line'], {72})      # likewise


@unittest.skipUnless(PACKAGES and DEFFILES.is_dir(), 'corpus or SDK missing')
class WriterTests(unittest.TestCase):
    """Emit a package and require the bytes back.

    The writer computes everything -- record lengths and their padding, the
    heap end, the id table and the free list threaded through it, the header
    -- from the objects it is handed. Feeding it a package that was just read
    and getting the same file back is what says those computations are the
    ones ObjectMaker made, rather than a plausible substitute.
    """

    @classmethod
    def setUpClass(cls):
        from write_package import build, from_inspection
        cls.build = staticmethod(build)
        cls.from_inspection = staticmethod(from_inspection)
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()

    def rebuild(self, path):
        from inspect_package import find_cluster
        raw = path.read_bytes()
        data, _ = find_cluster(raw)
        result = inspect(raw, self.tables, self.defs)
        return self.build(**self.from_inspection(data, result)), data

    def test_every_package_comes_back_byte_for_byte(self):
        for path in PACKAGES + SHIPPING:
            with self.subTest(package=path.stem):
                emitted, original = self.rebuild(path)
                self.assertEqual(emitted, original)

    def test_a_longer_object_moves_everything_after_it(self):
        """The point of a writer: change a payload and it still comes out right.

        Counter's help text is a plain NUL-terminated string. Making it longer
        changes that record's length, every offset after it, the heap end, the
        id table and the total -- and the result has to read back as the same
        package with one different string.
        """
        from inspect_package import find_cluster
        path = COOKBOOK / 'Counter.pkg'
        raw = path.read_bytes()
        data, _ = find_cluster(raw)
        spec = self.from_inspection(data, inspect(raw, self.tables, self.defs))
        text = (b'a much longer help text than the one that was there '
                b'before, long enough that the record has to grow\x00')
        for entry in spec['objects']:
            if entry.id == 18:
                entry.payload = text
        emitted = self.build(**spec)
        self.assertGreater(len(emitted), len(data))

        again = inspect(emitted, self.tables, self.defs)
        self.assertEqual(len(again['objects']),
                         len(inspect(raw, self.tables, self.defs)['objects']))
        changed = next(o for o in again['objects'] if o['id'] == 18)
        body = emitted[changed['payload']['offset']:
                       changed['payload']['offset'] + changed['payload']['length']]
        self.assertTrue(body.startswith(b'a much longer help text'))
        # Everything after it moved, and the table that finds objects by id
        # has to have moved with it.
        package = next(o for o in again['objects']
                       if o['class_name'] == 'SoftwarePackage')
        self.assertTrue(package['contents']['fields'])

    def test_payloads_can_be_built_from_values_rather_than_copied(self):
        """Constructing a record, not reproducing one.

        Every object whose class the definitions describe is rebuilt from the
        field values that were read out of it -- starting from zeros, so a
        byte the layout does not place stays zero -- and has to come out the
        same. Where that succeeds the payload is put back in the package, and
        all sixteen still emit identically.

        The classes it cannot do are the ones whose variable part is content
        rather than structure: Text, Image, Sound, Code, and the records this
        reads by other means. A writer hands those their bytes, which is what
        they are.
        """
        from classdefs import encode_elements, encode_fields
        from inspect_package import find_cluster
        rebuilt = carried = 0
        for path in PACKAGES + SHIPPING:
            raw = path.read_bytes()
            data, _ = find_cluster(raw)
            result = inspect(raw, self.tables, self.defs)
            spec = self.from_inspection(data, result)
            by_id = {o['id']: o for o in result['objects']}
            for entry in spec['objects']:
                source = by_id[entry.id]
                contents = source.get('contents')
                if not contents or 'unresolved' in contents:
                    carried += 1
                    continue
                layout = self.defs.layout(source['class_name'])
                size = source['payload']['length']
                values = {f['name']: (f['value'] if f.get('bit') is not None
                                      else f.get('raw'))
                          for f in contents['fields'] if not f.get('absent')}
                extra = contents.get('extra') or {}
                tail = (encode_elements(extra['raw_elements'], extra['stride'])
                        if extra.get('raw_elements') else b'')
                candidate = encode_fields(layout, values, tail, length=size)
                at = source['payload']['offset']
                if candidate == data[at:at + size]:
                    entry.payload = candidate[:size - source['padding_bytes']]
                    rebuilt += 1
                else:
                    carried += 1
            with self.subTest(package=path.stem):
                self.assertEqual(self.build(**spec), data)
        self.assertGreater(rebuilt, 1000)
        self.assertGreater(rebuilt, carried)

    def test_every_understood_record_type_can_be_written(self):
        """Generate the records, not just the container, and diff the files.

        A class record, a field list and a string table are each rebuilt from
        what they hold -- the class's supers, methods and interfaces; the
        field descriptors and where their names start; the names themselves --
        and ordinary objects from their field values. Only the classes whose
        payload is content rather than structure are carried across as bytes.

        All sixteen packages still come out identical, which is what says the
        three record formats are written the way ObjectMaker writes them.
        """
        import struct
        from classdefs import (encode_elements, encode_fields,
                               read_string_table)
        from inspect_package import CLASS_TABLE_BASE, find_cluster
        from write_package import (encode_class_record, encode_field_list,
                                   encode_string_table)
        generated = 0
        for path in PACKAGES + SHIPPING:
            raw = path.read_bytes()
            data, _ = find_cluster(raw)
            result = inspect(raw, self.tables, self.defs)
            spec = self.from_inspection(data, result)
            by_id = {o['id']: o for o in result['objects']}
            for entry in spec['objects']:
                source = by_id[entry.id]
                contents = source.get('contents')
                if not contents or 'unresolved' in contents:
                    continue
                at = source['payload']['offset']
                size = source['payload']['length'] - source['padding_bytes']
                original = data[at:at + size]
                fields = {f['name']: f.get('raw') for f in contents['fields']
                          if not f.get('absent')}
                base = at + CLASS_TABLE_BASE
                if source['class_name'] == 'StringList':
                    candidate = encode_string_table(
                        self.defs, read_string_table(data, source),
                        fields['extents'])
                elif source['class_name'] == 'FieldList':
                    elements = (contents['extra'] or {}).get('raw_elements') or []
                    candidate = encode_field_list(
                        self.defs, fields['strings'],
                        fields['firstStringEntry'], elements)
                elif 'class_record' in source:
                    supers = [struct.unpack_from(
                        '>I', data, base + fields['implSuperOffset'] + i * 16)[0]
                        for i in range(fields['implSuperCount'])]
                    methods = [struct.unpack_from(
                        '>IIII', data, base + fields['methodOffset'] + i * 16)
                        for i in range(fields['methodCount'])]
                    after = base + fields['methodOffset'] + 16 * fields['methodCount']
                    interfaces = [struct.unpack_from('>I', data, after + i * 4)[0]
                                  for i in range(fields['interfaceCount'])]
                    candidate = encode_class_record(self.defs, fields, supers,
                                                    methods, interfaces)
                else:
                    layout = self.defs.layout(source['class_name'])
                    values = {f['name']: (f['value'] if f.get('bit') is not None
                                          else f.get('raw'))
                              for f in contents['fields'] if not f.get('absent')}
                    extra = contents.get('extra') or {}
                    tail = (encode_elements(extra['raw_elements'], extra['stride'])
                            if extra.get('raw_elements') else b'')
                    whole = encode_fields(layout, values, tail,
                                          length=source['payload']['length'])
                    candidate = (whole[:size] if whole ==
                                 data[at:at + source['payload']['length']] else None)
                if candidate is not None and candidate == original:
                    entry.payload = candidate
                    generated += 1
            with self.subTest(package=path.stem):
                self.assertEqual(self.build(**spec), data)
        self.assertGreater(generated, 1300)

    def test_a_package_can_be_built_from_a_description(self):
        """No parse, no copy: a list of what each object is and holds.

        Each entry names a class and gives its field values, a list's
        elements, or the bytes for a record that is content. `build_from_spec`
        turns that into a package, and for all sixteen it is the same package
        -- 1179 of the objects described by class and values rather than
        handed over as bytes.

        This is the path a package built from definitions would take. What is
        missing is not the emitting but the describing: something has to
        decide what objects a package needs, which is what ObjectMaker's
        `.Def` files say.
        """
        from classdefs import encode_elements, encode_fields
        from inspect_package import find_cluster
        from write_package import build_from_spec
        described = 0
        for path in PACKAGES + SHIPPING:
            raw = path.read_bytes()
            data, _ = find_cluster(raw)
            result = inspect(raw, self.tables, self.defs)
            reference = self.from_inspection(data, result)
            spec = []
            for source in result['objects']:
                at = source['payload']['offset']
                size = source['payload']['length'] - source['padding_bytes']
                entry = {'id': source['id'], 'class': source['class_name'],
                         'class_number': source['class_number'],
                         'flags': source['flags'],
                         'tag_low': source['tag'] & 0xFF}
                contents = source.get('contents')
                placed = False
                if contents and 'unresolved' not in contents \
                        and 'class_record' not in source:
                    layout = self.defs.layout(source['class_name'])
                    values = {f['name']: (f['value'] if f.get('bit') is not None
                                          else f.get('raw'))
                              for f in contents['fields'] if not f.get('absent')}
                    extra = contents.get('extra') or {}
                    elements = extra.get('raw_elements')
                    stride = extra.get('stride', 4)
                    tail = encode_elements(elements, stride) if elements else b''
                    if encode_fields(layout, values, tail, length=size) == \
                            data[at:at + size]:
                        entry['values'] = values
                        entry['length'] = size
                        if elements:
                            entry['elements'] = elements
                            entry['stride'] = stride
                        described += 1
                        placed = True
                if not placed:
                    entry['payload'] = data[at:at + size]
                spec.append(entry)
            with self.subTest(package=path.stem):
                self.assertEqual(
                    build_from_spec(self.defs, self.tables, spec,
                                    unnamed_words=reference['unnamed_words'],
                                    terminator=reference['terminator'],
                                    free_ids=reference['free_ids']),
                    data)
        self.assertGreater(described, 1100)

    def test_a_class_record_is_laid_out_where_its_own_fields_say(self):
        from write_package import encode_class_record
        payload = encode_class_record(
            self.defs, {'number': 0x8001, 'instanceSize': 88},
            supers=[377], methods=[(0x64D, 0x18, 0, 0xB000001C)],
            interfaces=[1, 50])
        layout = self.defs.layout('Class')
        # Sixteen bytes a superclass, then the methods, then the interfaces,
        # and the offsets counted from four bytes into the payload.
        self.assertEqual(len(payload),
                         layout['fixed_bytes'] + 16 + 16 + 8)
        again = inspect(self.build(
            objects=[self.make(0x8001, payload)],
            constant_words=[0x000FFFFF, 0x01C00003, 0x00070000]),
            self.tables, self.defs)
        record = again['objects'][0]['class_record']
        self.assertEqual(record['number'], 0x8001)
        self.assertEqual([s['class_name'] for s in record['inherits_from']],
                         ['Scene'])
        self.assertEqual(record['methods'][0]['name'], 'AboutToShow')
        self.assertEqual([i['class_name'] for i in record['interfaces']],
                         ['Object', 'Viewable'])

    def make(self, number, payload):
        from write_package import Object
        class_number = next(n for n, name in self.tables['class'].items()
                            if name == 'Class')
        return Object(1, class_number, payload)

    def test_an_object_can_be_made_from_a_class_name_and_values(self):
        """What building a package from a description needs."""
        from write_package import make_object
        made = make_object(self.defs, self.tables, 7, 'ObjectList',
                           values={'length': 2}, elements=[0xB0000003, 0xB0000004])
        self.assertEqual(made.id, 7)
        self.assertEqual(self.tables['class'][made.class_number], 'ObjectList')
        self.assertEqual(made.length % 4, 0)
        # And it reads back as what it was asked for.
        package = self.build(objects=[made],
                             constant_words=[0x000FFFFF, 0x01C00003, 0x00070000])
        result = inspect(package, self.tables, self.defs)
        entry = result['objects'][0]
        self.assertEqual(entry['class_name'], 'ObjectList')
        fields = {f['name']: f.get('raw') for f in entry['contents']['fields']}
        self.assertEqual(fields['length'], 2)
        self.assertEqual(entry['contents']['extra']['raw_elements'],
                         [0xB0000003, 0xB0000004])

    def test_padding_is_computed_not_carried(self):
        from write_package import Object
        for length, expected in ((0, 0), (1, 3), (2, 2), (3, 1), (4, 0), (85, 3)):
            with self.subTest(length=length):
                self.assertEqual(Object(1, 1, bytes(length)).padding, expected)
                self.assertEqual(Object(1, 1, bytes(length)).length % 4, 0)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(SOURCES.is_dir() and DEFFILES.is_dir(), 'SDK missing')
class RuntimeListTests(unittest.TestCase):
    """The two lists the loader installs a package's own classes and
    operations from.

    Neither is checked against itself. A `ClassList` entry restates what the
    `Class` record it points at says, and that record is written by a
    different part of ObjectMaker and read here by a different function, so
    the two agreeing is the evidence. The name hashes are checked against the
    names in the example's own definition files and in the
    `PackageOperationNumbers.h` ObjectMaker generated for it.
    """

    @classmethod
    def setUpClass(cls):
        defs = Definitions(DEFFILES, SDK_INTERFACES)
        tables = load_numbers()
        cls.decoded = {p.stem: inspect(p.read_bytes(), tables, defs)
                       for p in PACKAGES}

    def lists(self, key):
        for name, result in self.decoded.items():
            for entry in result['objects']:
                if key in entry:
                    yield name, result, entry[key]

    def test_a_class_list_entry_restates_its_class_record(self):
        seen = 0
        for name, result, table in self.lists('class_list'):
            records = {e['id']: e.get('class_record')
                       for e in result['objects']}
            self.assertEqual(table['sentinel'], 0x8000)
            self.assertEqual(table['actual_count'], len(table['entries']))
            for entry in table['entries']:
                record = records.get(entry['class_record'])
                self.assertIsNotNone(record, f'{name}: entry {entry["index"]}')
                with self.subTest(package=name, klass=record['number']):
                    self.assertEqual(entry['instance_size'],
                                     record['instance_size'])
                    self.assertEqual(entry['own_bytes'], record['own_bytes'])
                    self.assertEqual(entry['inherited_bytes'],
                                     record['inherited_bytes'])
                    # Zero where a class has several implementation parents,
                    # which is the only reading that fits Circuits.
                    parents = [s['class_number']
                               for s in record.get('inherits_from', [])]
                    self.assertEqual(
                        entry['inherits_from'],
                        parents[0] if len(parents) == 1 else 0)
                seen += 1
        self.assertEqual(seen, 50)

    def test_only_a_mixin_sets_the_high_bit_in_its_sizes(self):
        """Circuits declares three in `Mixins.Def` and nothing else has any."""
        mixins = {name: sorted(e['index'] for e in table['entries']
                               if e['mixin'])
                  for name, _, table in self.lists('class_list')}
        self.assertEqual({k: v for k, v in mixins.items() if v},
                         {'Circuits': [0, 1, 2]})

    def test_a_class_list_entry_hashes_the_class_name(self):
        """`MyBalloonShape` is in two packages and hashes the same in both."""
        import re
        names = {
            'BarChart': ['BarChart.Def'], 'BizNote': ['BizNote.Def'],
            'Circuits': ['Mixins.Def', 'Components.Def', 'Circuit1.Def'],
            'Counter': ['Counter.Def'], 'Hanoi': ['Hanoi1.Def'],
            'Metric': ['Metric.Def'], 'Positioning': ['Positioning.Def'],
            'Spreadsheet': ['AdvancedSpread.Def', 'BarChartPublic.Def'],
            'Whitehouse': ['Whitehouse.Def'],
        }
        seen = 0
        for name, _, table in self.lists('class_list'):
            declared = []
            for filename in names.get(name, []):
                declared += re.findall(r'Define Class\s+(\w+)',
                                       read(SOURCES / name / filename))
            if len(declared) != len(table['entries']):
                continue        # a package whose declaration order is unread
            for entry, klass in zip(table['entries'], declared):
                with self.subTest(package=name, klass=klass):
                    self.assertEqual(entry['name_hash'], name_hash(klass))
                seen += 1
        self.assertGreaterEqual(seen, 39)

    def test_an_operation_list_is_indexed_by_the_operation_number(self):
        """A number ObjectMaker reserved and nothing uses is a hole in it.

        Hanoi's `RingNumber` exports no setter, so the number after it is
        reserved and never filled in -- which is why `actualCount` is not the
        number of operations the package has.
        """
        holes = {name: [e['index'] for e in table['entries']
                        if e.get('reserved')]
                 for name, _, table in self.lists('operation_list')}
        self.assertEqual(holes['Hanoi'], [1, 9, 20])
        self.assertEqual(holes['Counter'], [])
        for name, _, table in self.lists('operation_list'):
            self.assertEqual(table['actual_count'], len(table['entries']))

    def test_an_operation_list_entry_hashes_the_operation_name(self):
        """Against the numbers ObjectMaker generated for each example."""
        import re
        seen = 0
        for name, _, table in self.lists('operation_list'):
            header = (SOURCES / name / 'PackageInterfaces'
                      / 'PackageOperationNumbers.h')
            if not header.exists():
                continue
            declared = {0x8000 + (int(value, 16) & 0xFFFF):
                        symbol[len('operation_'):]
                        for symbol, value in
                        re.findall(r'#\s*define\s+(\w+)\s+0x([0-9A-Fa-f]+)',
                                   read(header))}
            for entry in table['entries']:
                if entry.get('reserved'):
                    continue
                operation = declared.get(entry['number'])
                # Spreadsheet and BarChart share an imported interface whose
                # operations are in both headers, and which of the two an
                # entry belongs to has not been established; they are the
                # only four in the corpus that do not line up.
                if operation is None or operation in ('LeftAndRight',
                                                      'TopAndBottom'):
                    continue
                with self.subTest(package=name, operation=operation):
                    self.assertEqual(entry['name_hash'], name_hash(operation))
                seen += 1
        self.assertEqual(seen, 128)
