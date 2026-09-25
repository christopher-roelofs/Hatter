#!/usr/bin/env python3
"""Read-only inspector for 68k Magic Cap package clusters (type CLUS).

This decodes the container the original ObjectMaker wrote: a fixed header, a
chain of object records, 68k code carrying its MacsBug symbols, and the offset
tables at the end. It is not a validator and not a writer. Fields that have
not been independently confirmed are reported raw rather than named, because a
plausible name for an unread field is worse than no name at all -- it gets
believed.

What "confirmed" means here is the cookbook source/binary pairs under
software/68k/extracted/cookbook. Each example ships its ObjectMaker
definitions beside the package that was built from them, so a decode can be
checked against a statement of what the package is meant to contain: the
definitions name every class and every instance, and the C names every method.

Usage:
    inspect_package.py <package> [...]        one line per object
    inspect_package.py --json <package>       the whole decode
    inspect_package.py --code <package>       just the methods and call sites
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from classdefs import (WORD, Definitions, LayoutError, decode_extra,
                       decode_field_element, decode_fields, describe_word,
                       package_field_offsets, read_string_table)
from profiles import header_directories

# Where the heap starts. Everything before it is the header below, whose
# constant words are the same in all fourteen cookbook packages.
HEAP_START = 0x44

# ClassNumbers.Def: `Class Code 477;`. Held as the number rather than the name
# so that code is still found when the SDK tables are not beside the package.
CODE_CLASS = 477

# A5-relative call vectors, from the code the SDK's own examples compile to.
# The displacement is the whole identity of the call: the selector is in D2
# for an ordinary dispatch, and the class and operation are in D0 and D2 for
# an inherited one, so which vector is jumped through is what says how to
# read the registers set just before it.
CALL_VECTORS = {
    0xFFFA: 'dispatch',        # -6(A5): selector in D2, receiver on the stack
    0xFFDA: 'inherited',       # -38(A5): class in D0, operation in D2
    0xFFD0: 'intrinsic',       # -48(A5): intrinsic number in D0
}

JSR_A5 = 0x4EAD                # JSR d16(A5)
MOVE_W_IMM_D2 = 0x343C         # MOVE.W #imm,D2
MOVE_W_IMM_D0 = 0x303C         # MOVE.W #imm,D0
MOVEQ_D2 = 0x7400              # MOVEQ #imm8,D2, imm in the low byte
MOVE_L_IMM_PUSH = 0x2F3C       # MOVE.L #imm32,-(SP)


# The SDK's own number tables, which are the only naming authority used here.
# Nothing is named from a guess about what a number looks like: a class is
# called ObjectList because ClassNumbers.Def says 29 is ObjectList, and when
# the tables are not present the numbers are printed bare.
NUMBER_TABLES = {
    'class': ('ClassNumbers.Def', 'Class'),
    'operation': ('OperationNumbers.Def', 'Operation'),
    'intrinsic': ('IntrinsicNumbers.Def', 'intrinsic'),
    # An attribute is declared in the same file and shares the operation
    # number space -- `Attribute SendSize 4414;` -- and a definition file
    # writes it the same way, as `operation_SendSize`.
    'attribute': ('OperationNumbers.Def', 'Attribute'),
}
# Relative to the checkout rather than to wherever this is run from, so the
# names come out the same from the repository root and from this directory.
SDK_INTERFACES = Path(__file__).resolve().parents[2] / (
    'software/68k/extracted/CW7-Magic-MPW/CodeWarrior Magic%2FMPW Installer'
    '/MagicDeveloper/Interfaces')


class FormatError(ValueError):
    pass


def load_numbers(interfaces=SDK_INTERFACES):
    """Number to name, read out of the SDK interface definitions.

    Each line is `<keyword> <Name> <number>;` with Macintosh line endings.
    The keyword's case is not consistent -- OperationNumbers.Def has 57
    lowercase `operation` lines among its 2257 -- so it is matched either way.
    Missing tables are not an error: the inspector's job is to read a package,
    and it reads the same one whether or not the SDK is beside it.
    """
    tables = {}
    for kind, (filename, keyword) in NUMBER_TABLES.items():
        names = {}
        path = Path(interfaces) / filename
        if path.exists():
            text = path.read_bytes().decode('mac-roman').replace('\r', '\n')
            for line in text.split('\n'):
                parts = line.strip().rstrip(';').split()
                if (len(parts) == 3 and parts[0].lower() == keyword.lower()
                        and parts[2].isdigit()):
                    names[int(parts[2])] = parts[1]
        # CW8 ships the number tables as C preprocessor constants in the
        # precompiled system-interface headers rather than as *.Def files.
        # Keep this fallback table-specific: operation and intrinsic names
        # are needed to decode code-bearing packages, not just class names.
        if not names:
            header_name = {
                'class': 'ClassNumbers.h',
                'operation': 'OperationNumbers.h',
                'intrinsic': 'OperationNumbers.h',
                'attribute': 'OperationNumbers.h',
            }[kind]
            prefix = {
                'class': '',
                'operation': 'operation_',
                'intrinsic': 'intrinsic_',
                'attribute': 'attribute_',
            }[kind]
            for directory in header_directories(interfaces):
                header = Path(directory) / header_name
                if not header.exists():
                    continue
                text = header.read_bytes().decode('mac-roman').replace('\r', '\n')
                for line in text.split('\n'):
                    parts = line.strip().split()
                    if len(parts) != 3 or parts[0] != '#define':
                        continue
                    name, value = parts[1], parts[2]
                    if kind == 'class':
                        if not name.endswith('_') or name.endswith('Globals_'):
                            continue
                        name = name[:-1]
                    elif not name.startswith(prefix):
                        continue
                    else:
                        name = name[len(prefix):]
                    try:
                        names[int(value, 0)] = name
                    except ValueError:
                        pass
                if names:
                    break
        tables[kind] = names
    return tables


def require(condition, message):
    if not condition:
        raise FormatError(message)


def u32(data, offset):
    require(0 <= offset <= len(data) - 4, f'truncated word at {offset:#x}')
    return struct.unpack_from('>I', data, offset)[0]


def u16(data, offset):
    require(0 <= offset <= len(data) - 2, f'truncated halfword at {offset:#x}')
    return struct.unpack_from('>H', data, offset)[0]


# The three words every cluster header carries unchanged. Used to find one
# inside something else, which is all that is done with them.
CLUSTER_SIGNATURE = bytes.fromhex('000fffff01c0000300070000')
SIGNATURE_AT = 0x1c


def find_cluster(data):
    """A cluster, wherever it is, and where it starts.

    A `.cap` is a distribution envelope -- "MCap", a name, then a tagged
    "FrozenPackage" -- with the cluster somewhere inside it. The envelope is
    not read here: the cluster is found by the three constant words its
    header always carries and then checked the ordinary way, by whether its
    own length fits where it was found. That is enough to inspect one and
    honest about what it is, which reading a length out of an envelope this
    does not understand would not be.
    """
    if len(data) >= HEAP_START:
        try:
            decode_header(data)
            return data, 0
        except FormatError:
            pass
    start = 0
    while True:
        found = data.find(CLUSTER_SIGNATURE, start)
        if found < 0:
            return data, 0          # let the ordinary error be raised
        base = found - SIGNATURE_AT
        if base >= 0:
            total = struct.unpack_from('>I', data, base + 0x10)[0]
            if 0 < total <= len(data) - base:
                return data[base:base + total], base
        start = found + 1


def decode_header(data):
    """The fixed prefix. Only the fields that move between packages are named.

    total_bytes is the file's own length and heap_end is where the object
    chain stops and the offset tables begin; both were read off all fourteen
    examples. highest_object_id is the largest id the heap actually uses, and
    that is all it is: it is not a count of objects, and neither is the word
    at 0x2c, which is only ever one less than it while the number of records
    is something else again. The three constant words are carried through
    unnamed: they are identical everywhere, so nothing in this corpus says
    what they select.
    """
    require(len(data) >= HEAP_START, 'shorter than a package header')
    total = u32(data, 0x10)
    heap_end = u32(data, 0x14)
    require(total == len(data),
            f'header length {total:#x} is not the file length {len(data):#x}')
    require(HEAP_START < heap_end <= total,
            f'heap end {heap_end:#x} outside the file')
    return {
        'total_bytes': total,
        'heap_end': heap_end,
        'highest_object_id': u32(data, 0x34),
        'constant_words': [f'{u32(data, off):08x}' for off in (0x1c, 0x20, 0x24)],
        'unnamed_words': {f'{off:#04x}': f'{u32(data, off):08x}'
                          for off in (0x00, 0x04, 0x08, 0x0c, 0x18, 0x28, 0x2c,
                                      0x30, 0x38, 0x3c, 0x40)},
    }


def walk_objects(data, heap_end):
    """The object chain, which is what makes the rest of the file readable.

    Each record opens with its own length, so the heap is walked rather than
    indexed. That the walk lands exactly on the end is the check that the
    layout below is the real one and not a pattern that happens to fit the
    first few records.

    Where it lands is either the end itself or a zero word four bytes short
    of it. The cookbook examples all have that word and the two shipping
    packages have none, so treating it as a terminator -- which is what was
    done while only the cookbook was in hand -- rejects real software.
    """
    objects = []
    offset = HEAP_START
    while offset + 12 <= heap_end:
        length, class_number, tag, flags, object_id = struct.unpack_from(
            '>IHHHH', data, offset)
        require(length >= 12, f'object at {offset:#x} is shorter than its header')
        require(offset + length <= heap_end,
                f'object at {offset:#x} runs past the heap')
        objects.append({
            'offset': offset,
            'length': length,
            'class_number': class_number,
            'tag': tag,
            # ObjectMaker computes these bits as (4 - (n & 3)) & 3 over the
            # record's real length: they say how many of the bytes at the end
            # are padding to a multiple of four, which is why only 0 to 3 are
            # ever seen. Checked against every string table in the corpus,
            # where 12 + the content the table itself describes + this comes
            # to exactly the record length.
            'padding_bytes': (tag >> 8) & 0xF,
            'flags': flags,
            'id': object_id,
            'payload': span(data, offset + 12, offset + length),
        })
        offset += length
    if offset == heap_end - 4:
        require(u32(data, offset) == 0,
                f'four bytes left at {offset:#x} and they are not a zero word')
    else:
        require(offset == heap_end,
                f'object chain ended at {offset:#x}, not at {heap_end:#x}')
    return objects


def span(data, start, end):
    payload = data[start:end]
    return {'offset': start, 'length': end - start,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'prefix_hex': payload[:16].hex()}


def decode_trailer(data, heap_end):
    """The tables after the heap.

    The first word is the trailer's own length, and it runs to the end of the
    file. Most of what follows are file offsets with the top bit set; the ones
    that land twelve bytes before an object's id word are that object's
    record, which is how they were recognised. The rest are reported as they
    are read rather than sorted into meanings this corpus does not settle.
    """
    length = u32(data, heap_end)
    require(heap_end + length == len(data),
            f'trailer length {length:#x} does not reach the end of the file')
    entries = []
    for offset in range(heap_end + 4, len(data) - 3, 4):
        word = u32(data, offset)
        entries.append({'offset': offset, 'word': f'{word:08x}',
                        'target': word & 0x7FFFFFFF if word & 0x80000000 else None})
    return {'offset': heap_end, 'length': length, 'entries': entries}


def read_macsbug_symbol(data, offset, limit):
    """A procedure name as 68k Mac compilers wrote them.

    The byte after the procedure has its top bit set and gives the length, and
    the name follows. Anything that is not a plain identifier is refused: code
    is full of bytes with the top bit set, and accepting them would invent
    procedures out of operands.
    """
    if offset >= limit:
        return None
    marker = data[offset]
    if not marker & 0x80:
        return None
    length = marker & 0x7F
    if not 1 <= length <= 63 or offset + 1 + length > limit:
        return None
    name = data[offset + 1:offset + 1 + length]
    # Plain ASCII only. Python calls 'µ' and '²' alphanumeric, and the code
    # these sit in is full of such bytes as operands: accepting them turned
    # two of the fourteen examples into procedures that are not there.
    if not all(c < 0x80 and (c in b'_.' or chr(c).isalnum()) for c in name):
        return None
    return name.decode('ascii'), 1 + length


def scan_code(data, start, end):
    """Methods and the calls they make, from the code an object carries.

    Procedures are found by their trailing symbol rather than by disassembling
    forwards: the symbol is unambiguous where an instruction boundary is not,
    and it is the name the SDK's own sources gave the method, so the result
    can be read against them.

    Call sites are recognised only in the exact shapes the generated
    interfaces emit -- an immediate into D2 or D0 and then a JSR through a
    known A5 vector. A call whose selector was computed rather than written
    in is reported with the vector and no number, because guessing one would
    be inventing a call the package does not make.
    """
    methods, calls = [], []
    body_start = start
    offset = start
    while offset < end - 1:
        word = u16(data, offset)
        if word == JSR_A5 and offset + 4 <= end:
            displacement = u16(data, offset + 2)
            call = {'offset': offset, 'vector': f'{displacement:04x}',
                    'kind': CALL_VECTORS.get(displacement, 'unknown-vector')}
            # What was loaded immediately before decides how it is read.
            if offset >= start + 4:
                previous = u16(data, offset - 4)
                immediate = u16(data, offset - 2)
                if previous == MOVE_W_IMM_D2:
                    call['selector'] = f'{immediate:04x}'
                elif previous == MOVE_W_IMM_D0:
                    call['operand_d0'] = f'{immediate:04x}'
            if offset >= start + 2 and u16(data, offset - 2) & 0xFF00 == MOVEQ_D2:
                call['selector'] = f'{u16(data, offset - 2) & 0xFF:04x}'
            calls.append(call)
            offset += 4
            continue
        symbol = read_macsbug_symbol(data, offset, end)
        if symbol:
            name, consumed = symbol
            methods.append({'name': name, 'offset': body_start,
                            'bytes': offset - body_start})
            offset += consumed
            while offset < end and data[offset] == 0:   # padding to a word
                offset += 1
            body_start = offset
            continue
        offset += 2
    return methods, calls


def find_indexicals(data, start, end):
    """Literal indexical references, pushed whole by the generated headers.

    An indexical is a fixed thirty-two bit name the ROM resolves, so it
    appears in code as an immediate push rather than as anything computed.
    Only the push form is reported.
    """
    found = []
    for offset in range(start, end - 5, 2):
        if u16(data, offset) == MOVE_L_IMM_PUSH:
            value = u32(data, offset + 2)
            if value & 0x80000000:
                found.append({'offset': offset, 'value': f'{value:08x}'})
    return found


def name_call(call, tables):
    """Put a name to a call site, where the number is one the SDK knows.

    A selector with the top bit set is the package's own -- it is an index
    into what this package defines, so no system table can name it and it is
    left as the number the code carries.
    """
    if 'selector' in call:
        selector = int(call['selector'], 16)
        if selector & 0x8000:
            call['name'] = f'package operation {selector & 0x7FFF}'
        elif call['kind'] != 'unknown-vector':
            call['name'] = tables['operation'].get(selector)
    if 'operand_d0' in call and call['kind'] == 'intrinsic':
        call['name'] = tables['intrinsic'].get(int(call['operand_d0'], 16))
    return call


def read_object_fields(data, entry, definitions, layouts):
    """An object's payload as named fields, when the class is one we have.

    A class the definitions do not carry is left as bytes. So is one whose
    ancestry cannot be resolved: a field list short by one ancestor puts
    every offset after it wrong, and would do so without complaining.
    """
    name = entry['class_name']
    if not name or name not in definitions.classes:
        return None
    if name not in layouts:
        try:
            layouts[name] = definitions.layout(name)
        except LayoutError as error:
            layouts[name] = str(error)
    layout = layouts[name]
    if isinstance(layout, str):
        return {'unresolved': layout}
    body = entry['payload']
    fields = decode_fields(data, body['offset'], body['length'], layout,
                           definitions)
    extra = decode_extra(data, body['offset'], body['length'], layout, fields)
    return {'fields': fields, 'extra': extra,
            'fixed_bytes': layout['fixed_bytes']}


# A Class record counts its own tables from four bytes into its payload, not
# from the start of it. Counter's implSuperOffset of 60 and methodOffset of 76
# both land exactly on their tables from there and from nowhere else, and the
# same base holds for every class record in the fourteen examples.
CLASS_TABLE_BASE = 4
METHOD_ENTRY = 16
SUPER_ENTRY = 16


def name_class(number, tables):
    """A class number as a name. Zero is no class, which a root class has."""
    if number == 0:
        return 'none'
    if number & 0x8000:
        return f'package class {number & 0x7FFF}'
    return tables['class'].get(number)


def decode_class_record(data, entry, tables):
    """What a package's own class says about itself.

    A Class record carries the class it inherits from, the methods it defines
    and the interfaces it answers -- which is the whole of what ObjectMaker
    had to write for `Define Class CounterScene; inherits from Scene;` and
    three operations, and so the whole of what anything generating a package
    would have to write in its place.

    A method entry is four words: the operation, then either where its code
    is and which Code object holds it, or -- for a field's generated getter
    and setter -- the class number and an accessor word in place of those.
    """
    fields = {f['name']: f for f in entry['contents']['fields']}

    def value(name):
        field = fields.get(name)
        return None if not field or field.get('absent') else field.get('raw')

    body = entry['payload']
    base = body['offset'] + CLASS_TABLE_BASE
    limit = body['offset'] + body['length']
    out = {'number': value('number'), 'instance_size': value('instanceSize')}

    # Each implementation superclass takes a sixteen-byte entry, not a word:
    # the method table always begins sixteen times the count past the super
    # list, in every class record in the corpus. Reading them as words turned
    # one entry into four supers, three of them the zeroes that follow the
    # class number.
    supers, count, at = [], value('implSuperCount'), value('implSuperOffset')
    if count and at is not None:
        for index in range(count):
            offset = base + at + index * SUPER_ENTRY
            if offset + 4 > limit:
                break
            number = u32(data, offset)
            supers.append({'class_number': number,
                           'class_name': name_class(number, tables)})
    out['inherits_from'] = supers

    methods, count, at = [], value('methodCount'), value('methodOffset')
    if count and at is not None:
        for index in range(count):
            offset = base + at + index * METHOD_ENTRY
            if offset + METHOD_ENTRY > limit:
                break
            selector, second, third, fourth = struct.unpack_from('>IIII', data, offset)
            method = {'offset': offset, 'selector': f'{selector:08x}'}
            if selector & 0x80000000:
                method['name'] = f'package operation {selector & 0x7FFFFFFF}'
            else:
                method['name'] = tables['operation'].get(selector)
            if fourth >> 24 == 0xB0:
                method['code_object'] = fourth & 0xFFFFFF
                method['code_offset'] = second
                # Zero in all but five of the corpus's methods, and what it
                # selects is not established, so it is reported rather than
                # left out: three overrides of CanApply carry 0x01000000 and
                # BarChart's two hand-written accessors carry 0x8000.
                if third:
                    method['method_flags'] = third
            else:
                # A generated accessor: no code of its own, and the words
                # that would say where it is say which class and which
                # accessor instead. Which is which is not established.
                method['accessor'] = {'class_number': second,
                                      'word': f'{third:08x}'}
            methods.append(method)
    out['methods'] = methods

    # A reference word, so the id is what is left once the 0xB0 that marks it
    # as one is taken off. Zero is a class with no fields of its own.
    field_list = value('fieldList') or 0
    out['field_list'] = field_list & 0xFFFFFF if field_list >> 24 == 0xB0 else None
    interfaces, count = [], value('interfaceCount')
    if count and methods:
        # Straight after the method table, and the first of them is Object:
        # taking the list to start a word later dropped exactly one entry and
        # left the count one short, which is how the alignment was settled.
        at = methods[-1]['offset'] + METHOD_ENTRY
        for index in range(count):
            offset = at + index * 4
            if offset + 4 > limit:
                break
            number = u32(data, offset)
            interfaces.append({'class_number': number,
                               'class_name': name_class(number, tables)})
    out['interfaces'] = interfaces
    return out


def name_hash(name):
    """The byte a list entry carries beside a name, hashed the ROM's own way.

    `Device/System.Equates` names a routine
    `OperationList_ByteCaseInsensitiveHash`, and that file turns out to be a
    symbol table for the PIC-1000 ROM (see `symbols.py`), so the algorithm was
    read out of the ROM rather than guessed at:

        h = lower(name[0])
        for each later character: h = rol8(h, 2) ^ lower(character)
        return h or 1                    -- zero is reported as one

    `_GoLower` next to it lowercases only A-Z, which is why this uses a byte
    comparison rather than `str.lower()` on anything but ASCII.
    """
    letters = bytearray(name.encode('latin-1'))
    for index, byte in enumerate(letters):
        if 0x41 <= byte <= 0x5A:
            letters[index] = byte + 0x20
    if not letters:
        return 0
    value = letters[0]
    for byte in letters[1:]:
        value = (((value << 2) | (value >> 6)) & 0xFF) ^ byte
    return value or 1


def decode_class_list(data, entry, tables):
    """The list the loader installs a package's classes from.

    `DefFiles/Runtime.Def` declares the fixed part outright -- `actualCount`,
    `maxCount`, three reserved halfwords and an `extraSentinel` that it says
    "must be 0x8000" -- so only the entries after it had to be worked out.
    Each is sixteen bytes and repeats, in the form the loader wants it, what
    the `Class` record it points at already says:

        +0  the Class record, as an ordinary 0xB0 reference
        +4  the bytes the class adds, then its instance size
        +8  the class it inherits from, or zero where it has more than one
            implementation parent, or none at all
       +12  zero, the hash of the class's name, then the inherited bytes

    The two sizes carry bit 15 for a mixin -- Circuits declares three in
    `Mixins.Def` and they are the only records in the corpus that set it.
    Everything but the hash is checked against the `Class` record it refers
    to, which is a different part of the file written by a different piece of
    ObjectMaker, so the two agreeing is the evidence for this layout.
    """
    payload = entry['payload']
    at, limit = payload['offset'], payload['offset'] + payload['length']
    require(limit - at >= 16, 'class list shorter than its fixed part')
    out = {'actual_count': u32(data, at), 'max_count': u32(data, at + 4),
           'sentinel': u16(data, at + 14), 'entries': []}
    for index in range((limit - at - 16) // 16):
        base = at + 16 + index * 16
        size, inherited = u16(data, base + 6), u16(data, base + 14)
        out['entries'].append({
            'index': index,
            'class_record': u32(data, base) & 0xFFFFFF,
            'own_bytes': u16(data, base + 4),
            'instance_size': size & 0x7FFF,
            'mixin': bool(size & 0x8000),
            'inherits_from': u32(data, base + 8),
            'inherits_name': name_class(u32(data, base + 8), tables),
            'name_hash': data[base + 13],
            'inherited_bytes': inherited & 0x7FFF,
        })
    return out


def decode_operation_list(data, entry):
    """The list the loader installs a package's own operations from.

    Eight bytes an entry, indexed by the operation's own number: entry n is
    operation 0x8001 + n, and a number ObjectMaker reserved but nothing uses
    -- a read-only attribute still reserves its setter -- is a pair of zero
    words rather than a gap, which is why `actualCount` is not the number of
    operations. An entry is

        +0  the MagicOperation giving the signature, as a 0xB0 reference
        +4  a kind byte, the hash of the operation's name, then two flag bytes

    The hash is the same one the classes use. The kind byte is zero for a
    plain operation and carries a type in its low bits for an attribute's
    getter; what those bits select has not been established, so it is reported
    raw.
    """
    payload = entry['payload']
    at, limit = payload['offset'], payload['offset'] + payload['length']
    require(limit - at >= 8, 'operation list shorter than its fixed part')
    out = {'actual_count': u32(data, at), 'entries': []}
    for index in range((limit - at - 8) // 8):
        base = at + 8 + index * 8
        reference = u32(data, base)
        if not reference and not u32(data, base + 4):
            out['entries'].append({'index': index, 'number': 0x8001 + index,
                                   'reserved': True})
            continue
        out['entries'].append({
            'index': index,
            'number': 0x8001 + index,
            'operation': reference & 0xFFFFFF,
            'kind': data[base + 4],
            'name_hash': data[base + 5],
            'flags': u16(data, base + 6),
        })
    return out


def attach_field_names(data, objects, tables):
    """Give each class's fields their names, from the table they all index.

    A FieldList says how many fields a class has and where their names start;
    the names themselves are in one StringList the whole package shares, named
    by the `strings` field that every one of those lists carries. So the names
    can only be put on once every object has been walked, which is why this
    happens here rather than while each class is read.
    """
    by_id = {entry['id']: entry for entry in objects}

    def field_of(entry, name):
        for field in entry.get('contents', {}).get('fields', []):
            if field['name'] == name:
                return field.get('raw')
        return None

    tables_by_id = {}
    for entry in objects:
        if entry['class_name'] != 'FieldList' or 'contents' not in entry:
            continue
        holder = by_id.get(field_of(entry, 'strings'))
        if holder is None or holder['class_name'] != 'StringList':
            continue
        if holder['id'] not in tables_by_id:
            tables_by_id[holder['id']] = read_string_table(data, holder) or []
        names = tables_by_id[holder['id']]
        first, count = field_of(entry, 'firstStringEntry'), field_of(entry, 'length')
        extra = entry['contents'].get('extra') or {}
        elements = extra.get('raw_elements') or []
        described = []
        for index, value in enumerate(elements):
            field = decode_field_element(value)
            position = (first or 1) - 1 + index
            field['name'] = names[position] if position < len(names) else None
            if 'class_number' in field:
                field['class_name'] = name_class(field['class_number'], tables)
            described.append(field)
        entry['fields_described'] = described
        if count is not None and len(described) != count:
            entry['fields_described_note'] = 'element count differs from length'

    for entry in objects:
        record = entry.get('class_record')
        if not record:
            continue
        holder = by_id.get(record.get('field_list'))
        if holder is not None and 'fields_described' in holder:
            record['fields'] = holder['fields_described']
        placed, added = package_field_offsets(record.get('fields') or [])
        for field, where in zip(record.get('fields') or [], placed):
            field.update(where)
        record['own_bytes'] = added
        # What is left is the superclass's own instances, which nothing here
        # can look up; that it comes out a whole number of words is the check
        # that the fields were placed the way the class placed them.
        if record.get('instance_size') is not None:
            inherited = record['instance_size'] - added
            record['inherited_bytes'] = inherited
            if inherited < 0 or inherited % 4:
                record['inherited_bytes_note'] = 'not a whole number of words'


def read_package_instances(data, objects):
    """Instances of the classes the package defines, using what it says they are.

    Nothing outside the package can describe these -- the SDK has never heard
    of `CounterScene` -- but the package describes them itself, and by this
    point that description has been read: which fields, of what type, in what
    order, and how many bytes of inherited instance they sit past. So an
    instance can be read with the class's own account of itself, which is
    also a check on that account: the fields have to land inside the object
    and the inherited part has to be there in front of them.
    """
    records = {}
    for entry in objects:
        record = entry.get('class_record')
        if record and record.get('fields'):
            records[record['number']] = record

    for entry in objects:
        number = entry['class_number']
        if not number & 0x8000 or number not in records:
            continue
        record = records[number]
        base = record.get('inherited_bytes')
        body = entry['payload']
        if base is None or base > body['length']:
            continue
        read = []
        for field in record['fields']:
            at = base + field['offset']
            if field.get('bit') is not None:
                if at >= body['length']:
                    continue
                byte = data[body['offset'] + at]
                read.append({'name': field['name'], 'type': field['type'],
                             'offset': at, 'bit': field['bit'],
                             'value': bool(byte & (0x80 >> field['bit']))})
                continue
            size = field.get('bytes') or WORD
            if at + size > body['length']:
                continue
            raw = int.from_bytes(
                data[body['offset'] + at:body['offset'] + at + size], 'big')
            read.append({'name': field['name'], 'type': field['type'],
                         'offset': at, 'bytes': size, 'raw': raw,
                         'value': describe_word(raw) if size == WORD and
                         field['type'] == 'reference' else raw})
        if read:
            entry['instance_fields'] = {'class_number': number,
                                        'inherited_bytes': base,
                                        'fields': read}


def inspect(data, tables=None, definitions=None):
    tables = tables if tables is not None else load_numbers()
    data, container_offset = find_cluster(data)
    header = decode_header(data)
    objects = walk_objects(data, header['heap_end'])
    layouts = {}
    for entry in objects:
        class_number = entry['class_number']
        entry['class_name'] = name_class(class_number, tables)
        if definitions is not None:
            contents = read_object_fields(data, entry, definitions, layouts)
            if contents:
                entry['contents'] = contents
            if entry['class_name'] == 'Class' and contents \
                    and 'unresolved' not in contents:
                entry['class_record'] = decode_class_record(data, entry, tables)
        if entry['class_name'] == 'ClassList':
            entry['class_list'] = decode_class_list(data, entry, tables)
        elif entry['class_name'] == 'OperationList':
            entry['operation_list'] = decode_operation_list(data, entry)
        # Only what the class table calls Code. Sound and Image payloads are
        # full of bytes that pass for a procedure name followed by something
        # that passes for a JSR, so scanning every object invented methods
        # inside Snake's sounds and pictures.
        if class_number != CODE_CLASS:
            continue
        body = entry['payload']
        start, end = body['offset'], body['offset'] + body['length']
        methods, calls = scan_code(data, start, end)
        if methods:
            entry['code'] = {
                'methods': methods,
                'calls': [name_call(call, tables) for call in calls],
                'indexicals': find_indexicals(data, start, end),
            }
    # Only once every object is walked: the names a class's fields go by are
    # in a table the whole package shares, which may be any object at all.
    if definitions is not None:
        attach_field_names(data, objects, tables)
        read_package_instances(data, objects)
    result = {'bytes': len(data), 'header': header, 'objects': objects,
              'trailer': decode_trailer(data, header['heap_end'])}
    if container_offset:
        result['found_at'] = container_offset
    return result


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('packages', nargs='+', type=Path)
    parser.add_argument('--json', action='store_true', help='the whole decode')
    parser.add_argument('--code', action='store_true',
                        help='only the objects that carry code')
    parser.add_argument('--fields', action='store_true',
                        help='read each object as the fields its class declares')
    parser.add_argument('--profile', default='cw7',
                        help='68k interface profile: cw7, 1.0, 1.5, '
                             'universal, or an interface directory')
    args = parser.parse_args(argv)

    from profiles import resolve
    try:
        interfaces = resolve(args.profile)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    tables = load_numbers(interfaces)

    definitions = None
    if args.fields or args.json:
        deffiles = interfaces / 'DefFiles'
        if deffiles.is_dir():
            definitions = Definitions(deffiles)
        elif args.fields:
            print(f'{deffiles} is not here; fields cannot be read',
                  file=sys.stderr)
            return 1

    for path in args.packages:
        try:
            result = inspect(path.read_bytes(), tables=tables,
                             definitions=definitions)
        except FormatError as error:
            print(f'{path}: {error}', file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(result, indent=2))
            continue
        header = result['header']
        print(f"{path.name}: {result['bytes']} bytes, "
              f"{len(result['objects'])} objects, "
              f"highest id {header['highest_object_id']}")
        for entry in result['objects']:
            if args.code and 'code' not in entry:
                continue
            name = entry['class_name'] or f"class {entry['class_number']}"
            print(f"  {entry['offset']:#08x} id={entry['id']:<5} {name:<22} "
                  f"tag={entry['tag']:#06x} flags={entry['flags']:#06x} "
                  f"{entry['length']:>6} bytes")
            for method in entry.get('code', {}).get('methods', []):
                print(f"      {method['name']} ({method['bytes']} bytes)")
                for call in entry['code']['calls']:
                    if not method['offset'] <= call['offset'] < \
                            method['offset'] + method['bytes']:
                        continue
                    what = call.get('selector') or call.get('operand_d0') or '?'
                    label = call.get('name') or ''
                    vector = '' if call['kind'] != 'unknown-vector' \
                        else f" [{call['vector']}]"
                    print(f"        {call['kind']:<10}{vector} {what} {label}")
            record = entry.get('class_record')
            if record:
                supers = ', '.join(str(s['class_name'])
                                   for s in record['inherits_from']) or 'nothing'
                print(f"      class {record['number']:#06x} inherits from {supers}"
                      f", instances {record['instance_size']} bytes")
                for field in record.get('fields', []):
                    points_at = (f" -> {field.get('class_name')}"
                                 if 'class_number' in field else '')
                    flags = f" ({', '.join(field['flags'])})" if field['flags'] else ''
                    at = ''
                    if field.get('offset') is not None:
                        at = f"  at +{record['inherited_bytes']}+{field['offset']}"
                        if field.get('bit') is not None:
                            at += f" bit{field['bit']}"
                    print(f"        field {str(field['name']):<20}"
                          f"{field['type'] or field['raw']}{points_at}{flags}{at}")
                for method in record['methods']:
                    if 'code_object' in method:
                        where = (f"object {method['code_object']}"
                                 f" +{method['code_offset']:#x}")
                    else:
                        where = f"generated accessor {method['accessor']['word']}"
                    print(f"        {str(method['name']):<26} {where}")
                names = [str(i['class_name']) for i in record['interfaces']]
                print(f"        answers to: {', '.join(names)}")
            if not args.fields:
                continue
            contents = entry.get('contents')
            if not contents:
                continue
            if 'unresolved' in contents:
                print(f"      fields not read: {contents['unresolved']}")
                continue
            for field in contents['fields']:
                if field.get('absent'):
                    continue
                where = f"+{field['offset']:#05x}"
                if field.get('bit') is not None:
                    where += f" bit{field['bit']}"
                print(f"      {where:<12} {field['name']:<26} {field['value']}")
            extra = contents['extra']
            if extra and extra.get('elements'):
                shown = [(i, e) for i, e in enumerate(extra['elements'], 1)
                         if e != 'nil']
                print(f"      +{extra['offset']:#05x}       "
                      f"{extra['count']} elements, {len(shown)} set")
                for index, element in shown:
                    print(f"        [{index}] {element}")
            elif extra:
                print(f"      +{extra['offset']:#05x}       "
                      f"{extra['bytes']} further bytes, {extra.get('note','')}")
                if extra.get('printable', '').strip('.'):
                    print(f"        {extra['printable']!r}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
