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
| MIPS 3.x | `software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/` |
| 68k 1.0 | `software/68k/extracted/CW7-Magic-MPW/CodeWarrior Magic%2FMPW Installer/MagicDeveloper/Interfaces/` |
| 68k 1.5 | `software/68k/extracted/CW8_Gold_Tools_199601/Metrowerks CodeWarrior/Magic Cap Support/Interfaces/` |

The MIPS SDK path must include `Interfaces/`, `Libraries/`, and `Samples/`.
The 68k examples also use
`software/68k/extracted/cookbook/Cookbook Examples/` as starter projects.
Hatter's local workspace contains copies of these assets; a fresh clone needs
them supplied separately. The CodeWarrior Pro 1 Windows archive and classic-Mac
VM are **not** required for the host package builders.

Check the installation with:

```sh
python3 toolchains/m68k/build_example.py --help
python3 toolchains/mips/build_sample.py --help
scripts/test-toolchains
```

The test script builds the preserved SDK samples as well as running host
regressions. It does not require or run the emulator. Package installation
and guest behavior are validated with `magicrecomp` separately.
