#!/usr/bin/env python3
"""The records that describe a package's own classes and operations.

A package with no code of its own carries an empty `ClassList`, an empty
`OperationList` and nothing else; the moment it declares a class it carries a
`Class` record for it, a `FieldList` naming its fields, a `MagicOperation`
for each operation it defines, a `DirectDispatchList` of the system
operations it overrides, and entries in the two runtime lists. This builds
all of those from the class's declaration.

Almost none of it had to be guessed at. `DefFiles/Class.Def` declares the
`Class` record field by field -- `implSuperCount`, `methodOffset`,
`classFlags`, `wirelineDepth`, `referenceMask` and the rest -- and
`DefFiles/Runtime.Def` does the same for the two lists, so what is written
here is the SDK's own account of the format. What the SDK does not say is how
the values are *computed*, and that was taken from the fifty class records in
the cookbook; `derive_system_classes.py` does the taking and
`system_classes.json` is what it found.
"""
import json
from pathlib import Path
import struct

#: The Class record's fixed part, from `Class.Def` and `AbstractClass` above
#: it. Table offsets in it are counted from four bytes into the payload,
#: which is the only base that puts the tables where they are.
FIXED_BYTES = 0x40
TABLE_BASE = 4
IMPL_SUPER_OFFSET = 0x3C
IMPL_SUPER_STRIDE = 16
METHOD_STRIDE = 16

#: `classFlags`, as far as the corpus establishes it. Three bits are set in
#: every one of the fifty records and are carried as a constant; 0x04 is set
#: on exactly the twenty-five that add no fields of their own, and 0x0A00 on
#: exactly the three mixins Circuits declares. Four records carry a bit none
#: of that explains -- see `unexplained_flags`.
CLASS_FLAGS = 0xA080
FLAG_NO_OWN_FIELDS = 0x0004
FLAG_NO_IMPLEMENTATION_PARENT = 0x0A00

#: A getter and a setter, in the third word of a generated method entry.
ACCESSOR_GETTER = 0x2000
ACCESSOR_SETTER = 0x1000

#: The top nibble of a field number says how to reach the field, and the
#: twelve bits under it say where it is. This is not inferred from the
#: packages: `NoDebug/FieldNumbers.h` states the number of every field in the
#: system, and matching those against the layouts the definition files give
#: is what fixes the table. `derive_system_classes.py --fields` re-checks it.
FIELD_KIND_WORD = 0x0        # Unsigned, Signed, Fixed, PixelDot, Pointer
FIELD_KIND_HALFWORD = 0x4    # UnsignedShort, SignedShort, Character
FIELD_KIND_REFERENCE = 0x8   # anything the definition files declare as a class

#: A field's kind is decided by what its type is, not by how big it is: a
#: `Pointer` is four bytes and a plain word, while an `ObjectList` is four
#: bytes and a reference. So the test is whether the definition files declare
#: the type as a class.
HALFWORD_TYPES = {'UnsignedShort', 'SignedShort', 'Character'}


def field_kind(type_name, definitions):
    """Which of the three ways a field is reached.

    `Types.Def` is asked before the class list, because several of the
    scalars are declared as classes as well -- there is a `Fixed` class and a
    `Fixed` type -- and a field of one of those is a plain word rather than a
    reference. `Sound.sampleRate` is the case that says so.
    """
    if type_name in HALFWORD_TYPES:
        return FIELD_KIND_HALFWORD
    if definitions is not None and type_name in definitions.type_sizes:
        return FIELD_KIND_WORD
    if definitions is not None and type_name in definitions.classes:
        return FIELD_KIND_REFERENCE
    return FIELD_KIND_WORD


def field_number(field, class_number, definitions=None):
    """What a generated accessor is given to find the field it stands for.

    `FieldNumbers.h` writes a system field's number as
    `(0x40040000 | ClassToFieldNumber(ClassList_))`, so the number is a kind
    nibble, twelve bits of position, and the class. The position is a
    halfword index **counted from the class's own fields**, not from the
    start of the instance: `Actor.status` sits four bytes into an Actor and
    carries 0, because the four before it belong to the class Actor inherits.

    A Boolean is a bit rather than a halfword, and takes the four bit
    positions a nibble can distinguish plus two more bits above the halfword
    index: the sixteen bits of a halfword are numbered from its top, the
    nibble counts down in fours from 15 and the pair counts down in ones
    from 3.
    """
    offset, bit = field['offset'], field.get('bit')
    if bit is not None:
        position = (offset & 1) * 8 + bit
        return (((15 - position // 4) << 28)
                | ((3 - position % 4) << 26)
                | ((offset // 2) << 16) | class_number)
    kind = field.get('kind')
    if kind is None:
        kind = field_kind(field['type'], definitions)
    return (kind << 28) | ((offset // 2) << 16) | class_number


def reference_masks(fields):
    """Which of a class's own longs hold objects, and which are copied.

    `Class.Def` calls them `referenceMask` and `copyReferenceMask`, "bit for
    each long as to what fields are objects" and the same again for the ones
    that are cloned. A field marked `noCopy` is in the first and not the
    second, which is what BarChart's `drawingData` is for: its class carries
    masks 3 and 1.
    """
    references = copies = 0
    for field in fields:
        if field.get('kind') != FIELD_KIND_REFERENCE:
            continue
        bit = 1 << (field['offset'] // 4)
        references |= bit
        if not field.get('no_copy'):
            copies |= bit
    return references, copies


class Classes:
    """What the system classes a package builds on are worth.

    Three of the numbers in a `Class` record are sums over the classes it
    inherits from -- the wireline depth, the total number of copy references,
    and the wireline base class -- so building a record needs the values for
    the system classes underneath it, and nothing in the SDK states them.
    They are recovered from the packages instead, the same way the system
    instance sizes were: a record whose implementation parents are known bar
    one says what that one must be worth.
    """

    def __init__(self, path=None):
        path = path or Path(__file__).with_name('system_classes.json')
        self.known = json.loads(path.read_text()) if path.exists() else {}

    def of(self, name, package=None):
        if package and name in package:
            return package[name]
        if name not in self.known:
            raise LookupError(f'nothing known about the system class {name!r}')
        return self.known[name]

    def derive(self, name, parents, own_copy_mask, package=None):
        """A class's depth, copies and base, from its parents.

        Depth is one more than its parents' depths added up and the copy
        references are its parents' plus its own; the base is inherited from
        the first parent, and a class with no parent at all has none. That
        holds for forty-eight of the fifty records in the cookbook. The two
        it does not hold for are Hanoi's `Ring` and `Pole`, whose only parent
        is another class in the same package: both come out one deeper than
        the package says. Nothing else in the corpus has that shape, so the
        rule is left as it is and the difference is reported rather than
        patched over with a special case fitted to two records.
        """
        values = [self.of(parent, package) for parent in parents]
        return {
            'depth': 1 + sum(v['depth'] for v in values),
            'copies': (bin(own_copy_mask).count('1')
                       + sum(v['copies'] for v in values)),
            'base': values[0]['base'] if values else 0,
        }


def class_flags(fields, parents):
    flags = CLASS_FLAGS
    if not fields:
        flags |= FLAG_NO_OWN_FIELDS
    if not parents:
        flags |= FLAG_NO_IMPLEMENTATION_PARENT
    return flags


def method_entry(selector, code_object=None, code_offset=0, flags=0,
                 accessor=None, field=None, class_number=0):
    """One sixteen-byte row of a class's method table.

    A method the package compiled is its selector, where it starts in the
    `Code` object, a word of flags, and a reference to that object. A
    generated getter or setter has no code: it is the selector, the field's
    number, which of the two it is, and a zero.

    The flags word is zero in all but five of the corpus's two hundred and
    fifty methods: 0x01000000 on the three that override `CanApply` and
    0x8000 on BarChart's two `SourceCanvas` accessors, which are written by
    hand rather than generated. What either bit selects is **not
    established**, so it is carried rather than computed.
    """
    if accessor is not None:
        return struct.pack('>IIII', selector,
                           field_number(field, class_number), accessor, 0)
    return struct.pack('>IIII', selector, code_offset, flags,
                       0xB0000000 | code_object)


def class_record(number, own_id, field_list_id, instance_size, fields,
                 parents, parent_numbers, methods, interfaces, derived):
    """A `Class` record, laid out the way `Class.Def` declares it."""
    references, copies = reference_masks(fields)
    method_offset = IMPL_SUPER_OFFSET + IMPL_SUPER_STRIDE * len(parents)
    fixed = bytearray(FIXED_BYTES)
    struct.pack_into('>I', fixed, 0x00, 0xB0000000 | own_id)
    struct.pack_into('>I', fixed, 0x08, number)
    struct.pack_into('>HH', fixed, 0x0C, len(parents), IMPL_SUPER_OFFSET)
    struct.pack_into('>HH', fixed, 0x10, len(methods), method_offset)
    struct.pack_into('>HBB', fixed, 0x14, class_flags(fields, parents),
                     derived['base'], derived['depth'])
    struct.pack_into('>I', fixed, 0x1C,
                     0xB0000000 | field_list_id if field_list_id else 0)
    struct.pack_into('>HH', fixed, 0x20, instance_size, len(interfaces))
    struct.pack_into('>III', fixed, 0x24, references, copies,
                     derived['copies'])

    out = bytes(fixed)
    for parent_number in parent_numbers:
        out += struct.pack('>IIII', parent_number, 0, 0, 0)
    out += b''.join(methods)
    out += b''.join(struct.pack('>I', n) for n in interfaces)
    return out


def field_list(fields, strings_id, first_string_entry):
    """A `FieldList`: how many fields, where their names start, then one
    element each in the `{u16 classNumber; u8 type; u8 flags}` form a field
    element takes everywhere else in the container."""
    out = struct.pack('>III', len(fields), strings_id, first_string_entry)
    for field in fields:
        out += struct.pack('>HBB', field.get('class_number', 0) or 0,
                           field['element_type'],
                           0x20 if field.get('no_copy') else 0)
    return out


def magic_operation(number, flags, signature):
    """A `MagicOperation`: the operation's result and arguments.

    `length` counts the elements, and each is the same four bytes a field
    element is -- the class a reference points at, a type code and flags --
    with the result first. A no-argument operation returning nothing has one
    element of zeros.
    """
    out = struct.pack('>IHH', len(signature), flags, number)
    for element in signature:
        out += struct.pack('>HBB', element.get('class_number', 0) or 0,
                           element.get('type', 0), element.get('flags', 0))
    return out


def class_list(entries):
    """The `ClassList`: `Runtime.Def`'s six fields, then sixteen bytes each."""
    out = struct.pack('>IIhhhh', len(entries), len(entries), 0, 0, 0,
                      -0x8000)
    for entry in entries:
        mixin = 0x8000 if entry['mixin'] else 0
        out += struct.pack('>IHHIBBH', 0xB0000000 | entry['record'],
                           entry['own_bytes'], entry['instance_size'] | mixin,
                           entry['inherits_from'], 0, entry['name_hash'],
                           entry['inherited_bytes'] | mixin)
    return out


def operation_list(entries, highest):
    """The `OperationList`, indexed by the operation's own number.

    A number that was reserved and never used is a pair of zero words, so the
    list is as long as the highest number the package gave out rather than as
    long as the number of operations it has.
    """
    # `actualCount` counts the slots, not the operations: BarChart's says 66
    # and only eight of them hold anything.
    out = struct.pack('>II', highest - 0x8000, 0)
    by_number = {entry['number']: entry for entry in entries}
    for number in range(0x8001, highest + 1):
        entry = by_number.get(number)
        if entry is None:
            out += struct.pack('>II', 0, 0)
            continue
        out += struct.pack('>IBBH', 0xB0000000 | entry['record'],
                           entry['kind'], entry['name_hash'], entry['flags'])
    return out


def direct_dispatch_list(operations):
    """The system operations a package's classes override, and nothing else.

    A bare run of operation numbers with no header at all, which is what the
    fifteen packages that carry one have. The order is the caller's: it is
    not sorted, and what ObjectMaker's order is has not been established.
    """
    return b''.join(struct.pack('>I', n) for n in operations)
