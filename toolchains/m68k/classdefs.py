#!/usr/bin/env python3
"""Field layouts for 68k Magic Cap classes, from the SDK's own definitions.

An object record's payload is its fields laid end to end, and which fields
those are is a statement the SDK makes in `DefFiles/*.Def`: a class declares
what it inherits from and the fields it adds, and the layout is the ancestors'
fields followed by its own. This works that out so an object can be read as
the fields it holds rather than as a run of bytes.

The sizes are the SDK's too. `Types.Def` gives them outright for the named
types; the rest are the handful below, each checked against an object whose
values the cookbook states in its Objects.Def.

Where a class or an ancestor is not in the definitions, the layout is refused
rather than approximated. A field list that is short by one ancestor puts
every offset after it wrong, and silently: it would decode, and it would be
wrong.
"""
import re
from pathlib import Path

# A reference to an object is a word. So is a plain number; a short is half of
# one. A Boolean is a single bit, packed with the Booleans beside it.
WORD, HALF, BIT = 4, 2, None
BASE_TYPES = {
    'Unsigned': WORD, 'Signed': WORD, 'UnsignedShort': HALF, 'Short': HALF,
    'UnsignedByte': 1, 'Byte': 1, 'Char': 1, 'Boolean': BIT,
    'Fixed': WORD, 'Pointer': WORD, 'ObjectID': WORD,
}

# The C scalars the SDK's own headers are written in, so that a type it
# defines there can be sized the way the compiler sized it.
C_SCALARS = {'char': 1, 'uchar': 1, 'signed char': 1, 'unsigned char': 1,
             'Byte': 1, 'UnsignedByte': 1, 'Boolean': 1,
             'short': 2, 'ushort': 2, 'unsigned short': 2, 'signed short': 2,
             'long': 4, 'ulong': 4, 'unsigned long': 4, 'signed long': 4,
             'int': 4, 'uint': 4, 'unsigned int': 4, 'float': 4}
C_TYPEDEF = re.compile(r'\btypedef\s+((?:unsigned |signed )?\w+)\s+(\w+)\s*;')
C_STRUCT = re.compile(r'\btypedef\s+struct\s*\{([^{}]*?)\}\s*(\w+)\s*;', re.S)
C_MEMBER = re.compile(r'((?:unsigned |signed )?\w+)\s+(\w+)\s*(?:\[(\d+)\])?\s*;')

CLASS_BLOCK = re.compile(r'^\s*Define Class\s+(\w+)\s*;(.*?)^\s*End Class\s*;',
                         re.M | re.S)
INHERITS = re.compile(r'^\s*inherits from\s+([^;]+);', re.M)
MIXES_IN = re.compile(r'^\s*mixes in with\s+([^;]+);', re.M)
FIELD = re.compile(r'^\s*field\s+(\w+)\s*:\s*([^;,]+?)\s*(?:,([^;]*))?;', re.M)
TYPE_SIZE = re.compile(r'^\s*Type\s+(\w+)\s+is\s+(\d+)\s+bytes\s*;', re.M)


class LayoutError(ValueError):
    pass


def read(path):
    return path.read_bytes().decode('mac-roman').replace('\r', '\n')


def strip_comments(text):
    """Comments and preprocessor lines.

    The definitions are run through the C preprocessor, and a field can be
    split across a conditional -- DataList's `stride` has its getter behind
    `#ifndef DEBUG`, so the directive lands between the type and the comma
    and ends up read as part of the type name.
    """
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'^\s*#[^\n]*', '', text, flags=re.M)


class Definitions:
    """Every class the SDK declares, and how big each named type is."""

    def __init__(self, deffiles, headers=None):
        self.classes, self.type_sizes = {}, {}
        for path in sorted(Path(deffiles).glob('*.Def')):
            self.add(path)
        # After the definitions, so that a size Types.Def states outright is
        # never displaced by one worked out from a header.
        if headers is not None:
            self.read_headers(headers)

    def add(self, path, override=False):
        """One more definition file, in the same syntax the SDK's are in.

        `override` is for a file that deliberately replaces a declaration
        already read -- a class the shipped SDK declares with no fields,
        whose real layout was recovered from the packages -- and is the only
        way a later file can win.

        An example declares its own classes exactly the way the SDK declares
        its -- `Define Class CounterScene; inherits from Scene; field
        visitCount: Unsigned, getter, setter;` -- so a package's own classes
        are read by pointing this at the example's `.Def` rather than by a
        second parser.
        """
        path = Path(path)
        text = strip_comments(read(path))
        for name, size in TYPE_SIZE.findall(text):
            self.type_sizes[name] = int(size)
        for name, body in CLASS_BLOCK.findall(text):
            supers = []
            for clause in INHERITS.findall(body):
                supers += [s.strip() for s in clause.split(',') if s.strip()]
            mixins = []
            for clause in MIXES_IN.findall(body):
                mixins += [s.strip() for s in clause.split(',') if s.strip()]
            fields = [(f, t.strip(), tuple(q.strip() for q in (r or '').split(',') if q.strip()))
                      for f, t, r in FIELD.findall(body)]
            # Later files do not redefine earlier classes in this corpus;
            # if one ever does, the first wins and the clash is visible.
            setter = dict.__setitem__ if override else dict.setdefault
            setter(self.classes, name, {
                'supers': supers, 'mixins': mixins, 'fields': fields,
                'source': path.name,
            })

    def read_headers(self, headers):
        """Sizes for types the definitions use but do not measure.

        `Dot` and `PixelDot` are not in Types.Def; they are C structs in the
        SDK's own headers, and the compiler that built these packages sized
        them from exactly that. Only plain typedefs and structs whose members
        are all scalars are taken -- anything with a pointer, a union or a
        nested type is left alone, and a field of that type keeps its class
        unresolved rather than being given a made-up width.
        """
        for path in sorted(Path(headers).glob('*.h')):
            text = strip_comments(read(path))
            for body, name in C_STRUCT.findall(text):
                total, ok = 0, True
                members = C_MEMBER.findall(body)
                if not members:
                    continue
                for member_type, _, count in members:
                    size = C_SCALARS.get(member_type.strip()) \
                        or self.type_sizes.get(member_type.strip())
                    if not size:
                        ok = False
                        break
                    total += size * (int(count) if count else 1)
                if ok:
                    self.type_sizes.setdefault(name, total)
            for base, name in C_TYPEDEF.findall(text):
                size = C_SCALARS.get(base.strip()) or self.type_sizes.get(base.strip())
                if size:
                    self.type_sizes.setdefault(name, size)

    def size_of(self, type_name):
        """Bytes for a field of this type, or None for a Boolean's single bit.

        A type that names a class is a reference to one, which is a word --
        that is why an unknown name is not an error here. It is why the
        classes have to be complete, though: a field whose type is a class
        that does not exist would be silently sized as a reference.
        """
        if type_name in BASE_TYPES:
            return BASE_TYPES[type_name]
        if type_name in self.type_sizes:
            return self.type_sizes[type_name]
        if type_name in self.classes:
            return WORD
        raise LayoutError(f'no size for type {type_name!r}')

    def ancestry(self, class_name):
        """The class and everything it inherits from, ancestors first.

        Depth first in declaration order, and each class once: a mixin
        reached down two paths contributes its fields at the first, which is
        what the field order of the packages says happens.
        """
        seen, order = set(), []

        def visit(name):
            if name in seen:
                return
            if name not in self.classes:
                raise LayoutError(f'class {name!r} is not in the definitions')
            seen.add(name)
            for parent in self.classes[name]['supers']:
                visit(parent)
            order.append(name)

        visit(class_name)
        return order

    def layout(self, class_name):
        """Where each field of an instance sits, in bytes from the payload.

        Booleans are bits, most significant first, and a run of them takes as
        many whole bytes as it needs; the next field of another type starts
        after those bytes, aligned to its own size. Both were read off
        Counter's SoftwarePackage, where one Boolean stands alone before a
        reference and sixteen more sit together after a short.
        """
        offset, bit, fields = 0, None, []
        for owner in self.ancestry(class_name):
            for name, type_name, quals in self.classes[owner]['fields']:
                size = self.size_of(type_name)
                if size is BIT:
                    if bit is None:
                        bit = 0
                    fields.append({'name': name, 'type': type_name,
                                   'owner': owner, 'offset': offset + bit // 8,
                                   'bit': bit % 8, 'size': None,
                                   'qualifiers': list(quals)})
                    bit += 1
                    continue
                if bit is not None:            # close the run of Booleans
                    offset += (bit + 7) // 8
                    bit = None
                if size > 1 and offset % min(size, WORD):
                    offset += min(size, WORD) - (offset % min(size, WORD))
                fields.append({'name': name, 'type': type_name, 'owner': owner,
                               'offset': offset, 'bit': None, 'size': size,
                               'qualifiers': list(quals)})
                offset += size
        if bit is not None:
            offset += (bit + 7) // 8
        return {'class': class_name, 'fields': fields, 'fixed_bytes': offset}


# What a FieldList element says a field is.
#
# Derived rather than assumed: every field the fourteen examples declare was
# matched to the element written for it, by name, and each declared type came
# out as exactly one code. Two Fixed fields of one class carry the identical
# element, which is what says this describes the type and not the position.
#
# An element is {u16 class number; u8 type; u8 flags}. The class number is the
# class a reference field points at and zero for everything else, which is how
# `ringList: ObjectList` reads 0x001d0700 against `moveList: Object` at
# 0x00010700 -- 29 and 1 being those classes' numbers.
FIELD_TYPES = {
    0x02: 'Boolean', 0x07: 'reference', 0x0B: 'PixelDot', 0x0E: 'Signed',
    0x13: 'Fixed', 0x16: 'Unsigned', 0x17: 'UnsignedShort',
}
# The only flag the corpus exercises: `field x: Object, getter, noCopy`.
FIELD_FLAGS = {0x20: 'noCopy'}


def decode_field_element(value):
    """One FieldList element, as the field it describes."""
    class_number, type_code, flags = (value >> 16, (value >> 8) & 0xFF,
                                      value & 0xFF)
    out = {'raw': f'{value:08x}', 'type_code': type_code,
           'type': FIELD_TYPES.get(type_code),
           'flags': [name for bit, name in FIELD_FLAGS.items() if flags & bit]}
    if class_number:
        out['class_number'] = class_number
    unknown = flags & ~sum(FIELD_FLAGS)
    if unknown:
        out['unknown_flags'] = f'{unknown:02x}'
    return out


# What each field type occupies in an instance. None is a Boolean, which is a
# bit, the same as in the system classes' own layouts.
FIELD_STORAGE = {'Boolean': None, 'UnsignedShort': 2, 'PixelDot': 4,
                 'Signed': 4, 'Fixed': 4, 'Unsigned': 4, 'reference': 4}


def package_field_offsets(fields):
    """Where a package class's own fields sit, past whatever it inherited.

    A class's fields follow its superclass's instances end to end, in the
    order declared, each aligned to its own width, with Booleans packed as
    bits and the whole rounded up to a multiple of four. The offsets are
    given relative to the inherited part because that is all this can know:
    the size of a system superclass is not in the definitions anywhere.

    The check that this is right is `instance_size` minus what it works out
    here, which has to be the superclass's own size -- a non-negative
    multiple of four, and the same number every time two classes inherit the
    same thing. It is, for all fifty class records in the cookbook and for
    twenty-six of the twenty-seven system classes they inherit from.
    """
    at, bit, out = 0, None, []
    for field in fields:
        size = FIELD_STORAGE.get(field.get('type'), 4)
        if size is None:
            if bit is None:
                bit = 0
            out.append({'offset': at + bit // 8, 'bit': bit % 8, 'bytes': None})
            bit += 1
            continue
        if bit is not None:
            at += (bit + 7) // 8
            bit = None
        if at % size:
            at += size - (at % size)
        out.append({'offset': at, 'bit': None, 'bytes': size})
        at += size
    if bit is not None:
        at += (bit + 7) // 8
    return out, at + (4 - at % 4) % 4


def read_string_table(data, entry):
    """The names in a StringList, which is where a package keeps its own.

    The strings are Pascal ones, a length byte then the characters, packed
    end to end. `dataOffset` counts from four bytes into the payload -- the
    same base a Class record counts its tables from.
    """
    fields = {f['name']: f.get('raw') for f in entry['contents']['fields']}
    if any(fields.get(k) is None for k in ('length', 'dataOffset', 'dataSize')):
        return None
    at = entry['payload']['offset'] + 4 + fields['dataOffset']
    end = at + fields['dataSize']
    out = []
    while len(out) < fields['length'] and at < end:
        size = data[at]
        if at + 1 + size > end:
            break
        out.append(data[at + 1:at + 1 + size].decode('mac-roman'))
        at += 1 + size
    return out


def is_reference(definitions, type_name):
    """Whether a word in this field names an object rather than counts.

    A field typed by a class holds a reference to one. Getting this wrong is
    how a size of zero comes out as "nil" and a count of 32 comes out as an
    object number.
    """
    return type_name in ('ObjectID', 'Pointer') or type_name in definitions.classes


def decode_fields(data, start, length, layout, definitions=None):
    """Read an object's payload as the fields the layout says are there.

    A field that would run past the record is reported as absent rather than
    read from whatever follows: records here are sometimes shorter than their
    class's full fixed part, and reading on would be reading the next object.
    """
    out = []
    for field in layout['fields']:
        at = start + field['offset']
        entry = {'name': field['name'], 'type': field['type'],
                 'owner': field['owner'], 'offset': field['offset']}
        if field['bit'] is not None:
            if field['offset'] >= length:
                entry['value'] = None
                entry['absent'] = True
            else:
                byte = data[at]
                entry['value'] = bool(byte & (0x80 >> field['bit']))
                entry['bit'] = field['bit']
        else:
            size = field['size']
            if field['offset'] + size > length:
                entry['value'] = None
                entry['absent'] = True
            else:
                raw = int.from_bytes(data[at:at + size], 'big')
                entry['raw'] = raw
                entry['bytes'] = size
                reference = definitions is None or \
                    is_reference(definitions, field['type'])
                entry['value'] = describe_word(raw) \
                    if size == WORD and reference else raw
        out.append(entry)
    return out


TOP_LEVEL_NUMBER = re.compile(
    r'^[ \t]*(Operation|Attribute|Intrinsic)\s+(\w+)\s+(\d+)\s*;', re.M)
CLASS_BODY = re.compile(r'Define\s+Class\s+\w+\s*;(.*?)End\s+Class\s*;', re.S)
MEMBER = re.compile(r'^[ \t]*(operation|attribute|intrinsic)\s+(\w+)\s*([^;]*);',
                    re.M)
# A field with accessors declares an attribute as surely as `attribute` does:
# Whitehouse writes only `field messageCount: Unsigned, getter, setter;` and
# its package carries MessageCount and SetMessageCount at 3 and 4. The name is
# the field's with its first letter raised, which is what the generated
# `PackageOperations.h` calls it.
MEMBER_OR_FIELD = re.compile(
    r'^[ \t]*(operation|attribute|intrinsic)\s+(\w+)\s*([^;]*);'
    r'|^[ \t]*field\s+(\w+)\s*:\s*[^;,]+?\s*,([^;]*);', re.M)


def accessor_declaration(match):
    """One class member as (kind, name, qualifiers), or None.

    A field without accessors declares no operation and is passed over; one
    with only a getter is read-only, which reserves its setter's number
    without exporting it, exactly as `attribute Name: T, readOnly` does.
    """
    kind, name, rest, field, qualifiers = match.groups()
    if kind:
        return kind, name, rest
    if 'getter' not in qualifiers and 'setter' not in qualifiers:
        return None
    return ('attribute', field[:1].upper() + field[1:],
            '' if 'setter' in qualifiers else 'readOnly')


DEFINE_CLASS = re.compile(r'Define\s+Class\s+(\w+)\s*;')


def package_class_numbers(texts):
    """The numbers ObjectMaker gives a package's own classes.

    Declaration order, from 0x8001, across the definition files in the order
    the project builds them. A class a package only refers to is numbered
    too -- Spreadsheet's copy of BarChart's declarations takes 6 to 11 after
    Spreadsheet's own 1 to 5 -- so this says what every declared class is
    called, not which of them the package writes a record for.

    Checked against every `PackageClassNumbers.h` in the cookbook and against
    the name hash in each package's own `ClassList`.
    """
    out = {}
    for text in texts:
        for name in DEFINE_CLASS.findall(strip_comments(text)):
            out.setdefault(name, 0x8001 + len(out))
    return out


def package_numbers(texts, system=None):
    """The numbers ObjectMaker gives a package's own operations.

    A package's operations are numbered from one with the top bit set, and
    the rule is not what it looks like at first. Counter declares
    `Operation ResetVisitCount 1;` at the top of its definition file and gets
    1, so the numbers look like the file's -- but Metric declares its
    operations inside the class body with no numbers at all and still gets 1
    and 2, so ObjectMaker is numbering them itself.

    What it does:

    - A top-level `Operation Name N;` **reserves** N, and an
      `Attribute Name N;` reserves N and N+1 for its setter. The reservation
      stands whether or not a class ever declares that name: BizNote writes
      `Attribute BizAddressCard 1;`, nothing declares it, and its first
      class-declared attribute starts at 3 rather than 1.
    - A name the SDK already defines is an override, not a new operation, and
      takes no number. BizCard declares `operation IndexedDate(...)` so that
      the Date Chooser can target it, and `IndexedDate` is a system operation,
      so BizNote's package numbers skip it entirely. This is what `system`
      is for: the names in the SDK's own operation and attribute tables.
    - Otherwise a class member is given the lowest number not yet taken --
      **and an attribute needs a consecutive pair**, because it is allocated
      with what `Runtime.Def` calls `FindUnassignedPair` while a plain
      operation uses `FindUnassignedNumber`. That single difference is what
      puts BizNote's `InstallIntoFileCabinet` at 5 and its `MeetingType`, one
      declared earlier, at 12: 5 was free but 6 was already reserved, so the
      pair had to go after the block at 6-11.
    - Intrinsics are numbered in a space of their own, also from one.

    `texts` is the definition files' contents, in the order the example's
    project builds them. Checked against the operation lists of all nine
    cookbook packages that define any -- every entry's name hash has to come
    out right -- rather than against the generated headers, two of which are
    stale with respect to the package shipped beside them.
    """
    system = system or frozenset()
    requested, out = {}, {}
    taken = {'operation': set(), 'intrinsic': set()}
    for text in texts:
        for kind, name, number in TOP_LEVEL_NUMBER.findall(strip_comments(text)):
            space = 'intrinsic' if kind == 'Intrinsic' else 'operation'
            requested[name] = (space, int(number))
            taken[space].add(int(number))
            if kind == 'Attribute':
                taken[space].add(int(number) + 1)

    def lowest(space, pair):
        number = 1
        while number in taken[space] or (pair and number + 1 in taken[space]):
            number += 1
        return number

    for text in texts:
        for body in CLASS_BODY.findall(strip_comments(text)):
            for match in MEMBER_OR_FIELD.finditer(body):
                declared = accessor_declaration(match)
                if declared is None:
                    continue
                kind, name, rest = declared
                space = 'intrinsic' if kind == 'intrinsic' else 'operation'
                key = f'{space}_{name}'
                if key in out or name in system:
                    continue
                if name in requested and requested[name][0] == space:
                    number = requested[name][1]
                else:
                    number = lowest(space, kind == 'attribute')
                taken[space].add(number)
                out[key] = 0x80000000 | number
                if kind == 'attribute':
                    taken[space].add(number + 1)
                    if 'readOnly' not in rest:
                        out[f'operation_Set{name}'] = 0x80000000 | (number + 1)
    return out


def encode_fields(layout, values, extra=b'', length=None):
    """The inverse of decode_fields: field values back into a payload.

    Copying a payload reproduces a package; building one from values is what
    makes a different package possible. Everything is placed by the layout --
    words at their offsets, Booleans into their bits, the extra part after
    the fixed fields -- starting from zeros, so anything the layout does not
    describe stays zero rather than being carried over from somewhere.

    `values` maps field name to the integer that was read out of it, which is
    what `decode_fields` reports as `raw`; a Boolean takes True or False.
    """
    size = length if length is not None else layout['fixed_bytes'] + len(extra)
    out = bytearray(size)
    for field in layout['fields']:
        if field['name'] not in values:
            continue
        value = values[field['name']]
        at = field['offset']
        if field['bit'] is not None:
            if at < size and value:
                out[at] |= 0x80 >> field['bit']
            continue
        width = field['size']
        if at + width > size:
            continue
        # A definition file writes -1 for a colour, and a field holds it as
        # the bit pattern rather than as a sign, so it is masked to width.
        out[at:at + width] = (int(value) & ((1 << (width * 8)) - 1)) \
            .to_bytes(width, 'big')
    if extra:
        at = layout['fixed_bytes']
        out[at:at + len(extra)] = extra[:max(0, size - at)]
    return bytes(out)


def encode_elements(elements, stride=WORD):
    """A list's elements, as the bytes that follow its fields."""
    return b''.join((int(e) & ((1 << (stride * 8)) - 1)).to_bytes(stride, 'big')
                    for e in elements)


def decode_extra(data, start, length, layout, fields):
    """A list's elements, which follow its fields.

    Classes that say `uses extra` carry a variable part, and for the lists it
    is their elements: Counter's SoftwarePackage has seventy-two bytes of
    fields and a `length` of 32, and its payload is exactly two hundred --
    seventy-two plus thirty-two references. A stride of four is assumed only
    because every element seen so far is a reference; a class carrying its
    own `stride` field says so and that is used instead.
    """
    fixed = layout['fixed_bytes']
    if fixed >= length:
        return None
    by_name = {f['name']: f for f in fields}
    count = by_name.get('length', {}).get('raw')
    stride = by_name.get('stride', {}).get('raw') or WORD
    room = length - fixed
    if not count or not stride or count * stride > room:
        # Text, OctetString, Image, Sound and Code all land here: their extra
        # part is bytes rather than a list of anything, and none of them
        # declares a field that says how to read it. The bytes are offered as
        # they are, with the printable ones shown, and no structure claimed.
        raw = data[start + fixed:start + fixed + room]
        return {'offset': fixed, 'bytes': room, 'elements': None,
                'note': 'not a list this class describes',
                'printable': ''.join(chr(c) if 32 <= c < 127 else '.'
                                     for c in raw[:64])}
    elements, raw_elements = [], []
    for index in range(count):
        at = start + fixed + index * stride
        raw = int.from_bytes(data[at:at + stride], 'big')
        raw_elements.append(raw)
        elements.append(describe_word(raw) if stride == WORD else raw)
    # Both, because what an element means depends on the class: a field list's
    # are type descriptors, and describing one as a reference or an indexical
    # because of its top bits loses the number a caller needs.
    return {'offset': fixed, 'bytes': room, 'stride': stride,
            'count': count, 'elements': elements,
            'raw_elements': raw_elements,
            'trailing_bytes': room - count * stride}


def describe_word(raw):
    """A word in a field, said plainly.

    The top byte carries the kind: references and indexicals both have the
    top bit set and the packages tell them apart by it -- b0 on every
    reference in the cookbook, and the indexicals the generated headers push
    as literals on everything else.
    """
    if raw == 0:
        return 'nil'
    if raw >> 24 == 0xB0:
        return f'object {raw & 0xFFFFFF}'
    if raw & 0x80000000:
        return f'indexical {raw:08x}'
    return raw
