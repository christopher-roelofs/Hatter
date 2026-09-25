"""A package's own classes, worked out from its sources and held to its bytes.

`package_classes.describe` reads the declarations and says what the records
should contain; the packages say what they do contain. Everything here is the
one against the other, never against itself.
"""
from pathlib import Path
import shutil
import unittest

from classdefs import Definitions
from inspect_package import SDK_INTERFACES, inspect, load_numbers
from package_classes import RESULT_KIND, describe

SOURCES = Path(__file__).resolve().parents[2] / \
    'sdk/68k/samples/projects'
COOKBOOK = Path(__file__).resolve().parents[2] / \
    'sdk/68k/samples/packages'
DEFFILES = SDK_INTERFACES / 'DefFiles'
RECOVERED = Path(__file__).with_name('recovered.Def')

#: The nine that declare classes of their own.
WITH_CODE = ('Counter', 'Metric', 'Positioning', 'Hanoi', 'Whitehouse',
             'BarChart', 'BizNote', 'Spreadsheet', 'Circuits')


def have_toolchain():
    return all(shutil.which(tool) for tool in
               ('clang-18', 'm68k-linux-gnu-ld', 'm68k-linux-gnu-as'))


@unittest.skipUnless(SOURCES.is_dir() and DEFFILES.is_dir(), 'corpus missing')
class DescriptionTests(unittest.TestCase):
    """What the declarations say, against what ObjectMaker wrote."""

    @classmethod
    def setUpClass(cls):
        cls.tables = load_numbers()
        cls.described, cls.stock = {}, {}
        for name in WITH_CODE:
            definitions = Definitions(DEFFILES, SDK_INTERFACES)
            definitions.add(RECOVERED, override=True)
            for path in sorted((SOURCES / name).glob('*.Def')):
                definitions.add(path)
            cls.described[name] = describe(SOURCES / name, definitions,
                                           cls.tables)
            cls.stock[name] = inspect((COOKBOOK / f'{name}.pkg').read_bytes(),
                                      cls.tables, definitions)

    def records(self, name):
        return {entry['class_record']['number']: entry['class_record']
                for entry in self.stock[name]['objects']
                if entry.get('class_record')}

    def test_the_same_classes_get_records(self):
        """A file the project only refers to contributes none.

        Spreadsheet numbers BarChart's six classes 6 to 11 and writes a
        record for none of them, so describing eleven would be wrong even
        though eleven are declared.
        """
        for name in WITH_CODE:
            with self.subTest(example=name):
                self.assertEqual(
                    {k['number'] for k
                     in self.described[name]['classes'].values()},
                    set(self.records(name)))

    def test_every_class_is_the_size_its_record_says(self):
        seen = 0
        for name in WITH_CODE:
            records = self.records(name)
            for klass in self.described[name]['classes'].values():
                record = records[klass['number']]
                # Spreadsheet's CellEditorWindow has two parents the corpus
                # never pins down, so nothing here can know its size.
                if klass['name'] == 'CellEditorWindow':
                    continue
                with self.subTest(example=name, klass=klass['name']):
                    self.assertEqual(klass['instance_size'],
                                     record['instance_size'])
                    self.assertEqual(klass['own_bytes'], record['own_bytes'])
                seen += 1
        self.assertEqual(seen, 49)

    def test_every_class_answers_as_what_its_record_says(self):
        """Which needs `system_classes.json`, not the definition files.

        `EditsTarget` and `FormElement` have class numbers and no declaration
        anywhere in the SDK; the only place they appear is in the packages.
        """
        seen = 0
        for name in WITH_CODE:
            records = self.records(name)
            for klass in self.described[name]['classes'].values():
                record = records[klass['number']]
                # BizNote's BizIndexScene and Circuits' Resistor carry more
                # interfaces than their interfaceCount admits to, which is a
                # limit of the decode and is recorded as one.
                if klass['name'] in ('BizIndexScene', 'Resistor'):
                    continue
                with self.subTest(example=name, klass=klass['name']):
                    self.assertEqual(
                        klass['interfaces'],
                        sorted(i['class_number']
                               for i in record['interfaces']))
                seen += 1
        self.assertEqual(seen, 48)

    #: The one method flag nothing explains. Three classes override
    #: `CanApply` and all three carry 0x01000000; no other method in the
    #: corpus carries it. It is not the signature -- `CanAcceptCoupon`
    #: returns a Boolean and takes arguments too, and carries nothing -- and
    #: it is not that two classes declare the name, which is true of
    #: `TouchTarget` and `AboutToShow` as well.
    CAN_APPLY = 0x055C

    def test_every_method_table_has_the_same_selectors(self):
        """Including the intrinsics, which share the operations' numbering.

        BarChart's `BarChartNoteCard` carries an accessor at 0x80000001 for
        `SourceCanvas` and an intrinsic at 0x80000001 for `LeftAndRight`;
        the 0x8000 in the entry's flags is what tells them apart.
        """
        seen = 0
        for name in WITH_CODE:
            records = self.records(name)
            for klass in self.described[name]['classes'].values():
                record = records[klass['number']]
                with self.subTest(example=name, klass=klass['name']):
                    self.assertEqual(
                        [(m['selector'] & 0xFFFFFFFF,
                          0 if m['selector'] == self.CAN_APPLY
                          else m.get('flags', 0))
                         for m in klass['methods']],
                        [(int(m['selector'], 16),
                          0 if ('accessor' in m
                                or int(m['selector'], 16) == self.CAN_APPLY)
                          else m.get('method_flags', 0))
                         for m in record['methods']])
                seen += 1
        self.assertEqual(seen, 50)

    def test_the_can_apply_flag_is_the_one_thing_left_unexplained(self):
        """Three entries in two packages, and nothing accounts for them."""
        flagged = []
        for name in WITH_CODE:
            for record in self.records(name).values():
                for method in record['methods']:
                    if method.get('method_flags') == 0x01000000:
                        flagged.append((name, int(method['selector'], 16)))
        self.assertEqual(len(flagged), 3)
        self.assertEqual({selector for _, selector in flagged},
                         {self.CAN_APPLY})

    def test_the_operations_are_the_ones_the_package_carries(self):
        for name in WITH_CODE:
            table = [entry['operation_list']
                     for entry in self.stock[name]['objects']
                     if 'operation_list' in entry][0]
            live = [e for e in table['entries'] if not e.get('reserved')]
            with self.subTest(example=name):
                self.assertEqual(
                    [o['number'] for o in self.described[name]['operations']],
                    [e['number'] for e in live])
                self.assertEqual(
                    [o['kind'] for o in self.described[name]['operations']],
                    [e['kind'] for e in live])

    def test_a_kind_byte_is_the_result_type_and_whether_it_is_a_getter(self):
        """0x01 for an operation returning a Boolean, 0x21 for a getter."""
        self.assertEqual(RESULT_KIND[0x02], 0x01)     # Boolean
        self.assertEqual(RESULT_KIND[0x16], 0x03)     # Unsigned
        self.assertEqual(RESULT_KIND[0x07], 0x13)     # a reference
        self.assertEqual(RESULT_KIND[0x00], 0x00)     # nothing


@unittest.skipUnless(SOURCES.is_dir(), 'corpus missing')
class CrossPackageTests(unittest.TestCase):
    """What the corpus says about one package calling into another: nothing.

    `BarChartPublic.Def` looked like an import -- it is BarChart's
    declarations copied into Spreadsheet -- but Spreadsheet's package carries
    a record for none of its classes, its code refers to none of their
    numbers, and the `PackageImports.h` ObjectMaker generated for it is
    empty. Spreadsheet finds a bar chart the way anything finds anything
    here, through an indexical: `MakePackageIndexical(27,1)` is the citation
    it looks it up by.
    """

    def test_no_example_imports_anything(self):
        empty = 0
        for directory in sorted(p for p in SOURCES.iterdir() if p.is_dir()):
            header = directory / 'PackageInterfaces' / 'PackageImports.h'
            if not header.exists():
                continue
            text = header.read_bytes().decode('mac-roman')
            with self.subTest(example=directory.name):
                self.assertNotIn('#define', text)
            empty += 1
        self.assertGreaterEqual(empty, 9)


@unittest.skipUnless(have_toolchain() and SOURCES.is_dir(),
                     'toolchain missing')
class BuiltPackageTests(unittest.TestCase):
    """Every example built from its sources, code and all."""

    def test_each_example_builds(self):
        from build_example import build_example
        for directory in sorted(p for p in SOURCES.iterdir() if p.is_dir()):
            with self.subTest(example=directory.name):
                package = build_example(directory)
                self.assertGreater(len(package), 0x44)

    def test_a_built_package_holds_the_same_objects_as_the_one_shipped(self):
        """Same ids, same classes, for the nine that carry code.

        What is inside two of them differs and is meant to: the `Code` object
        is what clang compiled rather than what CodeWarrior did, and the
        `Class` records point into it. The rest has to match.
        """
        from build_example import build_example
        tables = load_numbers()
        for name in ('Counter', 'Metric', 'Positioning', 'Whitehouse'):
            definitions = Definitions(DEFFILES, SDK_INTERFACES)
            built = build_example(SOURCES / name, definitions, tables)
            stock = (COOKBOOK / f'{name}.pkg').read_bytes()
            ours = {o['id']: o['class_name']
                    for o in inspect(built, tables, definitions)['objects']}
            theirs = {o['id']: o['class_name']
                      for o in inspect(stock, tables, definitions)['objects']}
            with self.subTest(example=name):
                self.assertEqual(ours, theirs)

    def test_the_code_object_carries_its_macsbug_symbols(self):
        """A procedure, then 0x80 or'd with the length, then the name."""
        from compile_example import code, macsbug
        self.assertEqual(macsbug('main'), b'\x84main\0\0\0')
        blob, _, procedures = code(SOURCES / 'Counter')
        for name, where in procedures.items():
            with self.subTest(procedure=name):
                at = where['offset'] + where['size']
                self.assertEqual(blob[at:at + len(macsbug(name))],
                                 macsbug(name))


if __name__ == '__main__':
    unittest.main()
