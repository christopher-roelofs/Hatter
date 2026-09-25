"""Minimal PEF container reader: sections, and pattern-data decompression.

For reading the SDK's own tools. ObjectMaker and FrozenDump are PowerPC PEF
binaries, not 68k, and their data -- where every diagnostic string lives -- is
stored pattern-compressed, so `strings` sees it only by accident and in
fragments. This unpacks it properly: ObjectMaker's data section comes out at
exactly the 61,728 bytes its header claims.

What this does not yet do is resolve a reference from code to a string. PEF
code reaches its data through a table of contents in r2, and the entries are
filled in by relocations in the loader section rather than being present in
the raw image -- so finding which routine prints which message needs those
relocations applied first. That is where the disassembly stands.
"""
import struct

KIND = {0: 'code', 1: 'unpacked data', 2: 'pattern data', 3: 'constant',
        4: 'loader', 5: 'debug'}


def sections(data):
    nsec = struct.unpack_from('>H', data, 32)[0]
    out = []
    for i in range(nsec):
        (nameoff, addr, execsz, initsz, rawsz, at, kind, share,
         align, pad) = struct.unpack_from('>iIIIIIBBBB', data, 40 + i * 28)
        out.append({'index': i, 'kind': KIND.get(kind, kind), 'addr': addr,
                    'exec_size': execsz, 'init_size': initsz,
                    'raw_size': rawsz, 'offset': at})
    return out


def varint(data, pos):
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def unpack_pattern(data, size):
    """PEF pattern-initialised data, per the Mac OS Runtime Architectures spec."""
    out = bytearray()
    pos = 0
    while pos < len(data) and len(out) < size:
        byte = data[pos]
        pos += 1
        opcode, count = byte >> 5, byte & 0x1F
        if count == 0:
            count, pos = varint(data, pos)
        if opcode == 0:                                  # zero
            out += bytes(count)
        elif opcode == 1:                                # block of literal bytes
            out += data[pos:pos + count]
            pos += count
        elif opcode == 2:                                # repeat a block
            repeat, pos = varint(data, pos)
            block = data[pos:pos + count]
            pos += count
            out += block * (repeat + 1)
        elif opcode == 3:                                # block with custom parts
            custom, pos = varint(data, pos)
            repeat, pos = varint(data, pos)
            common = data[pos:pos + count]
            pos += count
            for _ in range(repeat):
                out += common
                out += data[pos:pos + custom]
                pos += custom
            out += common
        elif opcode == 4:                                # zeroes with custom parts
            custom, pos = varint(data, pos)
            repeat, pos = varint(data, pos)
            for _ in range(repeat):
                out += bytes(count)
                out += data[pos:pos + custom]
                pos += custom
            out += bytes(count)
        else:
            raise ValueError(f'unknown pattern opcode {opcode} at {pos - 1}')
    if len(out) < size:
        out += bytes(size - len(out))
    return bytes(out)


def image(data, section):
    raw = data[section['offset']:section['offset'] + section['raw_size']]
    if section['kind'] == 'pattern data':
        return unpack_pattern(raw, section['exec_size'])
    return raw
