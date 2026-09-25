# Magic Sokoban (MIPS)

This is a complete Magic Cap 3.x game project. It installs a crate icon on the
Game room shelf and contains twelve Sokoban levels. Tap an adjacent tile to
move; push both crates onto goals. Undo, Restart, and Next are part of the UI.
The game stores its state in declared Magic Cap object fields.

## Source map

- `Sokoban.cdef`: class and persistent field declarations.
- `Objects.odef`: scene, controls, launcher, help, and native icon artwork.
- `Sokoban.cpp`: Magic Cap methods, drawing, and touch handling.
- `SokobanRules.h`: portable C++98 game rules and level data.
- `tests/rules_test.cpp`: host-side rules and solvability checks.

Build from the Hatter root:

```sh
python3 toolchains/mips/build_sample.py examples/mips/Sokoban --out out/Sokoban
PYTHONPATH=toolchains/mips python3 -m unittest test_sokoban
g++ -std=c++98 -Wall -Wextra -Werror examples/mips/Sokoban/tests/rules_test.cpp -o out/sokoban-rules-test
out/sokoban-rules-test
```

The installable package is `out/Sokoban/Sokoban.pkg`. Install and play it with
a Magic Cap 3.x guest in the sibling emulator repository. Do not copy its MIPS
package to a 68k device; use the [68k adapter](../../68k/Sokoban/README.md).

For a new game, copy this project directory and update its name, interface,
definitions, instances, and native methods together. The builder uses the
directory name as the package name; changing only the file name of an existing
`.pkg` does not rename its contents.
