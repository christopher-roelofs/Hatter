#!/usr/bin/env python3
"""Compile and extract one relocation-free native method; not a full linker."""
import hashlib
import json
import subprocess
from pathlib import Path
from inspect_format import require
from trace_linked_methods import read_elf
from link_package_methods import ROOT


def extract_leaf(data, symbol='rosemary_can_go_to'):
    sections, symbols = read_elf(data, expected_type=1)
    require(int.from_bytes(data[36:40], 'big') & 0xf0000000 == 0, 'native probe must be MIPS-I')
    matches = [(i, s) for i, s in enumerate(sections) if s['name'] == '.text']
    require(len(matches) == 1, 'expected one text section')
    index, section = matches[0]
    require(section['type'] == 1 and section['flags'] & 4 and section['size'] > 0, 'invalid text section')
    require(not any(s['type'] in (4, 9) and s['info'] == index and s['size'] for s in sections),
            'text relocations require a linker')
    matches = [s for s in symbols if s['name'] == symbol and s['type'] == 2 and s['section_index'] == index]
    require(len(matches) == 1, 'expected one native probe function')
    function = matches[0]
    start, size = function['address'], function['size']
    require(start % 4 == 0 and size > 0 and size % 4 == 0 and start + size <= section['size'], 'invalid method extent')
    require(not any(s['section_index'] == 0 and s['name'] for s in symbols), 'undefined symbols unsupported')
    require(not any(s['flags'] & 2 and s['size'] and s['name'] not in ('.text', '.reginfo', '.MIPS.abiflags') for s in sections),
            'additional allocated sections unsupported')
    code = data[section['offset'] + start:section['offset'] + start + size]
    return code


def main():
    source = Path(__file__).with_name('native_leaf.c')
    out = ROOT / 'out/rosemary-native-probe'
    out.mkdir(parents=True, exist_ok=True)
    obj = out / 'native_leaf.o'
    argv = ['clang-18', '--target=mips-unknown-elf', '-march=mips1', '-mabi=32', '-msoft-float',
            '-mno-abicalls', '-fno-pic', '-ffreestanding', '-fno-builtin', '-fomit-frame-pointer',
            '-G0', '-O2', '-c', str(source), '-o', str(obj)]
    result = subprocess.run(argv, capture_output=True, text=True)
    (out / 'compile.txt').write_text(result.stdout + result.stderr)
    result.check_returncode()
    data = obj.read_bytes()
    code = extract_leaf(data)
    (out / 'native_leaf.bin').write_bytes(code)
    disasm = subprocess.run(['llvm-objdump-18', '-dr', str(obj)], capture_output=True, text=True, check=True)
    (out / 'disassembly.txt').write_text(disasm.stdout)
    report = {'command': argv, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'elf_sha256': hashlib.sha256(data).hexdigest(), 'code_sha256': hashlib.sha256(code).hexdigest(),
              'code_bytes': len(code), 'code_hex': code.hex(), 'entry_offset': 0,
              'guest_executed': False, 'scope': 'one relocation-free leaf; not a general ABI/linker implementation'}
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
