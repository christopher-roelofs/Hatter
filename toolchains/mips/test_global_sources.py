import unittest
from link_package_methods import declarations
from resolve_global_sources import describe


class GlobalSourceTests(unittest.TestCase):
    def test_interface_boundaries_and_indexicals(self):
        name, entries = declarations('''define interface SystemPublic;
 indexical iDesk = 2;
 operation Tap = 1;
 end interface;
 define interface Other;
 operation Wrong = 1;
 end interface;''')
        self.assertEqual(name, 'SystemPublic')
        self.assertEqual(entries[('operation', 0)], ['Tap'])
        self.assertEqual(entries[('locator', 1)], ['iDesk'])

    def test_optional_intrinsic_keeps_runtime_symbolic(self):
        result = describe({'raw_source_kind': 0x86, 'interface_latin1': 'Public',
                           'raw_index': 2}, {'Public': {('intrinsic', 2): ['New']}})
        self.assertEqual(result['sdk_declared_names'], ['New'])
        self.assertEqual(result['form'], 'intrinsic-code-and-gp')
        self.assertTrue(result['missing_interface_returns_zero'])
        self.assertFalse(result['runtime_resolved'])

    def test_local_and_missing_interfaces(self):
        self.assertEqual(describe({'raw_source_kind': 3, 'interface_latin1': '@Tap'}, {})['local_name'], 'Tap')
        self.assertEqual(describe({'raw_source_kind': 3, 'interface_latin1': 'Unknown'}, {})['status'], 'external-interface-unavailable')

    def test_dispatcher_constraints(self):
        state = {'raw_source_kind': 6, 'interface_latin1': 'Dispatchers', 'raw_index': 6}
        self.assertEqual(describe(state, {})['status'], 'dispatcher-fallback')
        for changes in ({'raw_index': 7}, {'raw_source_kind': 0x86}, {'raw_destination_mode': 0x11}):
            self.assertEqual(describe({**state, **changes}, {})['status'], 'unsupported-dispatcher-fallback')

    def test_ambiguous_names_and_exact_immediate_kind(self):
        result = describe({'raw_source_kind': 2, 'interface_latin1': 'X'},
                          {'X': {('class', 0): ['A', 'B']}})
        self.assertEqual(result['status'], 'ambiguous-sdk-declaration')
        self.assertEqual(describe({'raw_source_kind': 10}, {})['form'], 'globals-relative')
        self.assertEqual(describe({'raw_source_kind': 0x8a}, {})['status'], 'unsupported-source-kind')


if __name__ == '__main__':
    unittest.main()
