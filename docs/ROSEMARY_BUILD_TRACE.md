# Rosemary MIPS sample build trace

This traces how the Rosemary (Magic Cap 3.x, MIPS) SDK builds a package, and
how Hatter's [MIPS toolchain](../toolchains/mips/README.md) reproduces that
pipeline on a Linux host. The SDK is `magicdeveloper.sit`, preserved in the
Magic Cap archive as `Software/MIPS/SDK/magicdeveloper.sit`. All 17 preserved
SDK sample directories build from their original sources; the guest results
are in [guest testing](ROSEMARY_ROM_TESTING.md), and the container layouts in
the [Rosemary container notes](ROSEMARY_CONTAINER_FORMATS.md).

## Current status

The chronological notes below include superseded investigations. The current
toolchain status is:

- all 17 preserved SDK sample directories build from their original sources;
- code-free packages, native methods, imported interfaces, mixins, indexicals,
  package globals, class operations, Text/images, and Magic Script are covered
  by the host builders and sample validation reports;
- MIPS o32 argument shifting is covered through five-argument calls such as
  HelloWorld's `FillBox` and is regression-tested for multiple stack words;
- remaining work is generality and compatibility outside the preserved sample
  set: arbitrary C++/ABI signatures, unmodeled relocation forms, all historical
  ROM target profiles, persistence/uninstall behavior, and unsupported frozen
  record variants.

## Primary evidence

All SDK paths below are relative to the extracted archive's
`MagicDeveloper/MagicDeveloper/` directory. Hatter's local copy keeps only
`Interfaces/` and `Samples/` (as `sdk/mips/Interfaces/` and
`sdk/mips/Samples/`); the scripts, libraries and tools are in the archive.

- `Samples/HelloWorld/HelloWorld.make`, `.cpp`, `.cdef`, `Objects.odef`.
- `Scripts/SelectCompiler`, `SelectTarget`, `LinkerScriptSeparatePackage`.
- `Interfaces/Generic.h`, `CoreDefines.h`, Apollo/Sputnik generated interfaces.
- `Libraries/Apollo/SeparatePackageLib.o`, `StandardPackage.lib`.
- `Tools/gcc`, `cc1`, `CompileClasses`, `CompileObjects`, `LinkXFile`,
  `BuildMagicCapPackage`.

The compiler binaries contain version string `3cygnus-2.7.1-951010`.
The inspected compiler/class/package tools are supplied as classic Mac binaries;
no corresponding compiler or package-tool source tree was identified in the
extracted archive. Sample and interface source are present. This does not establish
that the tool sources cannot be found elsewhere.

## HelloWorld, from definitions to package

HelloWorld provides a small nontrivial example: a `Greeter` class inherits
`Viewable` and overrides `Draw`. The C++ method uses system drawing methods;
object definitions construct the scene, greeter, installation list and metadata.
EmptyPackage is smaller but does not exercise a new drawing method.

| Stage | Input | Tool/output |
| --- | --- | --- |
| Define class | HelloWorld.cdef and system definitions | CompileClasses generates HelloWorld.cx and package .xh/.xph headers |
| Compile code | HelloWorld.cpp, generated headers, platform interfaces | gC/GCC produces HelloWorld.cpp.o |
| Define objects | Objects.odef, class definitions, optional locale phrases | CompileObjects produces Objects.ox |
| Resolve classes, objects and code | MagicCap.cx, MagicCapLibrary.x, .cx, .ox, compiled code and support object | LinkXFile produces .x.o, frozen package .fp, exports .exp and debug .dx |
| Link executable | compiled .o, generated .x.o and required code libraries | ld with supplied script produces .cd ELF |
| Assemble package | .fp and .cd | BuildMagicCapPackage -forEmbeddedMIPS produces HelloWorld-MIPS-USA |

These are dependencies, not a command sequence that can simply be pasted into
Linux. MPW variables, paths and generated rules must be translated. The last
stage sets Finder type `MCFP`, creator `MCAP`; extension alone is not a format or
architecture identifier. The normal build depends on the system class image
`Interfaces/MagicCap.cx`, as well as headers and code libraries.

## Confirmed machine and calling conventions

The SDK's Apollo support object is ELF32, big-endian, MIPS-I, relocatable.
`SelectCompiler` configures soft float, short enums, signed char, embedded PIC,
transition vectors and no ABI calls. It also supplies old compiler dump files
through `MACCPPDUMP`, another dependency a modern compiler cannot consume as-is.

`Generic.h` defines a transition vector with two words: code address, then global
pointer. Function pointers refer to this descriptor rather than directly to
instructions. The SDK distinguishes these from method code addresses; its
`MINIMAL_TRANSITION_VECTORS` path uses raw method code addresses with a separately
cached global pointer. A blanket conversion of every code reference to a descriptor
would therefore be incorrect.

Disassembly of `SeparatePackageLib.o`, `ReadBitField`, confirms the mechanism:

1. Save the caller's `$gp` and return address on the stack.
2. Find the `_functionPointer_Wildcard_SystemPublic_475_` import through a
   package-relative reference and dereference it to obtain the vector.
3. Load the callee's `$gp` from vector offset 4, and code address from offset 0.
4. Call the code and restore the caller's `$gp` afterward.

The two-word descriptor is therefore supported by both source and machine code.
The descriptor also explains why an ordinary modern C function-pointer call is
not sufficient.

## Linking is another compatibility boundary

The SDK linker script places data at virtual address zero with `_gp` at its
start, and text at `0x10000000`. These are link-time regions, not instructions
to map a guest package at those fixed addresses. It includes `.tvtab` and uses
`--embedded-relocs`; LinkXFile uses `-output-elf -transition-vectors`.

The support object contains relocation types 10, 7 and 36 among others. Current
readelf/LLVM label type 36 `R_MIPS_RELGOT`; in this historical object it occurs
on a `lui` paired with a GP-relative low instruction. Do not assume a modern
linker's interpretation of that numeric type matches the historical toolchain.
Its exact transformation needs investigation against the old linker or source.

The SDK's old ELF flags also differ from modern o32 object flags. Successfully
reading both objects does not prove they can be mixed in a single link.

## Linux experiment results

A probe reproduced these checks on Linux without a Mac and without modifying
the SDK:

- Clang 18 compiled a freestanding integer function to ELF32 big-endian MIPS-I.
- Its assembler built a one-argument descriptor-call adapter that switches and
  restores `$gp`; inspection confirmed the intended instructions and delay slots.
- Clang rejected both `-membedded-pic` and `-mtransition-vectors`.

This demonstrates available Linux code generation and an explicit ABI adapter.
The later SDK-package and guest-validation sections extend it through package
construction, installation, and execution. Clang reports its MIPS-I support as
experimental. No original MPW tool was executed.

## Implementation decision and next work

Use the SDK as the specification and compatibility reference. Do not start by
porting all of GCC or assuming ordinary Linux MIPS packages work.

First inspect `MagicCap.cx`, `MagicCapLibrary.x` and a known frozen package to
establish the class/object serialization and imported-reference format. Those
inputs are needed even for EmptyPackage. Implement a read-only inspector before
a writer, retaining unknown fields and checking boundaries.

In parallel conceptually, the compiler choice has two routes to evaluate:
recover the historical GNU modifications and rebuild them for Linux, or use a
modern compiler with explicit generated call wrappers and controlled relocation.
The latter has a small successful assembly probe, but is not yet sufficient for
arbitrary C++ or package globals. Avoid choosing between these routes until the
historical relocation and function-pointer behavior are understood.

The first complete build milestone should be a data-only EmptyPackage, followed
by HelloWorld's method override. Exact Apollo/Sputnik SDK interface compatibility
with the current DataRover ROM must be checked before interpreting installation
failures as compiler bugs. No ROM or save-state patching is part of this design.

## Container follow-up

The [read-only container inspector](ROSEMARY_CONTAINER_FORMATS.md) now checks SDK
section directories, section-12 names, and complete SALTCOD package/bundle
boundaries. It was exercised on 128 intermediate containers and 32 frozen
packages. Semantic class/object decoding and package writing remain outstanding.

### EmptyPackage values generated on Linux

The follow-up generator `toolchains/mips/build_empty_objects.py` now emits
five object value fragments with real local/imported selector assignments and
26 checked references. Pixel conversion is backed by the development guide
(page 97) and SDK Graphics.h. A locator-stride bug in import analysis was fixed.
See the latest EmptyPackage section in the
[container notes](ROSEMARY_CONTAINER_FORMATS.md) for exact
selectors, validation and limits. Named-object extras, the cluster root and
installation remain pending; these outputs are not yet a complete package.

### EmptyPackage name storage

The sample generator now includes the static name dictionary and two backing
objects, increasing its output to eight value fragments with 29 references.
The ROM trace corrected an earlier assumption: named subtype-three objects
resolve names through the cluster dictionary, not per-object name extras.
All 32 existing dictionary backing pairs reproduce exactly, covering 810 names;
143 research tests pass. The package cluster and installation remain pending.

### Cluster validation and corrected Boolean fields

All 32 existing cluster bodies now reconstruct from decoded fixed fields and
internal names, with PackageData validation. This caught reversed Boolean bit
numbering in the new object encoder; the ROM's Scene_AddToHistory caller and
corpus cluster flags establish MSB-first SDK offsets. Generated sample bodies
and regression expectations are corrected. No ROM was changed.
Remaining assembly dependencies are the empty export/shared-object tables and
import-status metadata, followed by cluster/heap integration and guest testing.

### Empty metadata tables constructed

EmptyPackage now has 17 fragments: object/name data plus empty export/shared
tables and PackageData/import-status objects. Thirty-seven references resolve
within the generated graph or SDK imports. Metadata validation records 89 exact
existing-body matches and 22 nonempty import-status variants. 149 tests pass.
The remaining assembly work is connecting a validated cluster root and emitting
the code-free envelope for isolated guest installation testing.

### First host-built package runs in the guest

The code-free EmptyPackage is now built end-to-end on Linux and installed via
PC Link in the unmodified Rosemary SDK ROM. The guest exposes its Storeroom
package, creates its Hallway door, opens the Scene, and displays the sample's
help text. See [guest testing](ROSEMARY_ROM_TESTING.md) for reproducible
commands and hashes. Native MIPS method linking remains the next milestone.

### Native-method preparation

A restricted native subclass constructor now matches 50 original class bodies.
A fresh Clang-compiled, receiver-ignoring Boolean leaf produces eight bytes of
relocation-free MIPS-I code. The extractor rejects unresolved dependencies and
unsupported ELF layouts rather than silently treating them as linked code.
Native package assembly and guest dispatch are still pending; the successfully
installed code-free baseline remains unchanged.

### Native candidate assembled; activation failure localized

NativeLeafProbe now contains one native CanGoTo override. The SDK-ROM guest
receives it but rejects activation. Correctly prefixed watchpoints place the
first exception inside FixUpCodeAddress's method-value validation, after code
and initialization attributes load. Offline tests pass (158), but native
execution remains unverified. Next is inspecting the offending method-code
slot/value; preserve the working code-free package as the control.

### First host-compiled native method executed

The native candidate's failure was missing reserved constructor/destructor
function-table slots 1/2. Both now contain null offsets; the leaf uses ID 3.
A SoftwarePackageContents.CanGoTo override installs and executes through normal
guest UI: three watchpoint hits at its RAM entry, with the expected operation
selector and receiver. Read-only snapshot inspection located the code; no ROM
or state patches were used. See [guest testing](ROSEMARY_ROM_TESTING.md) for details.
The next ABI check is a package-native call into a ROM method or intrinsic.

### Native-to-ROM calls: the convention, from package code and the guest

Established 2026-09-13 from Ne2000.pkg method code (file offset 14516 on),
`SeparatePackageLib.o` (`__DispatchObjectMethod` at 0xe1c) and a guest run of
a host-built probe (see [guest testing](ROSEMARY_ROM_TESTING.md), "Native-to-ROM call verified"):

- An operation call is `t7 = selector; a0 = receiver (a1.. = arguments);
  jalr` to the ROM's object-method dispatcher. Package code reaches the
  dispatcher through a globals word the loader fills from an initialization
  entry with source kind 6, interface `Dispatchers`, index 1, destination mode
  4 (index 0 = intrinsic dispatcher, 2 = inherited, 3 = delegated; the corpus
  requests `required_count = 7 - index`). The glue in the SDK library is
  exactly `lw t0, slot(gp); jr t0`.
- The selector for a SystemPublic operation is its **ordinal in
  PublicInterface.cdef + 1** and needs no relocation: `CanGoTo` (4319) was
  dispatched as `t7 = 0x10E0`, and the probe's `Name` (4186 → 4187 = 0x105B)
  reached `Object_Name` with `t7 = 0x105B`, the same value the ROM's own
  callers use. Package-defined operations use package selectors from the
  defined-component table; their code-side handling is not yet examined.
- On entry to a package method the dispatcher sets **`$gp` to the package
  globals base** (probe: `gp = 0x003CCBA0`, code at `0x003CCBB4`), so
  gp-relative loads of the initialized globals work without relocation.
  The ROM call returns with `$gp` changed (`0x0000E020`), so `$gp` must be
  saved and restored around every call, as the corpus code does.
- The first 16 bytes of a frame are the o32 argument home area; saved
  registers go above them. The result comes back in `v0`.

Clang 18 (`--target=mips-unknown-elf -march=mips1`) can assemble this form
directly; the probe is hand-written assembly with no relocations. Compiling C
that calls operations still needs generated wrappers (or the dispatcher-slot
convention expressed as inline assembly) because no modern compiler emits
the `t7` selector convention.

Second probe (NativeRomCall2, [guest testing](ROSEMARY_ROM_TESTING.md)): arguments follow o32
(`a1` onward, stack from 16(sp) as the Ne2000 code shows for five-argument
calls), and **intrinsics** are called the same way through `Dispatchers`
index 0 with `t7` = the intrinsic's literal number in PublicInterface.cdef
(`intrinsic Honk = 77;`) and no receiver.

### Compiling C on the host: the working pipeline

`toolchains/mips/build_c_package.py` (guest-verified 2026-09-13, see
[guest testing](ROSEMARY_ROM_TESTING.md), "C-compiled method verified"):

1. **Compile** with Clang 18: `--target=mips-unknown-linux-gnu -march=mips1
   -mabi=32 -msoft-float -fPIC -mabicalls -ffreestanding -fno-builtin
   -fno-jump-tables`. This yields the same shape as the SDK's GCC output:
   calls through GOT entries in `t9`, `$gp` copied to a saved register and
   reloaded around calls, data reached through GOT page entries.
2. **Stubs**: every undefined symbol must name a SystemPublic operation or
   simple intrinsic (PublicInterface.cdef, via `declarations()`); a
   five-instruction stub loads the dispatcher address from `__dispatchers`
   (a seven-word array in `.data`) through the GOT, sets `t7` to the
   selector (ordinal + 1) and jumps. Class operations, imports from other
   packages and locators are not generated yet.
3. **Link** with `ld.lld -shared -Bsymbolic` under a script placing `.got`
   first at address 0 with `_gp = 0`, then `.data`/`.rodata`/`.bss`, and
   `.text` at 0x10000000. lld honours `_gp = 0`, so GOT accesses become small
   positive `$gp` offsets, and the GOT ends up holding link-time addresses:
   text (>= 0x10000000) or globals (< image size). No dynamic relocations
   are emitted; MIPS local GOT entries are implicitly base-relative.
4. **Patch prologues**: Clang computes `$gp = t9 + _gp_disp`, which assumes
   text and data keep their link-time distance; in the guest they are
   separate buffers. Using the object's `_gp_disp` relocations, the
   `lui/addiu/addu rd, r, t9` triple is rewritten to `rd = $gp + 0`. The
   dispatcher supplies `$gp` = globals base on entry and callers keep it
   valid in the delay slot before `jalr`, so callees always see it.
5. **Globals image and script**: `.got + .data + .bss` becomes the global
   data; the initialization script writes literal bytes, `code`-relative
   words for GOT entries into text, `globals`-relative words for entries
   into data (page entries beyond the image stay literal), and
   `Dispatchers` index 0–3 resolutions into `__dispatchers`.
6. **Freeze** with the existing single-method builder: code = `.text`,
   function ID 3 = the method's text offset.

Verified in the guest: three ROM calls with arguments, a static helper call,
and a static counter whose final value matched prediction. This is the
"modern compiler with generated wrappers" route from the implementation
decision above; the historical GCC branch is not needed for code of this
shape. Still open for general packages: multiple classes/methods and their
class records, class operations, package-defined selectors, Text and other
constant objects, imported interfaces and locators, and a C++ front end for
the SDK's own headers.

### The SDK's generated GNU header, and HelloWorld

`Interfaces/Apollo/MagicCap.gnu.xh` is the class compiler's output for the
GNU toolchain. It confirms the selector rule from the tool's own numbers
(`operation_ContentBox 37`, `operation_FillBox 671`) and shows how the
historical compiler was driven: every call is a statement expression
declaring a pseudo-function `__1d_Name(DispatcherAddress, int operation,
Reference self, ...)` (`__2d_` for inherited/delegated calls, which add the
class number) and calling it with `ObjectMethodDispatcher` and
`operation_Name`; the modified GCC turned that into `t7 = operation` and a
jump to the dispatcher. So compiling unmodified SDK sources with Clang
needs only argument-shifting stubs named `__Nd_*` plus the `__Dispatch*`
glue symbols — the same mechanism as the stubs generated now, one level
up. That is the next step for the front end; HelloWorld was ported with a
small local header instead.

HelloWorld itself ([guest testing](ROSEMARY_ROM_TESTING.md)) is the first package with a new
class: `build_hello_package.py` adds an imported `Viewable`, a
package-defined Greeter class whose record names Viewable as superclass and
an imported `Draw` as its native method, a Greeter instance (Viewable fixed
fields + empty subview list) and the Scene's subview list pointing at it.

### Compiling the SDK's own sources (build_sdk_package.py)

Guest-verified with the unmodified HelloWorld.cpp ([guest testing](ROSEMARY_ROM_TESTING.md)):

- **Headers**: `sdk_headers.py` derives a patched header tree from
  `Interfaces/` (CR line endings normalised; 1997 C++ implicit `int` on
  `const` and `extern "C"` declarations made explicit; every edit counted in
  `edits.json`). Compile flags: `-x c++ -std=gnu++98 -fpermissive
  -fno-exceptions -fno-rtti` with `-DALLOW_TRANSITION_VECTOR_DEFINES
  -DROSEMARY_BRINGUP -DCORE_DINO -DPLATFORM_Apollo -DDINO_APOLLO
  -DBOOT_FROM_ROM -DINCLUDE_QUALITY_EXTRAS -DMAGIC_CAP -DCAP_SEPARATE_PACKAGE`
  (from SelectCompiler and MemoryMapDino.asm.h), include paths Interfaces,
  Apollo, Apollo/ExtraInterfaces, MipsHeaders, plus a package header
  directory for the `.xh/.xph` the class compiler would generate.
- **Operation calls**: `__1d_Op(dispatcher, operation, self, ...)` symbols are
  aliased to `__dispN` stubs (N = callee arguments, from the prototype in
  the header): `t7 = a1; t9 = a0; a0..a3 <- a2, a3, 16(sp), 20(sp)`; stack
  arguments 4.. are moved down two slots; `jr t9`. `__DispatchObjectMethod`
  and the other dispatcher symbols are glue jumping through the
  loader-filled `__dispatchers` words. The header's own numbers confirm the
  selector rule (`operation_PartColor 3998` = ordinal 3997 + 1).
- **Intrinsics**: the header calls a `CodePointer`
  `_functionPointer_Wildcard_<Interface>_<n>_` as a plain function pointer;
  only `-mtransition-vectors` could compile that. The derived header routes
  the call to `__tv_<Interface>_<n>`, a stub that loads the word, then code
  from +0 and GP from +4 of the pair it points to, sets `$gp` and jumps.
  The pair is a local eight-byte `.data` object filled by a kind-6
  **pair-mode** resolution (`SystemPublic`, index n); the word is a
  globals-relative pointer to it. Word-mode resolution into the pointer
  itself crashes the guest.
- `__2d_` (inherited/delegated calls, which pass a class number) and
  package-defined class numbers (`ClassNameToNumber(CURRENTCLASS)`) are not
  handled yet; they need the class-number relocation story.

### Inherited/delegated calls, package class numbers, indexicals

- The ROM's `DispatchObjectMethodCommon` (0x13c96e84) hands
  `DispatchObjectMethod` the selector from `t7`, the mode from `t0` (0 plain,
  1 inherited, 2 delegated — set by the three `__Dispatch*ObjectMethod`
  entries) and **the class number from `t8`**. Ne2000's code loads `t8` from
  a globals word before calling the inherited glue; that word is filled by
  an initialization entry of kind 2 with the package-local interface name
  `@ClassName`, resolved against the package's own export table. So
  `ClassNameToNumber(Class)` in package code is a loader-resolved global,
  never an immediate. `build_sdk_package.py` therefore aliases `__2d_*` to
  `__disp2_N` stubs (`t7 = op, t8 = class, t9 = dispatcher`, arguments
  shifted down three slots), emits a `_classNumber_<Class>_` word for each
  class named by the package header (`#define Class_ ({ extern int
  _classNumber_Class_; (ClassNumber)_classNumber_Class_; })`), and the
  package exports `@Class` (build_exports.py, mirroring Ne2000's
  PackageExportTable / HashEntries / CliqueNameTable bytes). Verified in the
  guest ([guest testing](ROSEMARY_ROM_TESTING.md), "Inherited calls").
- Indexicals in the GNU header are `_indexical_Wildcard_<Interface>_0_ +
  ordinal * 8`: one base locator word per interface, resolved by a kind-1
  entry at index 0 (the pipeline emits the word and the resolution; not yet
  exercised in the guest).

### Generic assembly (build_package.py) and DigiClock

`build_package.py` assembles any single-cluster code package from a spec:
objects (fixed fields, ObjectList bodies, Text, subview lists; references by
tag, system indexicals by name), package-defined classes (superclass list
of imported class selectors, native method records, own-fields word, fixed
layout), package indexicals, names, the metadata objects, exports
(`@Class`, `@iIndexical`), the function table, code and the initialization
script. Imports are allocated on demand in a fixed order. DigiClock is its
first user ([guest testing](ROSEMARY_ROM_TESTING.md)); HelloWorld still uses the older
EmptyPackage-derived builder. What DigiClock established beyond HelloWorld:

- Class records with several superclasses: the list holds the flavor first,
  then mixins; a mixin's leaf field follows the flavor's fixed part (Box 48
  bytes, then `destination`), and the abbreviated class format covers the
  whole instance (13 nibbles); the own-fields halfword 0x9004 (leaf size 4)
  matches corpus classes with one mixin field.
- Package indexicals are heap objects exported as `@iName` (kind locator,
  count 1, selector = the object's locator) and reached from code through a
  `_localLocator_iName_` word resolved by a kind-1 entry on `@iName`.
- The derived headers also hoist every `__1d_/__2d_` prototype to namespace
  scope with C linkage and turn the indexical macros into plain expressions
  over one namespace-scope `extern "C" int _indexical_Wildcard_X_0_`;
  otherwise Clang rejects the C/C++ linkage clash between `extern "C"`
  methods and `static` helpers (DigiClock has one).

Open: the `.cdef`/`.odef` front end (DigiClock's spec and package headers
are hand-transcribed), class operations (dispatchers 4–6), imported package
interfaces, mixins with more than one leaf field, Text objects with styles,
and images.

### The front end: .cdef / .odef -> package (odef_frontend.py, build_sample.py)

`odef_frontend.py` implements the definition languages of the Guide to
Development Tools ch. 6 as far as the samples use them: `define class` with
`inherits from` (first entry the flavor, then mixins), `overrides`, `field`,
`operation`/`attribute` declarations; `indexical` declarations; `instance
Class tag 'Name'` with int/hex/Boolean/'string' (with `\n`, `\uXXXX`),
`<pixels>` dots and boxes, `(Class tag)` references, `iIndexical`
(system -> imported locator, package -> bound object), `nilObject`,
`N.s`/`N.b`, `operation_X`; ObjectList entries; the `subview:` pseudo-field;
`indexical iX = (Class tag)`. Fields the sample omits are nil (0). Class
layouts come from the SDK class image: the flavor's derived layout, each
mixin's leaf fields appended (weak references as format 14), then own
fields; the own-fields word is `0x9000 | leaf bytes`. Method function IDs
are assigned in declaration order to the `Class_Op` functions present in
the compiled object. `build_sample.py <Sample>` runs the whole chain.

### Front-end coverage of the 17 SDK samples (2026-09-13)

`build_sample.py <Sample>` now builds **all 17** from their unmodified
source directories: HelloWorld, DigiClock, EmptyPackage (code-free),
PackageSceneSample, ExportSample, ImportSample, ScrollableTextField, Puzzle,
TimeMinder, WindowTool, RulesSample, SpeedScrollSample, and the four Magic
Script samples AccessDemo, Exceptions, SimpleStack, TicTacToe, and the
code-free Scenes (objects only: a `PackageCluster` root and no
function-offsets/code/init attributes, the form of CujoChat's second package
and GammonBundle's). What that took, all now in the pipeline:

- Definitions: tabs/whitespace in statements, `class operation`,
  `intrinsic` (package intrinsics become direct calls), `attribute` (getter
  and `SetX` setter as package operations), `#ifdef DEBUG` blocks dropped,
  concatenated string literals with `\'` escapes, `indexical iX =
  nilObject`, namespace-qualified tags (`Main.tag`), `data:`/`extra:` hex or
  `include 'file' a:b` extra data, bare `h,v` PixelDot and `l,t,r,b`
  PixelBox values, `4.0` Fixed literals, `operation_X` for package
  operations, Text instances with concatenated or empty text, every
  ObjectList subclass (DenseObjectList, Trigger) as a list body.
- Layouts: mixin groups placed as the class image implies (Door's
  HasDoorway: Swallower/Entrance/HasLock 48..55, own fields at 56),
  PixelDot as two halfwords, PixelBox, Micron/Fixed/Function/Pointer
  fields, subclasses shadowing an inherited field name (ConfirmationDialog
  .sound), package classes inheriting from package classes.
- Generated package headers: `struct Class_Fields`, per-field
  `_Class_field_kind_/type_/fixedOffset_/class_` tokens (bit fields as
  `byte,bit`, Dot fields as `_h`/`_v` Micron words) so Accessors.h's
  `Field/SetField` work; package operation macros with hoisted prototypes.
- Runtime: `toolchains/mips/mcap_accessors.cpp`, a port of SeparatePackageLib.o's
  Read*/Write*Field, BeginModifyFlavor, PeekFlavor and PeekUsableFlavor
  (reference tag bit 31/30 fast paths, indirection kind 1, slow paths
  through the Internal* intrinsics 471–501, 565/566, 583), compiled in only
  when referenced; class-method dispatchers 4–6; several `.cpp` per package;
  `.rel.dyn` words and out-of-extent GOT page entries handled.

Still outside the pipeline: package mixins with fields (see below). Guest-verified so far: HelloWorld,
DigiClock, PackageSceneSample (scene opens), TimeMinder (its `connect`
command appears under "Clock commands"), Puzzle and ScrollableTextField
(install), RulesSample (installs, activates, its Stamps scene opens),
ExportSample + ImportSample (ImportSample's button creates an ExportSample
object and installs a Greeter into a new Stamper bank through the imported
interface; see "Cross-package interfaces"), SpeedScrollSample (its tool
appears on a new "trinkets" tools page and creates a scroller on touch; see
"Package mixins").

### Package operation numbers: `operationBase1`/`operationCount`

RulesSample was the first sample whose code reads a package operation
number (`operation_CollectionFrequency`, a `_operationNumber_X_` word
resolved by an init entry of kind 3 on the export `@CollectionFrequency`,
the form CujoChat uses 1,998 times). It transferred but failed activation
in `CodeHandler_InitializeCodeGlobals`. Bisecting with the diagnostic
`MCAP_SKIP_FIXUPS` environment variable (drops one fixup category from the
init script; the build is then wrong by construction) moved the failure
past the init script only when the operation-number entries were dropped.
Watching the interpreter showed why: `DynamicInterchangeTable_FindExport`
returned 3 ("entry found, component number 0") for the kind-3 lookups
while the kind-2 (`@Class` -> 0x6B1..) and kind-1 (`@iName` -> RAM
reference) entries of the same package table resolved. The package
interchange table is built from the export table by
`AddExportToThisDynamicInterchangeTable`, and the loader maps a
package-relative operation selector to an operation number through the
cluster's `operationBase1`/`operationCount` fields, exactly as it maps
class selectors through `classBase1`/`classCount`. The corpus clusters
carry both pairs (CujoChat: classes 1355/23, operations 5047/80; Ne2000:
1355/3, 5047/5; the same numbers as their defined-components records);
`build_package.py` only filled the class pair. It now sets
`operationBase1` to the first package operation selector and
`operationCount` to the number of package operations. RulesSample then
activates and its scene opens ([screenshot](images/rosemary-rulessample.png)).
The only `Actor_FailSoon` during installation is PC Link's listener
cleanup after the hangup, not the package.

### Cross-package interfaces: ExportSample and ImportSample (2026-09-13)

`define interface Name "long/name"; class X; operation Y; indexical Z; end
interface` (exporter) and `import Name [or say iText]` (importer) are now
in the pipeline, following the corpus:

- Exporter: one export-table entry per kind under the long name — (kind,
  long name, count, first selector) — as WCPack's
  `www.genmagic.com/WirelessConnectivity/AirSurferInterface1` (class 1,
  locator 1) and MagicJavaScript's `genmagic.com/JavaScriptInterface1`
  (class 4, operation 18, intrinsic 2). Members must therefore be
  consecutive selectors in interface order (checked; ExportSample exports
  one class and one operation).
- Importer: one import record per kind under the long name with the local
  selector base and count (Ne2000: `genmagic.com/WCPackInterface1` classes
  1359.. after its own 1355..1357, operations 5053.. after 5047..5051);
  code words `_importClass_<Iface>_<n>_` / `_importOp_<Iface>_<n>_` /
  `_importLocator_<Iface>_0_` (+8·n) resolved by init entries of kind 2/3/1
  on the long name with index = member ordinal and required count =
  members − ordinal (Ne2000: kind 2 WCPackEthernetInterface1 index 0
  count 11; MagicJavaScript: kind 3 JavaScriptInterface1 index 2 count 16).
  `or say` makes the import weak: kind | 0x80 (WebBrowser40's 0x82/0x83
  on JavaScriptInterface1), and PackageData's `missingCliqueNames` Text /
  `missingCliqueMessageIndexicals` list carry the long name and the
  message object (this last pairing is inferred from the field names; the
  corpus has no `or say` package).
- `build_sample.py` follows `read "X.cdef"` into sibling sample directories
  for the foreign definitions; their `define interface` blocks and class
  signatures feed the importer's generated header (call macros for the
  imported operations in the system header's form).
- Package class operations (`class operation TryAClassOperation`) are
  direct calls like package intrinsics — no corpus package defines a class
  operation, so their method-record form is unknown; ImportSample.cpp
  itself implements it as an `IntrinsicMethod`.
- String literals in reference fields and list entries (`versionText:
  'internal'`, help texts) become implicit Text objects.

Two more things the sample exposed, both general:

**Auto accessors.** `field toBeInstalled: Viewable, setter, getter` plus
`attribute ToBeInstalled: Viewable` declares getter/setter operations the
class compiler implements without code. In frozen class records they are
method entries whose tag byte is an accessor type instead of 0x41 and whose
second word is the field's byte offset (CujoChat: `0x16000635 0x00000000`,
`0x170013c2 0x00000030`; Reversi: `0x16000f91 0x0000003c`). The ROM's
`GetAutoGetterOrSetterAddress` indexes two 38-entry vector tables
(0x13EBAC64 plain, 0x13EBACFC mixin; read from the ROM image): Word 0/1
(get/set), Halfword 2/3, Byte 4/5, Bit0..Bit7 6..21 (Bit0 reads bit 7 of
the byte, i.e. the MSB), ObjectReference 0x16/0x17, ClassSelector
0x18/0x19, OperationSelector 0x1a/0x1b, ClassOperationSelector 0x1c/0x1d,
IntrinsicSelector 0x1e/0x1f, TextReference 0x20/0x21, Pointer 0x22/0x23,
SharedObjectReference 0x24/0x25; `DispatchObjectMethod` passes the entry's
second word in `$gp` (`andi $5, $gp, 0xfff` = offset, `>> 12` = mixin
index). `odef_frontend.accessor_type` maps field types to these and
`build_package.class_record` emits the entries; a native `Class_Op` in the
code takes precedence. Without them the getter dispatch returned nil and
ExportSample crashed the guest ("Cleaning up…").

**`$gp` across ROM calls.** With the accessors in place ExportSample's
second `CopyNear` faulted (`AdEL pc=003C6C6C bad=3C1A13C6`): the
`__tv_SystemPublic_41` stub loads its vector-pair pointer through `$gp`,
but Clang keeps its own `$gp` copy in a callee-saved register and only
re-establishes `$gp` lazily (the first call site had `move $gp,$16` in the
delay slot, the later ones did not), whereas ROM code clobbers `$gp`. GCC
2.7.1, which built the SDK's library, restores `$gp` after every call
(`.cprestore`), which is what the ROM side assumes. All ROM-call stubs
(`__dispN`, `__disp2_N`, the `__Dispatch*` glue, `__tv_*`, and the
plain-C path's stubs) are now call wrappers: they save `$ra`/`$gp`, copy
the caller's stack arguments into their own outgoing area (eight words for
the arbitrary-signature intrinsic and glue stubs), `jalr` into the ROM,
restore and return — so `$gp` is valid for the whole method. All eleven
buildable samples rebuild; RulesSample and ImportSample re-verified in the
guest with the wrappers ([screenshot](images/rosemary-importsample.png): the
Stamper's new "new" bank holding the Greeter "From ImportSample").

### Package mixins, and three record details the ROM is strict about (2026-09-13)

SpeedScrollSample defines `CanStretchSpeedScroller` / `CanChangeSpeedScrollerImage`
with `mixes in with SpeedScroller` (no fields, only overrides) and
`SampleSpeedScroller` inheriting SpeedScroller plus both mixins. In the
corpus a mixed-in package class lists only its base as superclass
(CujoChat's class 1361, mixed into 1355, has the single superclass
TextField), so a package mixin's record is `supers = [base]` with its own
methods, and a class inheriting it adds no fields for it (mixins with
fields are still rejected). The struct parameters of package operations
(`bounds: Box`, `var bounds: Box`) are passed by pointer as the system
header does (`const Box *` / `Box *`), and an accessor may implement a
system operation (`field image: Image, getter` overrides Viewable's
`Image`). It builds, but three guest failures followed, each a general
rule now in the assembler:

1. **No empty method tables.** `SampleSpeedScroller` has no methods of its
   own. Its record carried a method table with count 0; corpus records
   without methods have header word 1 = 0 and no table (CujoChat's
   16-byte records). The ROM's `AppendMethodListDataToExtraFormat` enters
   its per-entry loop before testing the count, walked past the record,
   emitted "runs" from whatever followed and overran the ExtraFormatRun
   buffer into the serial driver: `[exc] AdEL` in
   `UartARxInterruptHandler` with the pattern `xxxx0811`, then "Cleaning
   up…" and, on each restart, a null-pointer `DBE` in
   `GrabAbbreviatedClassTablePointers`. Found with an emulator store
   watchpoint on the clobbered driver word: the last writers before
   the fault were `AppendMethodListDataToExtraFormat+0x184..0x194` from
   `HandleUnlinkedClassExtraFormat`. `class_record` now omits the table.
2. **Header bit 0x08000000 = the extra part is a reference list.** Corpus
   heap headers: Box/Scene with subviews `0xb9…`, ObjectLists `0xb8/0xb9`,
   Text `0xb0`, Images `0xb2…0xb5`; a Box without subviews `0xb1`. We set
   the bit by class (which is why Scenes worked) and not for a Box with
   subviews, so the loader never relocated the trinkets Box's list: the
   live copy still held the package selector `0x34` and `ToolButton_Draw`
   never ran. Now set whenever an object has subviews. This also made
   RulesSample's RuleBox draw its rotating-world Animation
   ([screenshot](images/rosemary-rulessample.png)).
3. **`superview`.** Every subview object in the corpus refers back to its
   parent (21/21 checked in CujoChat and Reversi); the front end fills it.

Also from this round: the header halfwords 3–5 of a class record are
offsets of further tables (`HandleUnlinkedClassExtraFormat` appends the
lists at halfwords 1, 3, 4 with format codes 0x14, 0x15, 0x12 and the class
number data at halfword 5 — for the 0x517/0x518 record classes); zero
means absent, which is what we emit. The ROM's `break 0xf` in
`RemoteDebugMessage` during activation is
`EmbeddedCode_TellDebuggerAboutPackage`, a debugger notification, not an
error.

The store watchpoint is what turned an interrupt-handler crash with garbage
registers into the name of the ROM routine that wrote the garbage.

### Magic Script (2026-09-13)

The Guide ch. 6 stack language is assembled by `magic_script.py` into what
the ROM's `ScriptedMethod_InterpretScript` executes, in the form
WebBrowser35.mc2 (the one corpus package with scripts) carries:

- `InterpretByteCodes` dispatches a 200-entry table of JVM opcodes (read
  from the ROM image at 0x13EBD1F0 and symbolized: `aconst_null`,
  `iconst_m1..5`, `bipush`, `sipush`, `ldc1`, `load_u4[_0..3]`,
  `store_u4[_0..3]`, `pop`, `dup`, `swap`, `iadd isub imul idiv irem ineg
  ishl ishr iushr iand ior ixor iinc`, `ifzero ifnonzero iflt ifge ifgt
  ifle if_equal if_nonequal if_icmp*`, `goto`, `return_u4`, `return_`,
  `invokedispatcher` for 0xb6–0xb9). The Guide's statements map onto them
  (`push (Class tag)`/`push iX` → `ldc`, `push N` → `iconst`/`bipush`/
  `sipush`, `push 0xHEX` → `ldc` of an integer, `push/pop variable n` →
  `load/store_u4`, `if … , goto` → the branch family with 16-bit relative
  offsets, `call Op [proto]` → `invokevirtual`).
- A script is a `ScriptedMethod` object (`constantPool`,
  `typeSignatureIndex`, `variableCount`, bytecode as extra bytes, header
  `0xb0`) with a `ConstantPool` (six list references) whose lists are
  indexed as one 1-based sequence in `ConstantPool_LoadConstant`'s order:
  `objects` (a weak ObjectList, format 14: instances, indexicals and the
  system type-signature indexicals `iReferenceVoidType`,
  `iReferenceUnsignedByteVoidType`, `iPerformWithConfirmationType`, …),
  `integers` (IntegerList, format 4: for each call a descriptor
  `operationIndex << 16 | signatureIndex` and a "method ref" whose value is
  the descriptor's index — the operand of `invokevirtual` — plus large
  literals), `operations` (OperationNumberList, format 10). Index 1 is the
  script's own prototype. `invokedispatcher` dissects the method ref, asks
  the signature object for the argument count, pops them, and calls through
  `CallObjectMethod` (0xb6), `CallInheritedObjectMethod` (0xb7),
  `CallClassMethod` (0xb8) or `CallIntrinsicMethod` (0xb9), by pointer or
  integer return as the signature says. The dispatcher hands the interpreter
  the ScriptedMethod in `$gp`, like an accessor entry's word.
- The attachment `instance Button b 'B' Action: (script s);` makes an
  `UnlinkedScriptClass` record — header halfwords (0x14, 0x18, 0, 0, 0, 0),
  the method-scripts list (`0d000001` + the ScriptedMethod), the single
  superclass (the object's class), one method entry `0x40 << 24 |
  operation` whose word is the 1-based script index — with heap header
  `0xb8` | UnlinkedScriptClass (SystemInternal), counted among the package's
  defined classes (WebBrowser35: records 43–48 of 77), not exported, with
  the base class's abbreviated format; the object becomes that class's
  instance (WebBrowser35 object 364, header `0xb1000575`).
- Front end: `script tag; … end script;` blocks and `Op: (script tag)` on
  instance lines (`parse_odef`); the statement splitter no longer treats
  the `->` of prototypes as a closing bracket (it swallowed everything after
  the first script). Also from these samples: byte-wide fields
  (`SignedByte`/`UnsignedByte`), several `text:` lines in one Text
  instance, and list classes with fixed fields (`StackOfCards`: fields, then
  entries).

TicTacToe in the guest: tapping a board square runs its script through
`ScriptedMethod_InterpretScript` → `invokedispatcher` → the package's
`SquareHit`; X appears and the game answers with O
([screenshot](images/rosemary-tictactoe.png)).

### Phrase files and script intrinsics (2026-09-13)

- **Phrase files.** `build_sample.py --locale USA` (the default) applies
  `<Locale>.Package.Phrases` (Guide ch. 7: `phrase for OBJ field FIELD
  replace 'old' with 'new';`, nested `#include` of phrase files, `dont
  require phrases…` ignored). HelloWorld's own USA phrases rename its scene
  "AhoyWorld" → "HelloWorld", the greeter "Yo, world!" → "Hello World" and
  its help text — the pre-localization strings we had been shipping. The
  other samples' USA files carry no records.
- **`call intrinsic_X` in scripts.** The pool's fourth list
  (`IntrinsicNumberList`, word format 12) holds the intrinsic's selector,
  imported as an interface entry of kind 5; the call is `invokeinterface`
  (0xb9), which `invokedispatcher` routes to `CallIntrinsicMethod`. Verified
  with a synthetic HelloWorld variant, HonkScript: the button's script
  reaches the ROM's `Sound_Honk` through the intrinsic dispatcher
  ([screenshot](images/rosemary-honkscript.png)).
- **Package mixins with fields — not implemented, by evidence.** The corpus
  was checked for a precedent (CujoChat's 23 classes: seven field-less
  records with no superclass at all, mixed into or inherited by others; every
  record with accessors puts them at absolute offsets after a system
  flavor's fixed part). No corpus package defines a mixin with fields, so
  the record form (own-fields word, accessor mixin-index bits, the
  inheriting class's format) cannot be confirmed; the front end rejects the
  case rather than guess. Mixin field *access* from C++ needs nothing from
  us: `ReadMixin*Field`/`WriteMixin*Field` are ROM intrinsics (488/506)
  reached through the usual transition-vector stubs. Also noted from that
  scan: the superclass list order in corpus records follows the `inherits
  from` declaration order (ObjectList last in one class, a mixin first in
  another), so "flavor first" is our convention, not the ROM's requirement.
