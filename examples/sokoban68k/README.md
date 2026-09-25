# Magic Sokoban — native 68k port

This builds a separate native 68k package, not a MIPS package running through
translation. The MIPS game's sources and build remain unchanged.

`build.py` adapts the existing `examples/mips/Sokoban` rules, twelve maps,
48×48 crate artwork, drawing, and touch controls. It generates C and 68k
ObjectMaker definitions under the output's `source/` directory. This is a
narrow, tested adapter for this sample, not a general C++ or ODEF translator.
Change the shared game sources, rebuild both targets, and run both test suites
when updating gameplay; do not edit the generated output as source.

## Build

Requires the preserved 68k SDK interfaces, Python, `m68k-linux-gnu-gcc`, and
GNU m68k binutils. Host tests also use Clang 18 and g++.

```sh
python3 examples/sokoban68k/build.py
PYTHONPATH=examples/sokoban68k python3 -m unittest test_build
```

The PIC-2000 / Magic Cap 1.5 package is:

`out/magic-sokoban-68k/Magic Sokoban.pkg`

Install through the emulator's package installer with the guest Storeroom
computer open. Its crate icon appears on the **Game room shelf**, not as a
separate Hallway door. Controls match the MIPS game: tap an adjacent tile,
push both crates onto goals, Undo one move, Restart, and Next after winning.
Level twelve wraps back to one. Snapshot resume preserves gameplay state.

An older-interface build is also available:

```sh
python3 examples/sokoban68k/build.py --profile 1.0 --out out/magic-sokoban-68k-10
```

Use this **1.0 build for Motorola Envoy**: installation through PC Link and
all twelve puzzles passed on the desktop. Do not assume the 1.5 package
works on every 68k ROM.

**HIX is not yet validated.** Its MC19 C2 ROM sends direct GMTP records over
PPP when the Storeroom computer is opened. The current host link expects
GMTP inside UDP/IPv4/PPP, so it drops HIX's `Cnct` request before replying.
The guest reports “The communications service is not available.” A stock
`Counter.pkg` fails at the same point, before package transfer. This is a
host transport compatibility gap, not evidence of a Sokoban defect. The
serial trace and analysis remain in the sibling emulator repository's
`docs/HIX300.md`.

## Compiler/SDK differences

- 68k `Draw` receives canvas and clip explicitly; text uses Pascal strings.
- Class fields, method tables, root lists, and icon installation use the
  ObjectMaker package format and the selected SDK profile.
- The counters are native TextFields, updated outside field modification.
- A5 must remain reserved for Magic Cap dispatch vectors. The common Clang
  driver now uses `-ffixed-a5`; the GCC driver does too.
- This package explicitly uses **GCC CPU32, PC-relative code**. LLVM 18
  produced incorrect dynamic array indexing in this game: repeated stack
  array stores targeted one byte, corrupting counters; level progression
  also differed from the shared rules. Disabling optimization did not solve
  it. Existing ObjectMaker callers still default to Clang; the new `compiler`
  argument opts into GCC. No ROM patches or emulator CPU changes are used.

## Guest verification

Validated on 2026-09-24: all twelve puzzles passed on PIC-2000, including
Next gating, pushing, Undo/Undo-after-win, Restart, wrap, and cross-engine
restore. The final campaign-complete and restored level-one screens were
visually checked. Three port tests, all 151 ObjectMaker tests, and the three
original MIPS Sokoban tests passed.

Validated 1.5 package: 8,324 bytes, SHA-256
`b21fd7c03dc0c3664b89f106da5e97e5fb443464a9e333329f086f55ebc00e68`.

Validated Envoy 1.0 package: 8,320 bytes, SHA-256
`44b82fe01c4fe2897d44bb835a653515e71e91cab7a52aa49e70c6ae59aeee47`.
Envoy passed the same complete campaign and control/restore checks, with
artifacts in `out/sokoban-validation/envoy/replay/`.

`test_guest.py` expects a snapshot showing the newly opened level-one board:

```sh
python3 examples/sokoban68k/test_guest.py --state out/magic-sokoban-68k/open.state
python3 examples/sokoban68k/test_guest.py \
  --rom 'roms/Motorola Envoy/envoy-1.0.rom' \
  --state out/sokoban-validation/envoy/open.state \
  --out out/sokoban-validation/envoy/replay
```

It obtains solutions from the shared host rules test, replays them as actual
guest taps, and checks expected state fields against guest RAM. It also tests
premature Next, pushing, Undo, Undo after winning, Restart, campaign wrap,
and interpreter/JIT snapshot interchange. Screens, logs, and states are in
`out/magic-sokoban-68k/replay/`. The host parity test compares the adapted
rules with the original over 240,000 actions, including forced completion.

To recreate the installed snapshot from the existing PIC Storeroom fixture:

```sh
scripts/install-package-68k 'out/magic-sokoban-68k/Magic Sokoban.pkg' out/magic-sokoban-68k install
build/mcap --rom 'roms/Sony PIC 2000/PIC-2000.rom' --headless --no-host-battery \
  --load-state out/magic-sokoban-68k/install.state -n 240000000 \
  --tap 1000000,1000000,420,12 --tap 30000000,1000000,449,253 \
  --tap 60000000,1000000,449,253 --tap 90000000,1000000,449,253 \
  --tap 140000000,1000000,180,150 --tap 190000000,1000000,305,80 \
  --dump-fb out/magic-sokoban-68k/open.pgm \
  --save-state out/magic-sokoban-68k/open.state
```

These coordinates are specific to that fixture's Hallway and shelf layout.
The runtime's exception diagnostics also include guest framework traps;
their presence alone is not used as a package pass/fail criterion.

### Tablet native-engine replay

On 2026-09-24, the Samsung SM-P610 passed the complete twelve-level replay
for **both PIC-2000 (1.5 package) and Envoy (1.0 package)**, including Next
gating, Undo/Undo-after-win, Restart, wraparound, and interpreter/JIT restore.
Both final completion screens were visually checked. Artifacts are in
`out/sokoban-validation/tablet-pic/` and `tablet-envoy/`. Wireless ADB
disconnected during the initial runs; replay resumed from the last verified
checkpoints after reconnecting, and both runs completed successfully.
The three host port tests also pass, now building both SDK profiles.

`android_runner.c` loads the APK's `libmcap.so` and calls its exported CLI.
Compile with the Android NDK's `aarch64-linux-android24-clang`, linking `-ldl`.
Extract `lib/arm64-v8a/libmcap.so` and `libSDL2.so` from the APK. Push both
libraries and the executable into a dedicated directory created with
`adb shell mktemp -d /data/local/tmp/sokoban-test.XXXXXX`; chmod the runner
executable. Then run the same replay with `--adb-transport TRANSPORT_ID
--remote-dir DIRECTORY --out LOCAL_RESULTS`, plus the appropriate ROM/state.

This exercises the actual tablet's AArch64 JIT, interpreter restore, and
guest rendering headlessly. It does **not** test Android touch-event delivery
or package installation through the Android UI. It never launches/stops the
managed Android emulator activity or writes its device states. If wireless
ADB disconnects, reconnect and use `--resume-after LAST_PASSED_TAG` with the
same output directory; only use a checkpoint previously reported as PASS.
