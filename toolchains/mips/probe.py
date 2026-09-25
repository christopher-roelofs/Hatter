#!/usr/bin/env python3
"""Reproduce Linux code-generation checks; does not build an installable package."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clang', default='clang-18')
    parser.add_argument('--objdump', default='llvm-objdump-18')
    parser.add_argument('--output', type=Path, default=ROOT / 'out/rosemary-probe')
    args = parser.parse_args()
    compiler = shutil.which(args.clang)
    objdump = shutil.which(args.objdump)
    if not compiler or not objdump:
        parser.error('Clang with MIPS support and LLVM objdump are required')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sdk = ROOT / 'software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper'
    support = sdk / 'Libraries/Apollo/SeparatePackageLib.o'
    if not support.is_file():
        parser.error('extract software/mips/sdk/magicdeveloper.sit first')
    report = {'installable_package_built': False, 'guest_tested': False, 'commands': []}

    def run(command, log):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True)
        (out / log).write_text(result.stdout + result.stderr)
        report['commands'].append({'argv': [str(x) for x in command], 'exit_code': result.returncode, 'log': log})
        return result

    flags = ['--target=mips-unknown-elf', '-march=mips1', '-mabi=32',
             '-msoft-float', '-mno-abicalls', '-fno-pic']
    for filename in ['codegen.c', 'call_vector.S']:
        src = Path(__file__).resolve().parent / filename
        dest = out / (src.stem + '.o')
        options = ['-ffreestanding', '-fno-builtin', '-G0', '-O2'] if src.suffix == '.c' else []
        result = run([compiler, *flags, *options, '-c', src, '-o', dest], src.stem + '-compile.txt')
        if result.returncode:
            raise SystemExit(result.stderr)
        blob = dest.read_bytes()
        if blob[:6] != b'\x7fELF\x01\x02' or struct.unpack_from('>H', blob, 18)[0] != 8:
            raise SystemExit('probe output is not ELF32 big-endian MIPS')
        if struct.unpack_from('>I', blob, 36)[0] & 0xf0000000:
            raise SystemExit('probe output does not advertise MIPS-I')
        result = run([objdump, '-dr', dest], src.stem + '-disassembly.txt')
        if result.returncode:
            raise SystemExit(result.stderr)
    run([compiler, '--version'], 'compiler-version.txt').check_returncode()
    unsupported = run([compiler, *flags, '-membedded-pic', '-mtransition-vectors',
                       '-x', 'c', '-c', '/dev/null', '-o', out / 'legacy-options.o'], 'legacy-options.txt')
    report['legacy_flags_accepted'] = unsupported.returncode == 0
    run([objdump, '-dr', support], 'sdk-support-disassembly.txt').check_returncode()
    report['sdk_support_sha256'] = hashlib.sha256(support.read_bytes()).hexdigest()
    report['probe_outputs'] = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                               for name in ['codegen.o', 'call_vector.o']}
    for relative in ['Samples/HelloWorld/HelloWorld.make', 'Scripts/SelectCompiler',
                     'Scripts/SelectTarget', 'Scripts/LinkerScriptSeparatePackage']:
        src = sdk / relative
        (out / (src.name + '.txt')).write_text(src.read_bytes().decode('mac_roman').replace('\r', '\n'))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'ELF32 big-endian MIPS-I probes built; evidence in {out}')
    print(f'Legacy compiler flags accepted: {report["legacy_flags_accepted"]}')
    print('No installable package produced; no guest execution performed.')


if __name__ == '__main__':
    main()
