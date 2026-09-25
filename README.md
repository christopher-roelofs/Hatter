# Hatter — build Magic Cap software

Hatter is the source workspace for writing Magic Cap applications. It provides
host-side package builders for Magic Cap 1.0/1.5 (68k) and 3.x (MIPS), working
application examples, package inspectors, and regression tests. The sibling
`magicrecomp` repository contains the emulator and the reverse-engineering
research that established these formats; Hatter does not need Ghidra to build
software.

## Start a project

Install the [local SDK dependencies](docs/SETUP.md) first. The simplest route
is to copy a working example, edit its source, then build its package:

| Target | Start from | Build command |
| --- | --- | --- |
| 68k 1.0/1.5 | `software/68k/extracted/cookbook/Cookbook Examples/Counter` | `python3 toolchains/m68k/build_example.py <project-dir> --profile 1.5 -o out/MyApp.pkg` |
| MIPS 3.x | `software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Samples/HelloWorld` or `examples/mips/Sokoban/` | `python3 toolchains/mips/build_sample.py <project-dir> --out out/MyApp` |

Run these from the Hatter root. Use `--profile 1.0` for older 68k ROMs. For a
cross-target game, [Magic Sokoban](examples/mips/Sokoban/README.md) and its
[68k adaptation](examples/68k/Sokoban/README.md) demonstrate shared rules with
target-specific package definitions.

The [developer guide](docs/MAGIC_CAP_DEVELOPER_GUIDE.md) explains classes,
objects, methods, Magic Script, and target differences. Each toolchain has a
short [68k](toolchains/m68k/README.md) or [MIPS](toolchains/mips/README.md)
workflow guide.

## Verify and inspect

```sh
scripts/test-toolchains                    # host tests and 17 SDK sample builds
python3 toolchains/m68k/inspect_package.py --fields out/MyApp.pkg
python3 toolchains/mips/inspect_format.py out/MyApp/MyApp.pkg
```

The inspectors are useful for checking a package before installing it. Runtime
installation and guest testing use the sibling emulator; they are not part of
the package compiler. Build outputs are written under ignored `out/`.

## Layout and boundary

- `toolchains/`: maintained package builders, their required modules, and
  regression tests.
- `examples/`: original application source; never substitute a generated
  package in `out/` for this source.
- `docs/`: developer instructions, not reverse-engineering logs.
- `software/`: ignored local copies of the historical interfaces, sample
  sources, and small package fixtures the builders or tests need. See
  [setup](docs/SETUP.md); the complete SDK archives stay in `magicrecomp`.

The builders are Python programs that invoke native cross-compilers. A native
rewrite is not planned without a measured bottleneck.
