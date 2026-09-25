"""The 68k source adapter must preserve the existing game's rules and assets."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from build import SAMPLE, rules_c, stage


class PortTests(unittest.TestCase):
    def test_native_package(self):
        from build import build_example, resolve
        from compile_example import CLANG, GCC
        self.assertIn('-ffixed-a5', CLANG)
        self.assertIn('-ffixed-a5', GCC)
        with tempfile.TemporaryDirectory(prefix='soko68k-package-') as tmp:
            root=Path(tmp); stage(root)
            for profile in ('1.0', '1.5'):
                with self.subTest(profile=profile):
                    package,missing=build_example(root,interfaces=resolve(profile),compiler='gcc',report=True)
                    self.assertFalse(missing)
                    self.assertGreater(len(package),4000)
                    self.assertLess(len(package),20000)

    def test_rules_parity(self):
        with tempfile.TemporaryDirectory(prefix='soko68k-rules-') as tmp:
            root = Path(tmp)
            (root / 'rules.h').write_text(rules_c())
            # Compile as C as well as C++: the guest compiler uses GNU89.
            subprocess.run(['clang-18', '-std=gnu89', '-x', 'c', '-c',
                            str(root / 'rules.h'), '-o', str(root / 'rules.o')], check=True)
            test = r'''
#include "SokobanRules.h"
#undef SOKOBAN_RULES_H
#include "rules.h"
#include <cassert>
#include <cstring>
int main() {
    Soko::State original; Soko_State port;
    unsigned random=12345;
    for (int level=0;level<12;++level) {
        Soko::reset(original,level); Soko_reset(&port,level);
        for(int n=0;n<20000;++n) {
            assert(!memcmp(&original,&port,sizeof(port)));
            random=random*1664525u+1013904223u;
            unsigned op=random>>28;
            if(op<12) {
                int dx=op%4==0?1:op%4==1?-1:0;
                int dy=op%4==2?1:op%4==3?-1:0;
                assert(Soko::move(original,dx,dy)==Soko_move(&port,dx,dy));
            } else if(op==12) assert(Soko::undo(original)==Soko_undo(&port));
            else if(op==13) assert(Soko::advance(original)==Soko_advance(&port));
            else if(op==14) { Soko::reset(original,level); Soko_reset(&port,level); }
            else { // Exercise completion and wrap even when random walking cannot solve.
                int a=-1,b=-1;
                for(int p=0;p<48;++p) if(Soko::goal(level,p)) { if(a<0)a=p;else b=p; }
                original.level=port.level=level;
                original.boxA=port.boxA=a; original.boxB=port.boxB=b;
                assert(Soko::advance(original)==Soko_advance(&port));
            }
        }
    }
}
'''
            (root / 'test.cpp').write_text(test)
            subprocess.run(['g++','-std=c++98','-fsanitize=address,undefined','-g',
                            '-I',str(SAMPLE),str(root/'test.cpp'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

    def test_staged_assets(self):
        with tempfile.TemporaryDirectory(prefix='soko68k-source-') as tmp:
            root=Path(tmp); stage(root)
            objects=(root/'Objects.Def').read_text()
            self.assertIn('entry: iGameRoomShelf;',objects)
            self.assertIn("Instance Icon 'Magic Sokoban' 22;",objects)
            source=(SAMPLE/'Objects.odef').read_text()
            pixels=re.search(r'data: \$ ([0-9a-f]+);',source)[1]
            self.assertIn('extra: $ '+pixels+';',objects)
            self.assertIn('SokobanBoard_Draw(ObjectID self, ObjectID canvas, ObjectID clip)',
                          (root/'Sokoban.c').read_text())


if __name__ == '__main__':
    unittest.main()
