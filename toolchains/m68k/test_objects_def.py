"""Reading ObjectMaker's Objects.Def, checked against what it compiled to.

Template is the smallest example and the only one whose every declared value
this reads, so it is the one held to producing the same bytes.
"""
import unittest
from pathlib import Path

from classdefs import Definitions, read
from inspect_package import (SDK_INTERFACES, find_cluster, inspect,
                             load_numbers)
from objects_def import (DefinitionError, content_of, make_indexical, number,
                         parse, read_indexicals, resolve, to_spec)
from objects_def import assignments
from write_package import make_object

SOURCE = Path(__file__).resolve().parents[2] / \
    'sdk/68k/samples/projects/Template'
BUILT = Path(__file__).resolve().parents[2] / \
    'sdk/68k/samples/packages/Template.pkg'
DEFFILES = SDK_INTERFACES / 'DefFiles'


class ValueTests(unittest.TestCase):
    def test_the_forms_a_value_can_take(self):
        numbers = {2: 7}
        self.assertEqual(resolve('nilObject', numbers), 0)
        self.assertIs(resolve('true', numbers), True)
        self.assertEqual(resolve('(Telename 2)', numbers), 0xB0000007)
        self.assertEqual(resolve('32', numbers), 32)
        self.assertEqual(resolve('3.w', numbers), 3)
        self.assertEqual(resolve('0x11005200', numbers), 0x11005200)

    def test_an_indexical_written_out_is_the_macro(self):
        """{60,1} is MakeIndexical(60,1), which Template's NameCard carries."""
        self.assertEqual(resolve('{60,1}', {}), 0x83078001)
        self.assertEqual(make_indexical(40, 7), 0x83050007)   # iHallway

    def test_a_point_is_fixed_with_eight_fractional_bits(self):
        self.assertEqual(resolve('<480.0,256.0>', {}), 0x0001E00000010000)
        self.assertEqual(resolve('<0.0,-8.0>', {}), 0x00000000FFFFF800)

    def test_a_long_string_is_its_pieces_joined(self):
        text = content_of(r"'one\ntwo ' \ 'three'")
        self.assertEqual(text, b'one\ntwo three')

    def test_something_unreadable_says_so(self):
        with self.assertRaises(DefinitionError):
            resolve('whatever this is', {})


@unittest.skipUnless(SOURCE.is_dir() and BUILT.exists() and DEFFILES.is_dir(),
                     'the Template example or the SDK is not here')
class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        indexicals = read_indexicals(read(SDK_INTERFACES / 'Indexicals.h'))
        cls.spec = to_spec(cls.defs, parse(read(SOURCE / 'Objects.Def')),
                           names=indexicals)
        raw = BUILT.read_bytes()
        cls.data, _ = find_cluster(raw)
        cls.result = inspect(raw, cls.tables, cls.defs)

    def test_every_instance_is_read(self):
        self.assertEqual(len(self.spec), 20)
        self.assertTrue(all(e['class'] for e in self.spec))

    def test_a_list_takes_its_entries_in_order(self):
        """`entry:` repeated is the list's contents; `entryN:` is numbered."""
        lists = [e for e in self.spec
                 if e['class'] == 'ObjectList' and 'elements' in e]
        self.assertTrue(lists)
        package = next(e for e in self.spec if e['class'] == 'SoftwarePackage')
        self.assertEqual(len(package['elements']), 32)
        self.assertTrue(package['elements'][5])          # entry6, a list
        self.assertEqual(package['elements'][12], 0x83050007)   # entry13

    def test_the_content_objects_come_out_byte_for_byte(self):
        """What the file says a Text or an OctetString holds, compiled.

        These are the objects whose whole payload is what the definition
        writes down, so they can be compared against the package ObjectMaker
        built without knowing how it numbered anything.
        """
        by_class = {}
        for entry in self.result['objects']:
            at = entry['payload']['offset']
            size = entry['payload']['length'] - entry['padding_bytes']
            by_class.setdefault(entry['class_name'], []).append(
                self.data[at:at + size])
        checked = 0
        for entry in self.spec:
            if 'bytes' not in entry:
                continue
            made = make_object(self.defs, self.tables, entry['id'],
                               entry['class'], values=entry['values'],
                               extra=entry['bytes']).payload
            with self.subTest(cls=entry['class'], size=len(made)):
                self.assertIn(made, by_class.get(entry['class'], []))
            checked += 1
        self.assertEqual(checked, 4)

    def test_what_the_definitions_do_not_declare(self):
        """The nine objects ObjectMaker adds, which this does not yet.

        A package carries class, operation and intrinsic lists, two string
        tables and a dictionary naming its objects, a boot record, and two
        lists no definition file mentions. Until those are generated a
        package cannot be built from source alone, so the count is held here
        to say how far this reaches.
        """
        declared = len(self.spec)
        self.assertEqual(len(self.result['objects']) - declared, 9)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(SOURCE.is_dir() and BUILT.exists() and DEFFILES.is_dir(),
                     'the Template example or the SDK is not here')
class SynthesisedTests(unittest.TestCase):
    """The two things a definition file does not say and ObjectMaker works out."""

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        raw = BUILT.read_bytes()
        cls.data, _ = find_cluster(raw)
        cls.result = inspect(raw, cls.tables, cls.defs)
        cls.instances = parse(read(SOURCE / 'Objects.Def'))

    def test_the_cluster_crc_is_a_sum_and_not_a_crc(self):
        """The heap added up, leaving out the boot record's own payload.

        It has to leave that out: the number is stored in it. No polynomial
        matches because none is used.
        """
        boot = next(o for o in self.result['objects']
                    if o['class_name'] == 'PackageBoot')
        stored = next(f['raw'] for f in boot['contents']['fields']
                      if f['name'] == 'clusterCRC')
        at = boot['payload']['offset']
        size = boot['payload']['length']
        heap_end = self.result['header']['heap_end']
        self.assertEqual(sum(self.data[0x44:at]) + sum(self.data[at + size:heap_end]),
                         stored)

    def test_the_root_list_is_indexed_by_the_instance_numbers(self):
        """`Instance NameCard 100` is slot 100, and the list is as long as
        the highest number any instance is given."""
        lists = [o for o in self.result['objects']
                 if o['class_name'] == 'ObjectList']
        root = max(lists, key=lambda o: len(
            (o['contents']['extra'] or {}).get('raw_elements') or []))
        elements = (root['contents']['extra'] or {}).get('raw_elements') or []
        declared = sorted(i['number'] for i in self.instances)
        self.assertEqual(len(elements), max(declared))
        self.assertEqual(sorted(i for i, e in enumerate(elements, 1) if e),
                         declared)


@unittest.skipUnless(SOURCE.is_dir() and BUILT.exists() and DEFFILES.is_dir(),
                     'the Template example or the SDK is not here')
class BuildFromSourceTests(unittest.TestCase):
    """A package built from an example's definitions and nothing else."""

    @classmethod
    def setUpClass(cls):
        from build_example import build_example
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        cls.package = build_example(SOURCE, cls.defs, cls.tables)
        cls.ours = inspect(cls.package, cls.tables, cls.defs)
        raw = BUILT.read_bytes()
        data, _ = find_cluster(raw)
        cls.theirs = inspect(raw, cls.tables, cls.defs)

    def test_it_holds_the_same_objects_ObjectMaker_produced(self):
        """The same objects, and each at the same id ObjectMaker gave it."""
        mine = {o['id']: o['class_name'] for o in self.ours['objects']}
        theirs = {o['id']: o['class_name'] for o in self.theirs['objects']}
        self.assertEqual(mine, theirs)
        self.assertEqual(len(self.ours['objects']), 29)

    def test_the_header_carries_the_words_a_package_will_not_open_without(self):
        """0x30 and 0x3c, left zero, are what stopped a built package opening.

        Every one of the sixteen has ffff at 0x30 and the highest object id
        at 0x3c, and a built Template with them zero installs but never
        activates. There is no other difference between the build that did
        not open and the one that did.
        """
        for offset in ('0x30', '0x3c'):
            with self.subTest(word=offset):
                self.assertEqual(self.ours['header']['unnamed_words'][offset],
                                 self.theirs['header']['unnamed_words'][offset])
        self.assertEqual(self.ours['header']['unnamed_words']['0x3c'],
                         f"{self.ours['header']['highest_object_id']:08x}")

    def test_the_only_records_that_differ_are_the_ones_a_build_stamps(self):
        """Every payload byte for byte, bar what only ObjectMaker can know.

        Twenty-seven of Template's twenty-nine come out identical. The two
        that do not are the package, which carries the date and time the
        build happened, and the boot record, whose checksum covers them.
        """
        mine = {o['id']: (o, self.package) for o in self.ours['objects']}
        raw = BUILT.read_bytes()
        theirs = {o['id']: (o, raw) for o in self.theirs['objects']}
        stamped = {'dateCreated', 'timeCreated', 'dateModified',
                   'timeModified', 'clusterCRC'}
        for object_id in sorted(mine):
            ours, theirs_ = mine[object_id], theirs[object_id]
            def payload(entry):
                o, data = entry
                at, size = o['payload']['offset'], o['payload']['length']
                return data[at:at + size]
            with self.subTest(id=object_id):
                if payload(ours) == payload(theirs_):
                    continue
                named = {f['name']: f.get('raw')
                         for f in ours[0]['contents']['fields']}
                other = {f['name']: f.get('raw')
                         for f in theirs_[0]['contents']['fields']}
                differing = {name for name in named
                             if named[name] != other.get(name)}
                self.assertTrue(differing <= stamped,
                                f'id {object_id} also differs in '
                                f'{sorted(differing - stamped)}')

    def test_it_is_only_the_stamped_records_that_differ_at_all(self):
        identical = sum(
            1 for ours in self.ours['objects']
            if (lambda t: self.package[ours['payload']['offset']:
                                       ours['payload']['offset']
                                       + ours['payload']['length']]
                == BUILT.read_bytes()[t['payload']['offset']:
                                      t['payload']['offset']
                                      + t['payload']['length']])(
                next(t for t in self.theirs['objects']
                     if t['id'] == ours['id'])))
        self.assertEqual(identical, len(self.ours['objects']) - 2)

    def test_the_boot_record_points_at_what_it_should(self):
        boot = next(o for o in self.ours['objects']
                    if o['class_name'] == 'PackageBoot')
        by_id = {o['id']: o['class_name'] for o in self.ours['objects']}
        fields = {f['name']: f.get('raw') for f in boot['contents']['fields']}
        for name, expected in (('classList', 'ClassList'),
                               ('operationList', 'OperationList'),
                               ('intrinsicList', 'IntrinsicList'),
                               ('package', 'SoftwarePackage'),
                               ('loadList', 'ObjectList')):
            with self.subTest(field=name):
                self.assertEqual(by_id[fields[name] & 0xFFFFFF], expected)

    def test_the_checksum_it_wrote_is_the_one_the_rule_gives(self):
        boot = next(o for o in self.ours['objects']
                    if o['class_name'] == 'PackageBoot')
        stored = next(f['raw'] for f in boot['contents']['fields']
                      if f['name'] == 'clusterCRC')
        at, size = boot['payload']['offset'], boot['payload']['length']
        heap_end = self.ours['header']['heap_end']
        self.assertEqual(sum(self.package[0x44:at])
                         + sum(self.package[at + size:heap_end]), stored)

    def test_the_root_list_is_where_the_package_says(self):
        """Element 24 of the package's own list, one slot per instance."""
        package = next(o for o in self.ours['objects']
                       if o['class_name'] == 'SoftwarePackage')
        elements = package['contents']['extra']['raw_elements']
        root_id = elements[23] & 0xFFFFFF
        root = next(o for o in self.ours['objects'] if o['id'] == root_id)
        slots = (root['contents']['extra'] or {}).get('raw_elements') or []
        declared = sorted(i['number'] for i in parse(read(SOURCE / 'Objects.Def')))
        self.assertEqual(len(slots), max(declared))
        self.assertEqual(sorted(i for i, e in enumerate(slots, 1) if e), declared)


class NumberingTests(unittest.TestCase):
    """The ids ObjectMaker gives, against the ids the packages carry.

    An instance is numbered when something first refers to it, walking the
    declarations in order -- so these check the rule against the real thing
    rather than against itself.
    """

    #: The examples built from one definition file, and the examples built
    #: from several, in the order their project file lists them.
    SOURCES = {
        'Template': ['Objects.Def'],
        'TemplateWithButtons': ['Objects.Def'],
        'StackTemplate': ['Objects.Def'],
        'StackTemplateWithIndex': ['Objects.Def'],
        'Counter': ['Objects.Def'],
        'Metric': ['Objects.Def'],
        'Hanoi': ['Objects.Def'],
        'Positioning': ['Objects.Def'],
        'Spreadsheet': ['Objects.Def'],
        'BarChart': ['Objects.Def'],
        'Whitehouse': ['Whitehouse.Def', 'AddressObjects.Def',
                       'ImageObjects.Def', 'OhSaySoundObjects.Def',
                       'Objects.Def'],
        'BizNote': ['BizNote.Def', 'LessonObjects.Def', 'Objects.Def'],
        'Snake': ['Snake.Def', 'Objects.Def', 'SoundObjects.Def'],
    }

    EXAMPLES = SOURCE.parent
    PACKAGES = BUILT.parent

    def instances(self, name):
        out = []
        for filename in self.SOURCES[name]:
            path = self.EXAMPLES / name / filename
            if path.exists():
                out += parse(read(path))
        return out

    def test_every_example_is_numbered_the_way_its_package_is(self):
        classes = set(load_numbers()['class'].values())
        for name in self.SOURCES:
            with self.subTest(example=name):
                instances = self.instances(name)
                ids = number(instances)
                package = inspect((self.PACKAGES / f'{name}.pkg').read_bytes())
                actual = {o['id']: o.get('class_name')
                          for o in package['objects']}
                declared = {i['number']: i for i in instances}
                for instance_number, object_id in ids.items():
                    want = declared[instance_number]['class']
                    got = actual.get(object_id)
                    # A class the package defines itself has no SDK name, so
                    # the inspector can only say which of them it is.
                    if want not in classes:
                        self.assertTrue(str(got).startswith('package class'),
                                        f'{name} id {object_id}: {got}')
                    else:
                        self.assertEqual(got, want, f'{name} id {object_id}')

    def test_a_package_is_the_one_thing_nothing_refers_to(self):
        for name in self.SOURCES:
            with self.subTest(example=name):
                instances = self.instances(name)
                ids = number(instances)
                unreferenced = [i['class'] for i in instances
                                if i['number'] not in ids]
                self.assertEqual(unreferenced, ['SoftwarePackage'])


class MoreValueTests(unittest.TestCase):
    """The forms the other examples write, each against a real package."""

    def test_a_double_brace_is_a_package_indexical(self):
        """`{{26}}` sets bit 23; the flat form appears in no package.

        StackTemplate's two prototype cards say `form: {{26}}` and carry
        0x83834000. MakeFlatIndexical(26) would be 0x83034000, which no
        package in the corpus contains.
        """
        self.assertEqual(resolve('{{26}}', {}), 0x83834000)
        self.assertEqual(make_indexical(26, 0), 0x83034000)
        self.assertEqual(make_indexical(26, 0, package=True), 0x83834000)

    def test_a_coordinate_and_a_fixed_are_scaled_differently(self):
        """Brackets mean eight fractional bits, bare means sixteen.

        StackTemplateWithIndex writes `offset1: <15.0>` and its package holds
        3840. Snake's rattle writes `sampleRate: 22254.54546` and holds
        0x56EE8BA3, which is 22254 and 35747/65536.
        """
        self.assertEqual(resolve('<15.0>', {}), 15 * 256)
        self.assertEqual(resolve('22254.54546', {}), 0x56EE8BA3)

    def test_two_plain_numbers_are_a_pixel_dot(self):
        """Metric's images write `imageSize: 17,31` -- whole pixels."""
        self.assertEqual(resolve('17,31', {}), 0x0011001F)

    def test_hex_may_be_a_word_or_a_run_of_bytes(self):
        self.assertEqual(resolve('$ 0000 0040', {}), 0x40)
        self.assertEqual(content_of('$ 0046 1940 \\ $ 65A8 3A40'),
                         bytes.fromhex('00461940' '65A83A40'))

    def test_a_semicolon_inside_a_string_does_not_end_the_value(self):
        """Snake's help text has one, and losing it truncates the string."""
        body = ("text: 'walk around; sometimes it will sleep';\n"
                "flags: 2;\n")
        self.assertEqual(assignments(body),
                         [('text', "'walk around; sometimes it will sleep'"),
                          ('flags', '2')])

    def test_a_negative_value_is_written_as_its_bit_pattern(self):
        """StackTemplate's cards say `color: -1` and carry ffffffff."""
        from classdefs import encode_fields
        layout = {'fixed_bytes': 4, 'fields': [
            {'name': 'color', 'offset': 0, 'size': 4, 'bit': None}]}
        self.assertEqual(encode_fields(layout, {'color': -1}), b'\xff' * 4)


class EveryDataOnlyExampleTests(unittest.TestCase):
    """Each example with no compiled code, built and held to stock's bytes.

    The others declare classes of their own, so they need a Code object this
    cannot produce yet; these five do not.
    """

    #: Name, and the definition files in the order the project lists them.
    EXAMPLES = {
        'Template': ['Objects.Def'],
        'TemplateWithButtons': ['Objects.Def'],
        'StackTemplate': ['Objects.Def'],
        'StackTemplateWithIndex': ['Objects.Def'],
        'Snake': ['Objects.Def', 'SoundObjects.Def'],
    }
    #: Every one of them now comes out at stock's size. StackTemplateWithIndex
    #: used to be 24 bytes short, because the SDK that shipped declares
    #: ContentListView with none of the eight fields its index view sets; what
    #: those are is in recovered.Def, worked out from the bytes.
    SHORT = {}

    @classmethod
    def setUpClass(cls):
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()

    def build(self, name):
        from build_example import build_example
        # A fresh Definitions each time: the builder adds the example's own
        # classes to whatever it is given, and one example's must not be
        # visible to the next.
        from classdefs import Definitions
        return build_example(SOURCE.parent / name,
                             Definitions(DEFFILES, SDK_INTERFACES),
                             self.tables, sources=self.EXAMPLES[name])

    def test_each_holds_the_same_objects_at_the_same_ids(self):
        for name in self.EXAMPLES:
            with self.subTest(example=name):
                ours = inspect(self.build(name), self.tables, self.defs)
                theirs = inspect((BUILT.parent / f'{name}.pkg').read_bytes(),
                                 self.tables, self.defs)
                self.assertEqual(
                    {o['id']: o['class_name'] for o in ours['objects']},
                    {o['id']: o['class_name'] for o in theirs['objects']})

    def test_only_the_stamped_records_differ(self):
        """The package carries the build's date, the boot record its sum."""
        for name in self.EXAMPLES:
            with self.subTest(example=name):
                package = self.build(name)
                stock = (BUILT.parent / f'{name}.pkg').read_bytes()
                ours = inspect(package, self.tables, self.defs)['objects']
                theirs = {o['id']: o for o in
                          inspect(stock, self.tables, self.defs)['objects']}

                def payload(entry, data):
                    at, size = entry['payload']['offset'], entry['payload']['length']
                    return data[at:at + size]

                differ = [o['id'] for o in ours
                          if payload(o, package) != payload(theirs[o['id']], stock)]
                self.assertEqual(len(differ), 2 + self.SHORT.get(name, 0),
                                 f'{name}: {differ} differ')


class WhitehouseTelecardTests(unittest.TestCase):
    @unittest.skipUnless((SOURCE.parent / 'Whitehouse').is_dir()
                         and (BUILT.parent / 'Whitehouse.pkg').exists()
                         and DEFFILES.is_dir(), 'Whitehouse or SDK is absent')
    def test_telecard_payloads_match_objectmaker(self):
        from build_example import build_example
        built, missing = build_example(SOURCE.parent / 'Whitehouse', report=True)
        self.assertFalse(missing)
        stock = (BUILT.parent / 'Whitehouse.pkg').read_bytes()

        def telecards(package):
            data, _ = find_cluster(package)
            return {o['id']: data[o['payload']['offset']:
                                 o['payload']['offset'] + o['payload']['length']]
                    for o in inspect(package)['objects']
                    if o['class_name'] == 'Telecard'}

        expected = telecards(stock)
        self.assertEqual(len(expected), 4)
        self.assertEqual(telecards(built), expected)


class PackageClassTests(unittest.TestCase):
    """An example's own classes, read the same way the SDK's are."""

    def test_a_package_class_lays_out_against_the_class_it_inherits(self):
        """Counter's scene is a Scene and one more Unsigned.

        Its package says `instanceSize` 88 and the SDK's Scene works out to
        84, so the layout has to come to 88 -- which is the check that
        reading an example's own definition file gives the same answer
        ObjectMaker got from it.
        """
        definitions = Definitions(DEFFILES, SDK_INTERFACES)
        definitions.add(SOURCE.parent / 'Counter' / 'Counter.Def')
        self.assertEqual(definitions.layout('CounterScene')['fixed_bytes'], 88)
        self.assertEqual(definitions.layout('Scene')['fixed_bytes'], 84)
        names = [f['name'] for f in definitions.layout('CounterScene')['fields']]
        self.assertEqual(names[-1], 'visitCount')

    def test_package_class_numbers_start_at_8001_in_declaration_order(self):
        """Against the numbers ObjectMaker generated for each example.

        `PackageClassNumbers.h` is its own output, so it says what it chose:
        `#define CounterScene_ 0x00008001`. Eight of the nine examples with
        classes agree; Circuits is the ninth and its definition files are
        declared in an order its project gives rather than by filename.
        """
        import re
        from classdefs import read, strip_comments
        define = re.compile(r'Define\s+Class\s+(\w+)\s*;')
        header = re.compile(r'#\s*define\s+(\w+)_\s+0x([0-9A-Fa-f]+)')
        agreed = 0
        for example in sorted(SOURCE.parent.iterdir()):
            numbers = (example / 'PackageInterfaces' / 'PackageClassNumbers.h')
            if not numbers.exists():
                continue
            mine = {}
            for path in sorted(example.glob('*.Def')):
                for name in define.findall(strip_comments(read(path))):
                    mine.setdefault(name, 0x8001 + len(mine))
            theirs = {name: int(value, 16)
                      for name, value in header.findall(read(numbers))
                      if int(value, 16)}
            agreed += mine == theirs
        self.assertEqual(agreed, 13)


class PackageNumberingAgainstThePackagesTests(unittest.TestCase):
    """The numbering held to the packages rather than to a generated header.

    A package carries the hash of each class's and each operation's name
    beside it, so it says which name is at which number without any header
    being involved -- which matters, because two of the headers the cookbook
    ships are stale with respect to the package next to them.
    """

    @classmethod
    def setUpClass(cls):
        from classdefs import Definitions
        cls.defs = Definitions(DEFFILES, SDK_INTERFACES)
        cls.tables = load_numbers()
        cls.system = set(cls.tables['operation'].values()) \
            | set(cls.tables['attribute'].values())

    def decoded(self, name):
        return inspect((BUILT.parent / f'{name}.pkg').read_bytes(),
                       self.tables, self.defs)

    def examples(self):
        for directory in sorted(p for p in SOURCE.parent.iterdir()
                                if p.is_dir()):
            if (BUILT.parent / f'{directory.name}.pkg').exists():
                yield directory

    def test_every_operation_is_where_the_package_says_it_is(self):
        from classdefs import package_numbers
        from inspect_package import name_hash
        from objects_def import project_order
        seen = 0
        for directory in self.examples():
            order = project_order(directory)
            numbers = package_numbers(
                [read(directory / f) for f in order], self.system)
            named = {(v & 0xFFFF) | 0x8000: k[len('operation_'):]
                     for k, v in numbers.items()
                     if k.startswith('operation_')}
            for entry in self.decoded(directory.name)['objects']:
                table = entry.get('operation_list')
                if not table:
                    continue
                for row in table['entries']:
                    if row.get('reserved'):
                        continue
                    with self.subTest(example=directory.name,
                                      number=row['number']):
                        operation = named.get(row['number'])
                        self.assertIsNotNone(operation)
                        self.assertEqual(name_hash(operation), row['name_hash'])
                    seen += 1
        self.assertEqual(seen, 132)

    def test_every_class_is_where_the_package_says_it_is(self):
        from classdefs import package_class_numbers
        from inspect_package import name_hash
        from objects_def import project_order
        seen = 0
        for directory in self.examples():
            classes = package_class_numbers(
                [read(directory / f) for f in project_order(directory)])
            named = {number: name for name, number in classes.items()}
            for entry in self.decoded(directory.name)['objects']:
                table = entry.get('class_list')
                if not table:
                    continue
                for row in table['entries']:
                    with self.subTest(example=directory.name,
                                      index=row['index']):
                        self.assertEqual(
                            name_hash(named[0x8001 + row['index']]),
                            row['name_hash'])
                    seen += 1
        self.assertEqual(seen, 50)

    def test_a_field_with_accessors_declares_an_attribute(self):
        """Whitehouse writes only the field and its package has the pair."""
        from classdefs import package_numbers
        numbers = package_numbers(
            [read(SOURCE.parent / 'Whitehouse' / 'Whitehouse.Def')])
        self.assertEqual(numbers['operation_MessageCount'], 0x80000003)
        self.assertEqual(numbers['operation_SetMessageCount'], 0x80000004)

    def test_an_attribute_takes_a_pair_of_numbers_that_are_both_free(self):
        """BizNote's `InstallIntoFileCabinet` gets 5 and `MeetingType` 12.

        5 was free and 6 was already spoken for, so the operation could take
        it and the attribute, which needs two in a row, could not.
        """
        from classdefs import package_numbers
        numbers = package_numbers(
            [read(SOURCE.parent / 'BizNote' / 'BizNote.Def')],
            set(load_numbers()['operation'].values()))
        self.assertEqual(numbers['operation_InstallIntoFileCabinet'], 0x80000005)
        self.assertEqual(numbers['operation_MeetingType'], 0x8000000C)

    def test_an_operation_the_sdk_already_has_is_an_override(self):
        """BizCard declares `IndexedDate` so the Date Chooser can target it."""
        from classdefs import package_numbers
        system = set(load_numbers()['operation'].values())
        numbers = package_numbers(
            [read(SOURCE.parent / 'BizNote' / 'BizNote.Def')], system)
        self.assertNotIn('operation_IndexedDate', numbers)
        self.assertIn('IndexedDate', system)


class ProjectOrderTests(unittest.TestCase):
    """Which definition files an example builds, and in which order."""

    def test_the_order_is_the_last_listing_in_the_project(self):
        from objects_def import project_order
        self.assertEqual(project_order(SOURCE.parent / 'Circuits'),
                         ['Mixins.Def', 'Components.Def', 'Circuit1.Def',
                          'Objects.Def', 'BookObjects.Def',
                          'ComponentObjects.Def', 'HelpObjects.Def',
                          'SoundObjects.Def'])

    def test_a_file_named_once_is_referred_to_and_not_built(self):
        """Spreadsheet's copy of BarChart's declarations.

        It is listed once where everything Spreadsheet builds is listed
        twice, and its six classes are numbered after Spreadsheet's own five
        rather than before them -- which is what the package says.
        """
        from objects_def import project_order
        self.assertEqual(project_order(SOURCE.parent / 'Spreadsheet'),
                         ['AdvancedSpread.Def', 'Objects.Def',
                          'BarChartPublic.Def'])

    def test_only_the_files_that_declare_instances_are_parsed(self):
        from objects_def import instance_sources
        self.assertEqual(instance_sources(SOURCE.parent / 'Snake'),
                         ['Objects.Def', 'SoundObjects.Def'])
        self.assertEqual(instance_sources(SOURCE.parent / 'Whitehouse'),
                         ['AddressObjects.Def', 'ImageObjects.Def',
                          'OhSaySoundObjects.Def', 'Objects.Def'])


class EveryExampleParsesTests(unittest.TestCase):
    """All fourteen read all the way through, with no value left unread."""

    def test_each_example_builds_a_cluster(self):
        from build_example import build_example
        for directory in sorted(p for p in SOURCE.parent.iterdir()
                                if p.is_dir()):
            with self.subTest(example=directory.name):
                package = build_example(directory)
                self.assertGreater(len(package), 0x44)

    def test_a_name_may_carry_an_escaped_quote(self):
        """Circuits declares `Instance BookPage 'What\\'s A Circuit?' 176;`.

        Matched as "anything but a quote", the declaration is skipped without
        a word and the only sign of it is a later reference to an instance
        that looks undeclared.
        """
        from objects_def import parse
        declared = parse("Instance BookPage 'What\\'s A Circuit?' 176;\n"
                         "End Instance;\n")
        self.assertEqual([i['number'] for i in declared], [176])

    def test_four_coordinates_are_a_box(self):
        from objects_def import resolve
        self.assertEqual(resolve('<138.0,282.0,204.0,318.0>', {}),
                         0x00008A00_00011A00_0000CC00_00013E00)


class PackageOperationNumberTests(unittest.TestCase):
    """The numbers ObjectMaker gives a package's own operations.

    Checked against `PackageOperationNumbers.h`, which is its own output and
    so says exactly what it chose. Two of the headers the cookbook ships are
    stale with respect to the package beside them, which is why the check
    that matters is the one against the packages above.
    """

    #: The definition files each example builds, in project order. The four
    #: not here declare operations across several files and the order their
    #: projects use has not been pinned down; the rule is the same.
    SOURCES = {
        'Counter': ['Counter.Def', 'Objects.Def'],
        'Metric': ['Metric.Def', 'Objects.Def'],
        'Positioning': ['Objects.Def', 'Positioning.Def'],
        'Hanoi': ['Hanoi1.Def', 'Objects.Def'],
        'BarChart': ['BarChart.Def', 'Objects.Def'],
    }

    def generated(self, example):
        import re
        header = (SOURCE.parent / example / 'PackageInterfaces'
                  / 'PackageOperationNumbers.h')
        return {name: int(value, 16) for name, value in
                re.findall(r'#\s*define\s+(\w+)\s+0x([0-9A-Fa-f]+)',
                           read(header))
                if int(value, 16)}

    def test_each_example_is_numbered_the_way_ObjectMaker_numbered_it(self):
        from classdefs import package_numbers
        for example, files in self.SOURCES.items():
            with self.subTest(example=example):
                texts = [read(SOURCE.parent / example / f) for f in files
                         if (SOURCE.parent / example / f).exists()]
                self.assertEqual(package_numbers(texts),
                                 self.generated(example))

    def test_a_read_only_attribute_still_reserves_its_setter(self):
        """Hanoi's RingNumber exports no setter and the next one starts at 3."""
        from classdefs import package_numbers
        numbers = package_numbers([read(SOURCE.parent / 'Hanoi' / 'Hanoi1.Def')])
        self.assertEqual(numbers['operation_RingNumber'], 0x80000001)
        self.assertNotIn('operation_SetRingNumber', numbers)
        self.assertEqual(numbers['operation_CurrentPole'], 0x80000003)

    def test_a_top_level_number_no_class_declares_is_dropped(self):
        """BarChart writes `Attribute SouceCanvas 50;` -- Source, misspelt."""
        from classdefs import package_numbers
        numbers = package_numbers(
            [read(SOURCE.parent / 'BarChart' / 'BarChart.Def')])
        self.assertNotIn('operation_SouceCanvas', numbers)
        self.assertEqual(numbers['operation_SourceCanvas'], 0x80000001)
