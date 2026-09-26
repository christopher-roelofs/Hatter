# Package development resources

This is an inventory of the historical SDKs and tools behind Hatter's
builders, and of what each one contributes. For writing a new package, start
with the [developer guide](MAGIC_CAP_DEVELOPER_GUIDE.md) instead. It covers the
68k Magic Cap 1.0/1.5 ObjectMaker workflow, the MIPS Magic Cap 3.1
`.cdef`/`.odef` workflow, the object model, Magic Script, native ABIs, and the
differences a cross-target project must preserve.

The target split is 68k Magic Cap 1.0/1.5 versus MIPS Magic Cap 3.x; simulator
architecture is a separate choice. On MIPS, the host-built toolchain builds all
17 SDK samples from their unmodified sources, and the preserved samples have
been validated in the guest (see [the Rosemary build trace](ROSEMARY_BUILD_TRACE.md)
and [guest testing](ROSEMARY_ROM_TESTING.md)). On 68k, all preserved cookbook
packages compile or serialize through the reconstructed pipeline, with the
code-bearing set guest-validated on the Magic Cap 1.0 and 1.5 profiles. See
[the 68k container notes](OBJECTMAKER_FORMAT.md).

## Available resources

Original distributions are kept in the Magic Cap preservation archive
(`ROMs/`, `Software/`, `Documentation/`). Hatter keeps only the interfaces,
sample sources and fixtures its builders need, under [`sdk/`](../sdk/README.md).

| Target | Archive source | Contents |
| --- | --- | --- |
| 68k / Magic Cap 1.0 | CodeWarrior 7 Gold (`Software/68k/CodeWarrior/CW7_Gold_*.cdr`) | tools, interfaces, ObjectMaker, MPW scripts |
| 68k / Magic Cap 1.0 and 1.5 | CodeWarrior 8 Gold (`Software/68k/CodeWarrior/CW8_Gold_*.cdr`) | `Only 1.0`, `Only 1.5` and `Universal` interfaces; Magic Link, Envoy and simulator profiles |
| 68k samples | `Software/68k/Packages/cookbook_samples.sit_.hqx` | cookbook source/binary pairs |
| MIPS / Magic Cap 3.x | Magic Developer SDK (`Software/MIPS/SDK/magicdeveloper.sit`) | MIPS GNU tools, class/object compilers, X-file linker, package builder, interfaces, libraries and 17 sample projects |
| MIPS test ROM | `ROMs/MIPS/Rosemary SDK/MagicCap-USA.image` | the SDK's Apollo ROM, used for guest validation |
| Mac/Windows simulators | `Software/Simulators/` | these alone do not supply a device package toolchain |

In Hatter, the 68k profiles are `sdk/68k/interfaces/`, the cookbook projects
`sdk/68k/samples/projects/` and their compiled packages
`sdk/68k/samples/packages/`; the MIPS interfaces and samples are
`sdk/mips/Interfaces/` and `sdk/mips/Samples/`.

CW8's reference CD has 17 Magic Cap example directories. The cookbook contains
14 examples with compiled packages: BarChart, BizNote, Circuits, Counter,
Hanoi, Metric, Positioning, Snake, Spreadsheet, StackTemplate,
StackTemplateWithIndex, Template, TemplateWithButtons and Whitehouse.

## What the 68k tools reveal

The strongest build references in the CodeWarrior distributions are:

- `EmptyPackage.make`: the actual MPW build recipe from the nested CW7
  Magic/MPW installer.
- The CW7 Magic release notes: compiler, linker and ABI requirements.
- The CW8 Magic notes: tool version 1.3.1b0 and explicit 1.5 support.
- The Metrowerks Magic utilities manual: ObjectMaker class/instance syntax and
  package construction, especially printed pages 73–95.
- The cookbook's `Counter`: a small compiled package plus C source,
  definitions and generated interfaces suitable for comparison.

The MPW recipe runs ObjectMaker to generate interfaces from system/package
definitions, compiles C, links code and a map, then runs ObjectMaker again to
combine linked code with object definitions into a package. The integrated
CodeWarrior plugins combine portions of that process. The executable tools and
sample source are preserved; source for those proprietary tools was not found.

The release notes specify MC68349 code generation, 32-bit integers and stack
parameter slots, and pointer results in D0 rather than A0. Generated interfaces
also use register pragmas and inline instruction words for method dispatch.
Ordinary global/static storage is restricted by the original toolchain. These
are real compatibility requirements: compiling the C with an arbitrary 68k
compiler would not reproduce the original calling conventions or packages.

ObjectMaker additionally handles class metadata, inheritance, static object
graphs, indexicals and linking methods by name. The `.µ` CodeWarrior projects
are binary project files, not makefiles. The MPW `.make` files provide a more
useful basis for a command-line replacement. The
[tool analysis](GHIDRA_CODEWARRIOR_ANALYSIS.md) records what the binaries
themselves reveal.

## Magic Cap 3 and the Rosemary SDK

Josh Carter's [developer documentation page](https://joshcarter.com/magic_cap/magic_cap_developer_docs/)
identifies the Package Development Guide as a Magic Cap 3.1 reference, and the
Roadmap, Tutorial and Development Tools guide as Windows SDK documentation.
His [Rosemary archive](https://joshcarter.com/magic_cap/packages/) identifies its
device packages as MIPS builds. Thus these resources address the DataRover target.

The [TLS browser article](https://oldvcr.blogspot.com/2023/01/bringing-tls-to-magic-cap-datarover.html)
describes the Rosemary SDK's GCC 2.7.1 MIPS cross-tools running under MPW on a
Power Mac. PowerPC compilation serves the Mac simulator; it does not make the
DataRover package PowerPC. The article uses a TLS proxy, not on-device TLS.

Other preserved Rosemary material: `RosemarySimulatorMac.sit` contains the
Magic Cap USA simulator application, not a full SDK directory, and
`WinDownload.zip` contains only `WinDownload.exe`, the SDK's download utility.
Windows simulator packages are PE/DLL files; their format must not be applied
to device packages.

The local [Development Tools guide](reference/MagicSDK_Guide_to_Development_Tools.pdf),
printed page 21, supplies a useful concrete detail: MIPS builds produce ELF code,
then extract code/data into frozen-package attributes. The same guide describes
separate Class Compiler, Object Compiler, X-File Linker and Package Builder tools,
with `.cdef`, `.odef` and C++ input. Windows simulator builds use DLLs. This is a
different pipeline from the older 68k ObjectMaker workflow.

## How the builders were established

1. **A read-only package inspector for each target.** MIPS is
   `toolchains/mips/inspect_format.py`; 68k is
   `toolchains/m68k/inspect_package.py`, which reads all fourteen cookbook
   packages -- header, object chain, class names from the SDK's own number
   tables, and the methods and call sites in the code -- and is checked
   against the definitions and C those examples were built from. Unknown
   fields are preserved rather than guessed.
2. **Data-only 68k packages.** `toolchains/m68k/build_example.py` builds
   Template and TemplateWithButtons from their sources at exactly the size
   ObjectMaker produced, and a guest check drives the built package through
   the guest's own UI to its scene and requires the same pixels as the
   original.
3. **68k code.** Clang compiles the cookbook C against rewritten SDK headers
   with the documented CPU32 ABI and generated dispatch wrappers; Counter and
   the other code-bearing examples build and run. The 1.0 and 1.5 system
   definitions stay explicit profiles.
4. **MIPS packages.** The Rosemary SDK's sample build, transition-vector ABI,
   embedded relocations and library objects were traced, and its
   ELF-to-frozen-package pipeline reimplemented as a separate MIPS backend.
5. **Guest validation.** Installation and behavior were tested on the
   corresponding emulated device with the MagicHat emulator. The build runs
   entirely on the modern host; the emulator is a test target, not a build
   dependency.

Definition parsing, diagnostics and object-graph handling may be shareable.
Calling conventions, runtime references and binary package serialization need
separate, evidence-based backends. Do not require ROM or save-state patches to
make a generated package work.

## Rosemary milestones

The [MIPS sample build trace](ROSEMARY_BUILD_TRACE.md) records the complete
HelloWorld pipeline, transition-vector evidence from SDK machine code, and the
Linux code-generation path. A code-free EmptyPackage builds on Linux, installs
through PC Link, and opens its Scene and help in the unmodified SDK-ROM guest.
A restricted native MIPS leaf method installs and executes through the normal
guest dispatcher, and a method written in C, compiled with Clang and linked
with lld on Linux, runs in the guest: it calls ROM operations with arguments
and an intrinsic through generated stubs and keeps state in package globals
(build trace, "Compiling C on the host"). The SDK's HelloWorld sample, built
from its **unmodified `HelloWorld.cpp` and the SDK's own headers** (build
trace, "Compiling the SDK's own sources"), draws its box in the guest complete
with its names and sound ([screenshot](images/rosemary-helloworld.png)), and
**DigiClock** -- five methods, mixins, inherited calls, indexicals -- runs in
the Stamper ([screenshot](images/rosemary-digiclock.png)). Both build from
their unmodified source directories with `build_sample.py` (`.cdef`/`.odef`
front end). See [guest validation](ROSEMARY_ROM_TESTING.md).

## What the SDK manuals add

The six `MagicSDK_*.pdf` manuals in `docs/reference` were read for toolchain
content. They are the Windows/Visual C++ edition of Magic Developer 3.2 but
describe the platform-independent parts precisely:

- *Guide to Development Tools* ch. 2 and 6: the five frozen-package
  attributes (code, global data, class/object definitions, exported and
  imported interfaces); MIPS packages are one file with code and data
  extracted from an ELF executable; the complete `.cdef` syntax (`define
  class`, `inherits from`, `field … getter, setter, weak`, `attribute …
  noSetter/noGetter/readOnly`, `operation … noMethod/noFail/intrinsic`,
  `class operation`, `intrinsic` (simple), `overrides`, `mixes in with`,
  `indexical`, `define interface`, `import … or say …`, `weakly`); the
  `.odef` syntax and value forms (`.s`/`.b` sizes, Fixed, `<pixels>`, Dot,
  Box, `include 'file' a:b`, `$hex`); method naming `Class_Operation` with
  `#define CURRENTCLASS`; "package globals" replace the old class globals;
  intrinsics are direct jumps and cannot be overridden or exported; and the
  Rosemary Magic Script, a stack language compiled at build time to
  JVM-style bytecodes (`push`, `call Op [(types) -> type]`, `if …, goto`).
- *Package Development Guide* ch. 2–3: operation/attribute semantics,
  dispatching order, simple intrinsics without a responder, dynamic linking
  (component numbers reassigned at startup; interfaces identified by long
  names collected into cliques; strong and weak imports).

They do not document the binary frozen format, the MIPS calling convention
or the initialization bytecode; those come from the SDK objects and ROM
traces recorded in the [container notes](ROSEMARY_CONTAINER_FORMATS.md).
Nothing in them contradicts the decoded formats. The Magic Script description
is what the builder's script assembler follows (build trace, "Magic Script").
