# Rosemary container inspection

These are the MIPS (Magic Cap 3.x) container layouts observed in the Magic
Developer SDK and the preserved package corpus, recorded in the order they were
established. Later sections refine or correct earlier ones; they are checked
layouts, not a complete specification. The read-only
[inspector](../toolchains/mips/inspect_format.py) reports package sections,
sizes, names and format errors; it does not validate class semantics or runtime
compatibility. The package writer that grew out of this work is described in
the [build trace](ROSEMARY_BUILD_TRACE.md), and the 68k counterpart in the
[ObjectMaker notes](OBJECTMAKER_FORMAT.md).

The corpus is the SDK's intermediate files (`MagicCap.cx`,
`MagicCapLibrary.x` and the sample outputs, from
`Software/MIPS/SDK/magicdeveloper.sit` in the Magic Cap preservation archive)
and the preserved MIPS device packages (`Software/MIPS/` in the same archive).
SDK addresses such as `Flattener_ReadHeapAttribute` (0x13ce5560) are from the
SDK's unstripped Apollo ELF, `Debugger/Apollo/MagicCap-USA`.

## SDK intermediate container

MagicCap.cx and MagicCapLibrary.x share this big-endian layout:

| Offset | Observed field |
| --- | --- |
| 0 | 32-bit header word 121 (0x79); treated as supported format/version marker |
| 4 | 16-bit section count N |
| 6 | N 16-bit section tags |
| aligned to 4 after tags | N 32-bit offsets, relative to file byte 4 |
| following directory | Section payloads, in directory order |

Section length is the distance to the next section; the last ends at EOF.
The first offset plus 4 equals the directory end in the inspected corpus.
Section 1 starts with `01740174` in the inspected examples; its meaning remains
unassigned. Tags 12–21 occur selectively and must not be renamed based solely
on guessed contents.

Section 12 starts with a 32-bit record count and a table of 32-bit offsets,
again relative to file byte 4. Each inspected record starts with a 32-bit byte
length followed by a name. The remaining record bytes are still opaque. Names
include System and names of packages such as Calculator and InternetMail.
The inspector bounds each name against its own record, not merely against EOF.
This is useful structure, but does not yet decode classes or operations.

## Frozen-package container

Observed browser, driver and game packages start with the eight bytes
`00 53 41 4c 54 43 4f 44` (NUL followed by SALTCOD). The following big-endian
32-bit word is 152 (0x98). Strings in the SDK FrozenDump executable identify
file offset 8 as the version number, supporting that interpretation.

Starting at byte 12, the observed record envelope is:

- One 32-bit big-endian header word.
- High byte retained as a raw tag/flags byte; the inspector does not yet split
  those bits into their semantic components.
- Low 24 bits give the payload byte length, excluding the four-byte header.
- Payload immediately follows, then the next record header.
- A zero header terminates the package.

All 32 packages examined have raw tag bytes
`20 30 10 53 b0 71 a0 60`, followed by the zero terminator. This is an observed
sequence, not an enforced requirement. Unknown record tags are retained. An
unrecognized version is rejected rather than parsed using an assumed layout.

For example, Ne2000.pkg has its first record at 0x0c with word 0x2000034c;
its 844-byte payload ends at 0x35c, where the next record begins. Following all
records and the terminator reaches exactly its 67,096-byte EOF.

Some files concatenate complete packages without a separate outer bundle table:

| File | Packages |
| --- | --- |
| CujoChat.pkg | 2 |
| WCPack.pkg | 3 |
| GamesBundle.pkg | 4 |
| GammonBundle.pkg | 2 |

The parser requires another SALTCOD header after each nonfinal terminator and
rejects arbitrary trailing bytes. Stopping at the first terminator would silently
lose bundled content.

## Validation and limits

Scanning the preserved MIPS software by content found and successfully inspected:

- 128 X-format containers (including additional files beyond the 124 `.cx`/`.x`
  extension matches), exposing 417 section-12 named records.
- 25 SALTCOD files containing 32 complete packages.
- Every supported section/record within its bounds and every frozen bundle fully
  consumed through EOF.

Eleven automated tests cover bundle offsets, unknown tags, every truncated
prefix of a small frozen fixture, oversized lengths, unsupported versions,
trailing garbage, section offsets and malformed names. These checks establish container readability, not all possible corruption:
for example an opaque last section has no decoded internal checksum or length
with which to detect every truncation.

Next, decode the class/object records inside the intermediate sections and map
the frozen attributes to the loader's actual structures. The existing SDK
FrozenDump and LinkXFile binaries and ROM loader are reference evidence. A writer
should follow only after those structures and references are understood. No
package bytes or ROMs were modified in this investigation.

## Class and operation record follow-up

The inspector now reads the record-directory structure in sections 13, 15, 16
and 17 as well as section 12. Each directory begins with a 32-bit count and
32-bit record offsets relative to file byte 4. Records in these additional
sections begin with a 32-bit kind, a 32-bit name byte length, and the name bytes.
The kind's semantics remain unknown. Names are not padded before subsequent
fields; records can start at unaligned byte offsets.

For section 13, the first word after the name is the class number. For section
16 it is the operation/intrinsic number. These interpretations were independently
compared with the generated Apollo `MagicCap.gnu.xh` declarations:

| System image records | Present and matching in header | Absent from compared header | Mismatches |
| --- | --- | --- | --- |
| 998 class records | 844 | 154 | 0 |
| 5,994 operation/intrinsic records | 4,523 | 1,471 | 0 |

Absent entries are not counted as validated. Operation names can appear in
multiple generated number namespaces, so the comparison checks membership in
the set of declared numbers for that name. It does not establish which namespace
belongs to each compiled record. For example, Exceptions has class number 167;
Try has intrinsic number 50.

Sections 15 and 17 expose type/indexical-looking names, but their trailing
numeric fields and kind values remain opaque. Section 19 contains a count and
sequential length-prefixed dependency paths, sometimes followed by up to three
zero padding bytes. Recorded paths are informational; the inspector never opens
or executes them, and old source-tree paths need not exist locally.

All 128 previously recognized X-format containers still parse with these
additional checks. The parser now has 15 passing tests, including class-number
bounds, unaligned records and dependency-length/padding failures.

An attempted fixed layout for the SALTCOD 0x20 named references fit the browser
but failed on EtherLinkIII.pkg. That interpretation was rejected and is not in
the parser. The frozen payloads remain opaque. Class names and numbers alone are
not sufficient to serialize a class: inheritance, fields, operation signatures,
interface binding and frozen-object references still need to be decoded before
writing an installable package.

## Inheritance and fixed-storage follow-up

For section-13 definition records (`raw_kind == 2`) whose undecoded tail begins
with word 1, the following layout is now supported. Offsets here are relative
to the first byte after the previously decoded class number:

| Relative offset | Field |
| --- | --- |
| 0 | Observed prefix word 1; meaning not assigned |
| 4 | Unassigned raw word |
| 8 | One-based field-access base index into this section's class records |
| 12 | Total fixed-storage bytes |
| 16 | Unassigned raw word |
| 20 | Leaf-storage bytes added by this class |
| 24 | Count followed by one-based `mixes in with` class indices |
| after that list | Count followed by one-based `inherits from` class indices |
| after both lists | Remaining opaque data, including still-undecoded field/method information |

`fixed_offset_bytes` is total fixed storage minus leaf storage. This is the
value exposed by generated `_Class_fixedOffset_` macros, not a complete layout
of each individual field. The field-access base is distinct from the declared
parents: a class can inherit through several classes while generated field access
still names Object as its base.

The decoder checks both relation lists against the local class table and each
record's boundary. It does not dereference arbitrary pointers or follow paths.
For example, EmbeddedCode has total size 8, leaf size 4, fixed offset 4 and
field-access base Object; its declaration parent is CodeHandler. MagicBeam's
parent list contains Object, HasReinitialize and WantsPowerEvents. HasDate instead
uses the separate `mixes in with Object` list.

Validation against the SDK's generated headers gave:

- 67 paired generated-header comparisons across the available profiles, with
  matching base, fixed offset and leaf size in every comparison.
- Six selected source-class comparisons: FilingChoice, HasReinitialize, HasDate,
  MagicBeam, DisplayServer and BacklightButton. Each decoded relationship list
  matches a source definition. MagicBeam has conditional alternative definitions;
  the report preserves both and confirms a matching variant, without claiming
  to evaluate the preprocessor conditions.
- 1,104 definition records decoded with the checked prefix-word-1 layout across
  the corpus. Another 7,479 definitions use unsupported prefixes and 1,731 records
  are reference-only; these are explicitly marked, not interpreted by this layout.
- 18 passing parser tests, including invalid relation indices, list bounds,
  impossible storage sizes and unsupported-prefix handling.

Linked/debug records expose a different prefix structure even though they share
the outer X-file version. The initial attempt to apply the compiler-record layout
to them failed and was rejected. The extra words' meaning must be established
before widening support. This is an important distinction between being able to
read a container and knowing every record variant inside it.

Per-field offsets, field
types and bit packing, method tables, and frozen-object reference serialization
remain to be decoded before package generation.

## Individual fields and method bindings

For the same 1,104 supported class definitions, the remaining class data now
exposes member-table directories. The decoder reads an auxiliary 32-bit-counted
index list, an unassigned flags word, and a 16-bit-counted operation-index list.
These values remain raw: the exact purposes of these lists/flags have not been
established. The following two 32-bit words locate the field and method tables;
a zero offset means the corresponding table is absent.

These offsets use **the original class tail start plus 8** as their base, where
original tail start means the byte immediately following the class number.
They are not file-relative. Each member table then uses its own start as the
base for its record offsets. These distinct bases were necessary to resolve
classes without fields and classes with auxiliary index lists correctly.

Each field table has a 32-bit count and 32-bit relative record offsets. The
observed field record is packed, without alignment between its fields:

| Field | Encoding |
| --- | --- |
| Name length | Big-endian u32 |
| Name | Exactly that many bytes |
| Type reference | Big-endian u32, one-based record index into section 15 |
| Leaf bit offset | Big-endian u32 |
| Unassigned flags | One byte |

The fixed bit offset is `class.fixed_offset_bytes * 8 + leaf_bit_offset`.
For example, BacklightButton.lowPowerMode has Boolean type and bit offset 64,
matching the generated header's byte/bit pair `8,0`. Boolean storage can share
bytes; treating the stored offset as a byte count would be incorrect. The
current tool resolves type names but does not yet compute all type sizes or
interpret the field flags.

Each method table likewise has a count and relative record offsets. The
observed binding is 12 bytes: one section-16 operation-record index followed
by two unassigned 32-bit words. The inspector resolves the method name and
operation number through section 16; it retains both additional words raw.
This is not yet a complete description of executable method linkage.

Validation now includes:

- 2,952 fields and 11,498 method bindings decoded across all 1,104 supported
  class definitions, with type/operation indices and record boundaries checked.
- 191 field-offset comparisons against generated private headers, including
  byte/bit offset forms; no mismatches.
- 67 complete method-name-set comparisons against private-header prototypes;
  no mismatches. This does not validate the full parameter signatures.
- 21 passing tests, including wrong relative offsets, oversized counts and names,
  missing type/operation references, overlapping tables and unaligned field data.

Other definition prefixes remain unsupported. No package writer or guest-tested
package has been produced. Next are the operation signatures and binding-word
semantics, followed by frozen-object serialization and runtime import resolution.

## Operation signatures

Section-16 definition records (`raw_kind == 2`) with tail prefix word 1 now
have decoded signatures. Offsets below are relative to the byte after the
operation number:

| Offset | Encoding |
| --- | --- |
| 0 | Supported prefix word 1 |
| 4 | Unassigned u32 category word |
| 8 | Raw modifier byte |
| 9 | Unaligned u32 return-type index into section 15; zero means void |
| 13 | Another raw modifier byte |
| 14 | Unaligned u32 explicit parameter count |
| 18 | Packed parameter records |

Each parameter is a u32 name length, name bytes, u32 type-table index and one
modifier byte. Parameters are not individually aligned. Up to three zero padding
bytes can follow the final parameter. The inspector resolves names/types but
retains modifier bytes without applying a universal interpretation. Reference-only
operations and other definition prefixes remain explicitly unsupported.

All 6,694 supported definitions parse within their bounds, exposing 6,240 explicit
parameters. This is structural validation, not independent validation of every
signature. A separate comparison checks five HelloWorld-related signatures
against `Apollo/MagicCap.gnu.xh`. The five passing comparisons cover Draw, FillBox, ContentBox, PartColor and
CurrentCanvas. For these cases, class-valued types map to Reference; FillBox's
input Box maps to `const Box *`, whereas ContentBox's parameter modifier 0x80
maps to `Box *`. Signed and Unsigned retain their declared C names. The limited
translation is a comparison aid, not a general-purpose header generator.

The comparison includes the generated dispatcher's address, selector and implicit
self arguments for object-method wrappers. These arguments are absent from the
explicit parameter list in the class definition. CurrentCanvas is compared with
its intrinsic wrapper separately. Confusing these two call paths would produce
incorrect calls even with the explicit types decoded correctly.

There are now 24 passing parser tests. New tests exercise packed return indices,
parameter modifiers, bad type indices, overlong names/counts, nonzero suffixes
and reference-only records.

The next missing pieces are the two raw words in method bindings, their code and
runtime-reference resolution, and frozen-object serialization. No installable
package or guest execution is claimed by these signature checks.

## Generated accessor bindings

The two previously unassigned words in each supported 12-byte method binding
are now interpreted for generated accessors. The first word of the record still
selects an operation from section 16. Word 4 selects the observed binding kind;
word 8 selects a one-based field record within the current class for kinds 1–5:

| Word 4 | Interpretation | Corpus bindings |
| --- | --- | --- |
| 0, with word 8 also zero | Ordinary method; executable linkage unresolved | 9,801 |
| 1 | Getter | 952 |
| 2 | Setter | 604 |
| 3 | Text getter variant | 71 |
| 4 | Text setter variant | 48 |
| 5 | Shared setter | 22 |

The 1,697 generated accessors all reference existing fields. The inspector
resolves each field's name, type and fixed bit offset, while retaining the raw
words. Unknown binding kinds are preserved rather than interpreted as pointers.
The ordinary zero/zero case is explicitly `ordinary-unresolved`: it does not
mean the class method is implemented at address zero.

The interpretation was checked independently against 18 source declarations in
HasDate, HasAccountInfo and Form. For example, HasDate declares getters/setters
for dateCreated and three other fields; their generated bindings select kinds
1/2 and the corresponding field indices. HasAccountInfo's Text fields select
kinds 3/4. Form.image's `sharedSetter` declaration selects kind 5. These checks
establish the compiler's classifications, not the full runtime behavior of each
accessor variant; in particular, the text/shared variants must not be emitted as
ordinary memory loads/stores without investigating runtime behavior.

All 18 bindings match. The parser now has 26 passing tests, including every
supported accessor kind, out-of-range field indices and preservation of unknown
kinds. Existing field-layout, method-name and sample-signature checks still pass.

This corrects the earlier assumption that these two words might directly hold
code linkage: for the supported generated accessors they hold compiler recipes.
Finding ordinary method code in the linked output and decoding the SALTCOD
payloads remain separate outstanding work. No package writer or guest-tested
package had been produced at this stage.

## Ordinary methods located in linked MIPS output

The SDK contains an unstripped ELF executable at
`Debugger/Apollo/MagicCap-USA`, alongside `MagicCap-USA.image`.
`toolchains/mips/trace_linked_methods.py` reads the ELF section and symbol
tables and matches supported ordinary class methods by their exact
`Class_Operation` symbol names. It uses executable-section function symbols,
not incidental strings or undefined imports.

```sh
python3 toolchains/mips/trace_linked_methods.py
```

Results for the SDK Apollo build:

- 7,677 ordinary methods have one exact ELF function-symbol match. Their entry
  bytes match the paired SDK ROM image at the corresponding address.
- 244 ordinary methods remain unresolved by this exact-name rule. They are listed
  rather than assigned guessed addresses. The result does not prove they lack
  implementations; alternate naming, omitted code or other linkage may explain them.
- The entire 2,732,256-byte ELF `.text` section is byte-identical to the matching
  region in the SDK ROM image. The ROM base, `0x13c00000`, comes from this ELF's
  `.monitortext` section.
- Examples are Object_Init at `0x13ced100`, Form_Draw at `0x13dbe1b8` and
  PixelMap_FillBox at `0x13d23758`.

The ELF `.tvtab` section contains 1,238 eight-byte entries. Interpreting each as
code-address/global-pointer words yields 1,212 entries pointing to named ELF
functions. 1,216 entries contain global pointer `0x0000e020`, exactly matching
this ELF's `_gp` symbol; the remaining 22 contain zero. Unmatched code targets
and zero-pointer entries are retained without assuming they are ordinary calls.
This is independent linked-output evidence for the two-word transition-vector
layout previously found in Generic.h and the support-object disassembly.

These are **SDK-build addresses**, not addresses validated against the
production DataRover ROM. Most ELF
function symbols report size zero, so the tool records only a bounded entry
preview and does not invent full function extents. It also does not yet connect
all runtime class-table slots to these symbols or resolve runtime package imports.

The tool's report includes source hashes, matched/unresolved methods, vector
entries and file offsets. Five additional
tests cover the ELF reader's symbol extraction, architecture check, truncated
directories, section/string bounds and invalid symbol metadata. All 31 research
tests pass. Frozen-package payload decoding remains the next package-building
boundary; this linked-ROM analysis does not produce an installable package.

## Frozen attribute roles confirmed by the loader

The SDK Apollo ELF's `Flattener_ReadStreamableMulticodeAttributes` at
0x13ce73e8 shifts the attribute header right by 28 and indexes a 12-entry jump
table at 0x13ebd538. Its direct helper calls and operation selectors identify:

| High nibble | Attribute |
| --- | --- |
| 0 | Termination path; normal terminator word is zero |
| 1 | Abbreviated classes |
| 2 | Import table |
| 3 | Defined components |
| 4 | Out-addressing table |
| 5 | Object-addressing table |
| 6 | Heap |
| 7 | Code |
| 8 | External function names |
| 9 | Unknown/default handling |
| A | Global-data initialization |
| B | Function offsets |

The source-image operation records independently name selectors 0x1234–0x1239
used by the first six handlers. The direct calls name the code, external-name,
initialization and function-offset handlers. Masking with 0x00ffffff confirms
the payload length field already inferred from the corpus. The intervening
four bits are flags; they are preserved raw rather than conflated with the tag.
Thus raw byte 0x71 is code attribute 7 with flags 1, not a separate attribute 0x71.

The inspector now labels these roles, retaining the payload bytes as opaque.
The loader evidence is from the SDK build. There are now 32 passing research
tests.

## Follow-up on unresolved method names in the current ROM

A read-only search checked all 244 unresolved exact `Class_Method` names against
the production DataRover 840 US and Japanese ROM images
(`ROMs/MIPS/Oki DataRover 840/` in the preservation archive): neither contains any
of the full names as byte strings. Operation-name fragments occur for 19 US and
two Japanese entries, but none has both its class and operation names found
separately. These fragments do not establish code identities.

The other SDK unstripped MIPS executables (Apollo/Sputnik, US/Japanese) also add
no exact defined function-symbol matches for these names. This does not establish
that the implementations are missing from the current ROM. Runtime class-table
resolution, aliases, inherited implementations and build-specific omissions need
separate investigation. Do not transfer the SDK's addresses to the production
ROM.

## Import tables and embedded function offsets

The inspector now decodes flags-zero import attributes. SDK Apollo
`Flattener_ReadImportTableAttribute` (0x13ce62fc) and
`ReadAlignedPascalStrings` (0x13ce43e0) establish each entry as:

1. A big-endian word whose low byte is the interchange kind; zero terminates.
2. Two Pascal byte strings, each with a one-byte length.
3. Padding aligning the **combined pair** to four bytes.
4. Three big-endian words, with the last a count restricted to 1–5000.

The two preceding words remain `raw_component_word` and `raw_range_word`;
complete range-resolution semantics are not yet implemented. Padding and upper
kind bits are retained. The inspector requires the terminator to end the
attribute. SDK `Interfaces/Generic.h` names `DynamicInterchangeKind` values
1–5 as locator, class, operation, class operation and intrinsic. All observed
secondary strings are empty, but tests cover nonempty strings and pair alignment.
This fixes the earlier EtherLinkIII misalignment from treating the first string
as independently padded.

Across 25 files containing 32 packages, all 315 entries decode: 47 locator,
90 class, 59 operation, 38 class-operation and 81 intrinsic entries. These are
import range entries, not 315 individually resolved methods.

Function-offset attribute B0 has an observed layout of a count N, N big-endian
words, and one trailing word (zero throughout the corpus, purpose unconfirmed).
`ReadFunctionOffsetsAttribute` (0x13ce67ec) stores the pristine buffer as method
information; `ReadAttributeToNewPristineBuffer` (0x13ce46a0) copies its payload
unchanged using `ReadObjectBytes` (0x13ce452c).

`EmbeddedCode_TranslateMethodInformation` (0x13e431e0) calls
`EachCodeAddressInPackage` with `FixUpCodeAddress` through transition vector
0x140a4aa8, targeting 0x13e4300c. That callback reads the count from buffer word
zero, indexes words with IDs 1 through N, converts 0xffffffff to a null pointer,
and otherwise adds the offset to the supplied code base. Zero is a valid offset,
not the null sentinel. The inspector exposes this table without manufacturing
absolute runtime addresses. The precise relationship between the supplied base
and the code attribute, the trailing word, and package class-method references
still need verification before writing packages.

All 30 observed function-offset tables decode, totaling 2,061 slots. All 38
research tests pass, including malformed
imports, alignment, unknown import flags, count bounds and function sentinels.
This remains read-only format research, not an installable package writer.

## Linking function IDs to bytes in the code attribute

`CodeHandler_LockCode` (SDK Apollo 0x13ccebb4) obtains `CodeBuffer`, calls
`LockReadExtra` and adds four bytes to the returned pointer (0x13ccec2c).
It passes a selected relocation base to `TranslateMethodInformation` on first
translation, then adjusts addresses if necessary to the actual buffer base.
Thus the final code base is **code attribute payload start + 4**, not the
payload start. `Buffer` has zero fixed storage in MagicCap.cx; the pristine
buffer loader copies the attribute verbatim into its body. `LockReadExtra`
(0x13c89160) returns `PeekExtra`. Together these establish the file-to-buffer
correspondence without assuming a fixed guest RAM address.

The inspector now links a package's single B0 table to its single 0x71 code
attribute using that base. It preserves the leading word without assigning its
purpose, reports absolute **file offsets**, and captures at most 16 entry bytes
without claiming function extents. Other code-attribute combinations remain
explicitly unsupported. Out-of-buffer or unaligned offsets in the supported
layout are rejected. The code-type value is retained as 1; this does not add a
general architecture detector for arbitrary package formats.

All 30 paired tables pass: **2,001 non-null entries** locate aligned words within
their code buffers, and **60 entries** are null sentinels. These totals count
slots, not distinct implementations, and do not prove the instructions execute
correctly. The corpus scan reports both totals. Tests cover the
four-byte base, zero offsets, bundled-package file positions, bounded previews,
null slots, invalid offsets and unsupported variants; all **41 tests pass**.

### How class method records feed the table

`UnlinkedClassWithMethods_EachCodeAddressInClass` (0x13c90268) reads the method-list
offset from the class flavor's halfword at +2. Its helper
`EachCodeAddressInMethodList` (0x13c902e8) reads a count masked with 0x7fff,
then a halfword displacement relative to the position after those two
halfwords. That reaches an array of eight-byte method records. Records whose
first byte is greater than 0x40 pass the word at record +4 to the callback;
when writeback is enabled, the translated value returns to that same word.
`FixUpCodeAddress` is the callback identified in the preceding section, so this
word holds a function ID before translation in this path. The first word's full
encoding and the operation-name association are not decoded yet. Records with
other first-byte values must not be treated as ordinary native methods.

The next boundary is parsing frozen heap object
boundaries and identifying their class flavors, then decoding the method lists
and operation references. The current inspector deliberately does not search
arbitrary heap bytes for plausible IDs or claim named method bindings from such
matches. No ROM or executable package was modified.

## Frozen heap object boundaries

The inspector now decodes flags-zero heap attributes (0x60), following
`Flattener_ReadHeapAttribute` (0x13ce5560), `ReadNextObject` (0x13ce54fc) and
`Flattener_ReadFrozenObject` (0x13ce4bd8) in the SDK Apollo ELF. Each record
starts with a big-endian header word; zero terminates the heap. Bits 31–30
select the record form:

| Value | Boundary layout |
| --- | --- |
| 1 | Header only; low 20 bits retained as a raw class selector |
| 2 | Header, 32-bit body length, optional external name, body, four-byte alignment padding |
| 3 | Header and one 32-bit locator selector |

Class selectors are inputs to the loader's component-range mapping, not assumed
runtime class numbers. Kind 2 uses the low 20 header bits as this selector.
Other flag bits remain raw. Kind 1 is supported from disassembly but does not
occur in the current corpus.

For kind 2, bits 29–28 control whether names are external. When that subtype is
3, the loader skips the external-name reader even if bit 24 is set; it marks
the block as named and preserves the body bytes. Otherwise, bit 24 introduces
an external name: a 16-bit code-unit count, big-endian 16-bit characters, and
padding aligning the count plus characters to four bytes. The body is separately
padded to four bytes. Padding is preserved, not required to be zero. This
subtype distinction is visible at 0x13ce5134–0x13ce519c and is essential for
parsing the supplied packages correctly.

All 32 package heaps end at their expected terminator, covering **5,543 records**:
4,625 kind-2 body records and 918 kind-3 locator-reference records. No external
names occur in this corpus; synthetic tests exercise that loader path. Reports
preserve body spans and hashes, selectors, padding, record positions and headers.
They do not deserialize body fields or resolve the selectors. Unknown heap
attribute flags remain opaque. All **45 research tests pass**.

A bounded check of Ne2000's three body records with selector 0x517 found method
lists at the offsets described in the preceding section. That selector matches
SDK class `UnlinkedClassWithInstances`, and Ne2000 imports `SystemInternal`
classes beginning at raw component word 1300. Their method lists contain 16,
7 and 8 records respectively; the final list mixes native entries with two
non-native entries. Native function IDs fit the package's decoded function
table. This remains a provisional class identification: import-range semantics
must be confirmed before the inspector can safely label those records or map
operation selectors to names. The discovery does not yet establish named
package-method bindings.

Next: verify the `SystemInternal` import mapping, decode the identified class
method lists, and connect their native IDs to the already located code entries.

## Import-aware method linkage

`ResolveImportedClique` (SDK Apollo 0x13ce6064) confirms the import range fields:
`raw_component_word` is the package selector start, `raw_range_word` is a
zero-based offset into the named interface, and `count` is the requested range
length. The loader asks the dynamic interchange table for the interface's
exported base/count. On its resolved path it adds the requested offset to that
base, then installs a mapping from the package selector range. Locators use an
eight-byte stride; class and operation selectors use unit increments. This
analysis does not implement the loader's missing-interface/fallback paths.

`Interfaces/DefFiles/Interfaces/InternalInterface.cdef` independently declares
`SystemInternal`, class numbers beginning at 1300, and
`UnlinkedClassWithInstances = 4`. Thus its zero-based interface offset is 3.
For example, Ne2000 imports this range at package selector 1300, so selector
1303 identifies that metaclass. The linkage tool uses the interface and offset,
not a hard-coded package selector. It likewise maps operation selectors through
imports to literal declarations in PublicInterface.cdef and
ConditionalInterface.cdef. Conditional alternatives are retained; this is not
an SDK preprocessor or proof of current-ROM export availability.

`FindOrInsertMethodEntry` (0x13cd0d50) masks the first method word with 0x000fffff
when looking up selectors, confirming the **low 20 bits**, not the low 24 bits,
identify the operation. The existing class iterator confirms the native-entry
threshold and eight-byte stride. The new read-only tool is:

```sh
python3 toolchains/mips/link_package_methods.py
```

Its report is hashed against its inputs. Across the
32 packages it identifies **511 UnlinkedClassWithInstances bodies**, containing
**3,350 method entries**: 1,872 native and 1,478 non-native. All 1,872 native
entries link to bounded code previews via the previously decoded function-ID
tables. **843 method entries** map to SDK-declared operation names. These counts
include repeated methods and bundled copies; they are not unique functions.

Concrete Ne2000 examples (heap object 1, file offsets in Ne2000.pkg):

| SDK operation | Function ID | Code entry file offset |
| --- | --- | --- |
| Connect | 9 | 15464 |
| CanSleep | 15 | 14516 |
| Read | 12 | 17892 |
| Write | 13 | 18356 |

The records' **metaclass** is now identified through import declarations, but
names of the classes they represent are still unassigned. Package-defined
operations remain `not-imported`; unknown interfaces retain interface/offset
without a fabricated name. Overlapping imports are marked ambiguous. Other
metaclass layouts, including UnlinkedClassWithMethods, remain outside this
linkage pass. Non-native values are retained without translating them as code.

Four new tests cover nonidentity import ranges, kind separation, ambiguity,
conditional declarations, selector masks, native thresholds and method bounds.
All **49 research tests pass**. Remaining work includes defined
component mappings, represented class names, other class layouts, and eventual
package construction and guest validation.

## Defined ranges and complete native-slot coverage

`Flattener_ReadDefinedComponentTableAttribute` (SDK Apollo 0x13ce6630) reads
triples of big-endian words: interchange kind (low byte), package selector
start, and count. Kinds 2–5 are class, operation, class operation and intrinsic;
locator kind 1 is rejected by this handler. A kind-zero word terminates the
attribute. The handler allocates a runtime component-number range and maps the
package selectors onto it, so these serialized selectors are not fixed runtime
numbers. The inspector now decodes this attribute for flags zero, checks bounds
and nonempty nonwrapping ranges, and preserves the raw kind word.

Ne2000 defines three classes starting at selector 0x54b and five operations
starting at 0x13b7. The table has **no name strings**. The method report now
labels local references `package-defined` with selector and range offset, rather
than leaving them `not-imported`. Import/local overlaps are marked ambiguous.
This establishes component identity inside the package without inventing names.

The SDK UnlinkedClassWithInstances.cdef and its `EachCodeAddressInClass` at
0x13c8ff08 confirm three method-list offsets within each supported class body:
object operations at halfword +2, class operations at +8, and intrinsics at +6.
The loader iterates all three with the same method-list callback. The report
now decodes all three lists and resolves each in its own interchange namespace.

This expands coverage to **3,479 method records**: 2,001 native and 1,478
non-native. Of their component references, 883 map to imported interfaces
(877 have literal SDK declarations) and 2,596 are package-defined. Per-package
set comparisons confirm that **every non-null function-table ID is referenced
by a decoded native method record**, with no unlocated native IDs. This holds
for all 30 packages with function tables; the other two packages have no such
slots or decoded native records. Repeated/bundled packages remain included.
The report stores both missing-ID sets, rather than relying on equal totals.
All **53 tests pass**.

Names of represented classes remain unresolved. `CodePackageCluster`'s
`UnlinkedClassInClusterByNumber` at 0x13cd008c indexes a contiguous locator array
from its reference field +0x64, using `(classNumber - classBase1) * 8`; it does
not look up a name. Connecting that array to frozen heap records requires the
object-addressing table. Source names may require package debug/export metadata
or matching SDK source, and must not be inferred solely from numeric selectors.
The next step is object-addressing decoding and class-array identification.
The package writer and guest execution validation remained unfinished at this
stage.

## Object selectors and represented class identities

All 32 package object-addressing attributes use byte 0x53. The SDK handler at
0x13ce5ec0 interprets bits 26–25 as the cluster-handling mode and bit 24 as
list-versus-range encoding. For 0x53 it calls
`ReadAndCreatePackageClusterReference` (0x13ce5730), consuming a cluster selector
and an auxiliary word, then `ReadAndAllocateAddressingRange` (0x13ce5a40).
That reader consumes selector-start/count pairs until a zero start word.
Its upper count bound is 10,000; locator selectors advance by eight bytes.
The inspector preserves the auxiliary word without assigning it a new meaning.

The heap loader reads the cluster object first, then reads the objects associated
with the allocated locator ranges in sequence. The inspector checks that the
cluster plus range counts equal the heap-record count and rejects duplicate
selectors in the supported layout. All **5,543 heap records** now have a mapped
package-local locator selector. Other addressing attribute variants remain
opaque, and combinations outside one decoded addressing table and one heap are
explicitly unsupported. The corpus uses selector 4 for the cluster and a single
range starting at 12, but the decoder does not hard-code those values.

The method report now follows the CodePackageCluster class-array fields verified
in the SDK lookup routine: reference +0x64, class base +0x8c, class count +0x94.
It maps `arraySelector + index * 8` through the decoded locator map and assigns
`classBase + index` to that heap record, verifying membership in the package's
defined class ranges. It does not merely assign class IDs by scanning for
class-shaped bodies. Metaclass identification still goes through the named
SystemInternal import.

All **511 supported class-flavor records** now have represented class selectors.
For Ne2000 the three are 0x54b, 0x54c and 0x54d, at locator selectors 12, 20 and
28 respectively. Each class's method records retain their operation namespace,
import or local component identity, and native function/code linkage. These
numeric identities are package-local, not source names or installed runtime
class numbers. The 2,001 native-slot coverage check continues to pass.

Four new tests cover addressing counts and malformed ranges, shifted selectors,
class-array lookup through a deliberately reordered locator map, absent locators
and invalid class ranges. All **57 tests pass**. Source-level class names and
local operation names remain unresolved; useful next work is export/debug-name
metadata and global-data initialization, followed by constructing a minimal
package and testing it in the guest.

## Global-data initialization: header and supported bytecode prefix

`CodeHandler_GlobalDataSize` (SDK Apollo 0x13cccee0) reads the first word of the
initialization buffer as the required globals size. The interpreter at
0x13ccd750 starts at buffer +8. The second header word is preserved raw: this
pass has not established its meaning and does not use it to truncate the script.
For example, Ne2000 requests 0x808 (2,056) bytes of globals.

The instruction high nibble encodes a count. Values 1–12 select the constants
1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24 from the SDK table at 0x13ebc2ec.
Values D/E/F read unsigned big-endian counts of 1/2/4 following bytes. High
nibble zero selects control instructions instead. The low nibble selects the
operation, via the jump table at 0x13ebc338. The inspector bounds-decodes copy,
destination advance/rewind, byte/halfword/word/doubleword repeat, zero fill,
and base-relative word operands. Control words remain raw; byte 0 terminates
this boundary scan. Trailing bytes remain preserved rather than assumed padding.
This is not an executor and does not apply writes, pass masks or relocations.

Base-relative instructions call `getBNum` at 0x13c68c58, with a separate encoding:
bytes below F0 are literal unsigned values; F0–F7 carry a signed three-bit high
part and one additional byte; F8/F9/FA read signed 16/24/32-bit values. FB skips
four bytes then reads the low signed 32-bit word, matching this MIPS reader.
The parser rejects FC–FF instead of silently emulating their zero-return path.
These BNums must not be confused with instruction high-nibble counts.

Opcodes C/D/E enter stateful interface/component-resolution processing. The
inspector stops **before** these instructions and preserves the complete
remaining span with `partial-global-init`. All 30 supplied code packages stop
at this boundary, after a total of 150 supported prefix instructions. No full
initialization script has been decoded yet. For Ne2000 the prefix contains
controls 07/08/09/0A and a base-relative word instruction, followed by opcode 1C.

Four tests cover signed BNum widths and truncations, literal bytes containing
zero, extended instruction counts, relocation operands, malformed instructions
and the explicit partial-decoding boundary. All **61 research tests pass**.
The corpus scan now reports the decoded header/prefix on A0 attributes;
other attribute flags remain opaque.

Next is decoding the interface-resolution instruction operands and pass state.
A package writer also still needs validated object/reference serialization and
relocation behavior; finishing this bytecode decoder alone will not establish
that generated packages boot or install correctly.

## Interface-resolution operand decoding

The global-initialization decoder now passes the former C/D stopping point.
The SDK interpreter at 0x13ccddc8 reads an update mask once per instruction,
then applies it for each repetition. Bits 7–0 conditionally update source kind,
interface name, component index/step, and five additional operand fields. Fields
whose complete semantics are unverified retain raw labels matching their SDK
stack slots. The report records changes and previously observed operand values;
it does not claim a complete executable machine state or populate unknown
runtime defaults.

The interface-name reader at 0x13ccde30 supports literal lengths up to 127,
0x80 followed by an explicit byte length, and 0xc0–0xff suffix edits. A suffix
edit drops up to `tag - 0xc0` bytes from the previous name, then appends a
byte-counted suffix. Tags 0x81–0xbf are invalid. The inspector currently rejects
edits producing more than 255 bytes rather than emulating the loader's clipping.
All supplied names remain within the supported range.

Component-index updates accept an ordinary BNum (step zero), 0xfe plus a BNum
(step one), or 0xff plus index and step BNums. The index advances after each
resolution entry. Control 01 resets tracked operand state, matching the loader's
pass setup. Opcode D also consumes a signed BNum destination delta after each
entry. Opcode E's extra chained resolution remains explicitly unsupported and
would preserve the remaining span as partial. Expansion is limited to 100,000
resolution entries per instruction by the inspector, not asserted as a hardware
limit.

All **30 corpus scripts** now parse through their stop instructions: **19,683
instructions**, including **5,419 resolution entries**. Trailing bytes remain
preserved, and this does not establish that every trailing byte is padding.
The report status `decoded-global-init-boundaries` means instruction/operand
boundaries are decoded; it does **not** mean runtime exports were resolved,
globals were initialized, relocations were applied, or the guest executed them.
The distinction matters because interface lookup can depend on installed
packages, pass masks, and runtime component assignments.

Tests now cover reused/compressed interface names, pass-state reset, repeated
index updates, signed destination deltas and truncated update operands. The
previous partial-instruction test now exercises opcode E. All **64 tests pass**.
The next useful validation is interpreting the supported writes
and relocation targets against globals/code bounds with symbolic interface
results, before attempting package construction.

## Initial-load globals write audit

`toolchains/mips/validate_global_init.py` checks supported script writes
against the declared globals allocation. It follows advances, rewinds, resets,
literal/repeated writes, base-relative words and resolution writes. Runtime
addresses remain symbolic. Scope is initial-load mask 0x0f, enabling all four
pass bits, not later selective relinking or runtime interface lookup failures.

The SDK initializes the destination from argument 3 at 0x13ccd7d8. Control 01
resets destination and resolution state; control 02 resets destination alone.
Resolution destination mode defaults to 4 at 0x13ccd828. Mode 4 writes a word;
mode 0x11 writes an eight-byte address/GP pair at 0x13cce858–0x13cce880. These are
the two resolution modes observed in this corpus. Unsupported modes/controls
are rejected. Literal repeat sizes are checked before host-memory expansion.

All **30 code-bearing packages** pass bounds and alignment checks for **12,912
write spans**. Of **7,433 base-relative targets**, **124 are outside** the nominal
code extent. Every exception uses signed BNum -1110585907, encoded as
`fa bd cd cd cd`. English and Japanese MagicJavaScript each contribute 61;
English and Japanese WebBrowser 4.0 each contribute one. These appear in code/GP
pairs alongside globals-relative offset zero and are not overwritten by later
supported writes in the same script. A placeholder is a plausible explanation,
but its purpose and whether runtime code uses these entries remain unknown.
The audit does not special-case this value as a valid code address.

Pointer extent checks are advisory and permit one-past addresses; passing does
not prove an address can be dereferenced or called. Unknown external bases or
additions to symbolic words remain unresolved. Zero unresolved *base-relative
targets* in this corpus does not include the 5,419 interface resolution entries,
whose runtime values are still symbolic.

The report records input hashes. Seven new tests cover bounds/alignment, bounded expansion, resets/deltas, signed
additions, symbolic values, advisory out-of-range targets and unsupported inputs.
All **71 research tests pass**. Next is resolving interface operands against SDK
exports and tracing the outlying code/GP entries before package construction.

## Initialization source classification and declaration names

A source-classification pass classifies all 5,419 resolution entries without
assigning runtime addresses. The SDK interpreter's tables at 0x13ebc378 and
0x13ebc3b8 distinguish component kind from the value requested. Source kinds
1–5 request locator/class/operation/class-operation/intrinsic selectors. Kind 6
requests intrinsic code and GP; kind 7 requests its GP. Kinds 8/9 use class
runtime lookup/field offset; kinds 13–15 request method/intrinsic code and GP.
Exact kinds 0 and 10–12 bypass interface lookup for immediate/base-relative
values. The upper source bits are retained; at 0x13cce52c the 0x80 bit permits a
failed interface/range lookup to yield zero. This does not imply every subsequent
transformation or destination operation will succeed.

The interpreter checks `index + required_count` against interface size and uses
stride eight for locator selectors, one for the other kinds (0x13cce3c0 onward).
The formerly raw field at stack slot 0x1a4 is therefore reported as required_count
in the new source report. Declaration-name matching labels the indexed component;
it does not validate the full runtime range or resolve its address.

Names starting with `@` select a package interchange table, constructed by
MakePackageInterchangeTable at 0x13cce354. The report retains these local names
without inventing selector assignments. The special `Dispatchers` fallback
requires exact source kind 6, destination mode 4, and an index below seven.
DispatcherEntryPoints at 0x13ccd67c constructs seven entries and returns seven.
The source report identifies this fallback without embedding SDK ROM addresses
as addresses suitable for the current guest ROM.

Corpus results: **2,022 unique SDK declaration-name matches**, **210 dispatcher
fallback entries**, **3,055 package-local interface entries**, and **132 external
interface entries** absent from the three loaded SDK declaration files. Here
“unique” means one name candidate per entry, not 2,022 distinct names. All 319
SystemPublic locator entries now have indexical names as well.

The shared declaration parser now recognizes indexicals as locators and stops
at the first `end interface;`. This fixes accidental inclusion of a later
AnnouncementInterception interface from PublicInterface.cdef. Conditional name
alternatives are still preserved rather than preprocessed. Existing method
linkage totals remain unchanged: 2,001 native methods located and 877 imported
operation references named.

Five new tests cover interface boundaries, indexicals, optional
intrinsic references, local/missing interfaces, dispatcher constraints and
ambiguous declarations; **76 research tests pass**. This does not resolve the
124 outlying code offsets or establish a working package writer. Next is tracing
the package interchange table to connect local names to package selectors.

## Package export names and local selector mapping

`package_exports.py` follows cluster field 0x58 to PackageExportTable, table
field 0 to PackageExportHashEntries, and table field 0x18 to CliqueNameTable.
The parser checks the imported SystemInternal class identities before applying
these layouts (cluster offsets 6/7, export table 11, names 12, entries 47).
The SDK MakePackageInterchangeTable at 0x13ccd11c and its callback
AddExportToThisDynamicInterchangeTable at 0x13ccd038 establish these references.

The observed entries body starts with a four-byte slot count, followed by
16-byte slots. PackageExportHashEntries_Stride at 0x13cd5d80 confirms stride 16;
FastEachHashEntryCommon at 0x13cb7af0 passes slot+4 to the callback and skips
slots whose leading link word has its high bit set. Each active slot contains
that link word, a packed kind/name-offset word, a component count and a selector
start. Kind is the packed word's high byte; its low 24 bits locate a Pascal
byte string in the names object's extra data, starting at body+8. The callback
filters names by their leading `@` when building a local interchange table.
The inspector preserves link words; it does not reconstruct hash buckets or
claim that a newly generated table would satisfy hash lookup invariants.

All 32 packages parse, yielding **3,090 active export records**. All **3,055
package-local initialization references** match one export of the same kind and
name, and pass the requested range check. Locator offsets advance by eight;
other selectors advance by one. These remain frozen package selector values,
not the runtime component numbers assigned when installed.

The source report now includes exports and each local reference's selector and
supporting record offset. Method reports include exact singleton local-export
names for classes and operation selectors; multi-component exports are not
assumed to name each individual component. This names **214 of 511 represented
classes**. Ne2000 class 0x54c is `NoCardEtherServer`, and 0x54d is `Ne2000Means`;
class 0x54b is exported through the driver interface but has no singleton local
class name. All 2,001 native method locations remain linked.

Four tests cover slot decoding, inactive slots, malformed sizes/names/kinds,
locator stride, range checks and ambiguous/missing names. All **80 research tests
pass**.
Next is matching the 132 external-interface initialization entries against
exports from other supplied packages, with provider ambiguity kept explicit.
The 124 unusual code offsets and package construction remain unresolved.

## Corpus providers for non-SDK initialization interfaces

The source classification now indexes non-local exports from **all 32 packages**,
including data-only packages. For each of the 132 references without loaded SDK
interface declarations it matches exact interface name and component kind, checks
`index + required_count` against export count, and reports the provider's frozen
selector (stride eight for locators, one otherwise). Provider file hash, package
index and export record offset are retained. This is a corpus candidate search,
not an emulation of installed-interface selection or runtime renumbering.

**116 references have candidates:** eight have one export candidate and 108 have
multiple candidates. File/language/version variants and duplicate exports remain
explicit; the tool does not silently select or merge them. **100 references have
a same-package candidate**, while 16 have candidates only in other packages.
Thus the earlier `external-interface-unavailable` classification means absent
from the three loaded SDK declaration files, not necessarily a dependency on a
separate package. That original classification is retained alongside provider
matches to distinguish declaration evidence from package export evidence.

The **16 references without corpus providers** comprise six WCPack intrinsic,
four WCPackEthernet class, four WCPackPCCard locator, and two SpellFinder
(operation/locator) references. None of these searches failed solely because
an available export range was too short.

The report also records exact interface-name byte occurrences in the retained
SDK ROM and current guest ROMs, with ROM hashes and file offsets:

| Interface | SDK US | Current US | Current Japan |
| --- | --- | --- | --- |
| genmagic.com/WCPackInterface1 | 0x422f29 | 0x3d3549 | 0x5560c9 |
| genmagic.com/WCPackEthernetInterface1 | 0x422f6b | 0x3d358b | 0x55610b |
| genmagic.com/WCPackPCCardInterface1 | 0x422f47 | 0x3d3567 | 0x5560e7 |
| genmagic.com/SpellFinder1 | 0x3e7551 | 0x3be7a9 | not found |

These are string occurrences, not validated ROM exports or executable addresses.
Their presence suggests ROM-provided interfaces as the next path to examine;
absence alone does not prove functionality is absent. No SDK address is applied
to a different ROM. Report field `rom_string_evidence_only` preserves this limit.

Five tests cover provider selector stride, duplicate/variant ambiguity, range
rejection, local-export exclusion, kind matching and ROM string offsets.
All **85 research tests pass**. Next is decoding ROM interface table entries
around the WCPack/SpellFinder names to validate export counts and component
mappings. Generated package execution and the 124 unusual offsets remain open.

## Selected ROM export object chains

A ROM export reader now follows stored object references around the
WCPack and SpellFinder name-table anchors, rather than treating string presence
as export evidence. It identifies an observed eight-byte ROM object header,
the names object's stored self-reference, an export table whose field 0x18
references that name object, and the entries object referenced by table field 0.
It checks the 12-byte export payload size, 16-byte slot layout, active count,
name bounds and uniqueness of the reference chain. The entries object must
precede the names object in this supported layout. Unsupported or ambiguous
chains fail explicitly. This is a bounded reader for these selected tables,
not a general ROM volume/object parser or a validation of hash bucket topology.

The export callback and iterator evidence described above also establishes the
record payload: kind/name offset, count and starting component selector. Six
new tests cover the reference chain, missing/ambiguous links, active counts,
name bounds, alignment and unsupported payload size. **91 research tests pass**.

All **16 references without package-corpus providers** have matching kinds and
sufficient export ranges in both the SDK US and current US ROM. The current
Japanese ROM matches **14**, with both SpellFinder references still unmatched
because that anchor is absent. The tool does not infer that SpellFinder could
never be supplied by another installed package.

Representative stored export values:

| Export | Count | SDK US start | Current US start | Current Japan start |
| --- | --- | --- | --- | --- |
| WCPack intrinsic | 3 | 0x4c5 | 0x4c5 | 0x4c6 |
| WCPackEthernet class | 11 | 0x626 | 0x5da | 0x5e5 |
| WCPackPCCard locator | 12 | 0x8001b909 | 0x80018d09 | 0x80019c09 |
| SpellFinder operation | 2 | 0x13be | 0x13be | unmatched |
| SpellFinder locator | 1 | 0x80016b49 | 0x80016849 | unmatched |

The different values demonstrate why SDK selectors must not be substituted for
current guest values. ROM locators retain their encoded reference bits; they
are not host pointers or decoded executable addresses. Interface matching still
does not execute runtime component renumbering, intrinsic code/GP lookup, or
post-resolution transformations.

Its results record ROM hashes, object offsets, exports and per-reference
candidates. This closes the missing-provider evidence gap for the checked US ROMs. Remaining work
includes choosing a concrete target/provider set, validating resolution value
transformations, and understanding the 124 anomalous code offsets before a
minimal package writer and guest installation test.

## Initialization value stage and first construction component

`build_global_init.py` adds a small encoder for the supported A0 payload subset.
It emits counted literal/zero writes, destination moves/resets, code/global
relative words and complete interface-resolution operand updates. BNums use
signed 32-bit values and the shortest supported encoding; instruction counts
use their separate compact/extended format. Interface names are emitted in
full, including the explicit long-name form, avoiding dependence on prior name
compression state. Resolution updates explicitly set all eight fields.

The interpreter's value stage at 0x13cce61c checks source width, then at
0x13cce6e4 computes the low 32 bits of `source * multiplier + addend`. Stack
fields 0x1af, 0x1b4 and 0x1bc therefore represent source width/sign, multiplier
and addend. Mode 4 writes the transformed word; mode 0x11 writes it followed
by the unmodified resolved GP. The new `transformed_words` helper implements
this stage for concrete, already-resolved values, rejecting unsupported modes.
It does not resolve interfaces or invent runtime code/GP values.

All **5,419 corpus resolution entries** specify/default to width 32,
multiplier one and addend zero. Modes are 4 (3,619 entries) and 0x11 (1,800).
Each entry was independently re-encoded and decoded with matching effective
source kind, interface, index, required count, width, multiplier, addend and
mode. This validates operand construction, not byte-identical reproduction of
compressed scripts, pass behavior or full-script execution equivalence.

`GlobalInitBuilder.finish(code_size)` decodes the output and runs the existing
write-bounds/alignment audit, rejecting outlying relative targets. The second
header word remains an explicitly required caller value because its meaning
is not established. No whole-package writer, object hash-table generator or
ROM patching was introduced. Eight tests cover BNum/count boundaries,
resolution operands, long names, literal/relative writes, reset behavior,
invalid bounds and source-width/arithmetic semantics. **99 tests pass**.

An illustrative 40-byte payload declares 20 globals bytes: four
literal bytes, a code-relative/global-relative pair, and a SystemPublic
intrinsic code/GP reference. The example uses an assumed 32-byte code extent
only for bounds checking; it contains no executable code and is not a package.
Next is constructing the minimal class/object/export records and a complete
container around a controlled code stub, then testing installation in the
separately verified Rosemary SDK ROM. The existing anomalous code offsets are
not accepted as valid pointers by the encoder.

## Frozen container and heap construction

`build_frozen.py` now emits version-152 package envelopes, attribute headers,
heap object records, import tables, defined-component ranges, object addressing
and function-offset tables. Bundles remain concatenations of complete packages.
Each constructed container is checked by the existing inspector, including
cross-attribute heap/addressing counts where both are present.

Heap construction supports header-only, body and locator-reference records.
Bodies remain explicit byte strings: this does not synthesize valid class or
PackageCluster fields. Named objects use UTF-16 code-unit bytes with their own
padding; subtype-three objects carry a named-block flag, with names resolved
through the cluster dictionary (see the later name-dictionary trace). Caller-supplied
padding can be preserved exactly, while new records default to zero padding.
Raw header bits remain explicit rather than assigning unverified meanings.

The corpus reconstruction command regenerates every heap record's header,
length, external name and padding from parsed fields, then rebuilds each
attribute/package envelope. It retains opaque body bytes and other attribute
payloads. All **25 files / 32 packages / 5,543 heap objects** reconstruct
**byte-for-byte identically**, including bundles; original packages are untouched.
This tests serialization, not a newly built application's runtime correctness.

Seven tests cover external-name padding, subtype-three/reference/header-only
records, malformed payloads, new container assembly, bundles/unknown attributes,
function-offset zero versus null, invalid component ranges and heap addressing
mismatches. All **106 research tests pass**. The synthetic container in the tests
is deliberately a structural fixture, not an installable application.

A minimal installable package still needs valid cluster and class-flavor bodies,
object/reference field serialization, an export hash table and the abbreviated
class attribute (0x10). These cannot be supplied by copying arbitrary placeholder
bodies into this envelope. The next construction step is to derive those fields
for an SDK sample and connect them to the initialization encoder and code stub.

## Abbreviated class records and fixed-field formats

Attribute 0x10 is now decoded and regenerated. Each entry is a nonzero 32-bit
class selector followed by an 8-bit word-format count N, ceil(N/2) packed format
bytes, and padding to align that count/format span to four bytes. A zero class
selector terminates the attribute. Each packed byte holds the earlier word's
format in its high nibble. Odd counts leave the final low nibble unused.
The decoder preserves unused bits and padding; fresh encoding defaults them
to zero. Unknown attribute flag variants remain opaque.

SDK Flattener_ReadAbbreviatedClassesAttribute at 0x13ce6480 maps the selector
through the class component map, reads the count and packed bytes, skips the
alignment bytes, and installs the abbreviated class. WriteAbbreviatedClass at
0x13cea450 emits the same form. AbbreviatedClass_Init at 0x13cd6cb0 packs pairs
of WordFormat values and clears an odd final low nibble.

The SDK `Interfaces/ObjectFormat.h` defines formats 0–14 as unstructured bytes,
halfwords, halfword/two-byte combinations, integer, first/second doubleword,
strong/weak pointers, class/operation/class-operation/intrinsic numbers and
strong/weak object references. Value 15 is reserved, with no named normal format
in this header. The inspector retains numeric values rather than rejecting a
reserved value based only on this SDK version. The header identifies the format
list as fixed-part words and gives fixed byte length as four times its count.
Its SDK fixed-part limit is 64 words; the serialized reader uses an 8-bit count,
so the structural parser does not impose that SDK construction limit.

A comparison of imported class identities against the
SDK MagicCap.cx layouts. Across **1,391 records**, **1,070 have matching SDK fixed
sizes**, **zero mismatch**, and **321 lack a unique comparable SDK layout**.
This size check does not yet derive all individual format nibbles from class
field declarations or validate inheritance/reference serialization semantics.

The corpus reconstruction now regenerates attribute 0x10 as well as heap
records. All 25 files still reconstruct byte-for-byte. Five tests cover nibble
order, odd unused bits/padding, empty/multiple records, count limits, malformed
input and trailing bytes. **111 research tests pass**.
Next is deriving the fixed-part format list for a minimal sample and constructing
its cluster/class bodies, rather than supplying opaque body placeholders.

## EmptyPackage fixed-field derivation

The retained SDK EmptyPackage.cdef declares no new classes. Its Objects.odef
uses SoftwarePackageContents, ObjectList, Scene and Text, with references to
system indexicals. It is therefore a useful first object-construction target
without needing a newly defined class or native method. Container/cluster
metadata is still required even though the sample has no new class declarations.

`derive_fixed_formats.py` now derives a conservative subset of fixed-field
formats from MagicCap.cx field types, offsets, inheritance and flags. Signed,
Unsigned and Flags become integer words; Boolean bitfields occupy unstructured
words; class-typed references become strong/weak object words according to the
observed 0x80 weak flag. Unsupported types, flags, offsets and conflicting word
formats fail explicitly. Unassigned words remain listed in the report, rather
than implying that their initialization semantics are known.

Mixin field offsets must be supplied explicitly when the field-access base is
not Object. In particular, blindly copying HasBorder's offset zero into Scene
would overlap Viewable's fields. The SoftwarePackageContents comparison uses
an explicit HasDate base of zero: PackageContents inherits zero-size Object
and HasDate's 16 bytes, matching its 16-byte fixed prefix. This placement is
recorded as an input, not generalized to all mixins.

SoftwarePackageContents' derived 18-word format list matches all **30** comparable
package entries. ObjectList and Text have empty fixed parts and match another
**64** entries. Thus **94 comparisons pass with zero mismatches**. This confirms
word formats, not field-value serialization, Boolean bit order or initialization
of omitted fields. Scene currently stops at compound type Dot; CodePackageCluster
stops at VolumeRosterPointer. They are not emitted with guessed formats.

Its report includes the SDK hash, explicit base offsets, field provenance,
formats and corpus comparisons. Five tests cover scalar/reference formats, weak references, explicit mixin
placement, repeated inheritance, unsupported fields and conflicts.
All **116 research tests pass**. Next is adding source-backed compound/pointer
type handling and locating the mixin base offsets needed for Scene before
serializing EmptyPackage's field values and full cluster.

## EmptyPackage compound fields and cluster formats

The conservative fixed-format derivation now covers all five selected classes:
SoftwarePackageContents (72 bytes), Scene (72), CodePackageCluster (188),
ObjectList (zero fixed bytes), and Text (zero fixed bytes). None has unassigned
fixed words. The empty fixed parts of ObjectList/Text do not describe or generate
their variable-length extra data.

Generic.h defines Dot as horizontal and vertical Micron members, with Micron
an alias of Signed. The SDK layout and corpus therefore support two integer
word formats for Dot. UnsignedShort uses the high/low-halfword formats, combining
with unstructured Boolean bytes or another halfword. Field bit ranges are tracked
to reject overlap even when overlapping fields have the same format.

Types.Def declares VolumeRosterPointer as a data pointer; CodePackageCluster.cdef
declares MethodCodeAddress as a function pointer. Their **weak-pointer word
format (8)** is corroborated by the corresponding positions in all 30 cluster
records. This observed rule is deliberately limited to these two types rather
than treating every C pointer alias identically. ClassNumber, OperationNumber,
ClassOperationNumber and IntrinsicNumber use formats 9–12.

Scene uses an explicit BackgroundWithBorder base offset of 44 bytes. SDK Box
inherits Viewable (44 bytes) and HasBorder (four bytes), and its total fixed
size is 48 bytes. HasBorder's field-access base is BackgroundWithBorder, so the
border field lands at byte 44. This explicit placement is recorded in the report;
the implementation still does not claim a general mixin-placement algorithm.

All **136 complete format-list comparisons match**: 30 SoftwarePackageContents,
30 CodePackageCluster, 12 Scene, 32 ObjectList and 32 Text. These compare every
format nibble, not only total sizes. The report records SDK input hashes,
field owners/offsets/types and the explicit mixin placement. Six added tests
cover Dot, Boolean/halfword combinations, two-halfword words, pointer/component
formats, overlapping fields and misalignment. **122 research tests pass**.

Next is encoding fixed-field values with confirmed Boolean bit ordering and
reference representation, plus ObjectList/Text extra data, then connecting
those objects to valid package cluster metadata. No generated EmptyPackage has
been installed or executed yet.

## Fixed-field values and ObjectList bodies

`build_object_values.py` now writes fixed fields from the derived layouts.
Every named field must have an explicit value; missing/unknown fields are
rejected. SDK Boolean offsets count from the high bit of each byte: the mask
is `1 << (7 - (bit_offset % 8))`. The earlier LSB-first interpretation was
incorrect; see the cluster validation correction below. Signed/scalar/component/
reference words and halfwords are big-endian.
Dot takes two explicit signed raw Micron integers; conversion from the sample's
point notation remains separate. Runtime roster/code pointer fields currently
accept only zero. Reference values must be supplied as encoded selector words;
this encoder neither assigns nor resolves them.

ObjectList extra data uses a high-byte word format (13 strong object reference
or 14 weak object reference), a low-24-bit element count and big-endian reference
words. ObjectList_InitialListWordFormat at 0x13cb9d1c returns 13; the corpus also
contains explicit weak lists. Empty body is another observed empty-list form,
with no word format asserted. The decoder preserves this distinction from a
four-byte zero-count list. Other class-specific header flags remain unsupported.

All **361 ObjectList bodies** reconstruct byte-for-byte: **309 strong**, **29
weak**, and **23 empty bodies**. This verifies the list
serialization, not that each supplied selector resolves in a newly built package.

An illustrative 72-byte SoftwarePackageContents fixed body is saved as
`generated-contents-fixed.bin`; its JSON companion records explicit values and
hash. It enables autoActivate and uses illustrative selectors 12 and 20 for
installation/help lists. Those selectors are placeholders without assembled
objects; this file is not an installable package.

Text bodies remain unimplemented. The corpus stores encoded text bytes, whereas
Text_Init constructs an in-memory representation with Unicode code units. They
must not be conflated by copying UTF-16 directly into a frozen Text record.
Nine tests cover fixed-value byte order, Boolean numbering, signed Dot values,
explicit references, null runtime pointers, strict field validation and all
supported list forms. **131 research tests pass**. Next is tracing the frozen
Text codec, converting the sample's point coordinates, and assigning real
package-local/imported selectors before assembling EmptyPackage.

### Plain Text chunks (SDK ROM trace)

The previous “frozen Text codec” description needs clarification: the object
loader at 0x13ce519c calls ReadObjectBytes and copies the body unchanged. Text
itself supports multiple in-memory representations. ClassifyChunk at
0x13d2d730 and Text_EachTextRunInRange at 0x13d2e9f4 establish the chunked form:

- Bytes 00..7f represent literal characters, with no terminator.
- Bytes 81..bf introduce 1..63 big-endian 16-bit character units.
- Byte 80 introduces a big-endian 16-bit count followed by that many units.
- C0..FF belong to style/control handling; FF also identifies the separate
  format-2 representation in its applicable context. These are unsupported by
  the new plain-text reader, rather than silently discarded.

`build_object_values.plain_text` emits ASCII and short Unicode chunks;
`read_plain_text` also accepts extended counts. Both restrict Unicode to
non-surrogate BMP characters. Styled text and supplementary-plane characters
remain unsupported. These functions operate on object bodies, not complete
frozen records or package files.

A check of imported Text objects across the existing corpus found
**862 byte-identical**, **2
semantically equivalent with different chunk boundaries**, **29 unsupported**.
The text equivalence check uses the new decoder; byte-identical reconstruction
provides independent corpus evidence but does not replace guest execution.
Four added tests cover known bytes, short/extended chunk boundaries, malformed
input, and unsupported characters. **135 research tests pass**.

Graphics.h explicitly defines kOnePixel as 256 and MicronToPixel as
`(short)(((micron)+128)>>8)`. This confirms runtime screen units; conversion of
CompileObjects numeric literals still needs corroboration before automatically
translating all .odef coordinates. Next: construct the sample Scene with verified
coordinate values, assign actual imported/local selectors, and assemble the
remaining package metadata. No newly generated package has been installed yet.

### EmptyPackage object values and reference assignment

`toolchains/mips/build_empty_objects.py` generates five object
value fragments, an imports payload, abbreviated class formats, and a manifest.
It explicitly transcribes
`Samples/EmptyPackage/Objects.odef`; it is not a general source compiler.

The coordinate ambiguity is resolved by **Guide to Development Tools, printed
page 97**, under Pixels and Dot: angle-bracket positions and Dot components are
specified in pixels. Together with SDK Graphics.h's kOnePixel=256, this gives
relativeOrigin `[0, -2048]` and contentSize `[122880, 65536]`. These also agree
with the Viewable prefix observed in an existing corpus Scene. `pixel_units`
accepts exact integer/decimal-string values, checks signed 32-bit bounds, and
rejects fractional internal units instead of inventing compiler rounding rules.

Local selectors reserve 4 for the future cluster and assign 12, 20, 28, 36, 44
to contents, installationList, packageScene, helpForObjects, packageSceneInfo.
Four imported classes receive selectors 1..4; four imported indexicals receive
0x10000004, 0x1000000c, 0x10000014, 0x1000001c. Separate import records associate
each with its actual SystemPublic interface offset, derived from the SDK's
PublicInterface.cdef. These are frozen selectors, not ROM addresses. The class
and locator namespaces are separate.

This work exposed and fixed an import-analysis bug: `resolve_import` previously
used unit stride for every kind. Locator imports require stride eight and
alignment checks; other component kinds retain unit stride. SDK
AddRealMapRange at 0x13cd4654 (especially 0x13cd4694..0x13cd46a8) corroborates
the locator scaling. Existing method-link and Text corpus reports retain their
previous totals after regeneration.

All **26 references** in the generated fixed fields and ObjectLists resolve to
null, a generated local object, or an explicitly imported SDK indexical. The
manifest records each reference, source hashes, field values, and artifact
hashes. The sample omits Scene.superview; this generator explicitly initializes
it to null. Other fields must be supplied exactly; no general implicit-default
policy is assumed.

**139 research tests pass**, including pixel limits, locator range alignment,
the sample Scene byte prefix and flags, list targets and help text. These
artifacts are **not an installable package**: named-object extras, the cluster
root and complete heap/envelope assembly remain. The two names `EmptyPackage`
are recorded as pending rather than silently omitted from a purported package.
Next is encoding those named-object extras and constructing the cluster root,
then validating installation in the SDK-ROM guest without ROM/state patches.

### Static object-name dictionaries

The earlier assumption that subtype-three names require per-object extras was
incorrect. `PersistentCluster_ObjectName` at SDK 0x13c8c470 falls back to the
cluster's pristineNameDictionary at fixed offset 0x38. The named-block header
flag does not imply that a name string follows that object's fixed fields.

`StaticObjectNameDictionary_LookUpObjectName` at 0x13c86710 reads a 16-byte
fixed body: lookup-object selector, TextHeap selector, first locator, locator
count. It indexes the lookup array with `(locator - first_locator) >> 3` and
reads a big-endian halfword. The lookup array uses FFFF for absent names in the
corpus; the named-block flag also matters to runtime name access. Each other
value is an offset in **halfwords**, relative to TextHeap's extra-data start.
TextHeap has a four-byte deletedNamesSize fixed field (zero in this corpus).
Its extra data consists of counted big-endian 16-bit character strings, without
terminators or per-string word alignment. `TextHeap_TextStringAtOffset` at
0x13cbce28 masks the count to 14 bits. The new encoder emits no upper count flags;
the reader rejects flagged strings, deleted-name state, surrogates, malformed
lengths, and offsets that do not identify a string boundary.

`build_object_names.py` constructs the dictionary and backing tables.
Following named dictionary objects in existing frozen packages reproduces **all 32 dictionaries' two
backing bodies byte-for-byte**, covering **810 names**. Duplicate strings remain
separate, matching the original compiler's output.

EmptyPackage now generates **eight object value fragments**: the original five,
plus PristineLookupTable (selector 52), TextHeap (60), and
StaticObjectNameDictionary (68). Its dictionary covers selectors 12 through 44,
with EmptyPackage names for contents and packageScene. Three additional
SystemInternal class imports and abbreviated formats accompany the new objects.
All **29 references** are accounted for. The dictionary still needs to be
connected to a generated cluster's pristineNameDictionary; the standalone
fragments cannot be installed.

**143 tests pass**, including exact dictionary bytes, duplicate/BMP names,
malformed lookup boundaries, and generated sample name lookup. Cluster assembly
remains the next task: packageData/export metadata, cluster flags and page
fields, package identity storage, and the loader's initialization requirements
must be established before calling the resulting file installable. Two corpus
packages use the 104-byte PackageCluster fixed layout without native code; the
other 30 use CodePackageCluster. This offers a code-free reference path for
EmptyPackage, but does not yet establish a complete minimal cluster recipe.

### Cluster reconstruction and Boolean correction

`build_cluster.py` adds explicit cluster-body construction and fixed-field
reading with a reconstruction check. It rejects unmodeled set bits instead of
silently clearing them. It reconstructs **all 32 complete cluster bodies byte-for-byte**: 30
CodePackageCluster bodies and two code-free PackageCluster bodies. The reader
also validates/reconstructs all 32 PackageData fixed bodies.

This exposed a substantive error in the previous fixed-value encoder. SDK
Boolean offsets are MSB-first, whereas ReadBitField's separate shift argument
is LSB-based. Looking only at ReadBitField had missed that conversion.
Scene_AddToHistory at 0x13dad0d4..0x13dad0dc passes byte offset 49 and shift 2;
the SDK field offset is 397 (byte 49, MSB-based bit 5). Therefore the sample's
addToHistory mask is **04**, not 20. Likewise autoActivate at bit 128 is **80**,
not 01; isPackageCluster at bit 1 is **40**, matching every corpus root.
The encoder, tests and generated EmptyPackage fragments have been corrected.
Earlier illustrative fixed-value artifacts should be regenerated with the
corrected encoder; they were never installed in a guest.

PackageCluster has 104 fixed bytes, CodePackageCluster 188. InternalPackageName
at 0x13cd1dbc obtains the extra-data pointer and calls strlen; existing packages
store a NUL-terminated ASCII name followed by zero padding to a four-byte
boundary. The constructor currently supports nonempty ASCII names up to 128
characters, matching the direct runtime path's bound, and requires all fixed
values explicitly. It does not infer page ranges or integration IDs.

The code-free corpus clusters identify the remaining construction dependencies:
pristineNameDictionary (now generated), pristineSharedObjects, PackageData,
PackageContents (now generated), and PackageExportTable. Their PackageData has
null linkingPrefix, references to missing-clique Text/ObjectList objects, and
acclimatized=true. Page ranges vary between packages; firstUncrowdedPageIndex is
FFFFFFFF in these examples. PackageCluster_Init at 0x13cd1a28 can allocate
PackageData if absent during initialization, but this is not proof that the
frozen-package install path permits omitting it. We retain that distinction.

**146 tests pass**. Next: construct the empty export/shared-object tables and
import-status metadata, then connect the cluster root and assemble the frozen
heap. No installable EmptyPackage or guest execution is claimed yet.

### Empty export/shared tables and import-status metadata

`build_package_metadata.py` constructs nine metadata objects from explicit
selectors and SDK-derived fixed layouts. The two code-free packages plus
Translation provide empty-table evidence:

- ObjectValueHashTable has hashEntrySize=8, zero counts/thresholds/free-entry,
  references to a DataList and ObjectList, and extra bytes `0400000100000000`
  (integer-list format, one empty bucket).
- PackageExportTable has the same empty bucket representation, hashEntrySize=12,
  and references to PackageExportHashEntries and CliqueNameTable.
- Empty DataList is `0000000800000000` (stride 8, zero entries). Empty
  PackageExportHashEntries is a zero count word. CliqueNameTable is eight zero
  fixed bytes. Empty reference lists retain `0d000000`.
- PackageData contains a null linkingPrefix, two references to import-status
  Text/ObjectList objects, and acclimatized=true (`80000000` final word).

Validation checks all 32 PackageData objects,
all import-status objects, and only tables whose entryCount is zero. **89
bodies match exactly**: 32 PackageData, 21 empty Text, 21 empty ObjectList,
6 shared-table/backing objects across two packages, and 9 export-table/backing
objects across three packages. **22 differ** because 11 packages contain
nonempty missing-clique Text/List pairs (e.g. SystemConditional, WCPack and
SpellFinder). These are not claimed to match the empty constructors. Supporting
nonempty dependency diagnostics remains separate work.

EmptyPackage imports only SystemPublic/SystemInternal symbols and now generates
**17 fragments with 37 checked references**, including all nine metadata objects.
Metadata class imports are looked up in the appropriate SDK interface and
round-trip through import resolution. Fixed layouts and abbreviated formats
are derived from MagicCap.cx. Three new tests check exact table/bucket bytes,
import-status references, acclimatized bit encoding and invalid selector maps.
**149 tests pass**.

The output is still assembly input: it lacks the root object and final heap.
Next is choosing/validating the new root's page-range and integration fields,
connecting its now-available metadata, emitting the code-free package envelope,
and testing it in an isolated SDK-ROM guest. Corpus-matching empty tables alone
do not establish successful package installation.

### First complete experimental EmptyPackage

`build_empty_package.py` connects a PackageCluster root to the 17 existing
objects and emits the same attribute sequence as the code-free corpus packages:
20 imports, 53 object addressing, 10 abbreviated classes, 60 heap. No code,
function table or native initialization script is emitted. Selectors are 4..140
in steps of eight. Named contents/Scene objects carry the named flag and use
the generated dictionary. Scene extra data contains an empty subview ObjectList.
The package's internal identity is EmptyPackage.

The root uses explicitly listed fixed fields, with source pages 0..0 as a trial,
firstUncrowdedPageIndex=FFFFFFFF, integration ID words 0/1, and
firstCompiledLocator=12. These trial page/ID choices are recorded in the
manifest and do not establish general build-tool allocation rules. The root's
prohibit-writes frozen-header flag matches the corpus root representation.

The default candidate is 1,468 bytes. New assembly checks verify all 18 heap
selectors, attribute order, empty decoded exports, root references and
repeatable output; invalid page ranges are rejected. **151 tests pass**.
See [guest testing](ROSEMARY_ROM_TESTING.md) for the actual installation result, which is
separate from structural parsing and corpus validation.

### Guest validation milestone

The default assembled candidate has now installed through normal PC Link in the
unmodified SDK-ROM guest. It appears in Storeroom, registers a Hallway door,
opens its Scene, and displays the generated help Text. Full commands and the
tested package/ROM hashes are recorded in [guest testing](ROSEMARY_ROM_TESTING.md). This supersedes earlier
statements that no newly generated package had been installed. Native MIPS
code generation/linking remains unvalidated; this sample defines no new classes
or methods. The next step is a minimal native-method sample, retaining this
working code-free package as a baseline.

### Restricted native subclass constructor

`build_native_class.py` now constructs the smallest useful native subclass
representation: one implementation superclass, no own fields, and one object
method. It emits the 12-byte six-halfword prefix, a halfword superclass count
and selector at +12, and a method list at +16 (`8001`, zero skip, then header
`41000000 | operation_selector` and a one-based function ID).

ROM UnlinkedClassWithMethods_ImplementationSuperclasses at 0x13c904ac reads the
first halfword as the superclass-list displacement and reads halfword class
selectors. UnlinkedClassWithInstances_FieldsFormat at 0x13c90150 reads the
halfword at +4; zero means no own field-format entries. Existing method-list
tracing establishes the +2 displacement and function-ID records.

It reconstructs **50 existing classes byte-for-byte** whose layout falls
within this exact subset. Classes
with extra fields, multiple superclasses, other method kinds or different
method-list forms remain outside this constructor.

`toolchains/mips/build_native_leaf.py` compiles `native_leaf.c`
with Clang 18 and extracts one ELF32 big-endian MIPS-I function. It emits
`03e00008 24020001`: `jr ra` with `addiu v0,zero,1` in the delay slot. The
function ignores its receiver, accesses no globals, makes no calls, and has no
text relocations. Extraction rejects undefined symbols, additional allocated
payloads, text relocations, wrong ELF type/architecture, and invalid extents.

The code-free EmptyPackage baseline remains the only guest-tested generated
package. The new method and class still need CodePackageCluster integration,
a defined class selector, its abbreviated layout, function-offset/code records,
and the appropriate initialization script. Then native dispatch must be
observed in the guest; the leaf's successful compilation is not that evidence.

### First native package assembly and failing guest check

`build_native_package.py` assembles the restricted leaf into a complete
code-bearing candidate, preserving the working code-free baseline. It adds
one defined Scene subclass, a CanGoTo import, CodePackageCluster and unlinked
class formats, function-offset/code attributes and a minimal global initializer.
The parser/method linker resolves its single function to the expected eight
code bytes; **158 tests pass**.

The guest receives the package but rejects activation. Watchpoint evidence
localizes the exception to FixUpCodeAddress's method-value bounds check at
0x13e43078..0x13e43080, after attribute reading and entry into class
initialization. See [guest testing](ROSEMARY_ROM_TESTING.md) for the exact candidate hash,
addresses, logs and next diagnostic. No claim of native dispatch is made.

### Reserved function IDs and successful native dispatch

The guest failure trace established that constructor/destructor metadata also
passes through FixUpCodeAddress as function IDs 1 and 2. The initial candidate
provided only one entry, so ID 2 failed validation. Reserve two FFFFFFFF null
offsets and assign the first actual method ID 3. This explains the two leading
null function entries consistently observed in the original code packages;
they are required metadata, not unused user methods.

The corrected candidate subclasses SoftwarePackageContents and overrides
CanGoTo with the compiled eight-byte Boolean leaf. It installs, activates, and
executes through normal package UI dispatch: three hits at RAM 003CCBE4, receiver
00046304, operation selector 10E0. This supersedes the earlier native-dispatch
failure status. Exact hashes, commands and scope are recorded in
[guest testing](ROSEMARY_ROM_TESTING.md). **158 tests
pass**. Next: a native method making an actual ROM call through the correct
transition-vector/global-pointer convention, with guest validation.

## What FrozenDump calls things (checked 2026-09-20)

`MagicDeveloper/Tools/FrozenDump` describes itself as a "Frozen Package
Disassembler". Its strings are the tool's own vocabulary for this format, and
they are quoted here as that and nothing more: they name things, they do not
by themselves say which byte means which. Where they overlap with what the
inspector already reads they agree; the rest is a list of what to look for.

Its attribute table is the one the inspector carries, and closes two questions
about the gaps in it:

| Tag | FrozenDump |
| --- | --- |
| `$1` | Abbreviated Classes |
| `$2` | Import Table |
| `$3` | Defined Component Table |
| `$4` | Out Addressing Table |
| `$5` | Object Addressing Table |
| `$6` | Heap |
| `$7` | Code |
| `$8` | External Function Names |
| `$9` | **Unknown ($9)** |
| `$A` | Global Data Initialization |
| `$B` | Function Offsets |
| `$C`-`$F` | **Unknown ($C)** … **Unknown ($F)** |

`$9` and `$C`-`$F` are unknown *to the SDK's own tool*, so they are unused
rather than something this project has failed to work out.

It also prints a legend of four-character `FixedFormat` codes, which is how a
class says what each word of its fixed part holds:

    bbbb  unstructured bytes        int   Integer
    hh    Halfword, Halfword        dbl1  Doubleword first half
    hbb   Halfword, Byte, Byte      dbl2  Doubleword second half
    bbh   Byte, Byte, Halfword      sptr  Strong pointer
    clas  Class number              wptr  Weak pointer
    oper  Operation number          sobj  Strong object
    clop  Class operation number    wobj  Weak object
    intr  Intrinsic number          end   End sentinel

and heads the abbreviated-class listing `ClassID  NFixedWords  FixedFormat`.
That is the MIPS counterpart of the 68k field descriptors in
[the ObjectMaker notes](OBJECTMAKER_FORMAT.md), and a different table from
them: nothing about one should be assumed from the other.

Finally it names the Data Initialization Script's opcodes, which the SDK
manuals do not document at all: `Reset`, `TargetGlobals (target=PkgGlobals)`,
`TargetCode (target=PkgCode)`, `EndImports`, `EndSpecials`, `StartReplaces`,
`EndReplaces`, `StartAugments`, `EndAugments`, `CopyByte`, `RelocateCode`,
`Class`, `Operation`, `ClassOperation`, `ClassInstanceSize`,
`ClassFieldsOffset`, `CodeOffset`, `PatchedOperationTransitionVector`,
`PatchedClassOperationTransitionVector`, and a script-end sentinel. It carries
`FrozenPackage.cpp`, `FrozenAttributeHeaderFormat.h` and
`FrozenObjectFormat.h` as assertion filenames, and an object header with a
`kFrozenUnattachedKind` and a `kFrozenClassNumberMask`.

Both of the last two groups are now decoded, from FrozenDump's own code --
see below.

## Third-party packages read (checked 2026-09-20)

The inspector was run over every Magic Cap package in the archive that the SDK
did not produce: ten games, seven drivers, CujoChat and two MagicWeb
JavaScript packages. All twenty read, 27 packages across the bundles and 209
records, and every record's attribute tag is one of the eight kinds above that
real software uses -- no `$4` out-addressing, `$8` external function names, or
`$9`.

This was done because the same exercise on the 68k side immediately exposed a
rule that had been read off SDK samples and was not true of shipping software.
Nothing equivalent turned up here.


## FixedFormat and the initialization script, decoded (2026-09-20)

FrozenDump is a PowerPC PEF binary and Ghidra reads it, but only once it is
told what r2 holds: CFM sets it from the main transition vector, which the
loader header points at, and for FrozenDump the TOC sits at data+`0x8000`.
Writing that into the register context takes its referenced strings from a
handful to 154 of 184. The same step on ObjectMaker is described in
[the 68k notes](OBJECTMAKER_FORMAT.md#reading-the-tool) and the
[tool analysis](GHIDRA_CODEWARRIOR_ANALYSIS.md).

### FixedFormat

A class's fixed part is described by **one byte per word**, each indexing this
table -- FrozenDump reads the bytes at `+0x20` of an abbreviated-class record
and prints `table[byte]` for each of the `NFixedWords`:

| Code | Name | Meaning |
| --- | --- | --- |
| 0 | `bbbb` | 4 unstructured bytes |
| 1 | `hh` | Halfword, Halfword |
| 2 | `hbb` | Halfword, Byte, Byte |
| 3 | `bbh` | Byte, Byte, Halfword |
| 4 | `int` | Integer |
| 5 | `dbl1` | Doubleword first half |
| 6 | `dbl2` | Doubleword second half |
| 7 | `sptr` | Strong pointer |
| 8 | `wptr` | Weak pointer |
| 9 | `clas` | Class number |
| 10 | `oper` | Operation number |
| 11 | `clop` | Class operation number |
| 12 | `intr` | Intrinsic number |
| 13 | `sobj` | Strong object |
| 14 | `wobj` | Weak object |
| 15 | `end` | End sentinel |

### The Data Initialization Script

One byte opens each instruction: the **low nibble is the operation** and the
**high nibble says where its operand comes from**.

A high nibble of 0 means a special with no operand, and the low nibble picks
it: 1 `Reset`, 2 `TargetGlobals` (target PkgGlobals), 3 `TargetCode` (target
PkgCode), 5 `EndImports`, 6 `EndSpecials`, 7 `StartReplaces`, 8 `EndReplaces`,
9 `StartAugments`, 10 `EndAugments`. Anything else is an unknown special, in
FrozenDump's own words.

Otherwise the high nibble is the operand encoding: 1 to 12 take the operand
from a small table -- 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24 -- while 13
reads one byte, 14 reads a halfword, and 15 reads a halfword three bytes in.
The low nibble is then the operation:

| Op | Meaning |
| --- | --- |
| 1 | `CopyByte n`, followed by n literal bytes |
| 2 | `Advance n` |
| 4 | `SetByte n` |
| 5 | `SetHalfword n` |
| 6 | `SetWord n` |
| 9 | `RelocateGlobal n` |
| 10 | `RelocateCode n` |
| 12 | `Relocate` |
| 14 | `Relocate2` |
| 15 | `RelocateAddendGlobal n` |

This is the bytecode the SDK manuals describe nowhere. It is read out of the
tool rather than out of any package, so it says what the opcodes are and not
yet what a particular script does with them.
