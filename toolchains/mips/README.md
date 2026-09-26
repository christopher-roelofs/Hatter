# MIPS Magic Cap 3.x packages

`build_sample.py` builds a package from a project directory containing Magic
Cap `.cdef`, `.odef`, and (when needed) `.cpp` source. It generates headers,
compiles MIPS-I code with Clang 18, and writes an installable `.pkg` plus a
`package-manifest.json` to the output directory.

Start from the SDK HelloWorld sample or one of Hatter's
[MIPS applications](../../examples/mips/README.md):

```sh
python3 toolchains/mips/build_sample.py HelloWorld --out out/HelloWorld
python3 toolchains/mips/build_sample.py examples/mips/Sokoban --out out/Sokoban
```

The first command resolves `HelloWorld` under the local SDK's `Samples/`
directory. The second reads a project directory directly. The package name
comes from that directory name, so the outputs are `out/HelloWorld/HelloWorld.pkg`
and `out/Sokoban/Sokoban.pkg`. Source and SDK files are never modified by a
build. The builder also accepts `--locale <name>` for a matching
`<name>.Package.Phrases` file.

To inspect an output before installation:

```sh
python3 toolchains/mips/inspect_format.py out/Sokoban/Sokoban.pkg
```

`inspect_format.py` is read-only. It reports package sections, sizes, names,
and format errors; it does not claim that a package will install on every ROM.

Run the host regression suite and sample matrix with `scripts/test-toolchains`.
See [setup](../../docs/SETUP.md) for the required SDK path and cross-compiler
versions, and the [developer guide](../../docs/MAGIC_CAP_DEVELOPER_GUIDE.md)
for class and object design. The [container formats](../../docs/ROSEMARY_CONTAINER_FORMATS.md),
[SDK build trace](../../docs/ROSEMARY_BUILD_TRACE.md) and
[guest testing notes](../../docs/ROSEMARY_ROM_TESTING.md) record what the
builder reproduces and how it was validated.

This builder has been exercised with all 17 preserved SDK samples, but Magic
Cap 3.x ROM profiles and unsupported C++/ABI features still need target-specific
testing. Install and exercise a new package in the matching emulator before
shipping it.
