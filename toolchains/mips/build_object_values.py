#!/usr/bin/env python3
"""Encode supported fixed fields and ObjectList extras using explicit selectors."""
from inspect_format import require
from fractions import Fraction
import re


def pixel_units(value):
    """Exact pixel literal to signed Micron; refuse unproven rounding rules."""
    require(type(value) is int or isinstance(value, str), 'pixels require integer or decimal string')
    if isinstance(value, str):
        require(re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value) is not None, 'invalid pixel literal')
    scaled = Fraction(value) * 256
    require(scaled.denominator == 1, 'pixel value is not exactly representable in Micron units')
    integer(scaled.numerator, 32, True)
    return scaled.numerator


def plain_text(value):
    """Encode unstyled BMP text in the ROM's chunked representation.

    ASCII bytes are literal. 0x81..0xbf introduce 1..63 big-endian
    Unicode units. Use short chunks only; no style or format-2 markers.
    """
    require(isinstance(value, str), 'Text requires a string')
    require(all(ord(c) <= 0xffff and not 0xd800 <= ord(c) <= 0xdfff for c in value),
            'only non-surrogate BMP characters are supported')
    result = bytearray()
    pos = 0
    while pos < len(value):
        if ord(value[pos]) < 0x80:
            result.append(ord(value[pos]))
            pos += 1
            continue
        end = pos + 1
        while end < len(value) and end - pos < 63 and ord(value[end]) >= 0x80:
            end += 1
        result.append(0x80 | (end - pos))
        result.extend(value[pos:end].encode('utf-16-be'))
        pos = end
    return bytes(result)


def read_plain_text(data):
    """Read unstyled chunks only; reject styles and the separate format 2."""
    result = []
    pos = 0
    while pos < len(data):
        marker = data[pos]
        pos += 1
        if marker < 0x80:
            result.append(chr(marker))
            continue
        require(marker < 0xc0, 'styled/format-2 Text is unsupported')
        count = marker & 0x3f
        if not count:
            require(pos + 2 <= len(data), 'truncated Text count')
            count = int.from_bytes(data[pos:pos + 2], 'big')
            pos += 2
            require(count > 0, 'zero-length Unicode chunk is unsupported')
        require(pos + count * 2 <= len(data), 'truncated Text characters')
        units = [int.from_bytes(data[i:i + 2], 'big') for i in range(pos, pos + count * 2, 2)]
        require(all(not 0xd800 <= c <= 0xdfff for c in units), 'surrogate Text is unsupported')
        result.extend(chr(c) for c in units)
        pos += count * 2
    return ''.join(result)


def integer(value, bits, signed=False):
    require(isinstance(value, int) and not isinstance(value, bool), 'integer field requires integer')
    minimum = -(1 << (bits - 1)) if signed else 0
    maximum = (1 << (bits - (1 if signed else 0))) - 1
    require(minimum <= value <= maximum, 'field value outside declared width')
    return value.to_bytes(bits // 8, 'big', signed=signed)


def fixed_body(layout, values):
    """Require every field; no inferred initialization defaults or runtime pointers."""
    fields = layout['fields']
    names = [f['name'] for f in fields]
    require(set(values) == set(names), 'values must specify every field exactly once')
    body = bytearray(layout['fixed_storage_bytes'])
    occupied = set()
    last = {f['name']: i for i, f in enumerate(fields)}   # a subclass may shadow a field name
    for index, f in enumerate(fields):
        if last[f['name']] != index:
            continue                                     # shadowed: left zero
        offset, width = f['bit_offset'], f['bit_width']
        require(offset >= 0 and offset + width <= len(body) * 8, 'field outside fixed body')
        bits = set(range(offset, offset + width))
        require(not occupied.intersection(bits), 'overlapping fields')
        occupied.update(bits)
        value, kind = values[f['name']], f['type']
        byte = offset // 8
        if kind == 'Boolean':
            require(width == 1 and isinstance(value, bool), 'Boolean field requires bool')
            if value:
                body[byte] |= 1 << (7 - offset % 8)
            continue
        require(offset % 8 == 0, 'unaligned non-Boolean field')
        if kind == 'PixelBox':
            require(width == 64 and isinstance(value, (tuple, list)) and len(value) == 4, 'PixelBox needs four pixel integers')
            encoded = b''.join(integer(v, 16, True) for v in value)
        elif kind == 'PixelDot':
            require(width == 32 and isinstance(value, (tuple, list)) and len(value) == 2, 'PixelDot needs two pixel integers')
            encoded = integer(value[0], 16, True) + integer(value[1], 16, True)
        elif kind == 'Dot':
            require(width == 64 and isinstance(value, (tuple, list)) and len(value) == 2, 'Dot needs horizontal/vertical raw Micron integers')
            encoded = integer(value[0], 32, True) + integer(value[1], 32, True)
        elif kind in ('VolumeRosterPointer', 'MethodCodeAddress'):
            require(value == 0 and width == 32, 'runtime pointers must start null')
            encoded = integer(value, 32)
        elif kind == 'Signed':
            require(width == 32, 'unexpected Signed width')
            encoded = integer(value, 32, True)
        elif kind in ('UnsignedByte', 'SignedByte'):
            require(width == 8, 'unexpected byte field width')
            encoded = integer(value, 8, kind == 'SignedByte')
        else:
            require(width in (16, 32), 'unsupported field width')
            require(kind in ('Unsigned', 'Flags', 'UnsignedShort', 'SignedShort', 'ClassNumber', 'OperationNumber',
                             'ClassOperationNumber', 'IntrinsicNumber', 'Micron', 'Fixed', 'Pointer', 'Function') or f['word_format'] in (13, 14),
                    f'unsupported field type {kind}')
            if kind == 'SignedShort':
                encoded = integer(value, 16, True); body[byte:byte + 2] = encoded; continue
            encoded = integer(value, width)
        body[byte:byte + len(encoded)] = encoded
    return bytes(body)


def object_list(selectors, *, word_format=13, omit_empty_header=False):
    require(len(selectors) <= 0xffffff, 'ObjectList count exceeds 24 bits')
    if omit_empty_header:
        require(not selectors, 'cannot omit nonempty list header')
        return b''
    require(word_format in (4, 9, 10, 11, 12, 13, 14), 'unsupported list word format')
    return integer((word_format << 24) | len(selectors), 32) + b''.join(integer(x, 32) for x in selectors)


def decode_object_list(data):
    if not data:
        return {'selectors': [], 'word_format': None, 'omit_empty_header': True}
    require(len(data) >= 4, 'truncated ObjectList')
    header = int.from_bytes(data[:4], 'big')
    require(header >> 24 in (13, 14), 'unsupported ObjectList flags/format')
    count = header & 0xffffff
    require(len(data) == 4 + count * 4, 'ObjectList size mismatch')
    return {'selectors': [int.from_bytes(data[i:i + 4], 'big') for i in range(4, len(data), 4)],
            'word_format': header >> 24, 'omit_empty_header': False}


def read_object_list(data):
    return decode_object_list(data)['selectors']
