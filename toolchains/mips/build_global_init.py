#!/usr/bin/env python3
"""Build the supported subset of A0 initialization payloads, not whole packages."""
from inspect_format import require, decode_global_init
from validate_global_init import validate

COUNTS = (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24)


def bnum(value):
    require(-(1 << 31) <= value < (1 << 31), 'BNum exceeds signed 32 bits')
    if 0 <= value < 240:
        return bytes([value])
    if -1024 <= value <= 1023:
        return bytes([0xf0 | ((value >> 8) & 7), value & 255])
    for width, tag in ((2, 0xf8), (3, 0xf9), (4, 0xfa)):
        if -(1 << (width * 8 - 1)) <= value < (1 << (width * 8 - 1)):
            return bytes([tag]) + value.to_bytes(width, 'big', signed=True)


def instruction(opcode, count):
    require(1 <= opcode <= 15 and opcode != 14, 'unsupported initialization opcode')
    require(0 <= count <= 0xffffffff, 'invalid instruction count')
    if count in COUNTS:
        return bytes([((COUNTS.index(count) + 1) << 4) | opcode])
    for width, nibble in ((1, 13), (2, 14), (4, 15)):
        if count < 1 << (width * 8):
            return bytes([(nibble << 4) | opcode]) + count.to_bytes(width, 'big')


def transformed_words(source, state, gp=None):
    """Concrete value stage only; caller must supply an already-resolved source."""
    require(0 <= source <= 0xffffffff, 'source must be a 32-bit word')
    spec = state.get('raw_field_af', 32)
    bits = spec & 127
    require(0 <= bits <= 32 and not (spec & 128 and bits == 0), 'unsupported source width')
    if bits < 32:
        if spec & 128:
            signed = source if source < 0x80000000 else source - 0x100000000
            require(-(1 << (bits - 1)) <= signed < (1 << (bits - 1)), 'source outside signed width')
        else:
            require(source < (1 << bits), 'source outside unsigned width')
    value = (source * state.get('raw_field_b4', 1) + state.get('raw_field_bc', 0)) & 0xffffffff
    mode = state.get('raw_destination_mode', 4)
    require(mode in (4, 0x11), 'unsupported destination transformation')
    if mode == 4:
        return [value]
    require(gp is not None and 0 <= gp <= 0xffffffff, 'pair requires resolved GP')
    return [value, gp]


class GlobalInitBuilder:
    def __init__(self, globals_size, second_header_word):
        require(0 <= globals_size <= 0xffffffff and 0 <= second_header_word <= 0xffffffff, 'invalid header')
        # The second word's role remains unknown: require an explicit value.
        self.header = globals_size.to_bytes(4, 'big') + second_header_word.to_bytes(4, 'big')
        self.code = bytearray()

    def literal(self, data):
        self.code.extend(instruction(1, len(data)) + data)

    def zeros(self, count):
        self.code.extend(instruction(8, count))

    def move(self, delta):
        self.code.extend(instruction(2 if delta >= 0 else 3, abs(delta)))

    def reset_destination(self):
        self.code.append(2)

    def relative_words(self, base, offsets):
        require(base in ('globals', 'code'), 'unsupported relative base')
        payload = b''.join(bnum(value) for value in offsets)
        self.code.extend(instruction(9 if base == 'globals' else 10, len(offsets)) + payload)

    def resolve(self, source_kind, interface, index, *, pair=False, required_count=1):
        require(source_kind in (1, 2, 3, 4, 5, 6, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86), 'unsupported resolution source')
        name = interface.encode('latin1')
        require(0 < len(name) <= 255 and b'\0' not in name, 'invalid interface name')
        require(index >= 0 and required_count > 0, 'invalid interface range')
        name = (bytes([len(name)]) if len(name) < 128 else bytes([0x80, len(name)])) + name
        # Full update mask: independent of previous resolution operands.
        payload = bytes([source_kind]) + name + bnum(index) + bnum(required_count)
        payload += b'\x20' + bnum(1) + bnum(0) + bytes([0x11 if pair else 4])
        self.code.extend(b'\x1c\xff' + payload)

    def finish(self, code_size):
        data = self.header + self.code + b'\x00'
        parsed = decode_global_init(data, 0, len(data))
        audit = validate(data, parsed, code_size)
        outside = [t for t in audit.get('relative_targets', []) if t.get('within_extent_or_one_past') is False]
        require(audit['outside_target_count'] == 0, f'generated relative target outside extent: {outside[:4]}')
        return bytes(data)
