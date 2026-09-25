# Starship Courier

Experimental MIPS Magic Cap package. The reported tap reset was reproduced
and fixed in the Rosemary SDK guest. Opening, movement, an invalid tap,
interception, and Reset have now been exercised successfully.

Build from the repository root:

```sh
python3 toolchains/mips/build_sample.py toolchains/mips/samples/StarshipCourier --out out/rosemary-starship-courier
```

The current revision removes the unmatched EndModifyFields on invalid geometry,
uses a local state copy followed by WriteFields for a move, positions the status
and reset controls within the scene, reserves a footer inside the board for
score/energy/turn, and removes the periodic board mutation/redraw. The pulse
field is retained to avoid changing the stored field layout.

Drawing and touch handling share the same grid bounds and minimum cell size.
The footer is excluded from touch hit testing. The counters read left to right:
score, energy, turn. The board is 10 by 6; tap a neighboring cell to move or
intercept the drone. This is still a prototype, without enemy turns or obstacles.

## Tap reset: reproduced and fixed

The original latest build faults at PC 003C4748, instruction 008001F4 (TEQ),
on a valid tap at (120,93). The linked instruction is at 10000864, in the
division used to turn touch coordinates into grid coordinates. LLVM 18 emits
this MIPS-II zero-divisor trap even with -march=mips1. The emulator reports
a reserved-instruction exception. This fault is not evidence of memory exhaustion.

The shared C/C++ package compiler flags now include
`-mllvm -mno-check-zero-division`. Callers must guard zero divisors; the game's
geometry validation already does. A regression test compiles signed division
and unsigned remainder and checks for DIV/DIVU without MIPS-II trap instructions.

Evidence is in out/rosemary-starship-courier/tap.log (failure) and
out/rosemary-starship-courier-fixed/{moved,attack,reset}.{log,pgm,state} (success).
The successful runs have only interrupt exceptions and no bus faults. A move
shows score/energy/turn 0/19/1; interception shows 10/11/10; Reset restores
0/20/0. Prior field-lock and inherited-Tap explanations were unverified hypotheses.

For installation use out/rosemary-starship-states/store.state, with Option
released using `--option-key '0,1'`. The old install-room.state shows Controls:
Option had been held since monitor boot, changing navigation into popups.
The corrected store.state was visually verified and used for PC Link transfer.

Remaining validation: shipping ROM, win/loss, footer taps, persistence, and
leaving/reopening the scene. No claim of full game or cross-ROM validation.
