# Package development resources and a modern build path

For a developer-facing introduction to writing new packages, see the
[Magic Cap Developer Guide](MAGIC_CAP_DEVELOPER_GUIDE.md). It covers the 68k
Magic Cap 1.0/1.5 ObjectMaker workflow, MIPS Magic Cap 3.1 `.cdef`/`.odef`
workflow, the object model, Magic Script, native ABIs, and the differences a
cross-target project must preserve.

Inventory checked 2026-09-11. Archive extraction is complete. The target split
is 68k Magic Cap 1.0/1.5 versus MIPS Magic Cap 3.x; simulator architecture is a
separate choice. On MIPS a host-built package toolchain now builds all 17 SDK
samples from their unmodified sources, with guest-validation evidence recorded
for the preserved samples (see [the Rosemary build trace](ROSEMARY_BUILD_TRACE.md)
and [guest testing](ROSEMARY_ROM_TESTING.md)). On 68k all preserved cookbook
packages now compile or serialize through the reconstructed pipeline, with the
code-bearing set guest-validated on the Magic Cap 1.0 and 1.5 profiles. See
[the 68k container notes](OBJECTMAKER_FORMAT.md).

## Available resources

| Target | Local evidence | Status |
| --- | --- | --- |
| 68k / Magic Cap 1.0 | CW7 tools, interfaces, ObjectMaker, MPW scripts, cookbook source/binary pairs | Extracted |
| 68k / Magic Cap 1.0 and 1.5 | CW8 `Only 1.0`, `Only 1.5`, `Universal` interfaces; Magic Link, Envoy and simulator profiles | Extracted; profiles include Mac aliases |
| MIPS / Magic Cap 3.x | Magic Developer SDK in `software/mips/sdk`, SDK manuals in `docs/reference`, browser and driver packages | SDK extracted; host build path, interfaces and 17 samples present; exact compatibility of every historical target profile remains pending |
| Mac/Windows simulators | Simulator archives and extracted applications | These alone do not supply a device package toolchain |

See [68k archive inventory](../software/68k/README.md). CW8's reference CD has
17 Magic Cap example directories. The cookbook contains 14 examples and compiled
packages: BarChart, BizNote, Circuits, Counter, Hanoi, Metric, Positioning, Snake,
Spreadsheet, StackTemplate, StackTemplateWithIndex, Template,
TemplateWithButtons and Whitehouse. Package copies are in
`software/68k/extracted/installable/cookbook`; none has yet been installed as part
of this archive investigation.

## What the 68k tools reveal

Under `software/68k/extracted/`, the strongest build references are:

- `research/EmptyPackage.make.txt`: the actual MPW build recipe from the nested
  CW7 Magic/MPW installer.
- `research/CW Magic Notes.txt`: compiler, linker and ABI requirements.
- `research/CW8-Magic-Notes.txt`: tool version 1.3.1b0 and explicit 1.5 support.
- `research/MW-Magic-Utilities.txt`: ObjectMaker class/instance syntax and
  package construction, especially printed pages 73–95.
- `cookbook/Cookbook Examples/Counter`: a small compiled package plus C source,
  definitions and generated interfaces suitable for comparison.

The MPW recipe runs ObjectMaker to generate interfaces from system/package
definitions, compiles C, links code and a map, then runs ObjectMaker again to
combine linked code with object definitions into a package. The integrated
CodeWarrior plugins combine portions of that process. We have executable tools
and sample source; full source for those proprietary tools was not found.

The release notes specify MC68349 code generation, 32-bit integers and stack
parameter slots, and pointer results in D0 rather than A0. Generated interfaces
also use register pragmas and inline instruction words for method dispatch.
Ordinary global/static storage is restricted by the original toolchain. These
are real compatibility requirements: compiling the C with an arbitrary 68k
compiler would not reproduce the original calling conventions or packages.

ObjectMaker additionally handles class metadata, inheritance, static object
graphs, indexicals and linking methods by name. The `.µ` CodeWarrior projects
are binary project files, not makefiles. The extracted MPW `.make` files provide
a more useful basis for a command-line replacement.

## Magic Cap 3 and the old project

Josh Carter's [developer documentation page](https://joshcarter.com/magic_cap/magic_cap_developer_docs/)
identifies the Package Development Guide as a Magic Cap 3.1 reference, and the
Roadmap, Tutorial and Development Tools guide as Windows SDK documentation.
His [Rosemary archive](https://joshcarter.com/magic_cap/packages/) identifies its
device packages as MIPS builds. Thus these resources address the DataRover target.

The [TLS browser article](https://oldvcr.blogspot.com/2023/01/bringing-tls-to-magic-cap-datarover.html)
describes the Rosemary SDK's GCC 2.7.1 MIPS cross-tools running under MPW on a
Power Mac. PowerPC compilation serves the Mac simulator; it does not make the
DataRover package PowerPC. The article uses a TLS proxy, not on-device TLS.

Earlier archive searches did not locate the Magic Developer tool distribution.
The subsequently supplied `magicdeveloper.sit` is now preserved and
extracted in [software/mips/sdk](../software/mips/sdk/README.md). This supplies
the MIPS GNU tools, class/object compilers, X-file linker, package builder,
interfaces, libraries and 17 sample projects. The missing-SDK limitation is
resolved; running or replacing the historical tools remains future work.

The local [Development Tools guide](reference/MagicSDK_Guide_to_Development_Tools.pdf),
printed page 21, supplies a useful concrete detail: MIPS builds produce ELF code,
then extract code/data into frozen-package attributes. The same guide describes
separate Class Compiler, Object Compiler, X-File Linker and Package Builder tools,
with `.cdef`, `.odef` and C++ input. Windows simulator builds use DLLs. This is a
different pipeline from the older 68k ObjectMaker workflow.

## Proposed implementation sequence

1. Build a read-only package inspector with architecture/version identification.
   Use the source/binary cookbook pairs for 68k and existing browser/driver
   packages for MIPS. Preserve unknown fields rather than guessing their meaning.
   **Done both sides.** MIPS is `toolchains/mips/inspect_format.py`; 68k is
   `toolchains/m68k/inspect_package.py`, which reads all fourteen
   cookbook packages -- header, object chain, class names from the SDK's own
   number tables, and the methods and call sites in the code -- and is checked
   against the definitions and C those examples were built from. The format and
   what remains unread are in [the 68k container notes](OBJECTMAKER_FORMAT.md).
2. **Done for data-only packages.** `toolchains/m68k/build_example.py`
   builds Template and TemplateWithButtons from their sources at exactly the
   size ObjectMaker produced, 27 of Template's 29 records byte-identical, and
   `scripts/test-template-68k` drives the built package through the guest's
   own UI to its scene and requires the same pixels as the original. What
   stops the other examples is the definition-file front end -- value forms it
   cannot read yet -- rather than anything about the container. Still to do:
   the Counter example with compiled code, and validating method references
   and relocation.
3. Add modern CPU32 code generation with the documented ABI and generated
   dispatch wrappers. Keep 1.0 and 1.5 system definitions as explicit profiles.
4. Inspect the now-extracted Rosemary SDK's sample build, transition-vector ABI,
   embedded relocations and library objects. Use its ELF-to-frozen-package
   pipeline to implement the separate MIPS backend; establish what tool source
   is available before assuming proprietary tools need full reimplementation.
5. Test installation and behavior on each corresponding emulated device. The
   eventual build should run entirely on the modern host; the emulator is a test
   target, not a build dependency.

Definition parsing, diagnostics and object-graph handling may be shareable.
Calling conventions, runtime references and binary package serialization need
separate, evidence-based backends. Do not require ROM or save-state patches to
make a generated package work.

## Rosemary follow-up

The [MIPS sample build trace](ROSEMARY_BUILD_TRACE.md) now records the complete
HelloWorld pipeline, transition-vector evidence from SDK machine code, and a
reproducible Linux code-generation probe. Linux MIPS-I object generation works;
a complete code-free EmptyPackage now builds on Linux, installs through PC Link,
and opens its Scene and help in the unmodified SDK-ROM guest. A restricted native MIPS leaf method also installs and executes through the
normal guest dispatcher, and **a method written in C, compiled with Clang and
linked with lld on Linux, now runs in the guest**: it calls ROM operations
with arguments and an intrinsic through generated stubs and keeps state in
package globals (build trace, "Compiling C on the host"), and **the SDK's
HelloWorld sample, ported to C and built on Linux, draws its box in the
guest** with a package-defined Viewable subclass — from the sample's
**unmodified `HelloWorld.cpp` and the SDK's own headers** (build trace,
"Compiling the SDK's own sources"), complete with its names and sound
(`docs/images/rosemary-helloworld.png`), and **DigiClock** — five methods,
mixins, inherited calls, indexicals — runs in the Stamper
(`docs/images/rosemary-digiclock.png`). Both now build **from their unmodified source directories** with
`build_sample.py` (`.cdef`/`.odef` front end). Class operations, imported
package interfaces, styled Text and images remain. See
[guest validation](ROSEMARY_ROM_TESTING.md).

## What the SDK manuals add (checked 2026-09-13)

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
traces above. Nothing in them contradicts the decoded formats. The Magic
Script description is the likely key to the scripted (non-native) method
records the inspector currently leaves undecoded.
