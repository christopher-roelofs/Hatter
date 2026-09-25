# Magic Sokoban (native MIPS Magic Cap package)

A separate game replacing the planned Starship Courier expansion, not an
overwrite of that prototype. Installs a crate icon on the **Game room shelf**
through an InstallSpecifier; it does not add a Hallway door.

The visible package, scene, help, and launcher names are **Magic Sokoban**.
The native 48x48, four-shade icon depicts a wooden crate on a goal tile with
sparkles. Its editable pixel preview is beside the packed bytes in Objects.odef.
Internal Sokoban class/interface names and object layout remain unchanged.

The enlarged icon is 50% wider/taller than the original 32x32 artwork, with
53x53 launcher bounds and the standard resolution of 256. Read-only inspection
of the shipped packages under `software/mips/games` found these reference sizes:

| Game | Image pixels | Launcher content size |
| --- | --- | --- |
| Betteris | 32x32 | 37x37 |
| Edgewise | 22x28 | 37x37 |
| MatchIt | 39x36 | 46x36 |
| Reversi | 48x51 | 45x46 |
| Solitaire Deluxe | 42x56 | 46x36 |
| Video Poker | 41x52 | 37x37 |
| Gammon (GammonBundle package 0) | 33x60 | 34x60 |

These are Image.imageSize and Icon.contentSize, respectively; every listed
image uses resolution 256. Image pixels and launcher bounds are not identical.
The SDK Puzzle sample uses a 37x37 image and 37x37 launcher.

## Play

Tap an orthogonally adjacent square to move the solid black player. Push the
X-marked crates onto the small black goal squares. A crate on a goal displays
an asterisk. Crates cannot be pulled, pushed through walls, or pushed in pairs.

- Twelve small puzzles, unlocked in order; the original three are unchanged.
- Move and push counters; blocked taps do not count.
- Undo reverses **one** successful move, including a winning push.
- Restart resets the current puzzle and clears undo/counters.
- Next works only after solving; after level twelve it returns to level one.
- Leaving the scene and emulator snapshots retain object-field game state.
  This is not a separate save-file/export feature.

The first release uses touch/mouse taps, not physical arrow keys. No solver,
deadlock detector, level editor, multi-step undo, or additional level packs yet.
Corner traps are intentional Sokoban behavior; use Undo or Restart.

## Build and test

From the repository root:

```sh
python3 toolchains/mips/build_sample.py toolchains/mips/samples/Sokoban --out out/rosemary-magic-sokoban-12
cp out/rosemary-magic-sokoban-12/Sokoban.pkg 'out/rosemary-magic-sokoban-12/Magic Sokoban.pkg'
PYTHONPATH=toolchains/mips python3 -m unittest test_sokoban test_c_package test_sdk_package
g++ -std=c++98 -Wall -Wextra -Werror -fsanitize=address,undefined -g toolchains/mips/samples/Sokoban/tests/rules_test.cpp -o /tmp/magicrecomp-sokoban-tests
/tmp/magicrecomp-sokoban-tests
```

Install `out/rosemary-magic-sokoban-12/Magic Sokoban.pkg` through the emulator package
installer, then open its crate icon in the Game room.

The rules header is freestanding C++98, shared with host tests. The SDK builder
uses the original source directory as a quoted-header include path despite
staging translation units in the output directory. Header functions have
internal linkage to avoid unsupported weak/COMDAT function placement in the
current package linker. Guest object fields hold all mutable game/undo state;
ROM text/drawing calls happen outside field modification locks.

The shared compiler retains the MIPS-I division workaround from Starship
Courier (no MIPS-II TEQ zero-divisor checks). Grid division guards are explicit.

## Validation (2026-09-24)

### Twelve-level campaign

Eleven Python/toolchain tests passed; the rules tests also passed with address
and undefined-behavior sanitizers. All twelve maps have valid enclosed borders,
unique layouts, two crates, two goals, and one player. Breadth-first search
proves each solvable. Tests cover refusing premature Next, advancing every
completed level, clearing counters/undo, and wrapping twelve to one.

Fresh-installed and replayed every solution in the SDK guest on x86-64 JIT,
with intermediate snapshot reloads for the CLI's sixteen-tap limit. Visually
checked all twelve completion screens and their counters, the final campaign
message, and Next returning to level one. The class/interface and field layout
are unchanged; no in-place guest package upgrade was tested.

Evidence: `out/rosemary-magic-sokoban-12/solved1` through `solved12`, plus
`install`, `open`, and `wrap` (`.log`, `.pgm`, `.state`).
Tested package SHA-256:
`563130ace5cc8018e284ac249c551174db02518bd4d1b56a69a21d7000c4ad68`.

New levels were generated locally and selected for different layouts with
nondecreasing shortest solutions; no third-party level set was copied.
Shortest move solutions for the added levels (U/R/D/L):

| Level | Solution | Moves | Pushes |
| --- | --- | --- | --- |
| 4 | DDRULUURRDLULDDL | 16 | 5 |
| 5 | DLLLLURRURDRDLLL | 16 | 9 |
| 6 | ULURLLLDLDRRRRURU | 17 | 8 |
| 7 | LLLLLDRLDRRRLUULUR | 18 | 7 |
| 8 | RUUURRDLULLDDRULURRR | 20 | 6 |
| 9 | DRRDRRRUULLDLDRRDRUU | 20 | 7 |
| 10 | RDDUULLDDDRRLLUURURDD | 21 | 5 |
| 11 | RRDLDRURRDDLUURULLDLLULD | 24 | 8 |
| 12 | LUURLDDRUULURDDDRRUULRDDLLUU | 28 | 6 |

### Previous icon and branding checks

Enlarged-icon update: three Sokoban tests passed. Visually verified the 48x48
icon fits on the Game room shelf, launches the game, and level one still solves.
Evidence: `out/rosemary-magic-sokoban-large/{install,gameroom,solved1}.{log,pgm,state}`.
Tested package SHA-256:
`61638c2533255022da508794745e29ac150c59bd31387ceed24dbaaf721e5d0d`.
A preliminary doubled-size launcher did not appear on the shelf; that build
was replaced, not delivered. The exact cause was not investigated.

Branding/icon update: eleven Python/toolchain tests passed, including a check
that the native icon pixels match the editable preview. Fresh-installed the
renamed package into the SDK guest, visually verified the Game room icon and
scene title, and completed level one (five moves, two pushes). No non-interrupt
exceptions or bus faults in that gameplay run.
Evidence: `out/rosemary-magic-sokoban/{install,gameroom,solved1}.{log,pgm,state}`.
Tested package SHA-256:
`0b40161e0182c4e049da97a55f4ff702b17a80e0ad739c24fe31db7c14bdebaf`.
In-place upgrade of an already installed version has not been tested.

### Original gameplay validation (before the branding/icon update)

Ten Python/toolchain tests passed. The C++ rules tests also passed with address
and undefined-behavior sanitizers. They cover blocked/wall/double-crate pushes,
adjacency, counters, undo, reset, win detection, and breadth-first solution
search for every level. Solver solutions (U/R/D/L) are:

| Level | Solution | Moves | Pushes |
| --- | --- | --- | --- |
| 1 | URDRU | 5 | 2 |
| 2 | LUUDDRRRUU | 10 | 2 |
| 3 | UUULDRDRDRUURUL | 15 | 5 |

Verified using `build/mcap` with the Rosemary USA SDK ROM:

- Fresh installation into Storeroom, crate icon on Game room shelf, opening.
- All three solutions on the x86-64 native JIT, including final completion.
- First solution on the interpreter.
- Undo after winning, then restart, from reloaded snapshots.
- Premature Next and a push into a wall leave level/counters unchanged.
- No non-interrupt exceptions in checked logs; zero reported bus faults.

Evidence: `out/rosemary-sokoban/{install,open,solved1,solved2,solved3,undo,restart,interpreter}.{log,pgm,state}`.
Tested package SHA-256:
`f81a87a858285eb375fbf904754ef3ddefc8066458ee8e20624c99a5d1c2c4b5`.

Fresh-install diagnostic command (requires the local SDK snapshots):

```sh
STATE=out/rosemary-starship-states/store.state INSNS=1500000000 scripts/install-package out/rosemary-sokoban/Sokoban.pkg out/rosemary-sokoban install --option-key '0,1' --log-exceptions 10000
```

Release the Option key explicitly with these snapshots. CLI tap sequences
accept at most 16 taps; split campaign runs at saved level boundaries.
The build is not byte-reproducible yet: keep the exact tested package when
matching evidence to a SHA rather than silently rebuilding it.

Not yet tested on the tablet/AArch64, shipping DataRover ROM, or 68k ROMs.
This package targets the MIPS toolchain; no 68k compatibility is claimed.

A separate [native 68k port](../../../sokoban68k/README.md) now reuses these
sources and is validated on PIC-2000. Use its separate build/package; the
MIPS `.pkg` itself is not compatible with 68k.
