#!/usr/bin/env python3
"""Emit a 68k Magic Cap package cluster.

The inspector reads one; this writes one. Everything it emits is computed from
the objects it is given -- the record headers, the heap end, the id table and
its free list, the padding counts -- rather than copied from anything, because
a writer that copies what it does not understand produces a file that works
only until something changes.

The test is `roundtrip.py --emit`: parse a real package, hand the objects
straight back here, and require the bytes to come out identical. Sixteen
packages do, including two nobody in this corpus wrote.

    header      0x44 bytes, described below
    records     each 12 bytes of header then its payload
    terminator  a zero word, if the original had one
    trailer     five words then one slot per object id

A record's length includes its header and is a multiple of four; the padding
that rounds it up is counted in the tag, which is where ObjectMaker puts it.
"""
import struct

HEAP_START = 0x44
TRAILER_HEADER_WORDS = 5
TRAILER_CONSTANT = 0xFFFF0088


class Object:
    """One record: what it is, what it holds, and the bits it carries.

    `tag_low` and `flags` are passed through rather than derived. Only the
    tag's padding bits are understood well enough to compute, and inventing
    the rest would be making up a file rather than writing one.
    """

    def __init__(self, object_id, class_number, payload, tag_low=0x88, flags=0):
        self.id = object_id
        self.class_number = class_number
        self.payload = bytes(payload)
        self.tag_low = tag_low
        self.flags = flags

    @property
    def padding(self):
        return (4 - (len(self.payload) & 3)) & 3

    @property
    def length(self):
        return 12 + len(self.payload) + self.padding

    def header(self):
        tag = (self.padding << 8) | self.tag_low
        return struct.pack('>IHHHH', self.length, self.class_number, tag,
                           self.flags, self.id)

    def emit(self):
        return self.header() + self.payload + bytes(self.padding)


def encode_string_table(definitions, names, extents=0):
    """A StringList's payload: its fields, then the names packed after them.

    The names are Pascal strings end to end, and `dataOffset` counts from
    four bytes into the payload -- the same base a Class record counts its
    tables from -- so it is the fixed part less those four.

    `extents` is a reference to a Buffer, and is nil in every table here
    below about a hundred names. The three largest carry one, so it is taken
    rather than assumed: a writer emitting a short table leaves it nil, and
    reproducing a long one needs the reference it had.
    """
    from classdefs import encode_fields
    layout = definitions.layout('StringList')
    data = b''.join(bytes([len(n)]) + n.encode('mac-roman') for n in names)
    return encode_fields(layout, {
        'length': len(names),
        'dataSize': len(data),
        'dataOffset': layout['fixed_bytes'] - 4,
        'extents': extents,
    }, data)


def encode_field_list(definitions, strings_id, first_entry, descriptors):
    """A FieldList's payload: how many fields, where their names start, and
    one descriptor a field.

    `strings_id` is the object id of the StringList the whole package shares,
    stored as a plain number rather than as a reference.
    """
    from classdefs import encode_elements, encode_fields
    layout = definitions.layout('FieldList')
    return encode_fields(layout, {
        'length': len(descriptors),
        'strings': strings_id,
        'firstStringEntry': first_entry,
    }, encode_elements(descriptors))


def field_descriptor(type_code, class_number=0, flags=0):
    """One FieldList element: what a field is, and what it points at."""
    return (class_number << 16) | ((type_code & 0xFF) << 8) | (flags & 0xFF)


SUPER_ENTRY = 16
METHOD_ENTRY = 16


def encode_class_record(definitions, values, supers, methods, interfaces):
    """A Class record's payload: its fields, then its three tables.

    The tables follow the fixed fields in order and run to the end of the
    payload, and the offsets the record carries for them count from four
    bytes into it -- so `implSuperOffset` is the fixed part less four, and
    the method table starts sixteen bytes per superclass after that.

    A superclass entry is the class number and twelve zero bytes; every one
    of the 124 in the corpus is. A method entry is four words, and they are
    taken as given: which words mean what depends on whether the method has
    code or is a generated accessor, and that belongs to whoever is
    describing the class rather than here.
    """
    from classdefs import encode_fields
    layout = definitions.layout('Class')
    super_offset = layout['fixed_bytes'] - 4
    method_offset = super_offset + SUPER_ENTRY * len(supers)

    tail = b''.join(struct.pack('>I', number) + bytes(SUPER_ENTRY - 4)
                    for number in supers)
    for entry in methods:
        tail += struct.pack('>IIII', *entry)
    tail += b''.join(struct.pack('>I', number) for number in interfaces)

    placed = dict(values)
    placed.update({
        'implSuperCount': len(supers), 'implSuperOffset': super_offset,
        'methodCount': len(methods), 'methodOffset': method_offset,
        'interfaceCount': len(interfaces),
    })
    return encode_fields(layout, placed, tail)


def make_object(definitions, tables, object_id, class_name, values=None,
                elements=None, extra=b'', tag_low=0x88, flags=0, stride=4,
                length=None):
    """A record built from what it is meant to contain, not from a copy.

    Give it a class the definitions describe and the values of that class's
    fields, and it places them: words at their offsets, Booleans into their
    bits, a list's elements after the fixed part. `extra` is for the classes
    whose variable part is content rather than structure -- Text, Image,
    Sound, Code -- where there is nothing to place and the bytes are the
    point.
    """
    from classdefs import encode_elements, encode_fields
    layout = definitions.layout(class_name)
    tail = encode_elements(elements, stride) if elements else extra
    # A record can be longer than its fields and its extra part account
    # for; where it is, the length is part of the description.
    payload = encode_fields(layout, values or {}, tail, length=length)
    number = next((n for n, name in tables['class'].items() if name == class_name),
                  None)
    if number is None:
        raise LookupError(f'no class number for {class_name!r}')
    return Object(object_id, number, payload, tag_low=tag_low, flags=flags)


CLUSTER_CONSTANTS = (0x000FFFFF, 0x01C00003, 0x00070000)


def cluster_checksum(objects, boot_id, terminator=True):
    """What a `PackageBoot` carries as its `clusterCRC`.

    Despite the name it is not a CRC: it is the bytes of the heap added up,
    leaving out the boot record's own payload -- which has to be left out,
    since the number is stored in it. None of the usual polynomials matches
    and a plain sum does, for all sixteen packages in the corpus.

    The heap is the records and the terminating word, so the sum runs over
    each record's header and payload, and the boot record contributes its
    twelve-byte header and nothing else.
    """
    total = 0
    for entry in objects:
        if entry.id == boot_id:
            total += sum(entry.header())
            continue
        total += sum(entry.emit())
    return total & 0xFFFFFFFF


def build_from_spec(definitions, tables, spec, **kwargs):
    """A package from a description of what is in it.

    Each entry names a class and gives what that class holds: field values by
    name, a list's `elements`, or `bytes` for the classes whose payload is
    content. Nothing is parsed and nothing is copied -- this is the path a
    package built from definitions takes, rather than one built by editing
    a package that already exists.

        [{'id': 2, 'class': 'ObjectList', 'values': {'length': 1},
          'elements': [0xB000000C]},
         {'id': 14, 'class': 'Text', 'bytes': b'About it\\0'}]

    `bytes` is what follows the fixed fields; `payload` is the whole of it,
    for a record this cannot describe any better than as the bytes it is.
    """
    objects = []
    for entry in spec:
        if 'payload' in entry:
            number = entry.get('class_number')
            if number is None:
                number = next((n for n, name in tables['class'].items()
                               if name == entry['class']), None)
            if number is None:
                raise LookupError(f"no class number for {entry['class']!r}")
            objects.append(Object(entry['id'], number, entry['payload'],
                                  tag_low=entry.get('tag_low', 0x88),
                                  flags=entry.get('flags', 0)))
            continue
        objects.append(make_object(
            definitions, tables, entry['id'], entry['class'],
            values=entry.get('values'), elements=entry.get('elements'),
            extra=entry.get('bytes', b''), stride=entry.get('stride', 4),
            length=entry.get('length'),
            tag_low=entry.get('tag_low', 0x88), flags=entry.get('flags', 0)))
    kwargs.setdefault('constant_words', CLUSTER_CONSTANTS)
    return build(objects, **kwargs)


def build(objects, constant_words, unnamed_words=None, terminator=True,
          free_ids=()):
    """A whole cluster, from the objects it is to contain.

    `free_ids` are ids below the highest that no object uses. They are not an
    error: a package that deleted something while it was being built leaves a
    hole, and the id table keeps those holes on a free list, so they have to
    be put back in the same order to reproduce a file that had them.
    """
    objects = list(objects)
    highest = max(o.id for o in objects) if objects else 0

    body = bytearray()
    offsets = {}
    at = HEAP_START
    for entry in objects:
        offsets[entry.id] = at
        body += entry.emit()
        at += entry.length
    if terminator:
        body += bytes(4)
        at += 4
    heap_end = at

    # The id table: a slot per id, holding the record or a link to the next
    # free slot. The two header words are where the chain starts and ends.
    slots = []
    for object_id in range(1, highest + 1):
        slots.append(0x80000000 | offsets[object_id] if object_id in offsets
                     else 0)
    # A free slot links to the next by id times four, and the two header
    # words hold the first and last that way too -- not by any offset into
    # the table, which is what the numbers look like until they are checked
    # against which ids are actually missing.
    chain = [i for i in free_ids if 1 <= i <= highest and i not in offsets]
    for position, object_id in enumerate(chain):
        following = chain[position + 1] if position + 1 < len(chain) else None
        slots[object_id - 1] = 0 if following is None else following * 4
    first = chain[0] * 4 if chain else 0
    last = chain[-1] * 4 if chain else 0

    trailer_length = (TRAILER_HEADER_WORDS + len(slots)) * 4
    trailer = struct.pack('>IIIII', trailer_length, TRAILER_CONSTANT, 0,
                          first, last)
    trailer += b''.join(struct.pack('>I', s) for s in slots)

    total = heap_end + trailer_length
    header = bytearray(HEAP_START)
    for offset, word in (unnamed_words or {}).items():
        struct.pack_into('>I', header, offset, word)
    struct.pack_into('>I', header, 0x10, total)
    struct.pack_into('>I', header, 0x14, heap_end)
    for offset, word in zip((0x1c, 0x20, 0x24), constant_words):
        struct.pack_into('>I', header, offset, word)
    struct.pack_into('>I', header, 0x2c, 0x01000000 | (highest - 1))
    # 0x30 is 0000ffff in all sixteen packages, and 0x3c is the highest id a
    # second time. Neither is worked out beyond that, but a writer that
    # leaves them zero is emitting a header no real package has, so they are
    # written rather than left out.
    struct.pack_into('>I', header, 0x30, 0x0000FFFF)
    struct.pack_into('>I', header, 0x34, highest)
    struct.pack_into('>I', header, 0x3c, highest)
    return bytes(header) + bytes(body) + trailer


def from_inspection(data, result):
    """The arguments `build` needs to reproduce a package that was read."""
    objects = [Object(o['id'], o['class_number'],
                      data[o['payload']['offset']:
                           o['payload']['offset'] + o['payload']['length']
                           - o['padding_bytes']],
                      tag_low=o['tag'] & 0xFF, flags=o['flags'])
               for o in result['objects']]
    header = result['header']
    present = {o['id'] for o in result['objects']}
    highest = header['highest_object_id']
    heap_end = header['heap_end']
    last_record = result['objects'][-1]
    terminator = last_record['offset'] + last_record['length'] != heap_end
    # The free list in the order the trailer chains it, which is not id order.
    free, at = [], struct.unpack_from('>I', data, heap_end + 12)[0]
    while at and at // 4 <= highest:
        object_id = at // 4
        free.append(object_id)
        at = struct.unpack_from(
            '>I', data, heap_end + (TRAILER_HEADER_WORDS + object_id - 1) * 4)[0]
    missing = [i for i in range(1, highest + 1) if i not in present]
    if sorted(free) != sorted(missing):
        free = missing
    return {
        'objects': objects,
        'constant_words': [int(w, 16) for w in header['constant_words']],
        'unnamed_words': {int(k, 16): int(v, 16)
                          for k, v in header['unnamed_words'].items()},
        'terminator': terminator,
        'free_ids': free,
    }
