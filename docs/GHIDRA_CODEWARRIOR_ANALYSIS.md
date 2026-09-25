# CodeWarrior and Magic Developer binary analysis

This note records the first Ghidra pass over the preserved classic Macintosh
developer tools. It is deliberately a starting point for deeper analysis, not
a claim that the proprietary tools have been decompiled.

## Targets analyzed

The files are classic Macintosh PowerPC PEF executables, including the 68k
ObjectMaker tool. They are host-side tools; the fact that ObjectMaker writes
68k packages does not make ObjectMaker itself a 68k executable.

| Tool | Source archive | Ghidra result |
| --- | --- | ---: |
| `ObjectMaker` | CW7 Magic/MPW installer | 569 functions, 1,462 defined data items |
| `CompileClasses` | Magic Developer SDK | 1,500 functions, 3,444 data items |
| `CompileObjects` | Magic Developer SDK | 1,367 functions, 2,848 data items |
| `BuildMagicCapPackage` | Magic Developer SDK | 494 functions, 1,049 data items |
| `LinkXFile` | Magic Developer SDK | 1,697 functions, 4,976 data items |
| `FrozenDump` | Magic Developer SDK | 391 functions, 880 data items |

The CW8 MPW layer was analyzed separately. It does not contain a second
standalone ObjectMaker in the preserved files; its value is the target-aware
compiler/linker wrappers and the expanded Magic Cap interface profiles:

| Tool | CW8 role | Ghidra result |
| --- | --- | ---: |
| `MWCMagic` | MPW C compiler wrapper for Magic Cap | imported and analyzed |
| `MWLinkMagic` | MPW Magic Cap linker | imported and analyzed; one non-fatal debug-resource warning |
| `CreateMake` | build-file generator for 68k, PowerPC, and fat targets | imported and analyzed |

The CW8 sources are under `software/68k/extracted/CW8_Gold_Tools_199601`.
The important interface roots are `Magic Cap Support/Interfaces/Only 1.0`,
`Only 1.5`, and `Universal`. The CW8 installation notes describe these as
part of the `Magic Developer` and `CodeWarrior MPW` installation, alongside
the 1.0 and 1.5 simulators and the MC Debug tool.

Ghidra 12.1.2 imported all six with its Preferred Executable Format loader as
PowerPC big-endian PEF. The analyzed project was temporary and is not part of
the source archive. The reproducible headless command is:

```sh
mkdir -p out/ghidra-project
/snap/ghidra/47/ghidra/support/analyzeHeadless \
  out/ghidra-project MagicTools \
  -import 'software/68k/extracted/CW7-Magic-MPW/CodeWarrior Magic%2FMPW Installer/MagicDeveloper/Tools/ObjectMaker' \
  -import software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Tools/CompileClasses \
  -import software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Tools/CompileObjects \
  -import software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Tools/BuildMagicCapPackage \
  -import software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Tools/LinkXFile \
  -import software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Tools/FrozenDump \
  -analysisTimeoutPerFile 120
```

The optional `scripts/ghidra_export_summary.java` script prints discovered
functions and defined data. It is useful for producing a stable inventory
before manually renaming functions in a Ghidra project.

## Findings useful to package development

### ObjectMaker

ObjectMaker identifies itself in its strings as **ObjectMaker 2.0**. Its error
and option strings expose a much clearer internal model than the package bytes
alone:

- `clusterLink` and `packageLink` are separate inputs;
- it supports `-output`, `-templates`, package names, and precompiled system
  classes;
- it distinguishes building the system from building a package;
- it has alignment and class-alignment warnings;
- it contains internal records named `MakerClass`, `MakerTypeOrClass`,
  `MakerField`, `MakerClassTracker`, `MakerMethod`, `MakerObject`,
  `MakerPackage`, and `MakerScriptedMethod`.

The `MakerScriptedMethod` record is the strongest new evidence that scripted
methods are first-class ObjectMaker metadata, not merely arbitrary bytes in a
resource. Its size/assertion strings are an immediate target for a second
pass. The `MakerPackage` and `MakerObject` names also support treating the
68k package as a graph assembled by a package builder rather than a flat
resource file.

The binary contains strings for errors such as:

```text
must read pre-compiled file when compiling a package
cannot precompile package classes, only system classes
operation %s (%lu) is not used in any class
card size is only valid for package ROM builds
```

These should become diagnostics in the modern builder instead of being
silently ignored.

### CompileClasses

The class compiler has explicit validation for:

- class field-size limits;
- `inherits from` entries that must be mixins where required;
- `inherits interface from` entries that must be mixins;
- class and interface definitions and generated headers.

This confirms that the MIPS declaration language's mixin/interface split is a
semantic rule enforced by the compiler, not merely a documentation convention.

### CompileObjects

The object compiler contains diagnostics for:

- `.odef` and phrase-file input;
- package versus built-in-package compilation;
- object/class numbers;
- indexical type checking;
- indexical values whose declared class/package does not match the target;
- unknown address/value forms.

This is important for new package tooling: an indexical should be treated as a
typed late-bound reference, not as a renamed object number. The compiler also
has a dedicated object-definition include environment (`OBJECT_COMPILER_INCLUDES`)
and a `-package` option.

### BuildMagicCapPackage

The package builder's strings give the two-input model directly:

```text
file.x   input frozen package + executable
file.x   output frozen package
```

It supports distinct output modes for:

- Power Macintosh frozen packages;
- Windows frozen packages;
- embedded MIPS frozen packages.

It validates 32-bit ELF input and contains source references such as
`PackageBuilderMain.cpp`, `DataInitScript.cpp`, and `FrozenPackage.cpp`.
The `SpecialOpCodeScriptEnd` assertion is particularly useful evidence that
data-initialization scripts are compiled into a defined bytecode/object format
with a terminator, rather than being interpreted directly from source text.

### LinkXFile

The linker exposes the package stages and options in its diagnostics:

- package name selection;
- `-o` and `-op` output object/package files;
- debug package and magic-debug output;
- exported function-name lists;
- `-output-big-endian`;
- object-file format validation;
- dead-code stripping restrictions;
- separate package and system builds.

The linker should therefore be modeled as more than an ELF linker wrapper: it
produces an X-file/package-oriented intermediate with package naming,
exports, and debugging metadata.

### FrozenDump

`FrozenDump` identifies itself as a **Frozen Package Disassembler** and names
the key structures it knows how to print:

- abbreviated classes;
- import table;
- object addressing table / heap;
- class number;
- class operation number;
- strong and weak objects;
- class instance size and field offsets;
- data initialization script;
- class operations and patched class-operation transition vectors.

This makes `FrozenDump` the best first binary oracle for MIPS package work. A
future replacement should compare its output against the SDK tool before
trying to infer frozen-object offsets from the ROM.

## What Ghidra did not solve automatically

Ghidra recovered architecture, functions, data, and strings, but it did not
automatically understand:

- classic Mac resource-fork `CODE`, `DATA`, `STR#`, or custom resources;
- ObjectMaker's internal C++ record types;
- the Magic Cap 68k package object classes;
- MIPS frozen-package attributes;
- Magic Script opcode names and stack types;
- the relationship between generated headers and package selectors.

The resource forks remain valuable. Each tool has a companion `.rsrc` file in
the extracted SDK where applicable. Resource inspection should be a separate
pass using a resource-fork parser or `DeRez`-compatible tooling; the resource
fork should not be flattened into the executable data fork and discarded.

## CW8 findings

CW8 is materially useful for new 68k development, but it should be treated as
a build/profile release rather than as a replacement package-format oracle.
`MWCMagic` exposes the historical target choices `power`, `mac68k`, and
`mac68k4byte`, along with Magic Cap-oriented options such as `-farcode`,
`-nearcode`, and `-codesmart`. `MWLinkMagic` exposes code-resource linking,
segment attributes, Magic Cap code-reference symbols, and package/map output.
`CreateMake` confirms that 68k code resources are a distinct build mode and
that the generated projects can select 68k, PowerPC, or fat output.

The CW8 interface definitions must be selected as a matched set:

| Target | Definition root | Guidance |
| --- | --- | --- |
| Magic Cap 1.0 | `Interfaces/Only 1.0` | use for a strict 1.0 package |
| Magic Cap 1.5 | `Interfaces/Only 1.5` | use for 1.5-only classes and operations |
| cross-version source | `Interfaces/Universal` | use only after validating both ROM profiles |

The 1.5 class-definition set changes from 1.0: it adds or rearranges classes
including `PowerSupply`, `CardSlot`, `Gadget`, `DeliveryReportCard`,
`SmartStamps`, `TCP`, `MemoryView`, `CleanUpMemoryScene`, and
`MacintoshModem`, while 1.0 contains `Vault` where the 1.5 set does not.
The operation and intrinsic definition files also differ. In particular,
CW8's intrinsic file contains substantially more system-vector declarations,
and one persistent-size entry changes classification from `Operation` to
`Attribute`. Do not merge these files or infer numbers from a different
profile.

For the current reimplementation, CW7 ObjectMaker remains the stronger source
for 68k package serialization. CW8 should supply profile-specific headers and
compiler/linker behavior until a CW8 package writer or additional package
samples prove otherwise.

## Recommended next reverse-engineering passes

1. In `ObjectMaker`, rename the functions surrounding the option parser and
   the `MakerScriptedMethod` strings. Identify the routines that serialize
   class, object, package, and method records.
2. Import the ObjectMaker resource fork and correlate resource IDs with the
   command-line strings and templates.
3. In `FrozenDump`, identify the routines that emit `Class`, `ClassOperation`,
   import-table, strong/weak-object, and data-init-script text. These routines
   are likely easier to understand than the package writer itself.
4. In `CompileObjects`, trace the indexical type-checking path and record the
   internal type tags it accepts.
5. In `BuildMagicCapPackage`, trace the ELF section-to-frozen-attribute map and
   the script-end opcode handling.
6. Compare the 1.0/1.5 ObjectMaker binaries if another version is present;
   differences in option strings and record sizes may resolve remaining 68k
   unknowns.

The existing source-level inspectors should remain the primary authority for
known fields. Ghidra-derived conclusions should be added only when they agree
with package samples, SDK declarations, or guest traces.
