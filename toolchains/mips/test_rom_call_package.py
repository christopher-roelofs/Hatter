import unittest
from build_global_init import GlobalInitBuilder
from build_native_package import build
from inspect_format import inspect, FormatError


class RomCallPackageTests(unittest.TestCase):
    CODE = bytes.fromhex('27bdffe0afbf001cafbc0018afb0001400808025'
                         '8f990000240f105b0320f809000000008fbc0018'
                         '8fbf001c8fb00014240200010 3e00008 27bd0020'.replace(' ', ''))

    def test_dispatcher_slot_init(self):
        init = GlobalInitBuilder(4, 0)
        init.resolve(6, 'Dispatchers', 1, required_count=6)
        raw, manifest = build(self.CODE, init=init, name='NativeRomCall')
        parsed = inspect(raw)['packages'][0]
        a0 = next(a for a in parsed['records'] if a['raw_tag_byte'] == 0xa0)['global_initialization']
        self.assertEqual(a0['global_data_bytes'], 4)
        entries = [e for i in a0['instructions'] for e in i.get('entries', [])]
        self.assertEqual(len(entries), 1)
        state = entries[0]['state']
        self.assertEqual((state['raw_source_kind'], state['interface_latin1'], state['raw_index'],
                          state['raw_field_a4'], state['raw_destination_mode']),
                         (6, 'Dispatchers', 1, 6, 4))
        self.assertFalse(manifest['validated_leaf'])
        self.assertEqual(manifest['initialization_trial']['globals_size'], 4)

    def test_other_code_needs_init(self):
        with self.assertRaises(FormatError):
            build(self.CODE)


if __name__ == '__main__':
    unittest.main()
