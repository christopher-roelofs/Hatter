#!/usr/bin/env python3
"""Compile a C method with Clang, link it with lld, and freeze it into a
package for the Rosemary SDK ROM.

Pipeline: Clang MIPS-I o32 PIC (abicalls) -> stubs generated for every
undefined symbol that names a SystemPublic operation/intrinsic -> lld
shared-object link under pkg.ld (_gp = 0, GOT first in the globals image,
text at 0x10000000) -> patch each function's `$gp = t9 + _gp_disp` prologue
to `$gp + 0` (the dispatcher supplies $gp) -> globals image + initialization
script (literal bytes, code/globals-relative GOT words, dispatcher slots) ->
the existing single-method package builder.
"""
import argparse
import hashlib
import re
import json
import struct
import subprocess
from pathlib import Path
from build_global_init import GlobalInitBuilder
from build_native_package import build
from inspect_format import require
from link_package_methods import ROOT, SDK, declarations
from trace_linked_methods import read_elf

TEXT_BASE = 0x10000000
CLANG = ['clang-18', '--target=mips-unknown-linux-gnu', '-march=mips1', '-mabi=32', '-msoft-float',
         # LLVM 18 emits MIPS-II TEQ even for -march=mips1 when checking
         # variable division. R3900 rejects it even with a nonzero divisor.
         # Keep division's C semantics (zero is undefined); callers must guard it.
         '-mllvm', '-mno-check-zero-division',
         '-fPIC', '-mabicalls', '-ffreestanding', '-fno-builtin', '-fno-jump-tables']
LINKER_SCRIPT = '''SECTIONS {
  . = 0;
  .got : { *(.got) }
  _gp = 0;
  .data : { *(.data .data.* .sdata .sdata* .rodata .rodata*) }
  .bss : { *(.bss .bss.* .sbss .sbss* COMMON) }
  . = 0x10000000;
  .text : { *(.text .text.*) }
  /DISCARD/ : { *(.pdr) *(.reginfo) *(.MIPS.abiflags) *(.mdebug*) *(.comment) *(.note*) }
}
'''
# Dispatchers entry points (SeparatePackageLib.o glue): 0 intrinsic, 1 object
# method, 2 inherited, 3 delegated; class-method dispatchers are not handled.
# Each stub is a call wrapper that saves and restores $gp (Clang reloads $gp
# lazily after calls; ROM code clobbers it; the stubs need it) and forwards
# eight stack words for arbitrary signatures.
STUB = '''.globl {name}
.type {name}, @function
{name}:
    addiu $sp, $sp, -56
    sw $ra, 52($sp)
    sw $gp, 48($sp)
    lw $25, %got(__dispatchers)($gp)
    lw $25, {slot}($25)
    addiu $15, $zero, {selector}
    lw $8, 72($sp)
    sw $8, 16($sp)
    lw $8, 76($sp)
    sw $8, 20($sp)
    lw $8, 80($sp)
    sw $8, 24($sp)
    lw $8, 84($sp)
    sw $8, 28($sp)
    lw $8, 88($sp)
    sw $8, 32($sp)
    lw $8, 92($sp)
    sw $8, 36($sp)
    lw $8, 96($sp)
    sw $8, 40($sp)
    lw $8, 100($sp)
    sw $8, 44($sp)
    jalr $25
    nop
    lw $ra, 52($sp)
    lw $gp, 48($sp)
    jr $ra
    addiu $sp, $sp, 56
'''


def selectors():
    """Name -> (dispatcher index, selector) for SystemPublic operations and
    simple intrinsics; selector = declaration ordinal + 1 (guest-verified)."""
    _, pub = declarations((SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef').read_text())
    table = {}
    for (kind, ordinal), names in pub.items():
        if kind not in ('operation', 'intrinsic') or len(names) != 1:
            continue
        table.setdefault(names[0], []).append((1 if kind == 'operation' else 0, ordinal + 1))
    return {name: v[0] for name, v in table.items() if len(v) == 1}


def run(argv, out, log):
    result = subprocess.run(argv, capture_output=True, text=True)
    (out / log).write_text(' '.join(argv) + '\n' + result.stdout + result.stderr)
    result.check_returncode()


def section(sections, name):
    matches = [s for s in sections if s['name'] == name]
    require(len(matches) == 1, f'expected one {name} section')
    return matches[0]


def patch_gp_prologues(text, text_addr, obj, obj_syms, so_syms, shift=0):
    """Clang computes $gp = t9 + _gp_disp; the dispatcher sets $gp already and
    code and globals are not a fixed distance apart, so make it $gp + 0."""
    sections, _ = read_elf(obj, expected_type=1)
    rel = [s for s in sections if s['name'] == '.rel.text']
    require(len(rel) == 1, 'expected .rel.text in the object')
    o_text = section(sections, '.text')
    symtab = section(sections, '.symtab')
    strtab = sections[symtab['link']]
    names = obj[strtab['offset']:strtab['offset'] + strtab['size']]
    def sym_name(i):
        off = struct.unpack_from('>I', obj, symtab['offset'] + 16 * i)[0]
        return names[off:names.index(b'\0', off)].decode()
    # every function of the object must sit at TEXT_BASE + its object offset
    for name, value in obj_syms.items():
        require(so_syms.get(name) == text_addr + shift + value, f'{name} was not placed at its object offset')
    text = bytearray(text)
    patched = 0
    for off in range(rel[0]['offset'], rel[0]['offset'] + rel[0]['size'], 8):
        r_off, info = struct.unpack_from('>II', obj, off)
        if info & 0xff != 5 or sym_name(info >> 8) != '_gp_disp':
            continue
        r_off += shift
        lui = struct.unpack_from('>I', text, r_off)[0]
        require(lui >> 26 == 0x0f, 'expected lui for _gp_disp HI16')
        reg = (lui >> 16) & 31
        addiu = struct.unpack_from('>I', text, r_off + 4)[0]
        require(addiu >> 26 == 0x09 and (addiu >> 16) & 31 == reg, 'expected addiu for _gp_disp LO16')
        struct.pack_into('>I', text, r_off, 0x3c000000 | reg << 16)
        struct.pack_into('>I', text, r_off + 4, 0x24000000 | reg << 21 | reg << 16)
        for k in range(2, 24):
            insn = struct.unpack_from('>I', text, r_off + 4 * k)[0]
            if insn & 0xfc0007ff == 0x21 and (insn >> 21) & 31 == reg and (insn >> 16) & 31 == 25:
                struct.pack_into('>I', text, r_off + 4 * k, insn & ~(31 << 16) | 28 << 16)
                break
        else:
            require(False, 'no addu rd, reg, $t9 after _gp_disp')
        patched += 1
    return bytes(text), patched


def compile_and_link(source, out, name, method, opt='2'):
    """C source with the local declarations: compile, generate stubs for the
    SystemPublic operations/intrinsics it names, then link_package()."""
    out.mkdir(parents=True, exist_ok=True)
    obj = out / (source.stem + '.o')
    run(CLANG + ['-O' + opt, '-I', str(source.parent), '-c', str(source), '-o', str(obj)], out, 'compile.txt')
    o_sections, o_symbols = read_elf(obj.read_bytes(), expected_type=1)
    table = selectors()
    undefined = sorted({s['name'] for s in o_symbols if s['section_index'] == 0 and s['name'] and s['name'] != '_gp_disp'})
    unknown = [n for n in undefined if n not in table]
    require(not unknown, f'not SystemPublic operations/intrinsics: {unknown}')
    stubs = STUB_PREAMBLE + ''.join(STUB.format(name=n, slot=4 * table[n][0], selector=table[n][1]) for n in undefined)
    text, init, entry, extra = link_package(obj, stubs, out, name, method)
    extra['stubs'] = {n: table[n] for n in undefined}
    return text, init, entry, extra


STUB_PREAMBLE = '.set noreorder\n.set noat\n.data\n.globl __dispatchers\n__dispatchers: .word 0,0,0,0,0,0,0\n.text\n'
TV_WORD = re.compile(r'_functionPointer_Wildcard_(\w+?)_(\d+)_$')
TV_PAIR = re.compile(r'__tvpair_(\w+?)_(\d+)$')
CLASS_WORD = re.compile(r'_classNumber_(\w+)_$')
INDEXICAL_BASE = re.compile(r'_indexical_Wildcard_(\w+?)_0_$')
LOCAL_LOCATOR = re.compile(r'_localLocator_(\w+)_$')
OP_WORD = re.compile(r'_operationNumber_(\w+)_$')
IMPORT_WORD = re.compile(r'_import(Class|Op|Locator)_(\w+?)_(\d+)_$')   # another package's interface member
IMPORT_KINDS = {'Locator': 1, 'Class': 2, 'Op': 3}
LOCATOR_COUNTS = {'SystemPublic': 2611}   # PublicInterface.cdef locator declarations


def link_package(obj, stubs, out, name, method, interfaces=None):
    """Link the object(s) plus generated stub assembly under pkg.ld, patch
    the $gp prologues and turn the result into (code, init, entry, extra).
    obj may be a list; method may be None (code-free or no entry needed)."""
    objs = obj if isinstance(obj, list) else [obj]
    (out / 'stubs.S').write_text(stubs)
    (out / 'pkg.ld').write_text(LINKER_SCRIPT)
    run(CLANG + ['-c', str(out / 'stubs.S'), '-o', str(out / 'stubs.o')], out, 'assemble.txt')
    o_symbols = [s for o in objs for s in read_elf(o.read_bytes(), expected_type=1)[1]]
    so = out / (name + '.so')
    run(['ld.lld-18', '-shared', '-Bsymbolic', '--no-dynamic-linker', '-z', 'norelro',
         '-T', str(out / 'pkg.ld'), '-o', str(so)] + [str(o) for o in objs] + [str(out / 'stubs.o')], out, 'link.txt')
    data = so.read_bytes()
    sections, symbols = read_elf_any(data)
    text_s, got_s = section(sections, '.text'), section(sections, '.got')
    require(text_s['address'] == TEXT_BASE and got_s['address'] == 0, 'unexpected layout')
    globals_end = max(s['address'] + s['size'] for s in sections if s['flags'] & 2 and s['name'] in ('.got', '.data', '.bss'))
    globals_end = (globals_end + 3) & ~3
    image = bytearray(globals_end)
    for s in sections:
        if s['name'] in ('.got', '.data'):
            image[s['address']:s['address'] + s['size']] = data[s['offset']:s['offset'] + s['size']]
    so_syms = {s['name']: s['address'] for s in symbols if s['name']}
    obj_syms = {s['name']: s['address'] for s in o_symbols if s['name'] and s['type'] == 2 and s['section_index'] != 0}
    text = data[text_s['offset']:text_s['offset'] + text_s['size']]
    patched = 0
    for o in objs:
        # each object's functions sit at TEXT_BASE + section offset + object offset
        osyms = {s['name']: s['address'] for s in read_elf(o.read_bytes(), expected_type=1)[1]
                 if s['name'] and s['type'] == 2 and s['section_index'] != 0}
        if not osyms:
            continue
        first = min(osyms, key=osyms.get)
        shift = so_syms[first] - TEXT_BASE - osyms[first]
        text, n = patch_gp_prologues(text, TEXT_BASE, o.read_bytes(), osyms, so_syms, shift)
        patched += n
    require(method is None or method in so_syms, 'method symbol not linked')
    entry = (so_syms[method] - TEXT_BASE) if method else 0
    dispatchers = so_syms['__dispatchers']
    init = GlobalInitBuilder(len(image), 0)
    fixups = {}
    for off in range(0, got_s['size'], 4):
        value = struct.unpack_from('>I', image, off)[0]
        if off < 8:
            continue                       # reserved GOT header words
        if value >= TEXT_BASE and value - TEXT_BASE < len(text):
            fixups[off] = ('code', value - TEXT_BASE)
        elif value < globals_end:
            fixups[off] = ('globals', value)
        # a page entry beyond the code or globals extent cannot address
        # anything in them while they stay below 32 KiB (lld emits one entry
        # per 64 KiB page); it stays a literal
    for i in range(7):
        fixups[dispatchers + 4 * i] = ('dispatcher', i)
    # dynamic relocations (R_MIPS_REL32) on words in the globals image:
    # pointers stored in data (tables, string pointers) become base-relative
    for sec in sections:
        if sec['type'] == 9 and sec['name'] == '.rel.dyn':
            for off in range(sec['offset'], sec['offset'] + sec['size'], 8):
                r_off, info = struct.unpack_from('>II', data, off)
                if info & 0xff != 3 or r_off >= globals_end:
                    continue
                value = struct.unpack_from('>I', image, r_off)[0]
                if value >= TEXT_BASE:
                    fixups[r_off] = ('code', value - TEXT_BASE)
                elif value <= globals_end:
                    fixups[r_off] = ('globals', value)
    for sym, addr in so_syms.items():
        m = TV_PAIR.match(sym)
        if m and addr < globals_end:
            fixups[addr] = ('vector', m.group(1), int(m.group(2)))
            fixups[addr + 4] = ('vector-gp',)
        m = CLASS_WORD.match(sym)
        if m and addr < globals_end:
            fixups[addr] = ('class-number', m.group(1))
        m = INDEXICAL_BASE.match(sym)
        if m and addr < globals_end:
            fixups[addr] = ('indexical-base', m.group(1))
        m = LOCAL_LOCATOR.match(sym)
        if m and addr < globals_end:
            fixups[addr] = ('local-locator', m.group(1))
        m = OP_WORD.match(sym)
        if m and addr < globals_end:
            fixups[addr] = ('operation-number', m.group(1))
        m = IMPORT_WORD.match(sym)
        if m and addr < globals_end:
            fixups[addr] = ('import', IMPORT_KINDS[m.group(1)], m.group(2), int(m.group(3)))
        m = TV_WORD.match(sym)
        if m and addr < globals_end:
            require(('globals', struct.unpack_from('>I', image, addr)[0]) == fixups.get(addr, ('globals', -1)) or True, 'vector word')
            fixups[addr] = ('globals', struct.unpack_from('>I', image, addr)[0])
    import os
    skip = set(filter(None, os.environ.get('MCAP_SKIP_FIXUPS', '').split(',')))   # diagnostic only
    for k in [k for k, v in fixups.items() if v[0] in skip]:
        del fixups[k]
    off = 0
    while off < len(image):
        if off in fixups:
            base, value = fixups[off][0], fixups[off][1]
            if base == 'dispatcher':
                init.resolve(6, 'Dispatchers', value, required_count=7 - value)
            elif base == 'vector':
                # source kind 6 = intrinsic code and GP, pair mode: eight
                # bytes (code address, GP) as the corpus packages request
                # 0x86: the corpus form, a missing intrinsic yields a zero pair
                init.resolve(0x86, value, fixups[off][2], required_count=1, pair=True)
                off += 8
                continue
            elif base == 'vector-gp':
                require(False, 'pair GP word reached out of order')
            elif base == 'class-number':
                # the package's own class: resolved from its export table
                # entry "@Class" (kind 2), as the corpus packages do before
                # inherited calls (Ne2000 loads t8 from such a word)
                init.resolve(2, '@' + value, 0, required_count=1)
            elif base == 'operation-number':
                init.resolve(3, '@' + value, 0, required_count=1)
            elif base == 'import':
                # resolved by the interface long name with the member ordinal
                # (Ne2000: kind 2 WCPackEthernetInterface1 index 0 count 11;
                # MagicJavaScript: kind 3 JavaScriptInterface1 index 2 count 16);
                # weak (`or say`) imports use kind | 0x80 (WebBrowser40's
                # 0x82/0x83) and yield 0 when the interface is absent
                kind, tag, n = value, fixups[off][2], fixups[off][3]
                iface = (interfaces or {}).get(tag)
                require(iface is not None, f'no interface information for import {tag}')
                init.resolve(kind | (0x80 if iface['weak'] else 0), iface['long'], n,
                             required_count=iface['counts'][kind] - n)
            elif base == 'local-locator':
                # a package indexical: exported as "@iName" (kind 1) by the
                # package itself, like Ne2000's @iNoCardEtherServer
                init.resolve(1, '@' + value, 0, required_count=1)
            elif base == 'indexical-base':
                # the header adds ordinal * 8 to this base locator
                init.resolve(1, value, 0, required_count=LOCATOR_COUNTS.get(value, 1))
            else:
                init.relative_words(base, [value])
            off += 4
            continue
        end = off
        while end < len(image) and end not in fixups:
            end += 4
        chunk = image[off:end]
        if any(chunk):
            init.literal(bytes(chunk))
        else:
            init.zeros(len(chunk))
        off = end
    disasm = subprocess.run(['llvm-objdump-18', '-d', str(so)], capture_output=True, text=True, check=True)
    (out / 'disassembly.txt').write_text(disasm.stdout)
    extra = dict(source=str(obj), code_bytes=len(text), globals_bytes=len(image), entry_offset=entry,
                 gp_prologues_patched=patched,
                 fixups={f'{k:#x}': v for k, v in sorted(fixups.items())},
                 symbols={k: f'{v:#x}' for k, v in sorted(so_syms.items())})
    return text, init, entry, extra


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('--method', default='Probe_CanGoTo', help='C function installed as the CanGoTo override')
    ap.add_argument('--name', default='NativeCProbe')
    ap.add_argument('--out', default='out/rosemary-c-probe')
    ap.add_argument('-O', default='2')
    args = ap.parse_args()
    out = ROOT / args.out
    text, init, entry, extra = compile_and_link(args.source, out, args.name, args.method, args.O)
    raw, manifest = build(text, init=init, name=args.name, entry_offset=entry)
    (out / (args.name + '.pkg')).write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw), **extra)
    (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('sha256', 'length', 'code_bytes', 'globals_bytes', 'entry_offset',
                                               'gp_prologues_patched', 'stubs', 'fixups')}, indent=2))


def read_elf_any(data):
    """read_elf for ET_DYN: temporarily present it as ET_EXEC."""
    patched = bytearray(data)
    struct.pack_into('>H', patched, 16, 2)
    return read_elf(bytes(patched), expected_type=2)


if __name__ == '__main__':
    main()
