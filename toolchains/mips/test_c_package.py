import shutil
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path


@unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
class CPackageTests(unittest.TestCase):
    def test_variable_division_does_not_emit_mips2_traps(self):
        from build_c_package import CLANG
        # Both operations previously emitted TEQ even for valid divisors,
        # causing a reserved-instruction exception on the target CPU.
        source = ('int quotient(int a, int b) { return b ? a / b : 0; }\n'
                  'unsigned remainder(unsigned a, unsigned b) { return b ? a % b : 0; }\n')
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / 'division.o'
            subprocess.run(CLANG + ['-O2', '-x', 'c', '-c', '-', '-o', str(obj)],
                           input=source, text=True, check=True, capture_output=True)
            listing = subprocess.check_output(['llvm-objdump-18', '-d', str(obj)], text=True)
            self.assertRegex(listing, r'\bdiv\b')
            self.assertRegex(listing, r'\bdivu\b')
            self.assertNotRegex(listing, r'\b(?:teq|tne|tge|tgeu|tlt|tltu)\b')

    def test_c_probe_builds(self):
        here = Path(__file__).parent
        out = here.parent.parent / 'out/rosemary-c-probe-test'
        subprocess.run([sys.executable, str(here / 'build_c_package.py'), str(here / 'c_probe.c'),
                        '--out', str(out.relative_to(here.parent.parent))], check=True, capture_output=True)
        import json
        m = json.loads((out / 'package-manifest.json').read_text())
        self.assertEqual(m['stubs'], {'Honk': [0, 77], 'Name': [1, 4187], 'SetName': [1, 4188]})
        self.assertGreaterEqual(m['gp_prologues_patched'], 1)  # helper is inlined at -O2
        self.assertEqual(m['globals_bytes'], 0x50)
        self.assertIn(['dispatcher', 1], m['fixups'].values())
        self.assertTrue(any(v[0] == 'code' for v in m['fixups'].values()))


if __name__ == '__main__':
    unittest.main()
