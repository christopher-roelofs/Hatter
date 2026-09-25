import shutil
import unittest
from build_package import class_record


class BuildPackageTests(unittest.TestCase):
    def test_class_record_layout(self):
        rec = class_record([15, 16, 17], [(1, 3), (2, 4)], 0x9004)
        # header: supers at 12, methods at 12 + 8 (count + 3 selectors, padded to 4)
        self.assertEqual(rec[:12].hex(), '000c0014900400000000' + '0000')
        self.assertEqual(rec[12:20].hex(), '0003000f00100011')
        self.assertEqual(rec[20:24].hex(), '80020000')
        self.assertEqual(rec[24:40].hex(), '4100000100000003' + '4100000200000004')
        # accessor entries follow the native ones; a class without methods has no table
        rec = class_record([15], [], 0, [(0x16, 5, 0x3c)])
        self.assertEqual(rec[12:].hex(), '0001000f' + '80010000' + '160000050000003c')
        self.assertEqual(class_record([3, 0x17, 0x18], [], 0).hex(), '000c00000000000000000000' + '0003000300170018')

    @unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
    def test_digiclock_assembles(self):
        import json
        from build_digiclock import main
        from link_package_methods import ROOT
        main()
        m = json.loads((ROOT / 'out/rosemary-digiclock/package-manifest.json').read_text())
        self.assertEqual(m['class_selectors']['Digitalis'], 18)
        self.assertEqual(m['exports'], [['class', '@Digitalis', 1, 18], ['locator', '@iDigitalis', 1, 28]])
        self.assertEqual(m['function_table'][:2], [None, None])
        self.assertEqual(len(m['function_table']), 7)
        self.assertEqual(m['references']['__2d_Draw'], '__disp2_1')

    @unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
    def test_rulessample_cluster_operation_range(self):
        # The loader maps package operation selectors through the cluster's
        # operationBase1/operationCount (corpus: CujoChat 5047/80); without
        # them the init script's kind-3 @Op lookups resolve to component 0.
        import json
        from build_sample import build_sample
        from link_package_methods import ROOT
        from inspect_format import inspect
        out = ROOT / 'out/rosemary-test-rulessample'
        build_sample(ROOT / 'sdk/mips/Samples/RulesSample', 'RulesSample', out)
        m = json.loads((out / 'package-manifest.json').read_text())
        ops = {k: v for k, v in m['operation_selectors'].items()}
        first = min(v for k, v in ops.items() if ['operation', '@' + k, 1, v] in m['exports'])
        count = sum(1 for e in m['exports'] if e[0] == 'operation')
        self.assertEqual((first, count), (8, 10))
        data = (out / 'RulesSample.pkg').read_bytes()
        package = inspect(data)['packages'][0]
        defined = [r for r in package['records'] if 'defined_components' in r][0]['defined_components']['entries']
        self.assertEqual([(e['kind'], e['selector_start'], e['count']) for e in defined], [('class', 36, 4), ('operation', 8, 10)])
        root = [r for r in package['records'] if 'heap' in r][0]['heap']['objects'][0]
        body = data[root['body']['offset']:root['body']['offset'] + root['body']['length']]
        # classBase1/classCount at bits 1120/1184, operationBase1/operationCount at 1216/1280
        words = [int.from_bytes(body[i:i + 4], 'big') for i in range(0, len(body), 4)]
        self.assertEqual((words[35], words[37], words[38], words[40]), (36, 4, 8, 10))


    @unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
    def test_code_free_scenes(self):
        # objects only: PackageCluster root, no function-offsets/code/init attributes (CujoChat pkg 1)
        from build_sample import build_sample
        from link_package_methods import ROOT, SDK
        from inspect_format import inspect
        out = ROOT / 'out/rosemary-test-scenes'
        raw, m = build_sample(SDK / 'Samples/Scenes', 'Scenes', out)
        package = inspect(raw)['packages'][0]
        self.assertEqual([r['attribute_kind'] for r in package['records']],
                         ['imports', 'abbreviated-classes', 'object-addressing', 'heap'])
        self.assertEqual(m['function_table'], [])
        self.assertIn('PackageCluster', m['class_selectors'])
        self.assertNotIn('CodePackageCluster', m['class_selectors'])


if __name__ == '__main__':
    unittest.main()
