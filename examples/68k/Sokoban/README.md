# Magic Sokoban (68k)

This adapter builds the same twelve-level game for Magic Cap 1.0/1.5. It
reuses the [MIPS project's](../../mips/Sokoban/README.md) game rules and artwork,
but generates 68k C and ObjectMaker definitions under the build output's
`source/` directory. Those generated files are not the authoritative source.

Build and test from the Hatter root:

```sh
python3 examples/68k/Sokoban/build.py --profile 1.5 --out out/Sokoban-68k
PYTHONPATH=examples/68k/Sokoban python3 -m unittest test_build
```

The package is `out/Sokoban-68k/Magic Sokoban.pkg`. For an older Magic Cap
1.0 ROM, use `--profile 1.0` and a different output directory. Install only
on a matching 68k guest.

The adapter uses `m68k-linux-gnu-gcc` in CPU32/PC-relative mode for native
game code. Its tests check that generated rules match the shared C++ rules,
that the launcher/icon survives translation, and that packages build against
both interface profiles. See [setup](../../../docs/SETUP.md) for prerequisites.
