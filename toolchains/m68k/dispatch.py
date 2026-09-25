#!/usr/bin/env python3
"""Calling Magic Cap from C compiled here, rather than by CodeWarrior.

The nine cookbook examples that are not yet built from source all need a
`Code` object, and the obstacle is not the compiler. `clang-18` already
targets m68k. It is that the SDK's headers are written in an MPW dialect no
compiler here speaks: twelve and a half thousand declarations of the form

    void ResetVisitCount(ObjectID self)={0x343C,0x8001,0x4EAD,0xFFFA};

which is not a function but four instruction words to paste at the call site,
and `#pragma parameter _InheritedX(__D0)` for the ones that take a class
number in a register. So a package's code is not compiled against those
headers; it has to be compiled against something that produces the same
bytes.

This module says what that something is, and `--probe` checks it by compiling
and disassembling:

  * the four words go in as `.short`, because LLVM's m68k assembler does not
    accept `jsr -6(%a5)` -- it parses neither the displacement form nor
    `%sp`/`%a7` in `addq.l` -- while it assembles `.short` without complaint
    and the words are what the SDK states anyway;
  * the receiver is pushed with an ordinary `move.l ...,-(%sp)`, which clang
    emits from a `"d"` operand;
  * **the caller removes the arguments.** Counter's `UpdateDisplay` calls
    `VisitCount(self)` and the very next word is `584f`, `addq.w #4,a7`.
    Its `ResetVisitCount` looks at first like the callee cleans -- it
    pushes twice, calls twice and never touches the stack pointer -- but
    that is only the compiler leaving the whole frame to `unlk`. Inline asm
    cannot leave it to `unlk`, because clang does not know what was pushed,
    so a call written here pops its own arguments.

What clang emits for the probe is byte for byte the sequence Counter's own
`Code` object carries around its calls.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

#: The A5 slots, from the instruction words the SDK's headers carry. The
#: displacement is the whole identity of the call.
DISPATCH = 0xFFFA        # -6, selector in D2, receiver on the stack
INHERITED = 0xFFDA       # -38, class in D0 and operation in D2
INTRINSIC = 0xFFD0       # -48, intrinsic number in D0
DELEGATE = 0xFFBA        # -70, target class in D0
FAST_PATH = 0xFFE0       # -32, the direct table lookup

MOVE_W_IMM_D2 = 0x343C
MOVE_W_IMM_D0 = 0x303C
JSR_A5 = 0x4EAD


def call(selector, vector=DISPATCH):
    """The words a call to one operation compiles to."""
    return [MOVE_W_IMM_D2, selector, JSR_A5, vector]


def inline(words):
    """Those words as something LLVM's m68k assembler will take."""
    return '.short ' + ','.join(f'{w:#06x}' for w in words)


PROBE = '''
void CounterScene_ResetVisitCount(unsigned long self)
{
    __asm__ __volatile__(
        "move.l %0,-(%%sp)\\n\\t"
        "FIRST\\n\\t"
        "move.l %0,-(%%sp)\\n\\t"
        "SECOND"
        : : "d"(self) : "d0", "d1", "d2", "a0", "a1", "memory");
}
'''

CLANG = ['clang-18', '--target=m68k-unknown-linux', '-mcpu=M68000', '-O2',
         '-ffreestanding', '-fomit-frame-pointer', '-c']


def compile_probe(source, workdir):
    c = Path(workdir) / 'probe.c'
    o = Path(workdir) / 'probe.o'
    c.write_text(source)
    subprocess.run(CLANG + [str(c), '-o', str(o)], check=True,
                   capture_output=True)
    listing = subprocess.run(['llvm-objdump-18', '-d', str(o)],
                             check=True, capture_output=True, text=True).stdout
    body = []
    for line in listing.splitlines():
        match = re.match(r'\s*[0-9a-f]+:\s((?:[0-9a-f]{2} )+)', line)
        if match:
            body += [int(b, 16) for b in match.group(1).split()]
    return bytes(body)


def probe():
    source = (PROBE.replace('FIRST', inline(call(0x8004)))
                   .replace('SECOND', inline(call(0x8002))))
    with tempfile.TemporaryDirectory() as workdir:
        code = compile_probe(source, workdir)
    wanted = (bytes.fromhex('343c8004' '4eadfffa'),
              bytes.fromhex('343c8002' '4eadfffa'))
    return code, wanted


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args(argv)
    if not args.probe:
        parser.print_help()
        return 0
    code, wanted = probe()
    print(code.hex(' '))
    for want in wanted:
        where = code.find(want)
        found = f'at {where:#x}' if where >= 0 else 'MISSING'
        print(f'  {want.hex(chr(32))}: {found}')
    return 0 if all(w in code for w in wanted) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
