# Set up Hatter

Run commands from the repository root. Hatter itself is Python source; the
historical SDKs supply interface definitions and sample projects, while modern
cross-compilers produce native code.

## Host tools

- Python 3 and a C++ compiler for sample rules tests.
- `clang-18`, `ld.lld-18`, and `llvm-objdump-18` for MIPS builds.
- `clang-18` and `m68k-linux-gnu-{as,ld,objcopy,readelf}` for 68k builds.
- `m68k-linux-gnu-gcc` for the GCC/CPU32 alternative used by Magic Sokoban.

Confirm the commands are on `PATH` before building. Do not substitute the
host's default `clang` or `gcc` without checking its target and version.

## Local SDK assets

The following directories are needed; they are intentionally ignored by Git
because they contain original third-party distributions:

| Target | Required local path |
| --- | --- |
| MIPS 3.x (Apollo) | `sdk/mips/Interfaces/` and `sdk/mips/Samples/` |
| 68k 1.0 | `sdk/68k/interfaces/1.0-original/` or `sdk/68k/interfaces/1.0/` |
| 68k 1.5 | `sdk/68k/interfaces/1.5/` and `sdk/68k/interfaces/system/` |

The MIPS SDK path must include `Interfaces/` and `Samples/`; Hatter's host
builder does not need the historical compiler binaries or libraries.
The local copy retains the Apollo headers used by this builder, not the
Sputnik or Macintosh Simulator variants. The 68k copy similarly omits debug
interfaces and keeps the 1.0/1.5 profiles used by the host builder. Restore
additional profiles from the complete archives in the Magic Cap preservation
archive (`Software/68k/CodeWarrior/`, `Software/MIPS/SDK/`) if future
toolchain work needs them; [package resources](PACKAGE_BUILDING.md) lists
what each archive supplies.
The 68k examples also use `sdk/68k/samples/projects/` as starter projects;
the matching `samples/packages/` and `sdk/68k/fixtures/` are test inputs.
Hatter's local workspace contains the necessary interfaces and sample sources,
not the complete historical distributions; a fresh clone needs these assets
supplied separately. The CodeWarrior Pro 1 Windows archive and classic-Mac VM
are **not** required for the host package builders.

Check the installation with:

```sh
python3 toolchains/m68k/build_example.py --help
python3 toolchains/mips/build_sample.py --help
scripts/test-toolchains
```

The test script builds the preserved SDK samples as well as running host
regressions. It does not require or run the emulator. Package installation
and guest behavior are validated separately with the MagicHat emulator
(`mhat`); see [guest testing](ROSEMARY_ROM_TESTING.md).
