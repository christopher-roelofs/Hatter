# Hatter — build Magic Cap software

Hatter is the source workspace for writing Magic Cap applications. It provides
host-side package builders for Magic Cap 1.0/1.5 (68k) and 3.x (MIPS), working
application examples, package inspectors, and regression tests. The separate
[MagicHat](https://github.com/christopher-roelofs/MagicHat) repository
contains the emulator (`mhat`) used to install and test packages; Hatter does
not need the emulator or Ghidra to build software.

## Start a project

Install the [local SDK dependencies](docs/SETUP.md) first. The simplest route
is to copy a working example, edit its source, then build its package:

| Target | Start from | Build command |
| --- | --- | --- |
| 68k 1.0/1.5 | `sdk/68k/samples/projects/Counter` | `python3 toolchains/m68k/build_example.py <project-dir> --profile 1.5 -o out/MyApp.pkg` |
| MIPS 3.x | `sdk/mips/Samples/HelloWorld` or `examples/mips/Sokoban/` | `python3 toolchains/mips/build_sample.py <project-dir> --out out/MyApp` |

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
installation and guest testing use the MagicHat emulator; they are not part of
the package compiler. Build outputs are written under ignored `out/`.

## Documentation

- [Setup](docs/SETUP.md): host tools and local SDK assets.
- [Developer guide](docs/MAGIC_CAP_DEVELOPER_GUIDE.md): classes, objects,
  methods, Magic Script, and 68k/MIPS differences.
- [Package resources](docs/PACKAGE_BUILDING.md): the historical SDKs and tools
  and what each contributes.
- [68k package format](docs/OBJECTMAKER_FORMAT.md): the ObjectMaker container
  written for Magic Cap 1.0/1.5.
- [MIPS container formats](docs/ROSEMARY_CONTAINER_FORMATS.md): the Rosemary
  SDK intermediate and frozen-package layouts.
- [Rosemary build trace](docs/ROSEMARY_BUILD_TRACE.md): how the SDK builds a
  package and how the Linux host path reproduces it.
- [Rosemary guest testing](docs/ROSEMARY_ROM_TESTING.md): validation of the SDK
  samples in the SDK ROM under MagicHat.
- [CodeWarrior tool analysis](docs/GHIDRA_CODEWARRIOR_ANALYSIS.md): findings
  from the ObjectMaker and Magic Developer binaries.

## Layout and boundary

- `toolchains/`: maintained package builders, their required modules, and
  regression tests.
- `examples/`: original application source; never substitute a generated
  package in `out/` for this source.
- `docs/`: developer instructions and the format references behind the
  builders.
- `sdk/`: ignored local copies of the historical interfaces, sample
  sources, and small package fixtures the builders or tests need. See
  [setup](docs/SETUP.md); the complete SDK archives stay in the Magic Cap
  preservation archive.

The builders are Python programs that invoke native cross-compilers. A native
rewrite is not planned without a measured bottleneck.
