# Magic Cap package development guide

This guide is for people who want to write a new Magic Cap package today,
whether they are restoring an original 1990s project or starting from an
empty directory. It describes the two development families preserved in this
repository:

| Magic Cap release family | CPU | Source model | Package pipeline |
| --- | --- | --- | --- |
| 1.0 | Motorola 68k / MC68349 | `.Def`, C, ObjectMaker definitions | MPW/CodeWarrior C compiler, linker, ObjectMaker |
| 1.5 | Motorola 68k / MC68349 | same programming model, 1.5 interface profile | 1.5 or universal interfaces, linker, ObjectMaker |
| 3.1 | MIPS / DataRover | `.cdef`, `.odef`, C/C++ and Magic Script | Class Compiler, Object Compiler, MIPS compiler, X-File Linker, Package Builder |

The 68k and MIPS systems share the object-oriented runtime ideas, but they do
not share a binary package format or an ABI. A source project can share its
class design, object graph, and most application logic, but it should be
built as two targets with target-specific interfaces and implementation files.

The host builders reproduce the parts of the original development workflow
needed by the included examples. Target-specific behavior still needs testing
in a matching Magic Cap guest.

## Start here

If you are new to Magic Cap, think of a package as five coordinated things:

1. A class and operation vocabulary: classes, fields, attributes, operations,
   overrides, and interfaces.
2. An object graph: instances, lists, strings, images, sounds, scenes, and
   references between them.
3. Code: native 68k or MIPS methods, and possibly Magic Script methods.
4. A package manifest: boot information, exported/imported interfaces,
   runtime lists, globals, and target metadata.
5. An installable container with a CRC and the references needed by the ROM
   loader.

The most productive workflow is to copy a small working sample, change one
thing, build it, inspect the output, and install it in the matching emulator.
For 68k, start with `Counter` or `TemplateWithButtons`. For MIPS, start with
`EmptyPackage`, `HelloWorld`, or `DigiClock`.

Useful repository entry points:

- [Set up the local SDKs and compilers](SETUP.md)
- [68k build workflow](../toolchains/m68k/README.md)
- [MIPS build workflow](../toolchains/mips/README.md)
- [Cross-target game example](../examples/mips/Sokoban/README.md)

## The Magic Cap object model

### Objects are references, not C structs

Magic Cap applications are built around runtime objects. A C variable holding
an `ObjectID` is a reference to an object managed by the runtime; it is not a
native pointer that may be dereferenced or retained arbitrarily. A field whose
type is `Object`, `ObjectList`, `Viewable`, `Box`, or another class has runtime
semantics defined by the class system.

Native C methods receive object references and ordinary value arguments. They
use generated accessors and operations to read fields or ask another object to
do work. The runtime owns allocation, persistence, relocation, copying, and
event dispatch.

The practical consequences are:

- Store object references in declared object fields, not in ordinary global
  pointers.
- Use the SDK operations such as `At`, `ElementAt`, `CopyNear`, `Implements`,
  and generated field accessors instead of guessing object layout.
- Treat `ObjectID` values as opaque across saves, package loads, and device
  sessions.
- Declare ownership and copying deliberately. A 68k `noCopy` field and a MIPS
  `weak` reference both change lifetime behavior, but they are not identical
  features.

### Classes, fields, and inheritance

A class describes the instance size, parent classes, fields, interfaces, and
methods that an object answers. A class can inherit implementation, answer as
an interface, or mix in behavior without having a conventional single parent.

Conceptually:

```text
Object
└── Viewable
    └── Control
        └── MyControl
            ├── fields: value, icon
            ├── operations: Draw, TouchTarget
            └── overrides: Draw
```

The runtime dispatches an operation by selector. An override must preserve the
declared signature. A method name such as `MyControl_Draw` is a source-level
convention used by both the historical 68k generator and the MIPS SDK; it is
not a C++ virtual function and should not be renamed casually.

Fields are storage. Attributes are public operation pairs or values exposed to
the runtime, scripting system, and authoring tools. A field can generate a
getter, setter, or both; an attribute can be read-only or deliberately expose
no getter/setter.

Example class declarations, 68k style:

```text
Define Class CounterScene;
    inherits from Scene;

    field count: Unsigned, getter, setter;
    field label: Text, noCopy;

    overrides OpenScene;
    operation Increment();
    attribute Count: Unsigned, safe, common;
End Class;
```

The equivalent MIPS declaration uses `.cdef` syntax:

```text
define class CounterScene;
    inherits from Scene;
    field count: Unsigned, getter, setter;
    field label: Text, weak;
    overrides OpenScene;
    operation Increment();
    attribute Count: Unsigned, safe, common;
end class;
```

The spelling and qualifiers differ between releases. Always use the target
profile's definitions and generated headers rather than copying a 68k
definition into a MIPS project.

### Operations, attributes, and intrinsics

An operation is a dynamically dispatched request. It may be implemented by a
class, inherited, or supplied by the system. An attribute normally describes a
getter/setter pair and participates in scripting and authoring conventions.

An intrinsic is different:

- It is a direct runtime/compiler-supported call.
- It does not have a normal responder in the class hierarchy.
- It cannot be overridden like an operation.
- Its selector and argument convention are target/profile-specific.

Use an operation when another object may override behavior. Use an intrinsic
only when the SDK explicitly provides one and its target interface declares
it. The BarChart example's `LeftAndRight` and `TopAndBottom` are package-local
68k intrinsics; they are not portable system intrinsics and are represented in
the 68k `IntrinsicList` in a different namespace from ordinary operations.

### Interfaces and dynamic linking

An interface is the stable contract used when a package refers to a class or
operation supplied by another package. On MIPS, imported interfaces are
identified by long names and grouped into runtime cliques; component numbers
can be reassigned at startup. Strong and weak imports determine whether a
missing provider is fatal.

On 68k, the cookbook corpus does not demonstrate a genuine cross-package
class interface: apparent imports in Spreadsheet are copied declarations and
do not become package imports. Do not infer that behavior is portable. For a
new 68k package, use the system interface numbers generated by ObjectMaker. For
MIPS, declare imports in `.cdef` and let the Class Compiler generate the
interface data.

## Magic Script

Magic Script is Magic Cap's portable, late-bound scripting language. It is
used for behavior that should be editable, localized, or invoked through the
runtime operation system rather than compiled as native machine code.

The MIPS SDK manuals describe Magic Script as a stack language compiled at
package-build time to JVM-like bytecodes. The important mental model is:

```text
source expression
    → stack bytecode
    → package method/script object
    → runtime interpreter
    → operation or intrinsic dispatch
```

A script does not directly manipulate C registers. Values are pushed onto a
stack, operations consume arguments from that stack, and branches operate on
labels or conditions.

Representative syntax from the SDK style:

```text
push 3;
push 4;
call Add [(Unsigned, Unsigned) -> Unsigned];
pop into variable 1;

push variable 1;
push 7;
call GreaterThan [(Unsigned, Unsigned) -> Boolean];
if true, goto finished;
call Increment [() -> void];
goto finished;
finished:
return;
```

The exact grammar is profile/tool-version dependent. In particular:

- `call Operation [(types) -> type]` supplies the compiler with a signature;
- the receiver may be implicit for an operation or explicit for a class call;
- an intrinsic call uses the intrinsic table and cannot be overridden;
- stack order matters: push arguments in the order expected by the compiler;
- a script method should declare its return behavior even when it returns
  `void`;
- a script must not assume that an `ObjectID` remains numerically stable.

Magic Script objects commonly appear as method/script bodies associated with a
class or object definition. They are not the same as native `Code` objects:
the MIPS package contains script bytecode or script method data, while a 68k
native method is placed in the package's `Code` object and referenced by class
method tables.

### A script-backed object, broken down

When debugging a scripted application, separate these layers instead of
calling all of them “the script object”:

| Layer | Meaning | Typical source |
| --- | --- | --- |
| Class declaration | The class and the method signature the script implements | `.cdef` or `.Def` |
| Instance | The persistent object that receives the event or owns the script | `.odef` or `Objects.Def` |
| Method entry | Selector, flags, return/argument signature, and implementation reference | compiled class data |
| Script body | Stack bytecode or script payload | generated method/script data |
| Constant/reference table | Object references, strings, indexicals, and literals used by the body | compiler/package data |
| Runtime call | The dispatched operation or intrinsic reached by `call` | system/package interface |

For example, a button does not become a button merely because its script says
`call DoSomething`. The package must also contain a button instance, a class
record that answers the relevant touch/action operations, a method entry that
points at the script body, and any referenced text or target object. If the
button appears but tapping it does nothing, inspect the method entry and
selector before rewriting the script.

The same distinction applies to a scripted field value. A string literal in a
script is not automatically a persistent `Text` object; a reference pushed by
the script is not automatically owned by the instance; and an indexical is a
late-bound package/resource name rather than a stable object number. These
differences are a frequent source of packages that build successfully but fail
after save/restore.

For a new scripted method, begin with a small operation-only script. Avoid
intrinsics, loops, and imported interfaces until the call and stack behavior
is visible in the emulator. Use the MIPS `FrozenDump`/package inspector and
the Rosemary validation traces to check that the script object, method entry,
and called selector all survived package building.

## Magic Cap 1.0 and 1.5: 68k development

### Historical source layout

A traditional 68k package usually contains:

```text
MyPackage/
├── MyPackage.Def              class/operation/instance declarations
├── Objects.Def                persistent object graph
├── MyPackage.c                native methods
├── PackageInterfaces/         generated operation/class headers
├── MyPackage.µ                 CodeWarrior project or build input
└── build outputs              linked code, map, package
```

The cookbook sources use additional definition files and project ordering.
The ordering matters: ObjectMaker numbers package classes, fields, operations,
and objects in source/project order. The current builder reads that order from
the source project where possible.

The historical MPW sequence is approximately:

```text
definitions + SDK interfaces
        │
        ├── ObjectMaker → generated C headers and operation numbers
        ├── 68k compiler → object files
        ├── linker → linked code and map
        └── ObjectMaker + linked code → package container
```

In this repository, the modern host-side equivalent is:

```sh
python3 toolchains/m68k/build_example.py \
  "sdk/68k/samples/projects/Counter" \
  -o Counter.pkg

python3 toolchains/m68k/inspect_package.py --code Counter.pkg
```

The current implementation builds the cookbook's data-only and code-bearing
examples, emits class/operation records, links compiled 68k code, and handles
BarChart's package intrinsics. It is not yet a drop-in replacement for every
historical ObjectMaker feature.

### 68k ABI rules that matter

The original Magic Cap compiler targets the MC68349's 68k/CPU32 environment.
When writing a replacement implementation or porting code, preserve these
rules:

- integers are 32-bit in the application ABI;
- arguments occupy stack slots according to the Magic Cap compiler convention;
- pointer/object results are returned in `D0`, not `A0`;
- generated dispatch wrappers use inline instruction sequences and register
  pragmas;
- ordinary global/static storage is constrained by the original runtime;
- the 68000 instruction subset is the safe common denominator for host-side
  code generation, even though the MC68349 is a CPU32 derivative.

Do not use an arbitrary m68k compiler and assume the resulting object is a
Magic Cap method. The code may assemble while using the wrong result register,
stack cleanup, relocation model, or instruction set.

### 68k package objects

The 68k container is a big-endian object cluster. Important generated objects
include:

| Object | Role |
| --- | --- |
| `ObjectList` | root references, load lists, and ordinary object arrays |
| `Code` | linked native methods, with a small fixed header |
| `FieldList` | field names, types, offsets, and copy flags |
| `Class` / `ClassList` | class record, inheritance, interfaces, and method table |
| `MagicOperation` | operation signature and operation number |
| `OperationList` | sparse package operation index |
| `IntrinsicList` | package intrinsic keys, operation records, code reference, offsets |
| `StringList` / `StringDictionary` | names attached to objects and records |
| `PackageBoot` | class/operation/intrinsic/load lists and cluster checksum |

An object reference is encoded in the package as a tagged reference such as
`0xB0000000 | object_id`; it is not the final RAM address. The loader resolves
these references when the cluster is installed.

The 68k package loader expects the class/operation/intrinsic lists to agree
with the class records and code. A package can be structurally readable but
still fail to install if a method offset, signature element, list length, or
boot reference is wrong.

### 68k object definitions

`Objects.Def` describes persistent instances and their initial values. It is
not a C initializer and should not contain raw addresses. Typical values
include:

- numbers and booleans;
- fixed-point values;
- `Dot`, `Box`, and pixel dimensions;
- text and string resources;
- object references by instance name/indexical;
- lists and nested objects;
- images, sounds, and buffers;
- scene/card/view hierarchies.

Keep the persistent graph small and explicit. A field reference that points at
an object in the same package must be represented by the object definition
system, not by a host pointer or a guessed object number.

### 68k version profiles

The extracted SDK contains separate interface profiles for:

- Magic Cap 1.0;
- Magic Cap 1.5;
- a Universal profile;
- Magic Link and Envoy/simulator variants.

The profile controls system class/operation numbers, available interfaces,
headers, and sometimes ROM behavior. Build against the exact target profile.
Do not mix a 1.5 `Def` file with 1.0 generated numbers merely because the
source text looks compatible.

The later 68k interface set is especially useful when targeting 1.5. It
supplies 1.0, 1.5, and universal definition roots, and its original MPW tools
include `MWCMagic`, `MWLinkMagic`, and `CreateMake`. The
compiler wrapper supports the original Magic Cap 68k target modes and the
linker understands code-resource output. Use the matching profile as a whole:
the 1.5 class, operation, and intrinsic definitions are not interchangeable
with 1.0 definitions. `Universal` is a compatibility profile, not proof that
one package will run unchanged on every ROM.

The host package builder uses the 1.5 interfaces for the corresponding
profile. It does not require running CodeWarrior or ObjectMaker on a classic
Mac.

## Magic Cap 3.1: MIPS development

### MIPS source layout

A modern MIPS SDK project is organized around separate declarations and object
values:

```text
MyPackage/
├── MyPackage.cdef            classes, operations, interfaces
├── Objects.odef              persistent instances and values
├── MyPackage.cpp             native methods
├── Makefile / generated make ├── build rules and dependencies
├── package globals           optional package-owned data
└── package output            frozen MIPS package
```

The SDK's build stages are explicit:

```text
.cdef → CompileClasses → class/interface compiler output
.odef → CompileObjects → object-definition output
.c/.cpp → GCC/cc1 → ELF object files
ELF → LinkXFile → transition-vector X-file
all outputs → BuildMagicCapPackage → frozen package
```

The original environment expected MPW on a Power Macintosh and the SDK's
compiler binaries and libraries. Hatter's host toolchain does not invoke those
historical binaries; its local SDK copy contains the interfaces and samples
needed by the modern builders. The complete original distribution remains in
the sibling `magicrecomp` workspace.

### `.cdef`: classes and interfaces

`.cdef` is the MIPS-era declaration language. It adds features needed for
dynamic linking and scripted/native packages, including:

- `define class` and `inherits from`;
- `field` with `getter`, `setter`, `weak`, and related qualifiers;
- `attribute` with `readOnly`, `noGetter`, and `noSetter` forms;
- `operation`, `overrides`, and `class operation`;
- `intrinsic`, including simple direct-call intrinsics;
- `mixes in with`;
- `define interface` and imports, including weak imports;
- `indexical` declarations;
- `read`/include relationships between definition files.

Use one authoritative declaration for each class. If an application imports a
class from another package, declare the interface/import relationship instead
of copying an approximate class definition into the application.

### `.odef`: instances and values

`.odef` describes the package's persistent object graph. It supports the
primitive and composite forms used by Magic Cap packages, including:

- `.s` and `.b` size forms;
- `Fixed`, `Dot`, and `Box` values;
- pixel dimensions and image data;
- `include 'file' a:b` ranges;
- hexadecimal values written with `$`;
- object names, lists, and references;
- localized phrases and phrase-file integration.

The Object Compiler validates class fields and emits the frozen object data.
`FrozenDump` is the first tool to use when a package installs but an object
looks wrong.

### MIPS native methods and transition vectors

MIPS package code is not a normal hosted MIPS executable. The SDK configures
GCC for embedded MIPS, soft float, short enums, position-independent code, and
the Magic Cap transition-vector ABI. Linking uses embedded relocations and the
SDK linker script; `LinkXFile` extracts the package code/data view from the ELF
link.

The target selection scripts distinguish MIPS device targets such as Apollo
and Sputnik from the PowerPC simulator. A simulator build is not a device
package merely because both compile from C++.

For a native method:

1. Declare the class and method in `.cdef`.
2. Use the generated headers and the SDK's dispatch macros.
3. Name the implementation `Class_Operation` and set `CURRENTCLASS` as the
   samples do.
4. Call ROM operations through generated stubs, not guessed addresses.
5. Link with the target's transition-vector options.
6. Inspect the X-file and frozen package before installing.

Keep the first native method leaf-like. The Rosemary validation samples prove
that a host-generated MIPS method can call ROM operations, call an intrinsic,
and preserve package-global state, but they do not make every SDK library or
ROM profile interchangeable.

### MIPS frozen-package contents

The MIPS package is a frozen representation of several linked components:

```text
native code + package globals
class definitions
object definitions
exported interfaces
imported interfaces
package metadata / CRCs / target attributes
```

The five frozen-package attributes described by the SDK are the useful way to
reason about the format. Do not apply the 68k `Code`, `ClassList`, and
`PackageBoot` object layout directly to MIPS. MIPS uses its own frozen records,
ELF-derived code/data extraction, and dynamic interface linking.

## A shared application design for both CPUs

The best cross-target strategy is a shared conceptual package with two build
front ends:

```text
shared design
├── shared object/class model
├── shared object names and resource plan
├── shared operation names and behavior
├── 68k declarations + C + ObjectMaker backend
└── MIPS declarations + C++/Script + frozen-package backend
```

Share:

- class and scene hierarchy;
- operation names and signatures where the SDK profiles agree;
- persistent object naming and resource organization;
- application state machine and user-visible behavior;
- Magic Script source when the target compiler supports the same operation
  signatures.

Separate:

- generated system numbers;
- native method ABI and compiler flags;
- package serialization;
- imports/exports and interface cliques;
- target-specific hardware, graphics, audio, and networking calls;
- any intrinsic that is not present in both profiles.

A useful source organization is:

```text
shared/
    model.txt
    behavior.script
    resources/
68k/
    App.Def
    Objects.Def
    App.c
    PackageInterfaces/
mips/
    App.cdef
    Objects.odef
    App.cpp
    Makefile
```

Do not promise byte-identical packages across targets. The goal is behavioral
parity and profile-correct packages, not a common container.

## Build and inspect loops

To run the repository-level native and host-toolchain regression checks:

```sh
scripts/test-toolchains
```

This runs the 68k and MIPS host regression suites and rebuilds all 17
preserved MIPS SDK samples. It does not build or run the emulator.

### 68k loop

```sh
# Build from the example source directory.
python3 toolchains/m68k/build_example.py \
  "sdk/68k/samples/projects/Counter" \
  -o out/Counter.pkg

# Inspect structure and native call sites.
python3 toolchains/m68k/inspect_package.py --fields --code \
  out/Counter.pkg

# Install and exercise the package with the matching ROM in magicrecomp.
```

Select the 1.5 profile explicitly for Magic Cap 1.5 devices. Guest
installation and behavior testing belong to the sibling `magicrecomp`
workspace.

### MIPS loop

The MIPS builder accepts an SDK sample name or a project directory:

```sh
python3 toolchains/mips/build_sample.py \
  sdk/mips/Samples/HelloWorld

python3 toolchains/mips/inspect_format.py path/to/package.pkg

# Build the complete preserved SDK sample matrix:
scripts/build-sdk-samples --out out/sdk-samples
```

Use the sample's `.cdef`, `.odef`, and generated make inputs as the authority;
do not invent a modern GCC command line and expect the ROM ABI to match.

## Debugging checklist

### The package does not build

- Confirm the target profile and SDK interface root.
- Check class/operation spelling and project definition order.
- Rebuild generated headers after changing a declaration.
- Look for a missing `CURRENTCLASS` or incorrectly named method.
- On MIPS, check that `.cdef` and `.odef` are being compiled by the correct
  compiler rather than treated as ordinary text.

### The package builds but will not install

- Inspect the package header, object bounds, alignment, and CRC.
- Check every boot/list reference and object ID.
- Check class record method offsets against the code object/X-file.
- Check operation signatures, especially value structs such as `Box`, `Dot`,
  and `PixelDot`.
- Check imported interfaces and target ROM compatibility.
- Compare the generated package with a stock package of the same release
  rather than with a package from another CPU family.

### The package installs but the scene is wrong

- Verify object names, indexicals, and list element order.
- Inspect the initial object graph before debugging native code.
- Check field copy/weak/noCopy behavior.
- Check that the app opens the intended scene and that the scene's root object
  is loaded in the package load list.
- Compare a framebuffer crop with the stock sample where one exists.

### A method crashes in the guest

- Verify the exact signature and return register/ABI.
- Check that an object reference was not treated as a host pointer.
- Check stack argument order and struct passing.
- Replace the method with a leaf method, then add one operation call at a time.
- For MIPS, inspect transition-vector calls and embedded relocations.
- For Magic Script, dump the bytecode and verify stack depth at every call and
  branch.

## What is established and what remains experimental

Established locally:

- 68k package round trips and cookbook class/operation numbering;
- 68k data-only package generation and guest scene parity;
- 68k native compilation/linking for all nine code-bearing cookbook examples;
- 68k native guest verification of all eight code-bearing cookbook examples
  (BarChart, BizNote, Circuits, Hanoi, Metric, Positioning, Spreadsheet, and
  Whitehouse);
- BarChart package intrinsic-list emission and guest installation;
- MIPS `.cdef`/`.odef` front end and frozen-package inspection;
- MIPS host-generated native methods and several SDK samples running in the
  Rosemary guest.
- all 17 preserved MIPS SDK samples building from their original source
  directories;

Still target-specific or incomplete:

- exact Magic Cap ROM compatibility for every MIPS SDK target profile;
- all MIPS SDK libraries and historical MPW tools running unchanged on Linux;
- undocumented JVM bytecodes outside the Guide's Magic Script source language
  and some scripted-object binary variants;
- undocumented 68k ObjectMaker flags and a few package-list ordering details.

When adding a new feature, preserve unknown fields and record the evidence for
any inferred value. A package that is slightly incomplete but inspectable is
more useful than one that silently emits guessed runtime metadata.
