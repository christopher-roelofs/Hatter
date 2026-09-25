#!/usr/bin/env python3
"""Compile an unmodified SDK package source (.cpp with Magic.h and the
generated MagicCap.gnu.xh) with Clang and freeze it.

The SDK's GNU header expresses an operation call as a pseudo-function
`__1d_Op(dispatcher, operation, self, ...)` that the historical GCC lowered
to `t7 = operation; jump dispatcher`.  Here each `__1d_*` symbol is an
alias of an argument-shifting stub `__dispN` (N = callee arguments), the
`__Dispatch*` symbols are glue that jump through the loader-filled
dispatcher slots, and intrinsic calls, rewritten by sdk_headers.py to
`__tv_<Interface>_<index>`, go through a stub that loads code and GP from
the ROM transition vector whose address the loader stores in
`_functionPointer_Wildcard_<Interface>_<index>_`.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from build_c_package import CLANG, run, link_package, STUB_PREAMBLE
from inspect_format import require
from link_package_methods import ROOT
from sdk_headers import OUT as HEADERS, derive
from trace_linked_methods import read_elf

SDK_FLAGS = ['-x', 'c++', '-std=gnu++98', '-fpermissive', '-w', '-fno-exceptions', '-fno-rtti',
             '-DALLOW_TRANSITION_VECTOR_DEFINES', '-DROSEMARY_BRINGUP', '-DCORE_DINO', '-DPLATFORM_Apollo',
             '-DDINO_APOLLO', '-DBOOT_FROM_ROM', '-DINCLUDE_QUALITY_EXTRAS', '-DMAGIC_CAP', '-DCAP_SEPARATE_PACKAGE']
DISPATCHERS = {'__DispatchIntrinsic': 0, '__DispatchObjectMethod': 1,
               '__DispatchInheritedObjectMethod': 2, '__DispatchDelegatedObjectMethod': 3,
               '__DispatchClassMethod': 4, '__DispatchInheritedClassMethod': 5, '__DispatchDelegatedClassMethod': 6}
PROTO = re.compile(r'__1d_(\w+)\(([^)]*)\)\s*;')


def prototypes(headers):
    """Name -> callee argument count for every __1d_ pseudo-function."""
    counts = {}
    for path in headers:
        for name, params in PROTO.findall(path.read_text(encoding='latin1')):
            n = len([p for p in params.split(',') if p.strip()]) - 2
            require(counts.setdefault(name, n) == n, f'conflicting prototypes for {name}')
    return counts


def wrapped(name, moves, stack_words, extra_args=0):
    """A stub that calls into the ROM and returns, saving and restoring $gp
    (and $ra) around the call.  Clang, unlike the GCC that built the SDK
    library, does not restore $gp after every call (it keeps a copy in a
    callee-saved register and reloads $gp lazily), while ROM code clobbers
    $gp and every stub locates package globals through it; ExportSample's
    second CopyNear crashed on that.  moves: register setup lines before the
    call ($25 = target); stack_words: (from, to) pairs copying the caller's
    outgoing words into this frame's outgoing area; extra_args: outgoing
    words beyond the four-word home area."""
    outgoing = 16 + 4 * extra_args
    frame = (outgoing + 8 + 7) & ~7
    lines = [f'.globl {name}', f'.type {name}, @function', f'{name}:',
             f'    addiu $sp, $sp, -{frame}', f'    sw $ra, {frame - 4}($sp)', f'    sw $gp, {frame - 8}($sp)']
    lines += moves
    for src, dst in stack_words:
        lines += [f'    lw $8, {frame + src}($sp)', '    nop', f'    sw $8, {dst}($sp)']
    lines += ['    jalr $25', '    nop', f'    lw $ra, {frame - 4}($sp)', f'    lw $gp, {frame - 8}($sp)',
              '    jr $ra', f'    addiu $sp, $sp, {frame}', '']
    return '\n'.join(lines)


def shift_stub(n):
    """__dispN: (dispatcher, operation, self, ...) -> t7 = operation, then
    the callee's o32 arguments: registers from a2/a3 and the caller's
    stack, stack arguments 4.. moved down two slots."""
    moves = ['    move $15, $5', '    move $25, $4', '    move $4, $6', '    move $5, $7']
    # the caller's stack words sit above our frame: (frame + 16 + 4k)
    if n > 2: moves.append('    lw $6, {F}+16($sp)')
    if n > 3: moves.append('    lw $7, {F}+20($sp)')
    extra = max(0, n - 4)
    frame = (16 + 4 * extra + 8 + 7) & ~7
    moves = [m.replace('{F}', str(frame)) for m in moves]
    return wrapped(f'__disp{n}', moves, [(4 * (i + 2), 4 * i) for i in range(4, n)], extra)


def shift2_stub(n):
    """__disp2_N for inherited/delegated calls: (dispatcher, operation,
    class, self, ...) -> t7 = operation, t8 = class number (the ROM's
    DispatchObjectMethodCommon passes $24 as the class), arguments shifted
    down three slots."""
    moves = ['    move $15, $5', '    move $24, $6', '    move $25, $4', '    move $4, $7']
    if n > 1: moves.append('    lw $5, {F}+16($sp)')
    if n > 2: moves.append('    lw $6, {F}+20($sp)')
    if n > 3: moves.append('    lw $7, {F}+24($sp)')
    extra = max(0, n - 4)
    frame = (16 + 4 * extra + 8 + 7) & ~7
    moves = [m.replace('{F}', str(frame)) for m in moves]
    return wrapped(f'__disp2_{n}', moves, [(4 * (i + 3), 4 * i) for i in range(4, n)], extra)


def data_word(name):
    return f'.data\n.globl {name}\n{name}: .word 0\n.text\n'


FORWARDED_STACK_WORDS = 8     # intrinsic/dispatcher glue: arbitrary signatures, forward eight stack words


def glue(name, index):
    moves = ['    lw $25, %got(__dispatchers)($gp)', '    nop', f'    lw $25, {4 * index}($25)']
    return wrapped(name, moves, [(16 + 4 * k, 16 + 4 * k) for k in range(FORWARDED_STACK_WORDS)], FORWARDED_STACK_WORDS)


def tv_stub(iface, index):
    """The SDK library reads _functionPointer_Wildcard_X_ as a pointer to an
    eight-byte (code, GP) transition vector; the loader fills such local
    pairs with the pair-mode resolution seen throughout the corpus."""
    word = f'_functionPointer_Wildcard_{iface}_{index}_'
    pair = f'__tvpair_{iface}_{index}'
    moves = [f'    lw $25, %got({word})($gp)', '    nop', '    lw $25, 0($25)', '    nop',
             '    lw $24, 4($25)', '    lw $25, 0($25)', '    move $gp, $24']
    data = f'.data\n.balign 8\n.globl {pair}\n{pair}: .word 0, 0\n.globl {word}\n{word}: .word {pair}\n.text\n'
    return data + wrapped(f'__tv_{iface}_{index}', moves,
                          [(16 + 4 * k, 16 + 4 * k) for k in range(FORWARDED_STACK_WORDS)], FORWARDED_STACK_WORDS)


def compile_sdk(source, out, name, method, opt='2', package_headers=None, runtime=False, interfaces=None):
    if not (HEADERS / 'Magic.h').exists():
        derive()
    out.mkdir(parents=True, exist_ok=True)
    inc = ['-I', str(out), '-I', str(HEADERS), '-I', str(HEADERS / 'Apollo'),
           '-I', str(HEADERS / 'Apollo/ExtraInterfaces'), '-I', str(HEADERS / 'MipsHeaders')]
    if package_headers:
        inc = ['-I', str(package_headers)] + inc
    sources = source if isinstance(source, list) else [source]
    objs, symbols = [], []
    for src_path in sources:
        text = src_path.read_bytes().decode('latin1').replace('\r\n', '\n').replace('\r', '\n')
        src = out / src_path.name
        src.write_text(text, encoding='latin1')
        obj = out / (src_path.stem + '.o')
        # Source is staged in out; quoted project headers still live beside
        # the original translation unit (as with a normal compiler invocation).
        run(CLANG + SDK_FLAGS + inc + ['-iquote', str(src_path.parent.resolve()),
            '-O' + opt, '-c', str(src), '-o', str(obj)], out, f'compile-{src_path.stem}.txt')
        objs.append(obj)
        symbols += read_elf(obj.read_bytes(), expected_type=1)[1]
    defined = {s['name'] for s in symbols if s['section_index'] != 0}
    if runtime and any(re.match(r'(Read|Write)\w+Field$|BeginModifyFlavor|PeekFlavor|PeekUsableFlavor', s['name']) for s in symbols if s['section_index'] == 0 and s['name'] not in defined):
        # the field accessor runtime (SeparatePackageLib.o port), only when referenced
        rt = Path(__file__).with_name('mcap_accessors.cpp')
        obj = out / 'mcap_accessors.o'
        run(CLANG + SDK_FLAGS + inc + ['-O' + opt, '-c', str(rt), '-o', str(obj)], out, 'compile-mcap_accessors.txt')
        objs.append(obj)
        symbols += read_elf(obj.read_bytes(), expected_type=1)[1]
        defined = {s['name'] for s in symbols if s['section_index'] != 0}
    symbols = [s for s in symbols if s['name'] not in defined or s['section_index'] != 0]
    undefined = sorted({s['name'] for s in symbols if s['section_index'] == 0 and s['name'] and s['name'] != '_gp_disp'})
    counts = prototypes(list((HEADERS / 'Apollo').glob('*.xh')) + (list(package_headers.glob('*.xh')) if package_headers else []))
    stubs, shifts, shifts2, used = STUB_PREAMBLE, set(), set(), {}
    for sym in undefined:
        if sym in DISPATCHERS:
            stubs += glue(sym, DISPATCHERS[sym]); used[sym] = 'glue'
        elif sym.startswith('__1d_'):
            n = counts.get(sym[5:])
            require(n is not None, f'no prototype for {sym}')
            shifts.add(n)
            stubs += f'.globl {sym}\n.set {sym}, __disp{n}\n'; used[sym] = f'__disp{n}'
        elif sym.startswith('__2d_'):
            n = counts.get(sym[5:])
            require(n is not None, f'no prototype for {sym}')
            shifts2.add(n)
            stubs += f'.globl {sym}\n.set {sym}, __disp2_{n}\n'; used[sym] = f'__disp2_{n}'
        elif sym.startswith(('_classNumber_', '_indexical_Wildcard_', '_localLocator_', '_operationNumber_',
                             '_importClass_', '_importOp_', '_importLocator_')):
            stubs += data_word(sym); used[sym] = 'loader-resolved word'
        elif sym.startswith('__tv_'):
            iface, index = sym[5:].rsplit('_', 1)
            stubs += tv_stub(iface, int(index)); used[sym] = f'vector {iface} {index}'
        else:
            require(False, f'unsupported reference {sym} (inherited/delegated calls and package classes are not handled yet)')
    for n in sorted(shifts):
        stubs += shift_stub(n)
    for n in sorted(shifts2):
        stubs += shift2_stub(n)
    text, init, entry, extra = link_package(objs, stubs, out, name, method, interfaces)
    extra.update(source=[str(p) for p in sources], source_sha256=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources],
                 references=used, header_edits=str(HEADERS / 'edits.json'))
    return text, init, entry, extra


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('--method', required=True)
    ap.add_argument('--name', default='SdkProbe')
    ap.add_argument('--out', default='out/rosemary-sdk-probe')
    ap.add_argument('--package-headers', type=Path)
    args = ap.parse_args()
    out = ROOT / args.out
    text, init, entry, extra = compile_sdk(args.source, out, args.name, args.method, package_headers=args.package_headers)
    (out / 'link-manifest.json').write_text(json.dumps(extra, indent=2) + '\n')
    print(json.dumps({k: extra[k] for k in ('code_bytes', 'globals_bytes', 'entry_offset', 'references', 'fixups')}, indent=2))


if __name__ == '__main__':
    main()
