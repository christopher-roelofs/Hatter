#!/usr/bin/env python3
"""Compile an example's C the way CodeWarrior would have.

`magic_headers.py` rewrites the SDK's inline-code declarations into something
clang will take; this uses them. Give it an example directory and it
generates the headers, compiles the `.c` beside them, and hands back the
object file.

    python3 compile_example.py <example directory> [-o out.o] [--disassemble]

What comes out is not byte-identical to what CodeWarrior produced, and is not
meant to be: clang allocates registers differently and cleans the stack after
each call where CodeWarrior leaves it to `unlk`. What *is* identical is every
dispatch -- the selector, the vector, the order the arguments go on the
stack, and the class number in D0 for an inherited call. `--check` holds it
to that, against the `Code` object in the package the cookbook ships.

Two flags are not optional. `-std=gnu89` is because the examples are K&R C
(`main() {}`), and `-ffreestanding` because there is no C library here.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from inspect_package import SDK_INTERFACES
from profiles import header_directories
from magic_headers import convert, normalise, struct_types

#: The SDK's interfaces, in the order a package's includes reach them.
HEADER_DIRECTORIES = ('.', 'NoDebug', 'Device/Universal/NoDebug')

#: `-mcpu=M68020` rather than M68000, because the packages themselves use
#: the 32-bit `mulu.l` and `divu.l` the 68000 has not got -- BarChart carries
#: four and two of them -- so CodeWarrior was compiling for the CPU32 core
#: the MC68349 has. clang has no cpu32 to choose, and the 68020 is the
#: nearest superset; without it a divide becomes a call to `__udivsi3`, which
#: is a relocation into a library that is not there.

#: The examples are K&R C written for a compiler that let a good deal
#: through. `main() {}` has no return type; Circuits' `CircuitWire_SnapWire`
#: is declared non-void and writes a bare `return;`. None of that is this
#: toolchain's business to fix -- the sources are what they are, and MPW
#: compiled them -- so clang is told to be as permissive.
CLANG = ['clang-18', '--target=m68k-unknown-linux', '-mcpu=M68020',
         # Magic Cap dispatch vectors live below A5. Larger methods otherwise
         # make LLVM allocate it as an ordinary callee-saved local register,
         # so subsequent SDK inline calls jump through stack/data memory.
         '-ffixed-a5',
         '-ffreestanding', '-fomit-frame-pointer', '-std=gnu89',
         '-Wno-implicit-int', '-Wno-implicit-function-declaration',
         '-Wno-int-conversion', '-Wno-incompatible-pointer-types',
         '-Wno-return-type', '-ffunction-sections']

# GCC's CPU32 backend is an alternative for code that exercises LLVM 18's
# incomplete dynamic-index lowering. PC-relative code needs no loader fixups.
GCC = ['m68k-linux-gnu-gcc', '-mcpu=cpu32', '-mpcrel', '-ffixed-a5',
       '-ffreestanding', '-fomit-frame-pointer', '-std=gnu99',
       '-fno-jump-tables', '-ffunction-sections']


def generate_headers(into, extra=(), interfaces=SDK_INTERFACES):
    """The SDK's headers, rewritten, plus an example's generated ones."""
    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    sources, seen = {}, set()
    for directory in header_directories(interfaces):
        for path in sorted(directory.glob('*.h')):
            if path.name not in seen:
                seen.add(path.name)
                sources[path.name] = normalise(path)
    for path in extra:
        sources[Path(path).name] = normalise(Path(path))
    structs = struct_types(sources.values())
    rewritten = 0
    for name, text in sources.items():
        out, count, _ = convert(text, structs)
        (into / name).write_text(out)
        rewritten += count
    return rewritten


def compile_source(source, headers, output, optimise='1', includes=(), compiler='clang'):
    command = {'clang': CLANG, 'gcc': GCC}[compiler] + [f'-O{optimise}', '-I', str(headers)]
    for directory in includes:
        command += ['-I', str(directory)]
    command += ['-c', str(source), '-o', str(output)]
    return subprocess.run(command, capture_output=True, text=True)


def build(example, output, workdir=None, optimise='1', interfaces=SDK_INTERFACES, compiler='clang'):
    """One example compiled, with its own generated interfaces included.

    An example with several `.c` files also has headers of its own beside
    them -- Circuits includes `Circuit1.h` -- so its own directory is
    normalised into the same place the rewritten SDK goes and put on the
    include path. Each source is compiled to its own object; a package's
    `Code` is the lot of them, in the order the project builds them.
    """
    example = Path(example)
    sources = sorted(example.glob('*.c'))
    if not sources:
        raise FileNotFoundError(f'no C in {example}')
    package_interfaces = sorted((example / 'PackageInterfaces').glob('*.h'))
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(workdir or temporary)
        headers = root / 'headers'
        generate_headers(headers, extra=package_interfaces,
                        interfaces=interfaces)
        # The example's own headers are Macintosh text as well.
        own = root / 'own'
        own.mkdir(parents=True, exist_ok=True)
        for path in example.glob('*.h'):
            (own / path.name).write_text(normalise(path))
        objects, results = [], []
        for index, source in enumerate(sources):
            normalised = root / source.name
            normalised.write_text(normalise(source))
            target = (Path(output) if len(sources) == 1
                      else Path(output).with_suffix(f'.{index}.o'))
            results.append(compile_source(normalised, headers, target,
                                          optimise, includes=(own,), compiler=compiler))
            objects.append(target)
    failed = [r for r in results if r.returncode]
    result = failed[0] if failed else results[0]
    result.objects = objects
    return result


#: `move.w #selector,d2` then `jsr d16(a5)`, which is the whole of a call.
CALL = re.compile(rb'\x34\x3c(..)\x4e\xad(..)', re.S)
#: `moveq #selector,d2`, where the selector is small enough to fit.
SMALL_CALL = re.compile(rb'\x74(.)\x4e\xad(..)', re.S)


def calls(code):
    """Every dispatch in a run of 68k, as (selector, vector)."""
    import struct
    out = []
    for match in CALL.finditer(code):
        out.append((struct.unpack('>H', match.group(1))[0],
                    struct.unpack('>H', match.group(2))[0]))
    for match in SMALL_CALL.finditer(code):
        out.append((match.group(1)[0],
                    struct.unpack('>H', match.group(2))[0]))
    return out


def text_section(object_file):
    """The compiled code, out of the ELF clang writes.

    Through a file rather than a pipe: `llvm-objcopy` seeks in its output,
    so writing to `/dev/stdout` silently produces nothing.
    """
    with tempfile.TemporaryDirectory() as temporary:
        binary = Path(temporary) / 'text.bin'
        subprocess.run(['llvm-objcopy-18', '-O', 'binary',
                        '--only-section=.text', str(object_file),
                        str(binary)], check=True, capture_output=True)
        return binary.read_bytes()


#: The `Code` object is one run of bytes with nothing to fix up at load
#: time, so the objects are linked into one before anything else happens:
#: every reference the compiler left -- a string in `.rodata`, a jump table,
#: a call between two of the package's own procedures -- is resolved here,
#: which is the only place it can be.
#: GNU ld, not lld: `ld.lld-18` segfaults on an m68k object whatever it is
#: asked to do, and binutils for m68k is installed here anyway.
LINK = ['m68k-linux-gnu-ld', '-e', '0']
OBJCOPY = 'm68k-linux-gnu-objcopy'
READELF = 'm68k-linux-gnu-readelf'

LINKER_SCRIPT = """
SECTIONS
{
  . = 0;
  .text : { %s *(.text .text.*) *(.rodata .rodata.*) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
"""

TEXT_SECTION = re.compile(r'\[\s*\d+\]\s+(\.text\.\S+)')


def text_sections(objects):
    """Each procedure's own section, in the order the sources define them.

    `-ffunction-sections` is what makes the symbols below possible: without
    it the procedures are one run and nothing can be put between them.
    """
    out = []
    for path in objects:
        listing = subprocess.run([READELF, '-SW', str(path)],
                                 capture_output=True, text=True).stdout
        for section in TEXT_SECTION.findall(listing):
            if section not in out:
                out.append(section)
    return out


def macsbug(name):
    """The symbol MPW leaves after a procedure, padded the way it pads it.

    A byte of 0x80 or'd with the length, then the name, then zeros up to a
    multiple of four: Counter's `main` is eight bytes of code at 0x08 and
    `84 6d 61 69 6e 00 00 00` at 0x10, with the next procedure at 0x18.
    """
    body = name.encode('ascii', 'replace')[:0x7F]
    block = bytes([0x80 | len(body)]) + body
    return block + b'\0' * (-len(block) % 4)


def symbol_assembly(sections):
    """One section per symbol, for the linker to put after its procedure."""
    lines = ['.text']
    for section in sections:
        name = section[len('.text.'):]
        lines.append(f'\t.section .mbsym.{name},"a"')
        lines.append('\t.byte ' + ','.join(str(b) for b in macsbug(name)))
    return '\n'.join(lines) + '\n'


def link(objects, output, workdir=None, symbols=True):
    """The compiled objects as one blob, with nothing left to relocate.

    `.rodata` is laid down immediately after `.text` so that the
    PC-relative references into it -- Circuits' two strings -- resolve
    against a known distance rather than being left for a loader that has no
    way to fix them.

    The MacsBug symbols go in here rather than afterwards, for the same
    reason: putting them between the procedures once the link is done would
    move every procedure after the first, and the references between them
    are already resolved by then.
    """
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as temporary:
        root = Path(workdir or temporary)
        sections = text_sections(objects) if symbols else []
        objects = list(objects)
        if sections:
            source = root / 'symbols.s'
            source.write_text(symbol_assembly(sections))
            marked = root / 'symbols.o'
            subprocess.run(['m68k-linux-gnu-as', '-o', str(marked),
                            str(source)], check=True, capture_output=True)
            objects.append(marked)
        placed = ' '.join(f'*({section}) *(.mbsym.{section[len(".text."):]})'
                          for section in sections)
        script = root / 'code.ld'
        script.write_text(LINKER_SCRIPT % placed)
        elf = root / 'code.elf'
        result = subprocess.run(
            LINK + ['-T', str(script), '-o', str(elf)]
            + [str(o) for o in objects],
            capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        binary = Path(output)
        subprocess.run([OBJCOPY, '-O', 'binary', str(elf), str(binary)],
                       check=True, capture_output=True)
        left = subprocess.run([READELF, '-r', str(elf)],
                              capture_output=True, text=True).stdout
        relocations = 0 if 'no relocations' in left else sum(
            1 for line in left.splitlines() if line[:1].isdigit())
        return binary.read_bytes(), relocations, procedures(elf)


PROCEDURE = re.compile(r'^\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+FUNC\s+\S+\s+'
                       r'\S+\s+\S+\s+(\S+)', re.M)


def procedures(elf):
    """Where each procedure ended up, and how long it is.

    The method table in a class record wants an offset into the `Code`
    object for every method, and the linker is the only thing that knows
    where anything landed.
    """
    listing = subprocess.run([READELF, '-sW', str(elf)],
                             capture_output=True, text=True).stdout
    out = {}
    for address, size, name in PROCEDURE.findall(listing):
        out[name] = {'offset': int(address, 16), 'size': int(size)}
    return out


def package_calls(package):
    """Every dispatch in the `Code` of a package that already exists."""
    from inspect_package import (CODE_CLASS, decode_header, find_cluster,
                                 walk_objects)
    data, _ = find_cluster(Path(package).read_bytes())
    header = decode_header(data)
    out = set()
    for entry in walk_objects(data, header['heap_end']):
        if entry['class_number'] != CODE_CLASS:
            continue
        body = entry['payload']
        out |= set(calls(data[body['offset']:
                              body['offset'] + body['length']]))
    return out


def code(example, workdir=None, interfaces=SDK_INTERFACES, compiler='clang'):
    """An example's C, compiled and linked into one run of 68k.

    What comes back is what a `Code` object holds, bar the lead word and the
    MacsBug symbols: no relocations, nothing to fix up at load, which is
    what the packages themselves are -- the corpus has not one fixup table
    between them.
    """
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(workdir or temporary)
        result = build(example, root / 'out.o', workdir=root,
                       interfaces=interfaces, compiler=compiler)
        if result.returncode:
            raise RuntimeError(f'{Path(example).name}: {result.stderr}')
        return link(result.objects, root / 'code.bin', workdir=root)


def compare(example, package, workdir=None):
    """What this compiles against what CodeWarrior compiled.

    The bytes differ and are meant to: clang allocates registers its own way
    and pops after each call where CodeWarrior leaves the frame to `unlk`.
    The dispatches are the part that has to agree, because they are the
    whole of what the package does -- which selector, through which vector.
    """
    # Off the linked blob, not the objects: `-ffunction-sections` puts each
    # procedure in a section of its own, so there is no one `.text` to read.
    blob, _, _ = code(example, workdir=workdir)
    return set(calls(blob)), package_calls(package)


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('example', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    parser.add_argument('--disassemble', action='store_true')
    parser.add_argument('--link', action='store_true',
                        help='link it into one relocation-free run of 68k')
    parser.add_argument('--check', type=Path, metavar='PACKAGE',
                        help="hold the dispatches to a package's own Code")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as temporary:
        output = args.output or Path(temporary) / 'out.o'
        result = build(args.example, output)
        if result.returncode:
            sys.stderr.write(result.stderr)
            return result.returncode
        print(f'{args.example.name}: compiled to {output}')
        if args.disassemble:
            subprocess.run(['llvm-objdump-18', '-d', str(output)])
        if args.link:
            blob, left, found = code(args.example)
            print(f'  linked: {len(blob)} bytes, {left} relocations left, '
                  f'{len(calls(blob))} calls, {len(found)} procedures')
            for name in sorted(found, key=lambda n: found[n]['offset'])[:6]:
                print(f'    {found[name]["offset"]:#06x} '
                      f'{found[name]["size"]:5d}  {name}')
            if args.output:
                Path(args.output).write_bytes(blob)
        if args.check:
            ours, stock = compare(args.example, args.check)
            print(f'  {len(ours)} dispatches here, {len(stock)} in the '
                  f'package, {len(ours & stock)} the same, '
                  f'{len(ours - stock)} only here, '
                  f'{len(stock - ours)} only there')
            if ours != stock:
                return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
