import shutil
import unittest
from pathlib import Path
from build_c_package import compile_and_link
from build_hello_package import build
from inspect_format import inspect
from link_package_methods import ROOT


@unittest.skipUnless(all(shutil.which(t) for t in ('clang-18', 'ld.lld-18', 'llvm-objdump-18')), 'LLVM 18 tools required')
class HelloPackageTests(unittest.TestCase):
    def test_hello_structure(self):
        here = Path(__file__).parent
        code, init, entry, extra = compile_and_link(here / 'hello.c', ROOT / 'out/rosemary-hello-test', 'HelloWorld', 'Greeter_Draw')
        raw, manifest = build(code, init, entry)
        parsed = inspect(raw)['packages'][0]
        self.assertEqual(len(parsed['heap_selectors']['objects']), 20)
        self.assertEqual(manifest['greeter_selector'], 156)
        self.assertEqual(manifest['names'][-1], 'Yo, world!')
        self.assertEqual(tuple(extra['stubs']['FillBox']), (1, 671))
        self.assertEqual(tuple(extra['stubs']['ContentBox']), (1, 37))
        attrs = {a['raw_tag_byte']: a for a in parsed['records']}
        kinds = [(e['kind'], e['raw_component_word']) for e in attrs[0x20]['imports']['entries']]
        self.assertIn(('class', 17), kinds)       # Viewable
        self.assertIn(('operation', 1), kinds)    # Draw


if __name__ == '__main__':
    unittest.main()
