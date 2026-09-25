# Hatter

Hatter is the development-tooling workspace for Magic Cap packages. Work on
the 68k and MIPS package builders, inspectors, and sample
applications continues here. The emulator remains in the sibling
`magicrecomp` repository.

The current builders are Python programs that invoke native cross-compilers.
Keep the Python CLIs and tests as the reference implementation; optimize a
measured bottleneck before considering a native rewrite.

## Layout

- `toolchains/m68k/`: 68k Magic Cap 1.0/1.5 package tooling.
- `toolchains/mips/`: MIPS Magic Cap 3.x package tooling.
- `examples/mips/`: original MIPS game sources and host rules tests.
- `examples/sokoban68k/`: 68k adapter for the shared Sokoban source.
- `scripts/`: package build and guest-test helpers. `test-toolchains` runs the
  standalone host checks. Guest-test helpers still expect the sibling
  emulator checkout and are not standalone.
- `docs/`: package-format research, build traces, and validation evidence.
- `software/`: local, ignored historical SDKs and package corpus. The source
  distributions are not committed; preserve this directory when cloning or
  backing up the workspace.
- `packages/`: ignored local package corpus used by format-oracle tests.

## Quick checks

Run from this repository root:

```sh
python3 -m unittest discover -s toolchains/m68k -p 'test_*.py'
python3 -m unittest discover -s toolchains/mips -p 'test_*.py'
scripts/build-rosemary-samples --sample HelloWorld
```

The historical SDK assets must be present at the paths documented in
[`docs/PACKAGE_BUILDING.md`](docs/PACKAGE_BUILDING.md). Building MIPS packages
also requires Clang/LLVM 18; building 68k native packages requires the
`m68k-linux-gnu` cross-compiler. See the tooling READMEs for exact commands.

This repository was split from `magicrecomp` on 2026-09-25. The original files
were copied, not deleted, so existing emulator workflows continue to work.
Hatter is the source of truth for subsequent development-tool changes. Guest
runtime tests may still need the sibling emulator until their harnesses are
fully decoupled.
