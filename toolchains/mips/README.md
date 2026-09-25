# Rosemary build investigation

Run from the current project:

```sh
python3 toolchains/mips/probe.py
```

Requires `clang-18`, `llvm-objdump-18` and the extracted SDK. Tool names can be
changed with `--clang` and `--objdump`. Outputs and command logs go to
`out/rosemary-probe/`. No original SDK files are changed. Clang can select a
cross-compilation target without a separate host executable per target; see
[Clang's cross-compilation documentation](https://clang.llvm.org/docs/CrossCompilation.html).

This is a feasibility probe, **not a package builder**. It compiles a freestanding
integer function and assembles a restricted transition-vector adapter. It checks
ELF class, byte order, machine and ISA flags, saves disassembly of the results
and SDK support object, and records the actual compiler's response to the legacy
flags. It does not assert that merely producing MIPS ELF proves runtime compatibility.

`call_vector.S` accepts a transition-vector pointer and one 32-bit integer
argument, returns an integer result, reserves the o32 argument home area, and
saves/restores `$gp` and `$ra`. It deliberately leaves MIPS-I load/branch delay
slots safe. It does not handle general signatures, stack arguments, structures,
varargs, exceptions, callbacks or package relocation. The adapter has been
assembled and inspected, not executed in the guest.

The default `clang` in this particular environment is a symlink to host GCC;
using `clang-18` explicitly avoids silently selecting that unrelated compiler.

See [the complete build trace](../../docs/ROSEMARY_BUILD_TRACE.md).

## Read-only container inspector

```sh
python3 toolchains/mips/inspect_format.py \
  software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Interfaces/MagicCap.cx \
  software/mips/drivers/Ne2000.pkg
python3 -m unittest discover -s toolchains/mips -p 'test_*.py'
```

The inspector emits JSON, leaves inputs unchanged, and returns a nonzero status
if any file is unrecognized or violates the supported container layout. It
handles concatenated SALTCOD packages, checks lengths and offsets, and retains
unknown tags as raw numbers. Each payload has an offset, length, SHA-256 and
short hex preview. It does not identify CPU architecture from extensions or
claim that a structurally readable package is installable.

Section-12 names are rendered reversibly as Latin-1 and also supplied as hex;
this is not a claim about the SDK's intended text encoding. Unknown payloads
remain in the original file and are not rewritten.

See [format findings](../../docs/ROSEMARY_CONTAINER_FORMATS.md). The current
corpus inspection is saved in `out/rosemary-inspection/corpus.json` and
`summary.json`.

The inspector also exposes class/operation numbers and dependency paths from
supported SDK intermediate sections. To compare decoded system numbers against
the separately generated Apollo header, run:

```sh
python3 toolchains/mips/compare_sdk_headers.py
```

Missing header declarations are reported separately from mismatches; the
comparison is not a claim that every compiled record has been validated.

To check the supported class-definition layout against generated private headers
and selected source inheritance declarations:

```sh
python3 toolchains/mips/compare_class_layouts.py
```

This compares total/leaf storage, field-access base and separate inheritance/mixin
relationships. Unsupported linked/debug record prefixes stay opaque. Source
comparisons preserve conditional alternatives; they do not replace preprocessing.

Supported definitions now also expose individual field names, type references,
bit offsets and method bindings. `compare_class_layouts.py` checks field offsets
and method-name sets against private headers. Unknown flags and binding words
remain raw, and unsupported class variants are still explicitly marked.

Supported operation definitions now expose return types, named parameters and raw
modifier bytes. To compare five HelloWorld-related signatures with the SDK GNU
wrappers, including generated dispatcher/self arguments:

```sh
python3 toolchains/mips/compare_sample_signatures.py
```

The type translation used for this comparison is deliberately limited; it is not
a replacement class compiler or a general C++ header generator.

Generated getter/setter bindings now resolve to their class fields. To compare
representative ordinary, text and shared accessors with source declarations:

```sh
python3 toolchains/mips/compare_accessor_bindings.py
```

The inspector identifies compiler binding kinds; it does not yet implement their
runtime behavior. Ordinary methods remain marked `ordinary-unresolved`.

To locate ordinary methods in the SDK's unstripped MIPS ELF and check their bytes
against its paired ROM image:

```sh
python3 toolchains/mips/trace_linked_methods.py
```

This writes `out/rosemary-inspection/linked-methods.json`, including unresolved
names and transition-vector entries. Addresses are for the SDK Apollo build and
must not be applied to the current guest ROM without a separate comparison.

Frozen imports now expose paired Pascal names and five SDK interchange kinds;
B0 function tables expose one-based IDs, offsets and null sentinels. To scan the
available package corpus and write hashed reports under `out/rosemary-inspection`:

```sh
python3 toolchains/mips/scan_frozen.py
```

Import range resolution and final code-base placement remain unimplemented.

For the observed single 0x71 code attribute plus B0 function table, reports now
link non-null function IDs to entry bytes at `payload start + 4 + code offset`.
These are file positions, not guest addresses; class/method names still require
frozen heap and operation-reference decoding.

Flags-zero heap attributes now expose bounded body/reference records, preserving
raw package-local class and locator selectors. Named-block bodies and external
counted names follow different loader paths. The inspector does not yet resolve
heap selectors or label class-method bodies.

To map imported metaclasses and operation selectors through SDK interface
declarations, decode supported class method lists, and connect their native IDs
to code previews:

```sh
python3 toolchains/mips/link_package_methods.py
```

The report preserves unknown and ambiguous mappings. It identifies the metaclass
and SDK-declared operation names; represented class names, package-local operation
names and runtime export availability remain unchecked.

Defined-component ranges now distinguish package-local operations from imports.
Method linkage includes object operations, class operations and intrinsics, and
reports missing/unlocated function-ID sets per package. Component names absent
from the supplied interface declarations remain unresolved.

The observed 0x53 object-addressing form now maps heap records to package-local
locator selectors. Method reports follow the code cluster's class-array pointer
to attach represented class selectors, checked against defined class ranges.
These numeric identities do not supply source-level class names.

A0 global-initialization attributes expose globals size and supported bytecode
prefixes. Stateful interface-resolution instructions stop decoding with an
explicit `partial-global-init` status and preserved remainder. No initialization
writes or relocations are executed.

Initialization decoding now handles C/D resolution operands, reused and compressed
interface names, and index updates. All corpus scripts reach a stop instruction;
this establishes byte boundaries only. Opcode E still preserves a partial
remainder, and runtime writes/export resolution remain unimplemented.

Run `python3 toolchains/mips/validate_global_init.py` to audit initial-load
(mask 0x0f) globals writes with runtime values kept symbolic. The hashed report
is `out/rosemary-inspection/global-init-validation.json`. All 30 code packages
pass bounds/alignment checks for 12,912 write spans. There are 124 outlying code
pointer offsets, all `0xbdcdcdcd`, retained as advisory findings; their purpose
is unverified. This audit does not resolve runtime exports or execute packages.
See the initial-load audit section in `docs/ROSEMARY_CONTAINER_FORMATS.md`.

Run `python3 toolchains/mips/resolve_global_sources.py` for initialization
source classification and SDK declaration names. `global-sources.json` records
2,022 named SDK references, 210 dispatcher fallbacks, 3,055 package-local entries
and 132 external-interface entries, with runtime addresses left unresolved.
The declaration parser includes indexicals and isolates the first interface in
multi-interface cdef files. Local interchange-table mapping remains to be decoded.

Local export mapping now follows the package's heap export/name tables:
`global-sources.json` maps all 3,055 local initialization references to frozen
selectors, and `package-methods.json` labels 214 classes from singleton local
exports. `package_exports.py` validates the observed table layout and preserves
export record offsets. These are not installed runtime component numbers.

The source report now searches all 32 packages for non-SDK interface providers:
116 of 132 references have export candidates (8 unique, 108 ambiguous), and 16
have none. Of matched references, 100 include a same-package candidate. It also
records ROM string occurrences for missing WCPack/SpellFinder interfaces, clearly
separated from validated exports or runtime resolution. No provider is installed
or automatically selected by this read-only analysis.

After regenerating `global-sources.json`, run
`python3 toolchains/mips/rom_interface_exports.py` to check selected ROM
export object chains. Both US ROMs supply export ranges for all 16 references
missing from the package corpus; the Japanese ROM supplies 14, with SpellFinder
unmatched. `rom-interface-exports.json` keeps hashes, object offsets and encoded
selectors. It is a bounded layout reader, not a runtime linker or general ROM
parser; selectors differ between ROMs.

`build_global_init.py` is the first construction component: a bounded subset of
A0 initialization payloads, with BNum/count encoding, literal/zero writes,
relative words and explicit resolution updates. `finish(code_size)` decodes
and audits the result. The second header word must be supplied explicitly.
`transformed_words` implements width checking and multiply/add for an already
resolved source; neither helper resolves runtime exports or creates a package.
The 40-byte example and its decoded report are under `out/rosemary-inspection/`.

Run `python3 toolchains/mips/build_frozen.py` to regenerate package envelopes
and heap records into `out/rosemary-inspection/rebuilt/`. All 25 corpus files
(32 packages, 5,543 heap objects) reconstruct byte-for-byte; class/object body
contents and other attribute payloads are retained. The module also provides
encoders for imports, component ranges, addressing and function offsets. Valid
new cluster/class bodies and abbreviated class metadata are still required
before this can build a new installable application.

Attribute 0x10 abbreviated class formats now decode and rebuild. Run
`python3 toolchains/mips/compare_abbreviated_classes.py` to compare their
fixed sizes with named SDK layouts: 1,070 matches, zero mismatches, and 321
without a comparable layout. The report retains raw format nibbles; full field
serialization and construction of new class bodies remain unfinished.

Run `python3 toolchains/mips/derive_fixed_formats.py` for the EmptyPackage
field-format investigation. SoftwarePackageContents, ObjectList and Text match
94 corpus entries. Scene and CodePackageCluster remain explicitly unsupported
at compound/pointer types. Mixin base offsets are required inputs, not guessed;
this is format derivation, not complete field-value or package serialization.

Fixed-format derivation now covers Scene and CodePackageCluster too, including
Dot, halfwords, the observed roster/code pointer types and component selectors.
All five selected classes match 136 corpus records without unassigned words.
Scene's border mixin offset is explicit and checked against the SDK size layout;
general mixin placement and field-value/extra-data serialization remain separate
work. The earlier unsupported-layout notes above describe the prior stage.

`build_object_values.py` encodes fixed fields from the derived layouts with
explicit values and LSB-first Boolean bits. It also encodes strong/weak/empty
ObjectList bodies; all 361 corpus lists reconstruct byte-for-byte. A standalone
SoftwarePackageContents body under `out/rosemary-inspection/` uses illustrative
selectors only. Frozen Text encoding and full sample assembly remain pending.

Plain Text object bodies can now be encoded/read with `plain_text` and
`read_plain_text` in `build_object_values.py` (ASCII and non-surrogate BMP,
no styles). Run `python3 toolchains/mips/validate_text_values.py` to check
existing imported Text bodies: 862 byte-identical, 2 equivalent, 29 unsupported.
See the latest Text section in `docs/ROSEMARY_CONTAINER_FORMATS.md` for ROM
addresses, limitations, and remaining package assembly work.

`python3 toolchains/mips/build_empty_objects.py` generates EmptyPackage's
five object value fragments and import/class-format payloads under
`out/rosemary-inspection/empty-package-objects/`. The manifest records the local
and imported selectors, all 26 reference targets, explicit field values and
source hashes. Coordinates use the SDK's documented pixel units. These are
assembly inputs, not an installable package: names and cluster construction
remain. The generator transcribes this one sample rather than parsing .odef.

Object names now use `build_object_names.py`: a static dictionary and its lookup
and TextHeap bodies. `python3 toolchains/mips/validate_object_names.py`
reconstructs all 32 corpus dictionaries' backing data exactly (810 names).
EmptyPackage generation now produces eight fragments and 29 reference entries,
including the two display names. The missing cluster root must connect the
name dictionary before these can form an installable package.

Cluster validation: `python3 toolchains/mips/validate_clusters.py` rebuilds
all 32 corpus roots and checks their PackageData bodies. `build_cluster.py`
constructs a root from explicit fixed values and an internal ASCII name. This
validation caught and corrected Boolean encoding: SDK bit offsets are MSB-first
within each byte. EmptyPackage's regenerated autoActivate/addToHistory masks
are now 80/04. Empty export/shared-object tables and import-status metadata
remain before connecting a complete root. 146 research tests pass.

`build_package_metadata.py` now provides empty export/shared tables and package
import-status objects. `python3 toolchains/mips/validate_package_metadata.py`
finds 89 exact corpus matches; 22 nonempty import-status bodies differ from the
empty constructors. EmptyPackage generation now emits 17 fragments with 37
checked references. The cluster root and final heap/envelope remain to assemble.
149 research tests pass.

`python3 toolchains/mips/build_empty_package.py` now assembles a complete
experimental 1,468-byte code-free candidate at
`out/rosemary-inspection/empty-package-candidate/EmptyPackage.pkg`, with a
manifest. It includes 18 heap objects and the imports, addressing, abbreviated
formats and heap attributes seen in code-free corpus packages. Page fields can
be supplied with `--first-page`/`--last-page`; the default 0..0 is a trial value,
not a general page allocator. Installation evidence is tracked in
`docs/ROSEMARY_ROM_TESTING.md`. 151 research tests pass.

**Guest milestone:** the default 1,468-byte candidate installed through PC Link,
created its Hallway door, opened its Scene, and displayed its generated help
text in the unmodified SDK-ROM guest. See `docs/ROSEMARY_ROM_TESTING.md` and
`docs/rosemary-empty-package-validation.json` for evidence and the tested hash.
Native-method package construction is the next step; this sample is code-free.

Native-method preparation:

- `python3 toolchains/mips/validate_native_class.py`: restricted one-super,
  one-native-method class constructor reproduces 50 corpus classes exactly.
- `python3 toolchains/mips/build_native_leaf.py`: compiles/extracts the
  8-byte relocation-free MIPS-I true-returning method into
  `out/rosemary-native-probe/`, retaining compiler output and hashes.

These new pieces are not yet assembled into a guest-tested native package.
CodePackageCluster/class/function-table integration and dispatch validation are
next. The existing code-free EmptyPackage stays the tested baseline.

`python3 toolchains/mips/build_native_package.py` now assembles the leaf
into a 1,754-byte candidate (run build_native_leaf.py first). Offline linkage
passes, but the SDK guest rejects activation in FixUpCodeAddress. See the
native-candidate section of `docs/ROSEMARY_ROM_TESTING.md`; tracing the offending
method-code value is next. The code-free EmptyPackage remains working.

**Native milestone:** NativeLeafProbe now installs and executes its compiled
CanGoTo override through normal package UI dispatch. Function IDs 1/2 must be
reserved null constructor/destructor slots; the leaf uses ID 3. The probe now
subclasses SoftwarePackageContents so opening the package exercises it.
Three entry hits are recorded in `out/rosemary-native-probe/dispatched.log`;
see `docs/rosemary-native-leaf-validation.json` for the tested hash and limits.
158 research tests pass. Native-to-ROM calls are the next milestone.

**ROM-call milestone:** `python3 toolchains/mips/build_rom_call_package.py`
assembles `rom_call.S` (Clang 18, MIPS-I) into NativeRomCall, whose `CanGoTo`
calls the ROM operation `Name(self)` through the object-method dispatcher
resolved into globals word 0 (`Dispatchers` index 1). The SDK-ROM guest
dispatched it, `Object_Name` ran with the probe's receiver and selector
0x105B, and control returned with a result. Selector = SystemPublic ordinal
+ 1; `$gp` = package globals on entry and must be restored after ROM calls.
See `docs/rosemary-rom-call-validation.json` and ROSEMARY_BUILD_TRACE.md.
160 research tests pass. Next: arguments, intrinsics and package globals.

**C milestone:** `python3 toolchains/mips/build_c_package.py c_probe.c`
compiles a C method with Clang (MIPS-I o32 PIC), generates dispatcher stubs
for the ROM operations it names, links with lld under a package-shaped
script (`_gp = 0`, GOT first, text at 0x10000000), patches the `_gp_disp`
prologues, and emits the globals image plus initialization script (GOT
relocation as code/globals-relative words, `Dispatchers` slots). The guest
ran it: three ROM calls, a static helper, and a `static` counter whose value
matched prediction. Requires `clang-18`, `ld.lld-18`, `llvm-objdump-18`.
See `docs/rosemary-c-probe-validation.json`.

**HelloWorld milestone:** `python3 toolchains/mips/build_hello_package.py`
builds the SDK's HelloWorld sample from `hello.c` (Greeter_Draw) with a
package-defined Greeter class (Viewable subclass) and a Greeter instance in
the Scene. The guest dispatched Draw to the C code and drew the black box:
`out/rosemary-hello/dispatched.png`, `docs/rosemary-hello-validation.json`.

**SDK-source milestone:** `python3 toolchains/mips/build_hello_package.py --sdk`
compiles the SDK's HelloWorld.cpp unmodified with its own headers (derived,
minimally patched copy from `sdk_headers.py`), using `build_sdk_package.py`
to supply `__dispN` argument-shifting stubs for the header's `__1d_*`
pseudo-functions, `__Dispatch*` glue, and transition-vector stubs/pairs for
intrinsics. The guest drew the box. See `docs/rosemary-hello-sdk-validation.json`.
The `--sdk` build now also names the package/scene/greeter through the
pristine name dictionary and imports `iSendSound`: HelloWorld appears in the
Storeroom, its AhoyWorld door in the Hallway, and the box is labelled
"Yo, world!" (`docs/images/rosemary-helloworld.png`).
**Inherited calls:** `--sdk --source hello_inherited.cpp` verifies
`InheritedHighlighted(self)`: `__disp2_N` stubs (t8 = class number), the
`_classNumber_Greeter_` word resolved from the package's own `@Greeter`
export (`build_exports.py`), guest class number 0x6B1 observed in the
inherited dispatcher. See `docs/rosemary-hello-inherited-validation.json`.
**DigiClock milestone:** `python3 toolchains/mips/build_digiclock.py`
builds the SDK DigiClock sample unmodified through the new generic
`build_package.py` (spec-driven object graph, classes, exports, names,
code). Installed, `InstallSelf` placed the clock in the Stamper's Office
drawer, and `Draw`/`Idle` keep it ticking (`docs/images/rosemary-digiclock.png`,
`docs/rosemary-digiclock-validation.json`).
**Front end:** `python3 toolchains/mips/build_sample.py <Sample>` builds
an SDK sample from its `.cdef`/`.odef`/`.cpp` (`odef_frontend.py`); HelloWorld
and DigiClock verified in the guest this way.
`build_sample.py` covers all 17 SDK samples (see ROSEMARY_BUILD_TRACE.md,
"Front-end coverage"); `mcap_accessors.cpp` is the field-accessor runtime
compiled in when a sample uses `Field/SetField`. Guest-verified from source:
HelloWorld, DigiClock, PackageSceneSample, TimeMinder, RulesSample (scene
opens; needed the cluster's `operationBase1`/`operationCount`), Puzzle and
ScrollableTextField (install), ExportSample + ImportSample (cross-package
interface: `define interface`/`import … or say`, auto getter/setter method
records, and ROM-call stubs that preserve `$gp`), SpeedScrollSample (package
mixins; no empty method tables, header bit 0x08000000 for reference-list
extra parts, `superview` on subviews), and the four Magic Script samples (`magic_script.py`:
Guide ch. 6 statements → the ROM's JVM-subset bytecode + ConstantPool +
UnlinkedScriptClass records; TicTacToe's board scripts run in the guest).
Code-free packages (Scenes) get a `PackageCluster` root and no code attributes.
`--locale` applies the sample's `<Locale>.Package.Phrases`; scripts may `call intrinsic_X`.
Known gap: package mixins with fields (no corpus precedent). `MCAP_SKIP_FIXUPS=<category>` is a
diagnostic that drops one fixup category from the init script for bisecting.
