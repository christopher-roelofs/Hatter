# Samples written here, rather than shipped with the SDK

`build_sample.py` takes a directory, so a sample of our own builds the same
way the SDK's do. This directory contains our games as well as guest probes.

## Games: preserve these source directories

- [Magic Sokoban](Sokoban/README.md): twelve-level MIPS game. `Sokoban.cpp`
  is the UI; `SokobanRules.h` contains rules and all levels; `Sokoban.cdef`
  defines persisted fields; `Objects.odef` contains the scene, launcher, and
  native icon artwork; `tests/rules_test.cpp` proves all levels solvable.
- [Starship Courier](StarshipCourier/README.md): earlier working MIPS game
  prototype. Keep its `.cpp`, `.cdef`, and `.odef` files and validation notes.

These are original source, not generated SDK copies. Keep the shared compiler
and `../test_sokoban.py` too. Build products under `out/` are not substitutes
for these directories. See the [Hatter workspace overview](../../../README.md).

## ColourProbe, and Probe2 as its control

Does this ROM still carry the colour raster functions? The SDK enumerates
`pix555Color` and `pix888Color` and marks only `pix444Color` unsupported, and
the Package Development Guide says outright that "Magic Cap supports true
color" although no communicator has a colour screen -- but whether a given
build kept those cases is a different question, and it decides whether the
emulator can ever show colour.

Each makes its own offscreen `PixelMap`, fills it with `rgbRed`, and reads the
pixel back. They are the same file but for `PROBE_DEPTH`. The answer is a box
on the screen, because the screen is the only instrument that works.

    depth  2  ->  dark grey   readback non-zero but not red: quantised
    depth 24  ->  black       readback is exactly rgbRed: colour preserved

Which is what they produce, on **both** ROMs -- the Rosemary SDK build and
the shipping DataRover 840 image, Magic Cap 3.1.2j. **The colour raster
functions are there.** The SDK-built package's class and operation numbers
carry to the shipping ROM unchanged, which the build trace had flagged as
needing checking before installation failures could be read as compiler bugs.

To install on the shipping ROM, the Storeroom is not where walking the
Hallway suggests -- its two screens show Desk, Library, Controls, then Game
room, and stop. Tap the **Directory board** instead: it lists the rooms, and
choosing Storeroom scrolls the Hallway to a door the walk never reaches.

    scripts/mkstates 'roms/Data Rover 840/DataRover-840-USA.image' states/dr840
    # from states/dr840/desk.state, px: 395,24  dismiss the splash
    #                                   443,11  Hallway
    #                                    67,93  Directory board
    #                                   177,131 Storeroom in the list
    #                                   393,117 the door
    ROM='roms/Data Rover 840/DataRover-840-USA.image' \
    STATE=states/dr840/install-room.state \
      scripts/install-package <package> <outdir> <tag>

Four earlier designs failed, and each failure is worth keeping:

- `AllocPixels` on `CurrentCanvas()` takes the system down to the
  "Cleaning up..." screen -- at depth 2 as readily as at 24, so it says
  nothing about depth. Never reallocate the live screen's pixels.
- A package's static `.data` is not findable in a `--dump-ram` dump, so a RAM
  marker is a blind instrument. Every "no marker found" result it gave was
  uninterpretable.
- `AllocPixels`'s `newPixels` is the backing store and is a *parameter*.
  Passing `nilObject` with class 0 allocates nothing, and every `ReadPixel`
  then returns 0 -- which is `rgbTransparent`, and correct. Pass `Pixels_`.
- `resolution` is a `PixelDot` in pixels per grid unit and must be `onePixel`,
  because the bounds are in microns.
- Do not report an answer in `rgbLtGray`: that is the scene's own background,
  so it renders invisible.

Run one:

    PYTHONPATH=toolchains/mips python3 toolchains/mips/build_sample.py \
        toolchains/mips/samples/ColourProbe --out out/probe.pkg
    scripts/install-package out/probe.pkg/ColourProbe.pkg out/colourprobe probe
    ./build/mcap --rom 'roms/Rosemary SDK/MagicCap-USA.image' \
      --load-state out/colourprobe/probe.state --headless --no-host-battery \
      -n 220000000 --tap-hold 1500000 \
      --taps-px '279,213,1000000;450,150,50000000;380,150,100000000' \
      --dump-fb out/colourprobe/probe-open.pgm
