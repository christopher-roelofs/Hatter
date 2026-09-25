# The 68k package container, as far as it is read

What ObjectMaker wrote for Magic Cap 1.0/1.5, decoded from the fourteen
cookbook examples under `software/68k/extracted` and checked against two real
shipping packages. `toolchains/m68k/` holds the inspector and its
tests; this is what it knows and, as importantly, what it does not.

Nothing here was settled by looking at a number and finding it plausible. The
cookbook ships each example's ObjectMaker definitions and C beside the package
built from them, and the SDK ships its own number tables, so every name below
is something the corpus says rather than something the shape suggested.

## Why this first

The MIPS side went inspector, then empty package, then code, and each step
rested on being able to read what the real tools produced. The 68k side starts
from a better position than MIPS did -- `scripts/test-counter-68k` already
installs the stock Counter package through PC Link, runs it, taps its button
and checks the count against a golden crop -- so a known-good package and a
guest that runs it are both in place. What was missing is being able to say
what is inside one.

## The corpus

Fourteen cookbook examples, which come with the definitions and C they were
built from, and two real third-party packages -- `BastilleR.cap` and
`3PrestoPPP.cap` -- which come with nothing. The cookbook is what anything
here is *derived* from; the two shipping packages are what it is *tested*
against, because everything the cookbook can show was built by one author in
one run of one toolchain.

That was worth doing immediately. The shipping packages are in the `.cap`
distribution envelope rather than raw, and they have no trailing zero word
after their object chain -- which the decode had been treating as a
terminator, on the strength of fourteen examples that all happen to have one.
Real software was rejected until that was fixed.

A third reference is the tool itself. `MagicDeveloper/Tools/ObjectMaker` is
the program that wrote this format, and its own diagnostics confirm the
instance layout outright: *"total size of fields in class %s has been padded
for 32 bit alignment"*, *"object field %s from class %s is not aligned (should
be for speed)"*, and *"can not handle multi-bit bit fields yet"*. It also
names its six dispatchers -- Method, Direct, Inherited, Delegate, Patch and
Extended -- which is where `DirectDispatchList` below came from.

## Layout

A package is a Macintosh file of type `CLUS`, creator `MCAP`: a header, a
chain of object records, then offset tables. A `.cap` wraps one in an
envelope (`MCap`, a name, a tagged `FrozenPackage`); the inspector finds the
cluster inside by the three constant words of its header rather than by
reading an envelope it does not understand.

| Offset | Meaning |
| --- | --- |
| `0x10` | the file's own length |
| `0x14` | where the object chain ends and the trailer begins |
| `0x1c`, `0x20`, `0x24` | `000fffff`, `01c00003`, `00070000` in all fourteen |
| `0x2c` | high half `0100`; low half is `0x34` minus one |
| `0x34` | the highest object id the heap uses |
| `0x44` | the first object record |

The word at `0x2c` is **not** the number of objects and neither is `0x34`.
Counter has 41 records, a highest id of 43 and `0x2c` reading 42; only
Circuits makes the low half and the record count coincide, which is exactly
how a wrong reading of this field would survive being checked against one
example. The inspector reports both raw.

### Object records

    u32 length          including this header
    u16 class number
    u16 tag             0x0088, 0x008a, 0x0188, 0x0288, 0x0388 observed
    u16 flags           0x0000 or 0x0100
    u16 object id
    ...payload...

Records are walked, not indexed: each carries its own length and the chain
runs from `0x44` to the end of the heap. That the walk lands exactly on the
end, in every package, is the evidence that this is the real layout rather
than a shape that fits the first few records.

It lands either on the end itself or on a zero word four bytes short of it.
The fourteen cookbook packages all have that word and the two shipping ones
have none, so reading it as a required terminator -- which is what fourteen
examples suggested -- rejects real software.

Class numbers are the system's, from `ClassNumbers.Def`: 29 is `ObjectList`,
20 is `AddressCard`, 477 is `Code`. A class number with the top bit set is one
the package defines -- Counter's `CounterScene` is `0x8001`, the first class it
declares.

`tag` and `flags` are carried through unread. They take few values and they
clearly mean something; nothing in this corpus says what.

### What is in a record

The payload is the object's fields laid end to end, and which fields those are
is a statement the SDK makes: `DefFiles/*.Def` gives every class, what it
inherits from and the fields it adds, so the layout is the ancestors' fields
followed by its own. `classdefs.py` works this out; `--fields` reads an object
with it.

Sizes are the SDK's too. `Types.Def` states them for its named types; `Dot`
and `PixelDot` are not there but are plain C structs in `Generic.h`, sized the
way the compiler that built these packages sized them. A word in a field typed
by a class is a reference, `0xB0` in the top byte and the object id below it;
an indexical is a word with the top bit set and something else in that byte,
the same form the generated headers push as a literal. Booleans are bits, most
significant first, and a run of them takes as many whole bytes as it needs.

A class the definitions do not carry -- every package-defined class, whose
definitions live in the package's own `.Def` rather than the SDK's -- is left
as bytes, and so is one whose ancestry does not resolve. A field list short by
one ancestor puts every offset after it wrong, silently; it would decode, and
it would be wrong.

Classes that say `uses extra` carry a variable part after the fields. For the
lists it is their elements, and the arithmetic closes exactly: Counter's
`SoftwarePackage` has 72 bytes of fields and a `length` of 32, and its payload
is 200 -- 72 plus 32 references, nothing left over. For `Text`, `OctetString`,
`Image`, `Sound` and `Code` the extra part is bytes rather than a list, and no
field of theirs says how to read it, so the bytes are offered as they are.

Across the fourteen examples, of 1261 objects: 407 read as fields alone, 373
as fields plus a list that accounts for the payload exactly, 356 carry an
extra part that is bytes, 91 are of package-defined classes the SDK cannot
describe, and 34 have a list with bytes left over that is not yet explained.

### The trailer

The first word is the trailer's own length and it runs to the end of the file.
Most of what follows are file offsets with the top bit set. One run of them
lands twelve bytes before each object's id word -- that is, on each object
record -- which is how they were recognised. The rest are reported as read.

## Code

One object of class `Code`, in nine of the fourteen examples. The five without
are not failures: the templates are objects only, and Snake's bulk is a sound
and three images.

Procedures are found by the MacsBug symbol that follows them -- a byte with
the top bit set giving the length, then the name -- which is the name the
sample's own C gave the method. Scanning only `Code` objects matters: sound
and image payloads contain byte sequences that pass for a name followed by
something that passes for a call, and scanning everything invented methods
inside Snake's pictures.

### Calling convention

Calls are `JSR d16(A5)`, and the displacement is the whole identity of the
call. The generated `PackageInterfaces/PackageOperations.h` states these
outright as inline instruction words:

| Vector | Meaning | Registers |
| --- | --- | --- |
| `-6` (`FFFA`) | dispatch | selector in D2, receiver on the stack |
| `-38` (`FFDA`) | inherited | class number in D0, operation in D2 |
| `-48` (`FFD0`) | simple intrinsic | intrinsic number in D0 |
| `-70` (`FFBA`) | delegate | target class in D0, operation in D2 |

A fifth, `-32` (`FFE0`), is used by 2218 of the 3209 operations the device
profile declares against 991 for `FFFA`, and **it is the fast path**. The A5
world is not a table of pointers but of six-byte stubs, and this one is a
routine rather than a jump. Read out of a running guest, with A5 at `0x28E`:

    202f 0004      MOVE.L   4(A7),D0          ; the receiver
    6712           BEQ.S    tail              ; nil -> the general dispatcher
    0800 0019      BTST     #25,D0            ; a tag bit in the reference
    660e           BNE.S    tail              ; tagged -> the general dispatcher
    207c 0004a6f8  MOVEA.L  #$0004A6F8,A0     ; the direct dispatch table
    2070 24fc      MOVEA.L  (...,A0,D2.w),A0  ; indexed by the selector in D2
    4ed0           JMP      (A0)              ; straight into the method
    tail:
    4ef9 0e090088  JMP      $0E090088

If the receiver is a plain object it indexes the table by selector and jumps
to the entry. That can be a native method or an odd encoded accessor address,
handled deliberately by the ROM's address-error handler (see Whitehouse guest
validation below). Otherwise it falls through to `$0E090088`, which is exactly
where `-6` jumps -- `4ef9 0e090088` is the whole of that slot.

That explains what no amount of reading the headers could. It is an
optimisation, not a semantic property, which is why no declared qualifier
predicts it, why the receiver class does not, and why thirty-four operations
change vector between the simulator interfaces and the device ones: what can
take the fast path is a fact about the target's dispatch table. A package's
own operations always take `FFFA`, because they are not in the ROM's table.

The other stubs at that table, for the record: `-70` delegate jumps to
`$0E08FFD2`, `-64` to `$0E08FFAE`, `-38` inherited to `$0E08FFF0`, `-76` to
`$0E08F984`, and `-48` intrinsic and `-58` are both of the form `MOVEA.L
($074C).W,A1; MOVEA.L $06F8(A1),A0; JMP (A0)` with different bases -- an
indirect jump through a table the ROM keeps in low memory.

Operation and intrinsic numbers are named from `OperationNumbers.Def` and
`IntrinsicNumbers.Def`. A selector with the top bit set is the package's own
and no system table can name it.

## Worked example

Counter's three methods, from `inspect_package.py --code`, beside what
`Counter.c` says they do and what `Counter.Def` numbers them:

    CounterScene_AboutToShow
      dispatch   8003 package operation 3     VisitCount(self)
      dispatch   8004 package operation 4     SetVisitCount(self, ...)
      dispatch   8002 package operation 2     UpdateDisplay(self)
      inherited  064d AboutToShow             InheritedAboutToShow(self)
    CounterScene_UpdateDisplay
      dispatch   8003 package operation 3     VisitCount(self)
      intrinsic  0144 IntToString             IntToString(..., &strng)
      dispatch   0032 ReplaceTextWithString   ReplaceTextWithString(iiTextField, strng)

`Counter.Def` numbers `ResetVisitCount` 1, `UpdateDisplay` 2 and the
`VisitCount` attribute 3 with its setter at 4, and the package contains
exactly four `MagicOperation` records to match. The `iiTextField` indexical is
pushed whole as the literal `87832001`.

## The classes a package defines

A package's own classes are `Class` records, and what one holds is the whole
of what ObjectMaker had to write for a `Define Class` -- which makes it the
whole of what anything generating a package would have to write in its place.
Its fields give the class number, the instance size, and counts and offsets
for two tables; the tables and the interface list follow in the extra part.

Those offsets count from **four bytes into the payload**, not from the start
of it. Counter's `implSuperOffset` of 60 and `methodOffset` of 76 both land
exactly on their tables from that base and from no other.

A method entry is four words: the operation, and then either where its code
starts and which `Code` object holds it, or -- for the getter and setter a
`field ..., getter, setter` generates -- the class number and an accessor word
in place of those. Which bit of that accessor word means what is not
established; Counter's getter and setter differ only as `00002000` against
`00001000`.

The interface list follows the method table immediately and begins at class 1,
`Object`. Reading it as though a word came first dropped exactly one entry and
left the total one short of `interfaceCount`, which is how the alignment was
settled.

Counter's, in full:

    class 0x8001 inherits from Scene, instances 88 bytes
      AboutToShow           object 28 +0x18
      package operation 1   object 28 +0x80
      package operation 2   object 28 +0xc2
      package operation 3   generated accessor 00002000
      package operation 4   generated accessor 00001000
      answers to: Object, Linkable, Viewable, HasCount, HasIterator,
                  HasIndexing, Panel, SingleLinkable, Box,
                  BackgroundWithBorder, HasBorder, Scene

`Counter.Def` declares `Define Class CounterScene; inherits from Scene;` with
`ResetVisitCount` 1, `UpdateDisplay` 2, an attribute with a generated getter
and setter, and `overrides AboutToShow`. The record says exactly that.

### Two decodes that agree

The method table and the MacsBug symbols share nothing: the table is stated
outright in the class record, and the symbols are found by pattern in the
code. They have to land in the same places, and for Counter they do, name for
name -- `+0x18` is where the table says `AboutToShow` lives and where the
symbol says `CounterScene_AboutToShow` begins.

Across the fourteen there are 50 class records and 129 method entries with
code; 119 of them land exactly on a symbol-found method, and 48 of the 50
interface counts come out exactly. Where the two disagree the table is the
one to believe -- it is stated, and the symbol scan is a heuristic that can
mis-split a body. That also makes the table the better basis for reading the
code, which is not yet what the inspector does.

### The direct dispatch list

A package's `DirectDispatchList` is a bare run of operation numbers with no
header of its own, and it holds **exactly the system operations the package's
classes override**. Metric's is `IsValidTextRun`, `Deactivate` and `Confirm`,
which are precisely the three system methods its class record carries;
packages that override nothing have an empty one. That is an exact set
equality in fifteen of the sixteen packages, the five empty ones included.

ObjectMaker names a `DirectDispatcher` beside its Method, Inherited, Delegate,
Patch and Extended ones, which is what this list is presumably for: an
override has to be reachable without going back through the dispatch that
found it.

The exception is `3PrestoPPP`, whose list carries one entry, `0x398`, that is
not among its overrides and is not in the CW7 operation table at all -- most
likely an operation from the 1.5 interfaces that this corpus cannot name.

### The field lists

A class's `fieldList` points at a `FieldList`, which is a `StringDictionary`:
`length` fields whose names begin at `firstStringEntry`. Those entries chain.
Taken in order within a package they run 1, then 1 plus the first list's
length, and so on with no gap and no overlap -- 25 lists across the nine
examples that have any, every one of them where the previous one left off.
So the names are one table the whole package shares rather than something
each class carries.

`strings` is an object id, and the object is a `StringList` -- the one table
every field list in the package indexes. The names in it are Pascal strings,
a length byte then the characters, packed end to end and beginning at
`dataOffset` counted from four bytes into the payload: the same base a `Class`
record counts its tables from. Its length is exactly the chain's total in
every package that has one.

An element is `{u16 class number; u8 type; u8 flags}`. The class number is the
class a reference field points at and zero for anything else, which is how
`ringList: ObjectList` reads `001d0700` against `moveList: Object` at
`00010700` -- 29 and 1 being those two classes' numbers. Two `Fixed` fields of
one class carry the *identical* element, which is what says this describes the
type rather than the position.

The type codes were derived rather than assumed: every field the examples
declare was matched to the element written for it, by name, and each declared
type came out as exactly one code.

| Code | Declared as |
| --- | --- |
| `02` | `Boolean` |
| `07` | a reference, to the class in the high half |
| `0b` | `PixelDot` |
| `0e` | `Signed` |
| `13` | `Fixed` |
| `16` | `Unsigned` |
| `17` | `UnsignedShort` |

The only flag the corpus exercises is `20`, `noCopy`: BarChart declares
`sourceCanvas: Object, getter, setter` and `drawingData: Object, getter,
noCopy`, and their elements differ in exactly that bit. `getter` and `setter`
leave no mark here -- they are the generated accessors in the method table
instead.

### Where the fields sit

A class's fields follow its superclass's instances end to end, in the order
declared, each aligned to its own width, with Booleans packed as bits and the
whole rounded up to a multiple of four. The offsets are reported relative to
the inherited part, because that is all this can know: the size of a system
superclass is written down nowhere in the definitions.

What makes it checkable anyway is that `instanceSize` minus what the class
adds has to *be* the superclass's size. That leaves a non-negative whole
number of words for all fifty class records, and the same number every time
two classes inherit the same thing -- for 26 of the 27 system classes the
cookbook inherits from, several of them from classes in different packages
that know nothing of each other. `Object` comes out at 0, which is the check
that the arithmetic is the right way round; `Scene` comes out at 84 from three
classes across two packages, and that is what makes Counter's 88 exactly a
Scene plus one `Unsigned`.

An alternative model where every field takes a whole word gets 22 of the 27
instead, and breaks `Object` and `Scene`.

`Stamp` is the one that does not fit, and is worth writing down rather than
explaining away. In Circuits alone, `Resistor` declares no fields and has
76-byte instances, while `Battery` adds one `Unsigned` and also has 76 --
which no layout where fields take room can produce. Hanoi's `MyStamp`, also
field-free, gives 60. Something about Stamp is not what this model says.

So a package-defined class comes back as the declaration it was compiled
from. Hanoi's, in full, against `Hanoi1.Def`:

    class 0x8003 inherits from package class 1, instances 68 bytes
      field poleNumber   UnsignedShort          at +60+0
      field ringList     reference -> ObjectList at +60+4

    Define Class Pole;
      field poleNumber: UnsignedShort, getter;
      field ringList: ObjectList, getter, setter;

The 60 is MyStamp, which the package defines two objects above; the 4 is the
reference finding its own alignment past a short.

## Worked example: the package object

Counter's `SoftwarePackage`, read with `--fields`, against what its
`Objects.Def` declares:

    +0x000  length                32        32 root-list entries
    +0x014  author                object 1  (AddressCard 101)
    +0x018  installList           object 2  (ObjectList 'Install' 3)
    +0x02c  autoActivate          True      bit 0 of its own byte
    +0x030  citation              object 4  (Citation 10)
    +0x034  publisher             object 1  the same card as author
    +0x044  gotoActionSelector    3         `gotoActionSelector: 3.w`
    +0x046  hidden .. reserved16  False     sixteen bits in two bytes
    +0x048  32 elements, 6 set    [6] [9] [10] lists, [13] indexical

`entry6`, `entry9` and `entry10` are the Standard Places, Objects With Help
and Help On Objects lists, and `entry13` is `iHallway` -- which is where the
definitions say each of them goes. The ids differ from the definitions'
because ObjectMaker renumbers them into the cluster.

## What is not read

- The `tag`'s low byte -- `0x88` or `0x8a`, from bits the writer sets for
  reasons not yet read -- and `flags`, which is one bit the record constructor
  is handed. Its high bits are the padding count, above.
- The three constant header words.
- The extra part of `Text`, `OctetString`, `Image`, `Sound` and `Code`: the
  bytes are reported, their structure is not. The strings in them are plainly
  text, and that is as far as this goes.
- The 34 records whose element count and stride leave bytes over.
- Which bits of a generated accessor's word mean what, and the two interface
  counts out of fifty that do not come out exactly.
- The absolute offset of a field, which needs a system class's instance size.
  Those are not in the definitions; they can be derived where a package
  defines a field-free subclass, and 26 of them are above, but that is a
  by-product rather than a table.
- Why `Stamp` and `PDUServer` do not fit the instance layout. With the two
  shipping packages the corpus is 105 class records and 36 system superclasses;
  34 of those come out at one size and those two do not.
- What the second word of each `ClassList` and `OperationList` entry is; the
  tables themselves are read below.
- Why `ObjectMaker` computes the instance sizes it does for `Stamp`,
  `PDUServer` and `Line`. Reading its code needs PEF relocations applied --
  see "Reading the tool" below.
- Field type codes outside the seven the examples use, and flags other than
  `noCopy`.
- The trailer entries that are not object offsets.
- Whether `Snake` and the templates carry behaviour some other way, or
  genuinely have none.

## Writing it back

`roundtrip.py` rebuilds a package from the decode and diffs it against the
original. Reading a format and understanding it are different claims, and this
is the second one: everything the decode asserts about a byte has to reproduce
that byte.

All sixteen packages rebuild their **container** byte for byte -- header,
every record, the trailer -- so the walk accounts for every byte of the file
with nothing skipped between records and nothing left over.

At the **field** level, not one object comes back different in any package. A
field placed a word out, a Boolean packed from the wrong end, a reference
written without its `0xB0`, an extra part starting in the wrong place: none of
that survives a byte comparison, and none of it is visible from reading alone.

What it also measures is how much is actually claimed. Of 328,048 payload
bytes across the sixteen, 71,366 are accounted for by a decoded field. The
rest is not mystery so much as content:

| Bytes | Class |
| --- | --- |
| 87,960 | `Code` -- 68k machine code, read as methods and call sites rather than as fields |
| 83,456 | `Sound` |
| 36,132 | `Image` |
| 13,996 | `Class` -- read, but by `decode_class_record` rather than as fields |
| 9,792 | `Text` |
| 9,100 | `StringList` -- the name tables, read as strings |
| 4,016 | `ClassList` |
| 3,196 | `OperationList` |

`ClassList` and `OperationList` are read as tables rather than as fields;
see [the runtime lists](#the-runtime-lists) below. Structure-heavy
packages come out high -- Template 83%, Counter 64% -- and media-heavy ones
low, Snake at 10% being a sound and three pictures.

### Instances of the package's own classes

Nothing outside a package can describe these: the SDK has never heard of
`CounterScene`. The package describes them itself, though, and that
description has been read -- so an instance can be decoded with the class's
own account of itself. Hanoi's, for example, is its game state:

    object 36 of package class 4, inherits 84 bytes
      +84  numPoles     3
      +86  numRings     6
      +88  moveList     object 38
    object 27 of package class 2, inherits 60 bytes
      +60  ringNumber        1
      +62  currentPole       1
      +64  currentPosition   1

Three poles, six rings, and each ring with its number and where it sits.

### Two routes to a system class's size

The inherited part of those instances needs the superclass's size, and there
are two ways to it that share nothing: computing the layout from the SDK's
class definitions, or subtracting a package class's own fields from the
`instanceSize` in its record. For 15 of the 16 classes where both can be had,
they agree exactly -- `Scene` is 84 both ways, `Object` is 0 both ways, and so
are `Box`, `Button`, `Card`, `Coupon`, `Form`, `GadgetWindow`, `NoteCard`,
`RestrictedField`, `Rule`, `Shape`, `ShapeTool`, `TextField` and
`ChooseableTool`.

`Line` is the exception at 72 against 80, alongside the `Stamp` and
`PDUServer` anomalies already on the record. Two explanations are now ruled
out for those: every interface profile in the archive -- 1.0, 1.5 and
Universal -- gives the same sizes, so it is not a version difference; and the
subclasses concerned mix in nothing and use no extra, so it is not a missed
mixin. Whatever it is, it is something the ROM or ObjectMaker's own code
knows and the definitions do not say.


## The runtime lists

`Context.Def` declares what the ROM is handed when a package starts:

    SetUpContextRuntime(classList: ClassList; operationList: OperationList;
                        intrinsicList: IntrinsicList;
                        directDispatchList: DirectDispatchList;
                        rootList: RootList; globalsSize: Unsigned)

which says what the four lists a package carries are for, and each turns out
to hold exactly what its name claims.

A **ClassList** is four header words -- the entry count twice, a zero, and
`0x8000` -- then four words an entry, and its references are the package's own
`Class` records and nothing else. An **OperationList** is two header words and
two an entry, referencing only `MagicOperation` records. The arithmetic closes
on every package in the corpus, which is what says those entry sizes are
right.

Both are sparse rather than dense: BarChart's operation table has 66 entries
holding eight references, so an entry count is not a count of operations. What
the other word of each entry holds is not read -- it is a different number for
each entry, and a key or a hash is a guess rather than a reading.

An **IntrinsicList** is two zero words in every package here, none of which
declares an intrinsic.

## Reading the tool

`MagicDeveloper/Tools/ObjectMaker` is a PowerPC PEF binary rather than 68k, and
its data section -- where every diagnostic string lives -- is pattern
compressed, which is why `strings` recovers those messages only in fragments
with opcode bytes between them. `pef.py` unpacks it properly: the data section
comes out at exactly the 61,728 bytes the header claims, and the messages read
cleanly.

Ghidra reads it properly. Its PEF loader takes the binary, applies the 478
data relocations, finds 612 functions and decompiles them to readable
pseudo-C. What it cannot guess is r2: every one of the 1600 table-of-contents
accesses is `lwz rN,disp(r2)`, and CFM sets r2 from the main transition
vector rather than from anything in the instruction stream. That vector is in
the file -- the loader header's `mainSection`/`mainOffset` name a pair of
words whose second is the TOC offset, data+`0x694` here. Writing that into
Ghidra's register context and re-analysing takes the referenced strings from
17 to **589 of 956**. `toolchains/m68k/ghidra/` has the scripts.

With that, the padding warning leads to `FUN_100043a8`, where a class is
finished off, and it confirms the instance layout from the writer's side: a
pending bit count is flushed to a whole byte, then the size is rounded up to a
multiple of four. That is the model derived from the packages, stated by the
tool that wrote them.

It also keeps **two** size counters per class rather than one, at `+0x12` and
`+0x16` of its own class structure, each with its own pending-bit count. What
the second area is for is not established.

### Stamp, explained

`Stamp`, `PDUServer` and `Line` looked like classes whose instance sizes did
not add up. They were not: the super list was being read wrong.

Each implementation superclass takes a **sixteen-byte entry**, not a word --
the method table begins exactly sixteen times `implSuperCount` past the super
list, in all 105 class records. Read as words, one entry came out as a class
number followed by three zeroes, so a class with four implementation parents
looked like a class with one parent and three blanks.

Read properly, Circuits' `Resistor` inherits from `Stamp` *and* three of the
package's own classes. And **a class's instance is every implementation
parent's instance plus its own fields**:

    Resistor      Stamp 60 + 8 + 4 + 4 + no fields      = 76
    Battery       Stamp 60 + 8 + 4 + one Unsigned       = 76
    LightBulb     Stamp 60 + 8 + 4 + 4 + 8 of its own   = 84
    CircuitSwitch Stamp 60 + 8 + 4 + 12 of its own      = 84

With that, all 33 system superclasses the corpus inherits from derive one
size each and none disagrees. `Stamp` comes out at 60 and `Line` at 72 --
exactly what their `.Def` layouts compute, which is the check that closes it.

The earlier note here said the sizes ran four bytes per `implSuperCount`
entry above what the fields required. That correlation was real but
accidental: it was counting the entries of a table being read at the wrong
stride.

### The field lists

A class's `fieldList` points at a `FieldList`, which is a `StringDictionary`:
`length` fields whose names begin at `firstStringEntry`. Those entries chain.
Taken in order within a package they run 1, then 1 plus the first list's
length, and so on with no gap and no overlap -- 25 lists across the nine
examples that have any, every one of them where the previous one left off.
So the names are one table the whole package shares rather than something
each class carries.

`strings` is an object id, and the object is a `StringList` -- the one table
every field list in the package indexes. The names in it are Pascal strings,
a length byte then the characters, packed end to end and beginning at
`dataOffset` counted from four bytes into the payload: the same base a `Class`
record counts its tables from. Its length is exactly the chain's total in
every package that has one.

An element is `{u16 class number; u8 type; u8 flags}`. The class number is the
class a reference field points at and zero for anything else, which is how
`ringList: ObjectList` reads `001d0700` against `moveList: Object` at
`00010700` -- 29 and 1 being those two classes' numbers. Two `Fixed` fields of
one class carry the *identical* element, which is what says this describes the
type rather than the position.

The type codes were derived rather than assumed: every field the examples
declare was matched to the element written for it, by name, and each declared
type came out as exactly one code.

| Code | Declared as |
| --- | --- |
| `02` | `Boolean` |
| `07` | a reference, to the class in the high half |
| `0b` | `PixelDot` |
| `0e` | `Signed` |
| `13` | `Fixed` |
| `16` | `Unsigned` |
| `17` | `UnsignedShort` |

The only flag the corpus exercises is `20`, `noCopy`: BarChart declares
`sourceCanvas: Object, getter, setter` and `drawingData: Object, getter,
noCopy`, and their elements differ in exactly that bit. `getter` and `setter`
leave no mark here -- they are the generated accessors in the method table
instead.

### Where the fields sit

A class's fields follow its superclass's instances end to end, in the order
declared, each aligned to its own width, with Booleans packed as bits and the
whole rounded up to a multiple of four. The offsets are reported relative to
the inherited part, because that is all this can know: the size of a system
superclass is written down nowhere in the definitions.

What makes it checkable anyway is that `instanceSize` minus what the class
adds has to *be* the superclass's size. That leaves a non-negative whole
number of words for all fifty class records, and the same number every time
two classes inherit the same thing -- for 26 of the 27 system classes the
cookbook inherits from, several of them from classes in different packages
that know nothing of each other. `Object` comes out at 0, which is the check
that the arithmetic is the right way round; `Scene` comes out at 84 from three
classes across two packages, and that is what makes Counter's 88 exactly a
Scene plus one `Unsigned`.

An alternative model where every field takes a whole word gets 22 of the 27
instead, and breaks `Object` and `Scene`.

`Stamp` is the one that does not fit, and is worth writing down rather than
explaining away. In Circuits alone, `Resistor` declares no fields and has
76-byte instances, while `Battery` adds one `Unsigned` and also has 76 --
which no layout where fields take room can produce. Hanoi's `MyStamp`, also
field-free, gives 60. Something about Stamp is not what this model says.

So a package-defined class comes back as the declaration it was compiled
from. Hanoi's, in full, against `Hanoi1.Def`:

    class 0x8003 inherits from package class 1, instances 68 bytes
      field poleNumber   UnsignedShort          at +60+0
      field ringList     reference -> ObjectList at +60+4

    Define Class Pole;
      field poleNumber: UnsignedShort, getter;
      field ringList: ObjectList, getter, setter;

The 60 is MyStamp, which the package defines two objects above; the 4 is the
reference finding its own alignment past a short.

## Worked example: the package object

Counter's `SoftwarePackage`, read with `--fields`, against what its
`Objects.Def` declares:

    +0x000  length                32        32 root-list entries
    +0x014  author                object 1  (AddressCard 101)
    +0x018  installList           object 2  (ObjectList 'Install' 3)
    +0x02c  autoActivate          True      bit 0 of its own byte
    +0x030  citation              object 4  (Citation 10)
    +0x034  publisher             object 1  the same card as author
    +0x044  gotoActionSelector    3         `gotoActionSelector: 3.w`
    +0x046  hidden .. reserved16  False     sixteen bits in two bytes
    +0x048  32 elements, 6 set    [6] [9] [10] lists, [13] indexical

`entry6`, `entry9` and `entry10` are the Standard Places, Objects With Help
and Help On Objects lists, and `entry13` is `iHallway` -- which is where the
definitions say each of them goes. The ids differ from the definitions'
because ObjectMaker renumbers them into the cluster.

## What is not read

- The `tag`'s low byte -- `0x88` or `0x8a`, from bits the writer sets for
  reasons not yet read -- and `flags`, which is one bit the record constructor
  is handed. Its high bits are the padding count, above.
- The three constant header words.
- The extra part of `Text`, `OctetString`, `Image`, `Sound` and `Code`: the
  bytes are reported, their structure is not. The strings in them are plainly
  text, and that is as far as this goes.
- The 34 records whose element count and stride leave bytes over.
- Which bits of a generated accessor's word mean what, and the two interface
  counts out of fifty that do not come out exactly.
- The absolute offset of a field, which needs a system class's instance size.
  Those are not in the definitions; they can be derived where a package
  defines a field-free subclass, and 26 of them are above, but that is a
  by-product rather than a table.
- Why `Stamp` and `PDUServer` do not fit the instance layout. With the two
  shipping packages the corpus is 105 class records and 36 system superclasses;
  34 of those come out at one size and those two do not.
- What the second word of each `ClassList` and `OperationList` entry is; the
  tables themselves are read below.
- Why `ObjectMaker` computes the instance sizes it does for `Stamp`,
  `PDUServer` and `Line`. Reading its code needs PEF relocations applied --
  see "Reading the tool" below.
- Field type codes outside the seven the examples use, and flags other than
  `noCopy`.
- The trailer entries that are not object offsets.
- Whether `Snake` and the templates carry behaviour some other way, or
  genuinely have none.

## Writing it back

`roundtrip.py` rebuilds a package from the decode and diffs it against the
original. Reading a format and understanding it are different claims, and this
is the second one: everything the decode asserts about a byte has to reproduce
that byte.

All sixteen packages rebuild their **container** byte for byte -- header,
every record, the trailer -- so the walk accounts for every byte of the file
with nothing skipped between records and nothing left over.

At the **field** level, not one object comes back different in any package. A
field placed a word out, a Boolean packed from the wrong end, a reference
written without its `0xB0`, an extra part starting in the wrong place: none of
that survives a byte comparison, and none of it is visible from reading alone.

What it also measures is how much is actually claimed. Of 328,048 payload
bytes across the sixteen, 71,366 are accounted for by a decoded field. The
rest is not mystery so much as content:

| Bytes | Class |
| --- | --- |
| 87,960 | `Code` -- 68k machine code, read as methods and call sites rather than as fields |
| 83,456 | `Sound` |
| 36,132 | `Image` |
| 13,996 | `Class` -- read, but by `decode_class_record` rather than as fields |
| 9,792 | `Text` |
| 9,100 | `StringList` -- the name tables, read as strings |
| 4,016 | `ClassList` |
| 3,196 | `OperationList` |

`ClassList` and `OperationList` are read as tables rather than as fields;
see [the runtime lists](#the-runtime-lists) below. Structure-heavy
packages come out high -- Template 83%, Counter 64% -- and media-heavy ones
low, Snake at 10% being a sound and three pictures.

### Instances of the package's own classes

Nothing outside a package can describe these: the SDK has never heard of
`CounterScene`. The package describes them itself, though, and that
description has been read -- so an instance can be decoded with the class's
own account of itself. Hanoi's, for example, is its game state:

    object 36 of package class 4, inherits 84 bytes
      +84  numPoles     3
      +86  numRings     6
      +88  moveList     object 38
    object 27 of package class 2, inherits 60 bytes
      +60  ringNumber        1
      +62  currentPole       1
      +64  currentPosition   1

Three poles, six rings, and each ring with its number and where it sits.

### Two routes to a system class's size

The inherited part of those instances needs the superclass's size, and there
are two ways to it that share nothing: computing the layout from the SDK's
class definitions, or subtracting a package class's own fields from the
`instanceSize` in its record. For 15 of the 16 classes where both can be had,
they agree exactly -- `Scene` is 84 both ways, `Object` is 0 both ways, and so
are `Box`, `Button`, `Card`, `Coupon`, `Form`, `GadgetWindow`, `NoteCard`,
`RestrictedField`, `Rule`, `Shape`, `ShapeTool`, `TextField` and
`ChooseableTool`.

`Line` is the exception at 72 against 80, alongside the `Stamp` and
`PDUServer` anomalies already on the record. Two explanations are now ruled
out for those: every interface profile in the archive -- 1.0, 1.5 and
Universal -- gives the same sizes, so it is not a version difference; and the
subclasses concerned mix in nothing and use no extra, so it is not a missed
mixin. Whatever it is, it is something the ROM or ObjectMaker's own code
knows and the definitions do not say.


## The runtime lists

`Context.Def` declares what the ROM is handed when a package starts:

    SetUpContextRuntime(classList: ClassList; operationList: OperationList;
                        intrinsicList: IntrinsicList;
                        directDispatchList: DirectDispatchList;
                        rootList: RootList; globalsSize: Unsigned)

which says what the four lists a package carries are for, and each turns out
to hold exactly what its name claims.

A **ClassList** is four header words -- the entry count twice, a zero, and
`0x8000` -- then four words an entry, and its references are the package's own
`Class` records and nothing else. An **OperationList** is two header words and
two an entry, referencing only `MagicOperation` records. The arithmetic closes
on every package in the corpus, which is what says those entry sizes are
right.

Both are sparse rather than dense: BarChart's operation table has 66 entries
holding eight references, so an entry count is not a count of operations. What
the other word of each entry holds is not read -- it is a different number for
each entry, and a key or a hash is a guess rather than a reading.

An **IntrinsicList** is two zero words in every package here, none of which
declares an intrinsic.

## Reading the tool

`MagicDeveloper/Tools/ObjectMaker` is a PowerPC PEF binary rather than 68k, and
its data section -- where every diagnostic string lives -- is pattern
compressed, which is why `strings` recovers those messages only in fragments
with opcode bytes between them. `pef.py` unpacks it properly: the data section
comes out at exactly the 61,728 bytes the header claims, and the messages read
cleanly.

Ghidra reads it properly. Its PEF loader takes the binary, applies the 478
data relocations, finds 612 functions and decompiles them to readable
pseudo-C. What it cannot guess is r2: every one of the 1600 table-of-contents
accesses is `lwz rN,disp(r2)`, and CFM sets r2 from the main transition
vector rather than from anything in the instruction stream. That vector is in
the file -- the loader header's `mainSection`/`mainOffset` name a pair of
words whose second is the TOC offset, data+`0x694` here. Writing that into
Ghidra's register context and re-analysing takes the referenced strings from
17 to **589 of 956**. `toolchains/m68k/ghidra/` has the scripts.

With that, the padding warning leads to `FUN_100043a8`, where a class is
finished off, and it confirms the instance layout from the writer's side: a
pending bit count is flushed to a whole byte, then the size is rounded up to a
multiple of four. That is the model derived from the packages, stated by the
tool that wrote them.

It also keeps **two** size counters per class rather than one, at `+0x12` and
`+0x16` of its own class structure, each with its own pending-bit count. What
the second area is for is not established.

### Stamp, again

Settled, and not the way this section first guessed -- see
[Stamp, explained](#stamp-explained) above. The super list is read sixteen
bytes to an entry, a class's instance is the sum of all its implementation
parents' instances plus its own fields, and with that every system superclass
in the corpus derives one size.

## Writing one

`write_package.py` emits a cluster. Everything in it is computed from the
objects it is handed -- each record's length and the padding that rounds it,
the heap end, the id table and the free list threaded through it, the header
words, the total -- rather than copied from anywhere, because a writer that
copies what it does not understand produces a file that works until something
changes.

### The trailer, fully read

What the round-trip left unexplained is now the thing that makes a writer
possible. The trailer is an **object table indexed by id**:

    u32 length            of the trailer, in bytes
    u32 0xffff0088        the same in every package
    u32 0
    u32 first free slot   as an id times four, or 0
    u32 last free slot    likewise
    u32 slot[1..highest]  0x80000000 | the record's offset

A slot for an id no object uses is not empty: it holds the next free id times
four, and the two header words are the head and tail of that chain. Counter's
ids 27 and 41 are free, its header words are 164 and 108 -- 41 and 27 times
four -- and slot 41 holds 108 while slot 27 holds zero. Every package agrees,
including the one with no free ids at all, whose head and tail are both zero.

That is why the trailer is exactly five words plus one per id, in every
package, which is the arithmetic that first suggested it.

### What it proves

All sixteen packages, read and handed straight back, come out **byte for
byte identical**. Nothing is carried across except the bits not yet
understood -- the tag's low byte and the `flags` word, which are passed
through rather than invented.

Then the real test. Counter's help text is a plain NUL-terminated string;
replacing it with a longer one moves every record after it, changes the heap
end, the id table, and the total. The result was installed into a PIC-2000
through PC Link, opened, and tapped four times:

    framebuffer 480x320, count crop sha256 cde4a1fd...
    matches the golden count of 1

-- the same crop hash `scripts/test-counter-68k` checks the stock package
against. A package this project generated installs and runs, and counts.


### Building a record rather than copying one

Reproducing a package needs only its bytes; making a different one needs to
be able to construct a record from what it is meant to contain.
`encode_fields` is the inverse of the decoder -- values into their offsets,
Booleans into their bits, a list's elements after the fixed part, starting
from zeros so that anything the layout does not describe stays zero -- and
`make_object` takes a class name and a dictionary of field values.

Of the 1822 objects in the corpus, **1180 rebuild exactly** from the values
read out of them, and the packages still emit identically with those
constructed payloads in place of the originals. The 642 that do not are the
classes whose variable part is content rather than structure -- `Text`,
`Image`, `Sound`, `Code`, `OctetString`, `StringList` -- together with
`Class`, `ClassList` and `OperationList`, whose tables this reads by other
means. A writer hands those their bytes, which is what they are.

### The records that describe a package's own classes

All three are written now.

A **string table** is its fields and then the names, Pascal strings end to
end, with `dataOffset` the fixed part less four. The only thing not computed
is `extents`, a Buffer reference that is nil in every table here below about
a hundred names and present in the three largest, so it is taken rather than
assumed. All 32 rebuild byte for byte.

A **field list** is how many fields, which object holds their names, where
in it they start, and one four-byte descriptor each. All 58 rebuild.

A **class record** is its fields and then three tables, in order, running to
the end of the payload: the superclasses at sixteen bytes each -- a class
number and twelve zero bytes, in all 124 of them -- then the methods at
sixteen bytes each, then the interface list. `implSuperOffset` is the fixed
part less four and the method table starts sixteen bytes per superclass after
that, so both offsets the record carries are computed rather than copied. All
105 rebuild.

With the value-level encoder for ordinary objects, **1310 of the corpus's
records are generated rather than copied** -- 105 class records, 58 field
lists, 32 string tables and 1115 ordinary objects -- and all sixteen packages
still emit byte for byte identical. What is still carried as bytes is content:
code, images, sounds and text.


### A package from a description

`build_from_spec` takes a list of what each object is and holds -- a class
name, its field values, a list's elements, or the bytes for a record that is
content -- and emits the package. Nothing is parsed and nothing is copied.

    [{'id': 2, 'class': 'ObjectList', 'values': {'length': 1},
      'elements': [0xB000000C]},
     {'id': 14, 'class': 'Text', 'bytes': b'About it\0'}]

Described that way, all sixteen packages come out identical, with 1179 of
their objects given as a class and values rather than as bytes. Template --
the smallest, 29 objects and no code -- describes 24 of its 29 that way.

What is left is not the emitting but the describing. Something has to decide
which objects a package needs and what goes in them, which is what
ObjectMaker's `.Def` files say and what `build_sample.py` does on the MIPS
side. The formats are all readable and writable now; the front end is not
written.

## Reading the definitions

`objects_def.py` reads an example's `Objects.Def` -- the file that says what
objects a package contains -- and turns it into the description
`build_from_spec` takes. It is the front end, and it is the part that decides
*what* rather than *how*.

The syntax is small but the values are not obvious, and each was settled
against what the package it compiled to actually carries:

- A reference, `(Telename 2)`, is to the instance the file numbers 2. Those
  numbers are the file's own; ObjectMaker renumbers as it writes and so does
  this.
- An indexical can be written `{60,1}`, which is `MakeIndexical(60,1)` from
  `Generic.h` -- four flag bits coming to `0x83000000`, the list shifted up
  thirteen, then the entry. Template's `NameCard` carries `0x83078001` for
  exactly that, and `iHallway`, `MakeIndexical(40,7)`, is the `0x83050007`
  its package holds.
- A point, `<480.0,256.0>`, is a `Dot`: two thirty-two bit numbers with eight
  fractional bits, so `0x0001E000 0x00010000`.
- A list writes its contents as repeated `entry:` lines; a package numbers
  them, `entry13:` being the thirteenth element of the list it is.
- A long string is several quoted pieces, usually with a backslash between
  them, sometimes just one after another.
- `{{26}}` is **not** `MakeFlatIndexical`, though `Generic.h` defines that
  and it looks like the obvious reading. It is `MakePackageIndexical(26, 0)`
  -- entry 26 of the package's own list -- with one more bit, 23, above the
  list field. All eight `{{n}}` in the cookbook sources carry that bit in the
  packages they compiled to, and the flat form appears in none of them.
- Angle brackets and a bare decimal are scaled differently, and the brackets
  are what say which. `<15.0>` is a coordinate, eight fractional bits, and
  StackTemplateWithIndex holds 3840 for it. `22254.54546` is a `Fixed`,
  sixteen fractional bits, and Snake's rattle holds `0x56EE8BA3` -- 22254 and
  35747/65536 -- for its sample rate.
- Two plain numbers, `17,31`, are a `PixelDot`: whole pixels, sixteen bits
  each, which is how an `Image` writes its size and its centre.
- Hex is written `$ 0046 1940`, and runs longer than a line are broken into
  several `$` pieces with a backslash between them. A single word may be
  written that way too, as a list element.
- A list may say how wide its elements are. Snake's behaviour speeds declare
  `stride: 8` and write sixteen hex digits an element.
- A negative is a bit pattern, not a sign: `color: -1` is `ffffffff`.
- **A semicolon does not always end an assignment.** Snake's help text
  contains "and walk around; sometimes it will sleep", and a reader that
  stops at the first semicolon writes a string 52 bytes shorter than the file
  asked for and says nothing about it. Values are scanned with the quoting
  taken into account rather than matched to the next `;`.

Five of the fourteen examples declare no classes of their own, so they need
no compiled code, and all five build. Four come out at **exactly** the size
ObjectMaker produced with every record byte for byte identical bar the two it
stamps -- the package, which carries the build's date and time, and the boot
record, whose checksum covers it. Template, TemplateWithButtons, StackTemplate
and Snake all do that; Snake is 30,244 bytes of sound, images and text.

The fifth, StackTemplateWithIndex, is short by one record: `ContentListView`
is not among the SDK's definition files, so eight of the fields its instance
assigns have no offset to go to. The builder says so rather than quietly
emitting a short record:

    object 22: no layout for flags1, flags2, key1, key2, offset1, offset2, type1, type2

The other nine examples need a `Code` object, which means CPU32 code
generation, and that is the next piece of work rather than a gap in the
container.

### What is still missing

Nine of Template's twenty-nine objects are not in any definition file;
ObjectMaker adds them:

| Count | What |
| --- | --- |
| 3 | `ClassList`, `OperationList`, `IntrinsicList` -- all empty here, since the package has no code |
| 2 | a `StringList` of the names its instances are given, and an empty one |
| 1 | a `StringDictionary` over those names |
| 1 | a `PackageBoot` record |
| 2 | two `ObjectList`s, one of them the 108-entry root list |

Most of that is already readable and writable. The three lists are empty in a
code-free package, the string tables are written elsewhere in these notes, and
the **boot record names its own fields**: `globalsSize`, references to the
class, operation, intrinsic and direct-dispatch lists, the `SoftwarePackage`
itself, a `loadList`, and a `clusterCRC`. Template's holds 0, the three lists,
nil, its package, its load list, and 48984.

Both of the things that stood in the way are settled.

**The cluster CRC is not a CRC.** It is the bytes of the heap added up,
leaving out the boot record's own payload -- which has to be left out, since
the number is stored in it. That is why no polynomial matched: CCITT, IBM and
DNP were all tried over four ranges in both bit orders from both initial
values, along with CRC-32 and a plain sum of everything. A sum of everything
*except the boot payload* reproduces the stored value for all sixteen
packages.

**The root list is indexed by the definition file's own instance numbers.**
Template declares `Instance NameCard 100` and slot 100 of its 108-entry list
holds that NameCard; `Instance Citation 10` sits at slot 10. The list is as
long as the highest number any instance is given -- 108 for Template, which
is why that number looked arbitrary. All twenty of Template's line up, and so
do ten of the fourteen examples exactly; the other four declare instances
across several definition files while only `Objects.Def` was read, and
nothing they declare is ever *missing* from the list.

Beside it, the `StringDictionary` is the named instances: nine names for
Template, each with the id of the object that carries it.

## Building an example

`build_example.py <directory>` reads an example's `Objects.Def` and writes a
package. It adds the nine objects the definitions do not declare -- the root
list, the load list, the three component lists, two string tables, the
dictionary over them, and the boot record -- computes the checksum over the
records once they are laid out, and points the package's element 24 at its
root list.

For Template it produces 29 objects of exactly the classes ObjectMaker
produced, 1944 bytes against its 1980. It is not the same file: the ids are
assigned here rather than by ObjectMaker, and the stock package's name table
holds a name no definition file in that directory mentions.

**What was checked in the guest.** The package transfers through PC Link and
its contents reach guest memory: built with a marker in place of a phrase of
its help text, that marker is in the guest's state afterwards, and the install
log carries the same six address errors every install here does, stock ones
included.

**What was not, and this matters.** A built package **does not open**. Resumed
from its install state and tapped the way Counter is, the stock Template
redraws the screen -- 66,708 pixels change -- while a built one leaves it
exactly as the install left it. So a package this builds installs and unpacks
but does not activate.

That the install-time screenshot is identical for every package, stock ones
included, is worth recording: it shows the Storeroom mid-transfer and says
nothing about whether anything installed. Comparing those was the first thing
tried and it proved nothing.

Three things have been ruled in or out since:

- **Flags are not load-bearing.** Seventeen of Template's twenty-nine records
  carry `0x0100`. Rebuilt with every one of them zeroed and nothing else
  changed, it still opens and draws the identical screen.
- **The name table was wrong and is now right.** A package's string table is
  its named objects *in object-id order*, plus one name no definition file
  mentions: the root list is called `Reference Numbers List`. Template and
  Counter both agree. Fixing it did not make a built package open.
- **A name is a bit in the record.** Nine of Template's records carry `0x8a`
  in the tag rather than `0x88`, and those nine are exactly the nine objects
  in its name table -- which is the `|2` the writer applies when it is given
  a name.

## Why a built package would not open

Two words of the header, and nothing else. Every package has `0000ffff` at
`0x30` and its highest object id a second time at `0x3c`; the writer set
neither, because `roundtrip.py` passes a package's own header words straight
back and so never needed them. A build from definitions has no package to
copy them from, so both came out zero, and a cluster with them zero installs
-- the transfer completes, the Storeroom reports no error -- and then never
activates. Filling them in is the whole fix:

    struct.pack_into('>I', header, 0x30, 0x0000FFFF)
    struct.pack_into('>I', header, 0x3c, highest)

Template built from `Objects.Def` now installs, puts its door in the Hallway,
and opens its scene, and every one of those screens is byte for byte the
screen the package ObjectMaker built produces from the same input.
`scripts/test-template-68k` does that walk against both and requires them to
agree. Twenty-seven of the twenty-nine records come out byte-identical as
well; the two that do not are the package, which carries the date and time of
the build, and the boot record, whose checksum covers it.

**Two earlier conclusions were wrong, and this is how.** Both renumbering
experiments left the `clusterCRC` stale -- the renumbering rewrote references
and the checksum was never recomputed over the new bytes -- so what they
measured was a bad checksum, not ids. "Object ids are load-bearing" was not
established by them and is withdrawn: a build with ids nothing like
ObjectMaker's opens perfectly well once the header words are there. What the
corrected experiment does show is that the checksum is verified before a
package will open, which is worth knowing on its own.

Coverage diffing never isolated any of this. At 256-byte granularity the
working and failing runs differ only in short RAM stubs and not at all in
ROM, so the instrument said the ROM walks the same path either way -- true,
and useless, because the difference was in what that path read.

## How ObjectMaker numbers objects

Not needed to make a package open, as it turns out, but worked out on the way
there and worth having, because it is what lets a build come out byte for
byte like ObjectMaker's.

Ids are neither the numbers a definition file uses nor the order it declares
things in. **An object is numbered when something first refers to it.** Walk
the declarations in order; for each, give the next id to each instance it
names, the first time that instance is named. Template's package is declared
first, so its `author`, `installList`, `receivers`, `citation` and its three
list entries become ids 1 to 7; then `Citation 10` is walked and its `title`
and `author` become 8 and 9; then `Telename 2` and its two octet strings
become 10 and 11; and so to 19.

Nothing refers to a `SoftwarePackage`, so the walk never numbers it. It is
numbered by the root list, which is built next and whose first slot holds it.

This reproduces every id in thirteen of the fourteen cookbook packages
exactly -- 19 of 19 in Template, 127 in BizNote, 146 in Whitehouse -- where
the examples built from several definition files are concatenated in the
order their project file lists them. The fourteenth, Circuits, agrees for 110
and then slips; it is also the one example carrying a definition file that
its project does not list.

After the declared objects the order is fixed, and all fourteen have it:

    root list          the instances at the slots their own numbers name
    package            numbered here, by the root list that refers to it
    string list        the empty one
    (one free id)      an object made and dropped while building
    code, classes, field lists, operations   only in a package with code
    class list
    operation list
    direct dispatch list                     only in a package with code
    intrinsic list
    load list
    string list        the names
    (one free id)      or, where the name table is long, a Buffer
    string dictionary
    package boot



## Towards the examples that carry code

Nine of the fourteen declare classes of their own. Their instances already
lay out -- an example declares a class in the same syntax the SDK does, so
`Definitions.add` reads it -- and Counter's scene works out to 88 bytes,
which is what its package says. What is left is the records that *describe*
that code, and the code itself.

### A package's own operation numbers

Not what they look like. Counter declares `Operation ResetVisitCount 1;` at
the top of its definition file and gets 1, so the numbers seem to be the
file's -- but Metric declares its operations inside the class body with no
numbers at all and still gets 1 and 2. ObjectMaker numbers them itself:

- Each `operation`, `attribute` or `intrinsic` a class declares takes the
  next number, top bit set, walking the class bodies in order.
- An **attribute reserves two**, the second for its setter, whether or not a
  setter is exported. Hanoi's read-only `RingNumber` takes 1, exports no
  setter, and the next attribute starts at 3.
- Intrinsics are numbered in a space of their own, also from one.
- A top-level `Operation Name N;` fixes that name's number, but only if a
  class actually declares it. BarChart writes `Attribute SouceCanvas 50;`
  with the `r` missing from Source; nothing declares that, so ObjectMaker
  drops it and numbers the real `SourceCanvas` 1.

`classdefs.package_numbers` does this, and it reproduces
`PackageOperationNumbers.h` -- ObjectMaker's own output, so it says exactly
what it chose -- for five of the nine, which is every example built from a
single definition file. The four that differ are multi-file and differ in
which order their files are read, not in the rule.

### What a class record needs, and what is now derivable

Counter's decodes completely:

    implSuper   00000179 and twelve zero bytes -- Scene, one entry
    methods     0000064d 00000018 00000000 b000001c   AboutToShow, overridden
                80000001 00000080 00000000 b000001c   ResetVisitCount
                80000002 000000c2 00000000 b000001c   UpdateDisplay
                80000003 00008001 00002000 00000000   VisitCount, a getter
                80000004 00008001 00001000 00000000   SetVisitCount
    interfaces  1 22 50 55 80 100 114 132 150 351 352 377

A method with code carries the offset into the `Code` object and a reference
to it; a generated accessor carries the class number and a word saying which
it is, 0x2000 for a getter and 0x1000 for a setter. The table is in selector
order, system operations before the package's own.

The interface list is the class's whole ancestry -- implementation
superclasses and mixins, transitively, excluding itself -- as class numbers
sorted ascending. `interfaceCount` is its length, and for CounterScene that
is the twelve above.

`wirelineBaseClassNumber` is 58 in 46 of the 50 class records, which is what
`Object.Def` declares Object's Telescript predefined number to be.

### What has to be right, and what does not

Rather than decode every field, ask the guest. Take stock Counter, blank one
field, **redo the `clusterCRC`** -- the renumbering experiments went wrong by
forgetting exactly that -- install it and run `scripts/test-counter-68k`,
which taps the button and checks the count against a golden crop before and
after a JIT restore. What survives being zeroed is not load-bearing:

    classFlags                                           runs
    wirelineBaseClassNumber, wirelineDepth               runs
    referenceMask, copyReferenceMask, totalCopyReferences runs
    OperationList entry, second word                     runs
    ClassList entry, the three words after the reference  FAILS

So the fields that resisted derivation -- the eight `classFlags` values,
`wirelineDepth` (whose obvious reading is right for Counter and only 9 of
50), the masks -- do not need deriving. Nor does the byte in an
`OperationList` entry that defeated every hash family tried against 129
samples, though it is real: it is stable by name, and `UpdateDisplay` carries
the same word in Counter and in Whitehouse.

The one that matters decodes cleanly:

    u32  reference to the Class record
    u16  bytes of the class's own fields    u16  instanceSize
    u32  superclass number
    u16  (not read, and not load-bearing)   u16  superclass instanceSize

Counter's `00040058 00000179 00360054` is four bytes of own fields (88 less
Scene's 84), instance size 88, superclass 377, superclass size 84. It holds
across the corpus: the Circuits classes that inherit straight from Object
carry their whole instance size as own-field bytes and zero in both
superclass columns, and Hanoi's `0x8002` inherits from its own `0x8001` and
carries that class's 60. Blanking only the unread half-word leaves Counter
running, so every part a writer has to produce is computable from the layout.

### The dispatch sequences are written down in the SDK

The A5 ABI needs no reverse engineering. A generated header declares each
operation as an MPW inline function whose body *is* its instruction words:

    void ResetVisitCount(ObjectID self)={0x343C,0x8001,0x4EAD,0xFFFA};

`343C ssss` is `move.w #selector,d2` and `4EAD FFFA` is `jsr -6(a5)`, which
is what Counter's compiled `Code` object holds at offset 0x18. The system API
ships the same way -- 12,536 declarations in
`Device/Universal/NoDebug/Operations.h`, each carrying its own sequence:

    4009  0x4EAD,0xFFDA   inherited   (-38)
    4009  0x4EAD,0xFFBA   delegate    (-70)
    2753  0x4EAD,0xFFE0   fast path   (-32)
    1256  0x4EAD,0xFFFA   dispatch     (-6)
     509  0x4EAD,0xFFD0   intrinsic   (-48)

with `0x7401` -- `moveq #1,d2` -- instead of `343C` where the selector is
small enough. So generating code is a translation rather than a discovery:
each of those declarations becomes a wrapper that pushes its arguments,
emits those same words, and cleans the stack. Nothing has to be invented,
because the bytes are in the SDK's own headers.

### Still unread

Only the `Code` object, which needs CPU32 code generation. No cross-compiler
has to be installed for it: the clang already here targets m68k
(`--target=m68k-unknown-linux -mcpu=M68000`; `-march=` is rejected, and there
is no cpu32 among the choices, so the 68000 subset is the one to use since
the MC68349's core is a superset of it). The MIPS side compiles its samples
with the same clang.

## The runtime lists

`PackageBoot` hands the loader a `ClassList`, an `OperationList` and an
`IntrinsicList`, and `Context.Def` says what they are for --
`SetUpContextRuntime(classList, operationList, intrinsicList,
directDispatchList, rootList, globalsSize)`. A package with no code of its own
leaves all three empty, which is why the five data-only examples build without
any of this being read. Everything below is needed the moment a package
defines a class.

Both lists were worked out the same way, and the order matters more than the
result: the SDK's own `DefFiles/Runtime.Def` declares the fixed part of each
one outright, and only what is *after* the declared fields had to be derived.

### The name hash, and where it came from

Both lists carry a byte beside each entry that is neither a size nor a count
nor an index. `MyBalloonShape` is declared in both BarChart and Positioning --
with class records that are not identical -- and carries `0xd0` in both, which
says it is a function of the name. No multiply-accumulate, rotate-accumulate
or CRC-8 over the name reproduces it.

`MagicDeveloper/Interfaces/Device/System.Equates` names a routine
`OperationList_ByteCaseInsensitiveHash`, and that file turns out to be a
symbol table for the PIC-1000 ROM -- see `experiments/pic1000/symbols.py`, and
[the ROM notes](#the-sdk-names-the-pic-1000s-routines). So the algorithm was
read out of the ROM at the address the equates give:

    h = lower(name[0])
    for each later character: h = rol8(h, 2) ^ lower(character)
    return h or 1               -- a hash of zero is reported as one

`_GoLower` beside it lowercases `A`-`Z` and nothing else. This reproduces the
byte for all 39 class names in the corpus and 128 of 132 operation names; the
four are `LeftAndRight` and `TopAndBottom` in BarChart and Spreadsheet, which
share an imported interface whose operations appear in both packages' headers,
and which entry belongs to which has not been established.

### ClassList

`Runtime.Def` gives the fixed part as `actualCount`, `maxCount`, three
reserved halfwords and an `extraSentinel` it says "must be 0x8000 to make
BeginRead(x, Extra_) work" -- which is exactly the `00000001 00000001 00000000
00008000` that Counter carries, and 0x8000 in all fourteen. Then sixteen bytes
an entry:

| Offset | Size | What |
| --- | --- | --- |
| 0 | 4 | the `Class` record, as an ordinary `0xB0` reference |
| 4 | 2 | the bytes the class adds to its instance |
| 6 | 2 | its instance size; bit 15 set for a mixin |
| 8 | 4 | the class it inherits from, or 0 where it has several implementation parents or none |
| 12 | 1 | zero |
| 13 | 1 | the hash of the class's name |
| 14 | 2 | the inherited bytes; bit 15 set for a mixin |

None of that is checked against itself. The sizes and the parent restate what
the `Class` record the entry points at already says, and that record is
written by a different part of ObjectMaker and read here by a different
function, so the two agreeing is the evidence: all 50 class records in the
corpus agree on all four. The mixin bit appears on exactly the three classes
Circuits declares in `Mixins.Def` and nowhere else.

### OperationList

Eight bytes an entry, and the list is indexed by the operation's own number:
entry *n* is operation `0x8001 + n`. A number ObjectMaker reserved but nothing
uses -- a read-only attribute still reserves its setter -- is a pair of zero
words rather than a gap, which is why `actualCount` is not the number of
operations a package has. Hanoi has 26 entries and three holes.

| Offset | Size | What |
| --- | --- | --- |
| 0 | 4 | the `MagicOperation` giving the signature, as a `0xB0` reference |
| 4 | 1 | a kind byte |
| 5 | 1 | the hash of the operation's name |
| 6 | 2 | flags |

The `MagicOperation` is a list of the operation's argument and result types in
the same `{u16 classNumber; u8 type; u8 flags}` form a class's fields use: a
plain no-argument operation has one element of zero, and Counter's
`SetVisitCount` has two, a void result and an `Unsigned` (type `0x16`)
argument.

The kind byte is 0 for a plain operation and non-zero for an attribute's
getter; the values seen are 0x01, 0x02, 0x13, 0x21, 0x22, 0x23, 0x2f and 0x33,
and what selects them is **not established**, so it is reported raw. Only one
flag bit is ever set (0x0100) and what it means is likewise unread.

## The SDK names the PIC-1000's routines

`Device/System.Equates` in the SDK is an MPW assembly include of eleven
thousand lines of `ClassList_ElementAt = SystemCode_ + $81C22`. Nothing in it
says which ROM it describes, but its header gives `StartOfROM = $E000000` and
`ROMChecksum = $DD2BE2B`, and that checksum is the word at offset 0x4c of
`roms/Sony PIC 1000/PIC-1000.rom`.

So it is a symbol table for one of the ROMs here: 10,528 routines at exact
addresses. `experiments/pic1000/symbols.py --check` is what says so beyond the
checksum. It scores how often a named address begins something that looks like
the start of a routine:

| ROM | Rate |
| --- | --- |
| PIC-1000-reconstructed.rom | 77.7% |
| PIC-1000.rom (the raw dump) | 54.1% |
| Envoy 1.0 | 7.2% |
| PIC-2000 | 6.1% |
| HIX-300 | 5.7% |

The check knows only a handful of prologues, so 77.7% is a floor. Everything
that is not a PIC-1000 scores what an unrelated list of addresses scores. And
the reconstruction beats the damaged dump by 24 points while having been
derived from format invariants with no reference to this file, so the two
agree independently -- which is evidence for the reconstruction as much as for
the table.

`dis68k.py --symbols` labels a disassembly with it, and `--symbol NAME` starts
at a named routine.

## Numbering a package's own classes and operations

The container is one half of building a package; deciding what goes in it is
the other. Both numberings are settled, and both are checked against the
packages rather than against the headers ObjectMaker generated beside them --
two of which are stale with respect to the package they ship next to, which
is only visible because a package states the hash of every class's and every
operation's name.

**Which definition files, in which order.** A project names its `.Def` files
several times over. The last of those listings is the build order, and a file
named only once is one the project refers to without building: Spreadsheet's
`BarChartPublic.Def` is BarChart's declarations copied in so that Spreadsheet
can talk to a bar chart, and its six classes are numbered after Spreadsheet's
own five while none of them is written into Spreadsheet's package.
`objects_def.project_order` works it out; with it, all fifty class name
hashes and all one hundred and thirty-two operation name hashes in the
cookbook come out right.

**Classes** take 0x8001 upwards in declaration order across those files.

**Operations** are not so simple:

- A top-level `Operation Name N;` **reserves** N, and `Attribute Name N;`
  reserves N and N+1 for the setter, whether or not any class declares the
  name. BizNote writes `Attribute BizAddressCard 1;`, nothing declares it,
  and its first class-declared attribute starts at 3.
- A `field x: T, getter, setter;` declares an attribute as surely as
  `attribute` does. Whitehouse writes only the field and its package carries
  `MessageCount` and `SetMessageCount` at 3 and 4.
- A name the SDK already has is an override and takes no number at all.
  BizCard declares `operation IndexedDate(...)` so the Date Chooser can
  target it, and `IndexedDate` is a system operation.
- Otherwise the lowest free number is taken -- **and an attribute needs a
  consecutive pair**, because it is allocated with what `Runtime.Def` calls
  `FindUnassignedPair` while an operation uses `FindUnassignedNumber`. That
  one difference is what puts BizNote's `InstallIntoFileCabinet` at 5 and its
  `MeetingType`, declared earlier, at 12: 5 was free and 6 was not.

## The records that describe a class

`DefFiles/Class.Def` declares the `Class` record field by field, and
`AbstractClass` above it declares the rest, so the layout is the SDK's own
account rather than anything worked out from the bytes:

| Offset | Field |
| --- | --- |
| 0 | `Cited`'s citation -- the record's own id |
| 4 | `telescriptName` |
| 8 | `number` |
| 12 | `implSuperCount`, `implSuperOffset` |
| 16 | `methodCount`, `methodOffset` |
| 20 | `classFlags`, `wirelineBaseClassNumber`, `wirelineDepth` |
| 24 | `globalList` |
| 28 | `fieldList` |
| 32 | `instanceSize`, `interfaceCount` |
| 36 | `referenceMask` |
| 40 | `copyReferenceMask` |
| 44 | `totalCopyReferences` |
| 48 | `globalData` |
| 52 | `instanceList` |
| 56 | `patchPlaces` |
| 60 | `patchOffsets` |

The fixed part is 64 bytes and the two table offsets count from four bytes
into the payload, which is the only base that puts the implementation
superclass table at 0x40 and the methods after it. A method entry is the
selector, the offset into the `Code` object, a word of flags and a reference
to that object; a generated getter or setter has the field's number in place
of the offset, 0x2000 or 0x1000 in place of the flags, and no code object.

The flags word is zero in all but five of the corpus's methods -- 0x01000000
on three overrides of `CanApply` and 0x8000 on BarChart's two hand-written
`SourceCanvas` accessors -- and what either selects is **not established**.

### A field number

`NoDebug/FieldNumbers.h` states the number of every field in the system as
`(0x40040000 | ClassToFieldNumber(ClassList_))`, which is what fixes the
encoding: a kind nibble, twelve bits of position, and the class number. The
position is a halfword index **counted from the class's own fields**, so
`Actor.status`, four bytes into an Actor, carries 0.

| Nibble | Kind |
| --- | --- |
| 0 | a word -- `Unsigned`, `Signed`, `Fixed`, `PixelDot`, `Pointer` |
| 4 | a halfword -- `UnsignedShort`, `SignedShort`, `Character` |
| 8 | a reference |
| 12-15 | a Boolean, which is a bit |

What decides between 0 and 8 is the type, not the size: `Types.Def` is asked
before the class list, because several scalars are declared as classes as
well and a `Fixed` field is a plain word. A Boolean numbers the sixteen bits
of a halfword from the top, the nibble counting down in fours from 15 and a
further pair of bits counting down in ones from 3. This reproduces 2,328 of
the 2,397 numbers the header states; the 69 it does not are in five classes,
fifty-seven of them in `System` alone, whose Boolean runs this places one bit
along from where the header does. None of the five is a superclass of
anything in the cookbook.

### The numbers that are sums over what a class inherits

`wirelineDepth` is one more than its implementation parents' depths added up,
`totalCopyReferences` is theirs plus the bits in its own `copyReferenceMask`,
and `wirelineBaseClassNumber` is the first parent's. The SDK states none of
those for the system's own classes, so they are recovered from the packages
the way the system instance sizes were --
`toolchains/m68k/derive_system_classes.py` writes what it finds to
`system_classes.json`, and the corpus settles 26 of them.

It comes out for 48 of the 50 class records. The two it does not are Hanoi's
`Ring` and `Pole`, whose only implementation parent is another class of the
same package; both come out one deeper than the package says. Nothing else in
the corpus has that shape, so the rule is left alone and the difference
reported rather than patched over with a special case fitted to two records.

`classFlags` carries three bits in all fifty records, 0x04 on exactly the
twenty-five that add no fields of their own, and 0x0A00 on exactly Circuits'
three mixins. Four records carry a bit none of that explains -- 0x20 on
ChartTool and five of Circuits' components, 0x10 on BizNote's
`BizDrawerStack`, 0x4000 on BarChart's `BarChartForm` -- and the corpus does
not say what any of the three select.

`toolchains/m68k/class_records.py` writes all of this, and it is held
to the standard the rest of the writer is: every `ClassList`, every
`OperationList`, every `FieldList`, every `MagicOperation` and 48 of the 50
`Class` records in the cookbook come back **byte for byte** from the decode.

## What is left, and what stands in the way

All fourteen cookbook examples now read all the way through: every value form
in their definitions is understood, and the multi-file ones build from the
order their projects give. The five with no code of their own build at
**exactly stock's size with every payload identical bar the two ObjectMaker
stamps** -- the package's build date and the boot record's sum over it -- and
`scripts/test-template-68k` walks each of them to its scene in the guest and
requires the same pixels as the package ObjectMaker built.

The other nine stop at one wall: they need a `Code` object. Everything around
that object is now written and checked -- the `Class` record, the
`FieldList`, the `MagicOperation`s, both runtime lists and the
`DirectDispatchList` all re-emit byte for byte -- so what is left is the code
itself.

### The examples' C compiles, and every call is the right one

`clang-18` targets m68k and emits the right bytes; what stood in the way was
the dialect the SDK's headers are written in.
`Device/Universal/NoDebug/Operations.h` declares the system's operations

    void ResetVisitCount(ObjectID self)={0x343C,0x8001,0x4EAD,0xFFFA};

twelve and a half thousand times, which is not a function but four
instruction words for MPW C to paste at the call site. Nothing here speaks
it -- and it is the *only* thing that does not. Pointed at an unmodified
`Counter.c`, clang reports one error class and it is this one.

`toolchains/m68k/magic_headers.py` rewrites each declaration into a
`static inline` function that pushes the arguments itself and then emits the
same words, and `compile_example.py` compiles an example against the result.
**All nine code-bearing examples compile.** What is emitted is not
byte-identical to CodeWarrior's -- clang allocates registers its own way and
pops after each call where CodeWarrior leaves the frame to `unlk` -- but
every dispatch is:

| | dispatches here | in the package | the same |
| --- | --- | --- | --- |
| all nine examples | 378 | 378 | **378** |

Not one extra and not one missing, which is what says the rewritten headers
carry the SDK's own instruction words through untouched.

Three things had to be right, and each was read off the cookbook's compiled
code rather than assumed:

  * **arguments are pushed right to left, each as a four-byte long.** BizNote
    calls `AutoFile(card, false, true)` with `pea 1`, `clr.l -(a7)` and then
    the two objects, so a Boolean takes a whole long like everything else.
  * **the caller removes them.** Counter's `UpdateDisplay` calls
    `VisitCount(self)` and the next word is `584f`, `addq.w #4,a7`; BizNote
    takes sixteen and twenty-four back with `lea d(a7),a7`. Its
    `ResetVisitCount` looks at first as though the callee cleans, because it
    pushes twice, calls twice and leaves the whole frame to `unlk` -- which
    inline asm cannot do, since clang does not know what was pushed.
  * **a class number goes in D0**, which is what `#pragma parameter F(__D0)`
    says on the inherited and delegate forms.

And three about the assembler. LLVM's m68k parses neither `jsr -6(%a5)` nor
`%sp` in `addq.l`, so the words go in as `.short`. A long argument list has
to go through an array and one *address* register -- `12(%d3)` is not an
addressing mode, and with D0, D1, D2, A0 and A1 already spoken for, clang
runs out of registers on a six-argument call. And the examples are K&R C
written for a permissive compiler, so `-std=gnu89 -Wno-implicit-int
-Wno-return-type` is not laziness: `main() {}` has no return type and
Circuits' `CircuitWire_SnapWire` is declared non-void and writes a bare
`return;`.

Twenty-one declarations are variadic and are left out rather than
approximated, so that calling one fails at the link instead of quietly
passing the wrong thing.

### And it links to something with nothing left to fix up

A compiler leaves references behind -- a string in `.rodata`, a jump table,
a call between two of the package's own procedures -- and a Magic Cap
package has no way to resolve any of them later: there is not one fixup
table in the corpus. So they are resolved at the link, with `.rodata` laid
down immediately after `.text`, and all nine come out clean:

| | bytes | relocations left |
| --- | --- | --- |
| Counter | 240 | 0 |
| Hanoi | 3,958 | 0 |
| BizNote | 5,646 | 0 |
| Spreadsheet | 6,438 | 0 |
| Circuits | 7,631 | 0 |

Two things about that. It is **`m68k-linux-gnu-ld`**, not `ld.lld`, which
segfaults on an m68k object whatever it is asked to do; binutils for m68k is
installed here, and so, as it turns out, is a whole m68k GCC.

And it compiles for the **68020, not the 68000**. The packages themselves use
the 32-bit `mulu.l` and `divu.l` the 68000 has not got -- BarChart's code
carries four and two of them -- so CodeWarrior was building for the CPU32
core the MC68349 has. clang has no cpu32 to choose and the 68020 is the
nearest superset. Without it a divide becomes a call to `__udivsi3`, which is
a relocation into a library that is not there.

### The Code object, and a package that runs

A `Code` object is what `Code.Def` says it is -- `field unused: Object;
field kind: Unsigned;`, "68K is 0", both zero -- followed by the procedures
as its extra part. Each procedure is trailed by its MacsBug symbol: a byte of
0x80 or'd with the length, the name, and zeros up to a multiple of four.
Counter's `main` is eight bytes of code at 0x08 and
`84 6d 61 69 6e 00 00 00` at 0x10, with the next procedure at 0x18.

Those symbols go in **during** the link, not after it. Putting them between
the procedures afterwards would move every one but the first, and the
references between them have been resolved by then; so each procedure is
compiled into its own section with `-ffunction-sections` and the linker
script places its symbol behind it.

With that, `build_example.py` builds a package with code, and
**`scripts/test-counter-68k --built` passes**: Counter compiled from its own
C, packaged with records this wrote, installed through PC Link, opened, and
its `CounterScene_AboutToShow` ran -- the visit count incremented and the
text field updated, to the same golden crop the package CodeWarrior built
produces.

Every record in a built Counter is at the same id, of the same class, and
byte for byte what ObjectMaker wrote, bar four: the `SoftwarePackage`, which
carries the build's date and time; the `PackageBoot`, which sums over it; the
`Code`, which is what clang compiled rather than what CodeWarrior did; and
the `Class`, whose method table points into that code.

### What a class record needs, and where each part comes from

| | |
| --- | --- |
| parents, fields, methods | the `Define Class` block |
| field offsets and the two masks | the fields, placed the way an instance places them |
| instance size, wireline depth, copy references | its parents' values, added up |
| what its parents are worth | `system_classes.json`, derived from the corpus |
| the interfaces | its parents', plus `inherits interface from` |
| a method's code offset | the linker |

Two of those are worth spelling out. The interface list cannot be worked out
from the definition files: `EditsTarget` and `FormElement` have class numbers
and no declaration anywhere in the SDK, and a `ConversionField` that leaves
them out comes up two short. They are recovered from the packages, by
intersecting what each single-parent record says its parent answers as --
intersecting, because a class may add to the list with `inherits interface
from`, as BizNote's `PeopleTextField` does.

And an `OperationList` entry's kind byte is a small code for the result's
type with 0x20 on top where the operation is a getter. All 132 operations in
the corpus agree: a plain operation returning a Boolean carries 0x01 and a
getter of one carries 0x21.

### What is still open

  * **The `CanApply` flag.** Three classes override it and all three carry
    0x01000000 in the method entry; nothing else in the corpus carries it. It
    is not the signature -- `CanAcceptCoupon` returns a Boolean and takes
    arguments too, and carries nothing -- and it is not that two classes
    declare the name, which is true of `TouchTarget` and `AboutToShow` as
    well.
  * `Spreadsheet`'s `CellEditorWindow` inherits `TitledWindow` and
    `BalloonSpout`, and nothing else in the corpus mentions either, so its
    instance size cannot be derived.
  * The `DirectDispatchList`'s order, which is neither sorted nor the order
    the classes override things in.
  * Three `classFlags` bits.

### Cross-package interfaces: there are none

`BarChartPublic.Def` looks like an import -- it is BarChart's declarations
copied into Spreadsheet -- but nothing comes of it. Spreadsheet's package
carries a record for none of its classes, its compiled code refers to none of
their numbers, and the `PackageImports.h` ObjectMaker generated for it is
empty, as it is for every example in the cookbook. Spreadsheet finds a bar
chart the way anything finds anything here, through an indexical:
`MakePackageIndexical(27,1)` is the citation it looks one up by.

So the corpus exercises no cross-package mechanism at all. What the two real
third-party packages do is a separate question.

### Whitehouse guest validation (2026-09-21)

Whitehouse builds, transfers at the emulator's default 115200 timing, and
opens to the same White House scene as the stock package. Its entrance is
installed into `iDowntown`. From the installation state, tap the top-right
navigation twice (Storeroom → Hallway → Downtown), then the building's door
at (240,180). The generic Hallway route in `test-code-examples-68k` instead
opened the Game room. Its animated cat clock produced different screenshots
and a false failure. The script now uses Whitehouse's Downtown route and a
visually verified scene fingerprint, so agreement in the wrong room cannot
pass this check.

Earlier diagnoses of a broken native ABI or corrupt class dispatch were
not supported. The stock package logs the same address exceptions. The ROM
deliberately jumps to odd encoded addresses for fast accessors: its handler
at `0E088776` recognizes the dispatcher at `00000284`, extracts the encoded
address from the CPU32 exception frame, and resumes at `0E0887B0` to decode
the accessor. The `81000381`/`Quantum` trace alone is therefore not a crash.
Likewise, the ROM uses privilege exceptions on `MOVE SR` to enter supervisor
mode. Guest output and subsequent execution are needed to judge failure.

There was one independent object-writing defect: two Telecards declare a
one-byte `header1` before `data1`, absent from the SDK's public layout. The
builder now emits that prefix; all four Whitehouse Telecard payloads match
the shipped package, covered by `WhitehouseTelecardTests`.

Run `scripts/test-code-examples-68k out/whitehouse-verified --example Whitehouse`
for fresh builds and installations, or add `--skip-install` to reuse those
installation states. The title/application crop has SHA-256
`431a7de76f2969ea961390876d51c5cf8095be8c09494c0a5a079af5c9cdbb58` after
excluding the animated hallway clock.
The script also checks reset with zero counts and a save/restore cycle.
A PC watchpoint separately confirmed the rebuilt
`WhitehouseScene_VerifySetToZero` executes on reset. Sending mail, incrementing
the message counts, and the nonzero confirmation path remain untested.

The full code-bearing matrix can be run with:

    INSNS=2000000000 scripts/test-code-examples-68k out/pic-68k-code-full

It currently passes all eight examples. The generic route reaches the Hallway
for seven packages; Whitehouse uses its Downtown entrance route explicitly.
