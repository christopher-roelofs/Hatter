#!/usr/bin/env python3
"""Assemble a ROM-call probe (rom_call.S by default) into a package."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from build_global_init import GlobalInitBuilder
from build_native_leaf import extract_leaf
from build_native_package import build
from link_package_methods import ROOT


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', default='rom_call.S')
    ap.add_argument('--name', default='NativeRomCall')
    ap.add_argument('--dispatchers', default='1',
                    help='comma-separated Dispatchers indices stored in globals words 0..n')
    ap.add_argument('--out', default='out/rosemary-rom-call')
    args = ap.parse_args()
    source = Path(__file__).with_name(args.source)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    obj = out / (source.stem + '.o')
    argv = ['clang-18', '--target=mips-unknown-elf', '-march=mips1', '-mabi=32', '-c', str(source), '-o', str(obj)]
    subprocess.run(argv, check=True)
    code = extract_leaf(obj.read_bytes())
    disasm = subprocess.run(['llvm-objdump-18', '-dr', str(obj)], capture_output=True, text=True, check=True)
    (out / 'disassembly.txt').write_text(disasm.stdout)
    # globals: one word per requested dispatcher entry point (7 exist; the
    # corpus requests the remaining count, 7 - index)
    indices = [int(x) for x in args.dispatchers.split(',')]
    init = GlobalInitBuilder(4 * len(indices), 0)
    for index in indices:
        init.resolve(6, 'Dispatchers', index, required_count=7 - index)
    raw, manifest = build(code, init=init, name=args.name)
    (out / (args.name + '.pkg')).write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw), source=str(source),
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), assemble=argv,
                    dispatcher_slots=indices)
    (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
