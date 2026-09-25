#!/usr/bin/env python3
"""Static name dictionary bodies, following Rosemary's pristine-name lookup."""
from build_object_values import integer
from inspect_format import require


def name_tables(names):
    """One name or None per consecutive locator. Return lookup and TextHeap.

    Lookup entries are halfword offsets into TextHeap extra data. Preserve
    duplicate strings as independent entries, as observed in compiled packages.
    """
    lookup, strings = bytearray(), bytearray()
    for name in names:
        if name is None:
            lookup.extend(b'\xff\xff')
            continue
        require(isinstance(name, str) and len(name) > 0, 'name must be nonempty text or None')
        require(all(ord(c) <= 0xffff and not 0xd800 <= ord(c) <= 0xdfff for c in name),
                'names support non-surrogate BMP characters only')
        require(len(name) <= 0x3fff, 'name exceeds 14-bit character count')
        require(len(strings) // 2 < 0xffff, 'name offset collides with absent-name sentinel')
        lookup.extend(integer(len(strings) // 2, 16))
        strings.extend(integer(len(name), 16) + name.encode('utf-16-be'))
    return bytes(lookup), bytes(4) + strings


def read_names(lookup, text_heap, count):
    require(type(count) is int and count >= 0, 'invalid name count')
    require(len(lookup) == count * 2, 'name lookup size mismatch')
    require(len(text_heap) >= 4 and text_heap[:4] == bytes(4), 'unsupported TextHeap deleted-name state')
    extra = text_heap[4:]
    require(len(extra) % 2 == 0, 'unaligned TextHeap')
    # Establish string boundaries before accepting offsets into the heap.
    strings, pos = {}, 0
    while pos < len(extra):
        start = pos
        header = int.from_bytes(extra[pos:pos + 2], 'big')
        require(header & 0xc000 == 0, 'unsupported TextHeap name flags')
        pos += 2
        require(header > 0 and pos + header * 2 <= len(extra), 'empty or truncated stored name')
        units = [int.from_bytes(extra[i:i + 2], 'big') for i in range(pos, pos + header * 2, 2)]
        require(all(not 0xd800 <= u <= 0xdfff for u in units), 'surrogate name unsupported')
        strings[start // 2] = ''.join(map(chr, units))
        pos += header * 2
    result = []
    for i in range(count):
        offset = int.from_bytes(lookup[i * 2:i * 2 + 2], 'big')
        require(offset == 0xffff or offset in strings, 'name offset is not a string boundary')
        result.append(None if offset == 0xffff else strings[offset])
    return result


def name_dictionary(lookup_selector, text_selector, first_locator, count):
    require(first_locator & 7 == 4 and first_locator != 0, 'invalid first locator')
    require(type(count) is int and count >= 0 and first_locator + count * 8 <= 0x100000000,
            'invalid locator range')
    require(lookup_selector & 7 == 4 and text_selector & 7 == 4, 'invalid name-table selectors')
    return b''.join(integer(x, 32) for x in (lookup_selector, text_selector, first_locator, count))
