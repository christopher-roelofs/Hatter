import shutil
import unittest
from odef_frontend import parse_cdef, parse_odef, Values, statements, strip_comments


class FrontEndTests(unittest.TestCase):
    def test_parse_cdef(self):
        classes, ix = parse_cdef('read "MagicCap.cdef";\n// c\ndefine class D;\n\tinherits from Box;\n\tinherits from HasDestination;\n'
                                 '\toverrides Draw;\n\tfield n: Unsigned, getter;\nend class;\nindexical iD: D;\n')
        self.assertEqual(classes[0]['supers'], ['Box', 'HasDestination'])
        self.assertEqual(classes[0]['overrides'], ['Draw'])
        self.assertEqual(classes[0]['fields'][0], {'name': 'n', 'type': 'Unsigned', 'flags': ['getter']})
        self.assertEqual(ix, {'iD': 'D'})

    def test_parse_odef_values(self):
        inst, bind = parse_odef("instance Scene s 'A; B';\n relativeOrigin: <0.0,-8.0>;\n subview: (G g);\n t: 'x\\ny';\nend instance;\n"
                                "indexical iG = (G g);\n")
        self.assertEqual(inst[0]['name'], 'A; B')
        v = Values(bind, {}, lambda n: 99)
        self.assertEqual(v.convert('<0.0,-8.0>', 'Dot'), [0, -2048])
        self.assertEqual(v.convert('(G g)', 'Reference'), ('ref', 'g'))
        self.assertEqual(v.convert('iG', 'Reference'), ('ref', 'g'))
        self.assertEqual(v.convert('iBook12', 'Reference'), ('ix', 'iBook12'))
        self.assertEqual(v.convert('0x11005200', 'Flags'), 0x11005200)
        self.assertEqual(v.convert("'x\\ny'", 'Text'), 'x\ny')
        self.assertEqual(v.convert('operation_Foo', 'OperationNumber'), 99)
        self.assertEqual(v.convert('6.s', 'UnsignedShort'), 6)
        self.assertEqual(v.convert('nilObject', 'Reference'), 0)


if __name__ == '__main__':
    unittest.main()


class FrontEndMoreTests(unittest.TestCase):
    def test_attributes_intrinsics_and_values(self):
        from odef_frontend import parse_cdef, Values, extra_data
        classes, _ = parse_cdef('define class C;\n\tinherits from Object;\n\tattribute Size: Unsigned;\n'
                                '\tattribute Name: Text, readOnly;\n\tintrinsic Quick(x: Unsigned): Boolean;\n'
                                '\tclass operation Make(): C;\nend class;\n')
        c = classes[0]
        self.assertEqual(c['operations'], ['Size', 'SetSize', 'Name', 'Make'])
        self.assertEqual(c['intrinsics'], ['Quick'])
        self.assertTrue(c['signatures']['Make']['class_op'])
        v = Values({'iN': (None, None)}, {}, lambda n: ('op', n), tags={'a'})
        self.assertEqual(v.convert('iN', 'Reference'), 0)
        self.assertEqual(v.convert('(Scene Main.a)', 'Reference'), ('ref', 'a'))
        self.assertEqual(v.convert('186,186', 'PixelDot'), [186, 186])
        self.assertEqual(v.convert('4.0', 'Fixed'), 0x40000)
        self.assertEqual(v.convert("'ab' 'c\\'d'", 'Text'), "abc'd")
        self.assertEqual(extra_data('$ 0200 7FC0 $ FC00', None), bytes.fromhex('02007fc0fc00'))


class MixinAndSubviewTests(unittest.TestCase):
    def test_package_mixin_and_struct_params(self):
        from odef_frontend import parse_cdef, c_type, accessor_type
        classes, _ = parse_cdef('define class S;\n\tinherits from Viewable;\n\toperation SetBounds(bounds: Box);\n'
                                '\toperation Bounds(var bounds: Box);\nend class;\n'
                                'define class M;\n\tmixes in with S;\n\toverrides CanStretch;\nend class;\n')
        self.assertEqual(classes[1]['mixes_in_with'], 'S')
        self.assertEqual(classes[1]['supers'], [])
        self.assertEqual(c_type('Box'), 'const Box *')
        self.assertEqual(c_type('var Box'), 'Box *')
        self.assertEqual(c_type('var Unsigned'), 'Unsigned *')
        # accessor type table: Word 0, Bit0 (MSB) 6, ObjectReference 0x16, Text 0x20
        self.assertEqual((accessor_type('Unsigned', 0), accessor_type('Boolean', 0), accessor_type('Boolean', 3),
                          accessor_type('Viewable', 0), accessor_type('Text', 0)), (0, 6, 12, 0x16, 0x20))

    @unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
    def test_speedscroll_records_superview_and_headers(self):
        import json
        from build_sample import build_sample
        from link_package_methods import ROOT, SDK
        from inspect_format import inspect
        out = ROOT / 'out/rosemary-test-speedscroll'
        build_sample(SDK / 'Samples/SpeedScrollSample', 'SpeedScrollSample', out)
        m = json.loads((out / 'package-manifest.json').read_text())
        data = (out / 'SpeedScrollSample.pkg').read_bytes()
        package = inspect(data)['packages'][0]
        objects = [r for r in package['records'] if 'heap' in r][0]['heap']['objects']
        sel = m['selectors']
        # the Box with subviews carries the reference-list bit; its button refers back to it
        box = objects[(sel['trinkets'] - 4) // 8]
        self.assertEqual(box['raw_header'] >> 24, 0xb9)
        button = objects[(sel['scrollerButton'] - 4) // 8]
        self.assertEqual(button['raw_header'] >> 24, 0xb1)
        body = data[button['body']['offset']:button['body']['offset'] + 4]
        self.assertEqual(int.from_bytes(body, 'big'), sel['trinkets'])
        # the method-less SampleSpeedScroller record has no method table; mixins list their base
        cs = m['class_selectors']
        records = [o for o in objects if o.get('raw_class_selector') == cs['UnlinkedClassWithInstances']]
        by_len = {}
        for o in records:
            b = data[o['body']['offset']:o['body']['offset'] + o['body']['length']]
            by_len.setdefault(len(b), []).append(b)
        empty = [b for b in by_len.get(20, []) if b[2:4] == b'\x00\x00']
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0][12:20].hex(), '0003' + f"{cs['SpeedScroller']:04x}{cs['CanStretchSpeedScroller']:04x}{cs['CanChangeSpeedScrollerImage']:04x}")

