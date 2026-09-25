import shutil
import unittest
from build_sdk_package import shift_stub, shift2_stub, prototypes, compile_sdk
from link_package_methods import ROOT, SDK
from sdk_headers import derive, OUT


class SdkPackageTests(unittest.TestCase):
    def test_shift_stub_moves_stack_arguments(self):
        # a gp-preserving wrapper: frame of 16 (home) + 4 (fifth argument) + 8 (ra, gp)
        # rounded to 32; the caller's fifth argument sits at 32 + 24
        s = shift_stub(5)
        self.assertIn('addiu $sp, $sp, -32', s)
        self.assertIn('lw $8, 56($sp)', s)
        self.assertIn('sw $8, 16($sp)', s)
        self.assertNotIn('lw $8, 60($sp)', s)
        self.assertIn('sw $gp, 24($sp)', s)
        self.assertIn('lw $gp, 24($sp)', s)
        self.assertIn('jalr $25', s)
        self.assertNotIn('sw $8', shift_stub(2))

    def test_shift_stub_moves_multiple_stack_arguments(self):
        s = shift_stub(7)
        # The first two callee arguments occupy a2/a3; the remaining three
        # are copied into the callee's outgoing area in order.
        self.assertIn('lw $8, 64($sp)', s)
        self.assertIn('sw $8, 16($sp)', s)
        self.assertIn('lw $8, 68($sp)', s)
        self.assertIn('sw $8, 20($sp)', s)
        self.assertIn('lw $8, 72($sp)', s)
        self.assertIn('sw $8, 24($sp)', s)

    @unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
    def test_headers_and_helloworld(self):
        edits = derive()
        self.assertEqual(edits['Apollo/MagicCap.gnu.xh']['tv-call to stub'], edits['Apollo/MagicCap.gnu.xh']['tv-stub declaration'])
        counts = prototypes([OUT / 'Apollo/MagicCap.gnu.xh'])
        self.assertEqual((counts['ContentBox'], counts['FillBox'], counts['Highlighted']), (2, 5, 1))
        out = ROOT / 'out/rosemary-hello-sdk-test'
        headers = out / 'pkgheaders'
        headers.mkdir(parents=True, exist_ok=True)
        for name in ('HelloWorld.xh', 'HelloWorld.xph'):
            (headers / name).write_text('')
        code, init, entry, extra = compile_sdk(SDK / 'Samples/HelloWorld/HelloWorld.cpp', out, 'HelloWorld', 'Greeter_Draw', package_headers=headers)
        self.assertEqual(extra['references']['__1d_FillBox'], '__disp5')
        self.assertEqual(extra['references']['__DispatchObjectMethod'], 'glue')
        vectors = [v for v in extra['fixups'].values() if v[0] == 'vector']
        self.assertEqual(sorted(v[2] for v in vectors), [425, 427])


if __name__ == '__main__':
    unittest.main()


class InheritedStubTests(unittest.TestCase):
    def test_shift2_stub(self):
        s = shift2_stub(4)
        self.assertIn('move $24, $6', s)          # class number -> t8
        self.assertIn('lw $7, 24+24($sp)', s)     # frame 24 + the caller's 24($sp)
        self.assertNotIn('sw $8', s)
        self.assertIn('sw $8, 16($sp)', shift2_stub(5))
        self.assertIn('lw $gp, 16($sp)', s)       # restored after the ROM call

    def test_inherited_stub_moves_multiple_stack_arguments(self):
        s = shift2_stub(7)
        self.assertIn('lw $8, 68($sp)', s)
        self.assertIn('sw $8, 16($sp)', s)
        self.assertIn('lw $8, 72($sp)', s)
        self.assertIn('sw $8, 20($sp)', s)
        self.assertIn('lw $8, 76($sp)', s)
        self.assertIn('sw $8, 24($sp)', s)

    def test_export_tables(self):
        from build_exports import export_tables
        from derive_fixed_formats import derive
        from inspect_format import inspect
        classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
                   if s['raw_tag'] == 13 for r in s['named_records']}
        bodies = export_tables({'PackageExportTable': derive('PackageExportTable', classes, {})},
                               {'exportEntries': 116, 'exportNames': 124}, [('class', '@Greeter', 1, 16)])
        self.assertEqual(bodies['exportEntries'].hex(), '00000001' + '00000000' + '02000000' + '00000001' + '00000010')
        self.assertEqual(bodies['exportNames'], bytes(8) + b'\x08@Greeter')
        self.assertTrue(bodies['exports'].endswith(bytes.fromhex('0400000100000001')))
