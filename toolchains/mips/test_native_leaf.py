import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from build_native_leaf import extract_leaf
from inspect_format import FormatError


@unittest.skipUnless(shutil.which('clang-18'), 'clang-18 required for native leaf validation')
class NativeLeafTests(unittest.TestCase):
    def compile(self, source):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'probe.o'
            subprocess.run(['clang-18', '--target=mips-unknown-elf', '-march=mips1', '-mabi=32', '-msoft-float',
                            '-mno-abicalls', '-fno-pic', '-ffreestanding', '-fno-builtin', '-fomit-frame-pointer',
                            '-G0', '-O2', '-x', 'c', '-c', '-', '-o', str(path)], input=source,
                           text=True, capture_output=True, check=True)
            return path.read_bytes()

    def test_leaf_code(self):
        data = self.compile('unsigned char rosemary_can_go_to(void *p) { return 1; }')
        self.assertEqual(extract_leaf(data), bytes.fromhex('03e0000824020001'))

    def test_relocations_rejected(self):
        data = self.compile('extern unsigned char external(void); unsigned char rosemary_can_go_to(void *p) { return external(); }')
        with self.assertRaisesRegex(FormatError, 'relocations'):
            extract_leaf(data)

    def test_wrong_elf_kind_rejected(self):
        data = bytearray(self.compile('unsigned char rosemary_can_go_to(void *p) { return 1; }'))
        struct.pack_into('>H', data, 16, 2)
        with self.assertRaises(FormatError):
            extract_leaf(data)


if __name__ == '__main__':
    unittest.main()
