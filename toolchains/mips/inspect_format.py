#!/usr/bin/env python3
"""Read-only inspector for observed Rosemary X-file and SALTCOD containers.

Container boundaries, selected named record prefixes and dependencies are decoded;
this is not a package compatibility validator or writer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

SALT = b'\0SALTCOD'

# SDK Apollo Flattener_ReadStreamableMulticodeAttributes jump table.
ATTRIBUTE_KINDS = {1: 'abbreviated-classes', 2: 'imports', 3: 'defined-components',
                   4: 'out-addressing', 5: 'object-addressing', 6: 'heap',
                   7: 'code', 8: 'external-function-names',
                   10: 'global-data-initialization', 11: 'function-offsets'}


class FormatError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise FormatError(message)


def u32(data, offset):
    require(0 <= offset <= len(data) - 4, f'truncated word at {offset:#x}')
    return struct.unpack_from('>I', data, offset)[0]


def span(data, start, end):
    require(0 <= start <= end <= len(data), f'invalid span {start:#x}..{end:#x}')
    payload = data[start:end]
    return {'offset': start, 'length': end - start,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'prefix_hex': payload[:16].hex()}


def decode_class_layout(data, record, classes):
    """Decode only the independently checked prefix-word-1 definition layout."""
    if record['raw_kind'] != 2:
        return {'status': 'reference-record-not-decoded'}
    start = record['opaque_tail']['offset']
    end = start + record['opaque_tail']['length']
    if end - start < 4 or u32(data, start) != 1:
        return {'status': 'unsupported-definition-prefix'}
    require(start + 28 <= end, 'truncated class layout prefix')
    base = u32(data, start + 8)
    total = u32(data, start + 12)
    leaf = u32(data, start + 20)
    require(leaf <= total, 'class leaf size exceeds fixed storage')

    def resolve(index):
        require(1 <= index <= len(classes), 'class layout reference outside class table')
        target = classes[index - 1]
        return {'record_index': index, 'name_latin1': target['name_latin1'],
                'class_number': target['class_number']}

    cursor = start + 24
    lists = {}
    for label in ('mixes_in_with', 'inherits_from'):
        require(cursor + 4 <= end, 'truncated class relation count')
        count = u32(data, cursor)
        cursor += 4
        require(count <= (end - cursor) // 4, 'class relation list exceeds record')
        lists[label] = [resolve(u32(data, cursor + i * 4)) for i in range(count)]
        cursor += count * 4
    return {'status': 'decoded-observed-prefix-1',
            'raw_prefix_word': 1, 'raw_word_at_4': u32(data, start + 4),
            'raw_word_at_16': u32(data, start + 16),
            'field_access_base': resolve(base), 'fixed_storage_bytes': total,
            'leaf_storage_bytes': leaf, 'fixed_offset_bytes': total - leaf,
            **lists, 'decoded_span': span(data, start, cursor),
            'remaining_opaque_tail': span(data, cursor, end)}


def decode_class_members(data, record, types, operations):
    layout = record['layout']
    if layout['status'] != 'decoded-observed-prefix-1':
        return {'status': 'unsupported-class-layout'}
    start = layout['remaining_opaque_tail']['offset']
    end = start + layout['remaining_opaque_tail']['length']
    require(start + 4 <= end, 'truncated class member prefix')
    count = u32(data, start)
    require(count <= (end - start - 4) // 4, 'class auxiliary list exceeds record')
    auxiliary = [u32(data, start + 4 + i * 4) for i in range(count)]
    cursor = start + 4 + count * 4
    require(cursor + 6 <= end, 'truncated class member flags/count')
    flags = u32(data, cursor)
    count = struct.unpack_from('>H', data, cursor + 4)[0]
    cursor += 6
    require(count <= (end - cursor) // 4, 'class operation list exceeds record')
    raw_operation_indices = [u32(data, cursor + i * 4) for i in range(count)]
    cursor += count * 4
    require(cursor + 8 <= end, 'truncated class member table offsets')
    base = record['opaque_tail']['offset'] + 8
    field_relative, method_relative = u32(data, cursor), u32(data, cursor + 4)
    header_end = cursor + 8

    def table(relative):
        if not relative:
            return None, []
        offset = base + relative
        require(header_end <= offset <= end - 4, 'class member table outside record')
        size = u32(data, offset)
        require(size <= (end - offset - 4) // 4, 'class member directory exceeds record')
        directory_end = offset + 4 + size * 4
        offsets = [offset + u32(data, offset + 4 + i * 4) for i in range(size)]
        require(all(directory_end <= x < end for x in offsets), 'class member outside record')
        require(all(a < b for a, b in zip(offsets, offsets[1:])), 'unordered class members')
        require(not offsets or offsets[0] == directory_end, 'gap before first class member')
        return offset, offsets

    field_table, field_offsets = table(field_relative)
    method_table, method_offsets = table(method_relative)
    fields = []
    last_field_end = field_table + 4 + 4 * len(field_offsets) if field_table is not None else None
    for index, offset in enumerate(field_offsets):
        require(offset + 4 <= end, 'truncated field name length')
        length = u32(data, offset)
        tail = offset + 4 + length
        stop = tail + 9
        limit = field_offsets[index + 1] if index + 1 < len(field_offsets) else (method_table or end)
        require(stop <= limit, 'field exceeds its record/table')
        require(index + 1 == len(field_offsets) or stop == limit, 'unexpected field record suffix')
        type_index = u32(data, tail)
        require(1 <= type_index <= len(types), 'field type outside type table')
        bit_offset = u32(data, tail + 4)
        name = data[offset + 4:tail]
        fields.append({'name_latin1': name.decode('latin1'), 'name_hex': name.hex(),
                       'type_record_index': type_index, 'type_name_latin1': types[type_index - 1]['name_latin1'],
                       'leaf_bit_offset': bit_offset,
                       'fixed_bit_offset': layout['fixed_offset_bytes'] * 8 + bit_offset,
                       'raw_flags_byte': data[tail + 8], 'record': span(data, offset, stop)})
        last_field_end = stop
    if last_field_end is not None and method_table is not None:
        require(last_field_end <= method_table, 'overlapping field/method tables')
        require(method_table - last_field_end <= 3 and not any(data[last_field_end:method_table]),
                'unexpected bytes between field and method tables')
    methods = []
    for index, offset in enumerate(method_offsets):
        limit = method_offsets[index + 1] if index + 1 < len(method_offsets) else end
        require(offset + 12 <= limit, 'truncated method binding')
        require(index + 1 == len(method_offsets) or offset + 12 == limit, 'unexpected method binding stride')
        operation_index = u32(data, offset)
        require(1 <= operation_index <= len(operations), 'method operation outside operation table')
        operation = operations[operation_index - 1]
        methods.append({'operation_record_index': operation_index,
                        'name_latin1': operation['name_latin1'],
                        'operation_number': operation['operation_number'],
                        'raw_word_4': u32(data, offset + 4), 'raw_word_8': u32(data, offset + 8),
                        'record': span(data, offset, offset + 12)})
    accessor_kinds = {1: 'getter', 2: 'setter', 3: 'text-getter',
                      4: 'text-setter', 5: 'shared-setter'}
    for method in methods:
        kind, index = method['raw_word_4'], method['raw_word_8']
        if kind in accessor_kinds:
            require(1 <= index <= len(fields), 'accessor field outside class field table')
            field = fields[index - 1]
            method['binding'] = {'kind': accessor_kinds[kind], 'field_record_index': index,
                                 'field_name_latin1': field['name_latin1'],
                                 'field_type_name_latin1': field['type_name_latin1'],
                                 'fixed_bit_offset': field['fixed_bit_offset']}
        else:
            method['binding'] = {'kind': 'ordinary-unresolved' if kind == 0 and index == 0 else 'unknown'}
    used_end = max(header_end, last_field_end or 0,
                   (method_offsets[-1] + 12 if method_offsets else (method_table + 4 if method_table else 0)))
    return {'status': 'decoded-observed-member-tables', 'raw_auxiliary_indices': auxiliary,
            'raw_flags_word': flags, 'raw_operation_indices': raw_operation_indices,
            'relative_offset_base': base, 'field_table_offset': field_table,
            'method_table_offset': method_table, 'fields': fields, 'methods': methods,
            'remaining_opaque_suffix': span(data, used_end, end)}


def decode_operation_signature(data, record, types):
    if record['raw_kind'] != 2:
        return {'status': 'reference-record-not-decoded'}
    start = record['opaque_tail']['offset']
    end = start + record['opaque_tail']['length']
    if end - start < 4 or u32(data, start) != 1:
        return {'status': 'unsupported-definition-prefix'}
    require(start + 18 <= end, 'truncated operation signature')

    def type_ref(index, allow_void=False):
        if allow_void and index == 0:
            return {'record_index': 0, 'name_latin1': 'void'}
        require(1 <= index <= len(types), 'signature type outside type table')
        target = types[index - 1]
        return {'record_index': index, 'name_latin1': target['name_latin1'],
                'raw_kind': target['raw_kind']}

    result = {'status': 'decoded-observed-signature-prefix-1',
              'raw_word_at_4': u32(data, start + 4),
              'raw_flags_byte_8': data[start + 8],
              'return_type': type_ref(u32(data, start + 9), True),
              'raw_flags_byte_13': data[start + 13], 'parameters': []}
    count = u32(data, start + 14)
    cursor = start + 18
    require(count <= (end - cursor) // 9, 'signature parameter count exceeds record')
    for _ in range(count):
        require(cursor + 4 <= end, 'truncated parameter name length')
        length = u32(data, cursor)
        cursor += 4
        require(cursor + length + 5 <= end, 'parameter exceeds signature')
        name = data[cursor:cursor + length]
        cursor += length
        result['parameters'].append({'name_latin1': name.decode('latin1'), 'name_hex': name.hex(),
                                     'type': type_ref(u32(data, cursor)),
                                     'raw_flags_byte': data[cursor + 4]})
        cursor += 5
    require(end - cursor <= 3 and not any(data[cursor:end]), 'unexpected signature suffix')
    result['padding'] = span(data, cursor, end)
    return result


def inspect_xfile(data):
    require(u32(data, 0) == 121, 'unsupported X-file header/version')
    require(len(data) >= 6, 'truncated X-file count')
    count = struct.unpack_from('>H', data, 4)[0]
    require(count > 0, 'empty section directory is not supported')
    table = (6 + count * 2 + 3) & ~3
    end = table + count * 4
    require(end <= len(data), 'truncated X-file directory')
    tags = struct.unpack_from(f'>{count}H', data, 6)
    offsets = [u32(data, table + i * 4) + 4 for i in range(count)]
    require(offsets[0] == end, 'first X-file section does not follow directory')
    require(all(a <= b for a, b in zip(offsets, offsets[1:])), 'unordered X-file section offsets')
    require(offsets[-1] <= len(data), 'X-file section outside file')
    sections = []
    for i, (tag, start, stop) in enumerate(zip(tags, offsets, offsets[1:] + [len(data)])):
        section = {'index': i, 'raw_tag': tag, **span(data, start, stop)}
        if tag in (12, 13, 15, 16, 17):
            require(start + 4 <= stop, f'truncated section {tag} count')
            record_count = u32(data, start)
            record_table_end = start + 4 + record_count * 4
            require(record_table_end <= stop, f'section {tag} record table exceeds section')
            record_offsets = [u32(data, start + 4 + j * 4) + 4 for j in range(record_count)]
            require(all(record_table_end <= x < stop for x in record_offsets), f'section {tag} record outside section')
            require(all(a < b for a, b in zip(record_offsets, record_offsets[1:])), f'unordered section {tag} records')
            section['named_records'] = []
            for begin, finish in zip(record_offsets, record_offsets[1:] + [stop]):
                prefix = 0 if tag == 12 else 4
                name_start = begin + prefix + 4
                require(name_start <= finish, f'truncated section {tag} name length')
                name_length = u32(data, begin + prefix)
                name_end = name_start + name_length
                require(name_end <= finish, f'section {tag} name exceeds record')
                name = data[name_start:name_end]
                record = {'name_latin1': name.decode('latin1'), 'name_hex': name.hex(),
                          'record': span(data, begin, finish)}
                if prefix:
                    record['raw_kind'] = u32(data, begin)
                tail = name_end
                if tag in (13, 16):
                    require(tail + 4 <= finish, f'truncated section {tag} number')
                    record['class_number' if tag == 13 else 'operation_number'] = u32(data, tail)
                    tail += 4
                record['opaque_tail'] = span(data, tail, finish)
                section['named_records'].append(record)
        elif tag == 19:
            require(start + 4 <= stop, 'truncated dependency count')
            dependency_count = u32(data, start)
            cursor = start + 4
            require(dependency_count <= (stop - cursor) // 4, 'dependency count exceeds section')
            section['dependency_paths'] = []
            for _ in range(dependency_count):
                require(cursor + 4 <= stop, 'truncated dependency length')
                length = u32(data, cursor)
                cursor += 4
                require(cursor + length <= stop, 'dependency path exceeds section')
                path = data[cursor:cursor + length]
                section['dependency_paths'].append({'path_latin1': path.decode('latin1'),
                                                   'path_hex': path.hex()})
                cursor += length
            require(stop - cursor <= 3 and not any(data[cursor:stop]), 'unexpected bytes after dependency paths')
            section['padding'] = span(data, cursor, stop)
        if tag == 13:
            for record in section['named_records']:
                record['layout'] = decode_class_layout(data, record, section['named_records'])
        sections.append(section)
    types = next((s['named_records'] for s in sections if s['raw_tag'] == 15), [])
    operations = next((s['named_records'] for s in sections if s['raw_tag'] == 16), [])
    for operation in operations:
        operation['signature'] = decode_operation_signature(data, operation, types)
    for section in sections:
        if section['raw_tag'] == 13:
            for record in section['named_records']:
                record['members'] = decode_class_members(data, record, types, operations)
    return {'format': 'rosemary-xfile-observed-v121', 'header_word': 121,
            'architecture': 'undetermined', 'offset_base': 4,
            'directory': span(data, 0, end), 'sections': sections}


def decode_imports(data, start, end):
    kinds = {1: 'locator', 2: 'class', 3: 'operation', 4: 'class-operation', 5: 'intrinsic'}
    entries = []
    cursor = start
    while True:
        require(cursor + 4 <= end, 'missing import table terminator')
        begin = cursor
        raw_kind = u32(data, cursor)
        kind = raw_kind & 255  # Matches the loader's low-byte mask.
        cursor += 4
        if kind == 0:
            require(cursor == end, 'unexpected bytes after import terminator')
            return {'status': 'decoded-import-table', 'entries': entries,
                    'terminator_offset': begin, 'raw_terminator': raw_kind}
        require(kind in kinds, 'unsupported import interchange kind')
        names = []
        name_bytes = 0
        for _ in range(2):
            require(cursor < end, 'truncated Pascal import string')
            length = data[cursor]
            cursor += 1
            require(cursor + length <= end, 'import string exceeds attribute')
            name = data[cursor:cursor + length]
            names.append({'text_latin1': name.decode('latin1'), 'hex': name.hex()})
            cursor += length
            name_bytes += length + 1
        padding = (-name_bytes) % 4
        require(cursor + padding + 12 <= end, 'truncated import range')
        padding_hex = data[cursor:cursor + padding].hex()
        cursor += padding
        words = [u32(data, cursor + i * 4) for i in range(3)]
        require(1 <= words[2] <= 5000, 'import count outside loader range')
        cursor += 12
        entries.append({'raw_kind_word': raw_kind, 'kind': kinds[kind],
                        'name': names[0], 'secondary_name': names[1],
                        'padding_hex': padding_hex, 'raw_component_word': words[0],
                        'raw_range_word': words[1], 'count': words[2],
                        'record': span(data, begin, cursor)})


def decode_function_offsets(data, start, end):
    require(start + 8 <= end, 'truncated function offset table')
    count = u32(data, start)
    require((count + 2) * 4 == end - start, 'unsupported function offset table length')
    entries = []
    for index in range(1, count + 1):
        value = u32(data, start + index * 4)
        entries.append({'function_id': index, 'raw_word': value,
                        'code_offset': None if value == 0xffffffff else value})
    return {'status': 'decoded-observed-function-offset-table', 'count': count,
            'entries': entries, 'raw_trailing_word': u32(data, end - 4)}


def link_function_code(data, records):
    """Locate entries in the observed single-code-attribute embedded layout.

    These are file positions, not load addresses or inferred function extents.
    """
    codes = [r for r in records if r['attribute_tag'] == 7]
    tables = [r for r in records if 'function_offsets' in r]
    if not tables:
        return {'status': 'no-decoded-function-offset-table'}
    if len(codes) != 1 or len(tables) != 1 or codes[0]['raw_tag_byte'] != 0x71:
        return {'status': 'unsupported-code-attribute-combination'}
    code = codes[0]['payload']
    start = code['offset']
    end = start + code['length']
    require(code['length'] >= 4, 'code buffer missing leading word')
    base = start + 4  # CodeHandler_LockCode: LockReadExtra(codeBuffer) + 4.
    entries = []
    for entry in tables[0]['function_offsets']['entries']:
        offset = entry['code_offset']
        linked = {'function_id': entry['function_id'], 'code_offset': offset}
        if offset is None:
            linked['status'] = 'null-method'
        else:
            require(offset % 4 == 0 and base + offset + 4 <= end,
                    'function offset is unaligned or outside code buffer')
            linked.update(status='located-in-code-attribute', file_offset=base + offset,
                          entry_preview=span(data, base + offset, min(base + offset + 16, end)))
        entries.append(linked)
    return {'status': 'linked-observed-code-type-1', 'code_base_file_offset': base,
            'raw_leading_word': u32(data, start), 'entries': entries}


def decode_bnum(data, cursor, end):
    require(cursor < end, 'truncated BNum')
    tag = data[cursor]
    cursor += 1
    if tag < 0xf0:
        return tag, cursor
    if tag < 0xf8:
        require(cursor < end, 'truncated short BNum')
        high = tag & 7
        if high & 4:
            high -= 8
        return (high << 8) | data[cursor], cursor + 1
    require(tag <= 0xfb, 'unsupported BNum tag')
    length = {0xf8: 2, 0xf9: 3, 0xfa: 4, 0xfb: 8}[tag]
    require(cursor + length <= end, 'truncated extended BNum')
    # The MIPS reader skips the upper word of the eight-byte form.
    begin = cursor + (4 if tag == 0xfb else 0)
    return int.from_bytes(data[begin:cursor + length], 'big', signed=True), cursor + length


def decode_init_resolution(data, cursor, end, count, state, op):
    def byte():
        nonlocal cursor
        require(cursor < end, 'truncated initialization resolution operand')
        value = data[cursor]
        cursor += 1
        return value

    def number():
        nonlocal cursor
        value, cursor = decode_bnum(data, cursor, end)
        return value

    mask = byte()
    require(count <= 100000, 'resolution count exceeds inspector expansion limit')
    entries = []
    for _ in range(count):
        changes = {}
        if mask & 128:
            changes['raw_source_kind'] = byte()
        if mask & 64:
            tag = byte()
            previous = bytes.fromhex(state.get('interface_hex', ''))
            if tag <= 128:
                length = byte() if tag == 128 else tag
                prefix = b''
            else:
                require(tag >= 192, 'invalid compressed interface name tag')
                prefix = previous[:len(previous) - min(tag - 192, len(previous))]
                length = byte()
            require(len(prefix) + length <= 255, 'unsupported oversized compressed interface name')
            require(cursor + length <= end, 'truncated interface name')
            name = prefix + data[cursor:cursor + length]
            cursor += length
            changes.update(interface_hex=name.hex(), interface_latin1=name.decode('latin1'))
        if mask & 32:
            require(cursor < end, 'truncated resolution index')
            if data[cursor] in (254, 255):
                mode = byte()
                changes['raw_index'] = number()
                changes['raw_index_step'] = 1 if mode == 254 else number()
            else:
                changes['raw_index'] = number()
                changes['raw_index_step'] = 0
        if mask & 16:
            changes['raw_field_a4'] = number()
        if mask & 8:
            changes['raw_field_af'] = byte()
        if mask & 4:
            require(cursor < end, 'truncated resolution multiplier')
            if data[cursor] == 255:
                byte()
                changes['raw_field_b4'] = -1
            else:
                changes['raw_field_b4'] = number()
        if mask & 2:
            changes['raw_field_bc'] = number()
        if mask & 1:
            mode = byte()
            changes['raw_destination_mode'] = mode
            if mode in (0x12, 0x21, 0x23, 0xa1, 0xa3):
                changes['raw_field_cc'] = number()
        state.update(changes)
        entry = {'raw_update_mask': mask, 'changes': changes, 'state': dict(state)}
        if op == 13:
            entry['destination_delta'] = number()
        entries.append(entry)
        if 'raw_index' in state:
            state['raw_index'] += state.get('raw_index_step', 0)
    return entries, cursor


def decode_global_init(data, start, end):
    require(start + 8 <= end, 'truncated global initialization header')
    result = {'status': 'partial-global-init', 'global_data_bytes': u32(data, start),
              'raw_second_header_word': u32(data, start + 4), 'instructions': []}
    cursor = start + 8
    resolution_state = {}
    immediates = [1, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24]
    labels = {1: 'copy-literal-bytes', 2: 'advance-destination', 3: 'rewind-destination',
              4: 'repeat-byte', 5: 'repeat-halfword', 6: 'repeat-word', 7: 'repeat-doubleword',
              8: 'zero-bytes', 9: 'base-relative-words-argument-3',
              10: 'base-relative-words-argument-4', 11: 'base-relative-words-argument-5',
              15: 'add-base-relative-words'}
    while cursor < end:
        begin = cursor
        byte = data[cursor]
        cursor += 1
        high, op = byte >> 4, byte & 15
        if high == 0:
            if op > 10 or op == 3:
                raise FormatError('invalid global initialization control')
            result['instructions'].append({'offset': begin, 'raw_opcode': byte, 'kind': 'control'})
            if op == 1:
                resolution_state.clear()
            if op == 0:
                result.update(status='decoded-global-init-boundaries',
                              trailing_bytes=span(data, cursor, end))
                return result
            continue
        if op == 14:
            result.update(unsupported_opcode=byte, opaque_remainder=span(data, begin, end))
            return result
        require(op in labels or op in (12, 13), 'invalid global initialization opcode')
        if high <= 12:
            count = immediates[high]
        else:
            length = {13: 1, 14: 2, 15: 4}[high]
            require(cursor + length <= end, 'truncated global initialization count')
            count = int.from_bytes(data[cursor:cursor + length], 'big')
            cursor += length
        if op in (12, 13):
            entries, cursor = decode_init_resolution(data, cursor, end, count, resolution_state, op)
            result['instructions'].append({'offset': begin, 'raw_opcode': byte,
                'kind': 'interface-resolution-operands', 'count': count, 'entries': entries,
                'record': span(data, begin, cursor)})
            continue
        operands = []
        if op in (9, 10, 11, 15):
            require(count <= end - cursor, 'global initialization operand count exceeds buffer')
            for _ in range(count):
                value, cursor = decode_bnum(data, cursor, end)
                operands.append(value)
        else:
            length = count if op == 1 else {4: 1, 5: 2, 6: 4, 7: 8}.get(op, 0)
            require(cursor + length <= end, 'global initialization literal exceeds buffer')
            cursor += length
        result['instructions'].append({'offset': begin, 'raw_opcode': byte, 'kind': labels[op],
                                       'count': count, 'bnum_operands': operands,
                                       'record': span(data, begin, cursor)})
    raise FormatError('global initialization missing stop instruction')


def decode_object_addressing(data, start, end):
    """Observed 0x53: create cluster, consume auxiliary word, allocate ranges."""
    require(start + 12 <= end, 'truncated object addressing table')
    cluster = u32(data, start)
    auxiliary = u32(data, start + 4)
    ranges = []
    cursor = start + 8
    while True:
        require(cursor + 4 <= end, 'missing addressing range terminator')
        first = u32(data, cursor)
        cursor += 4
        if first == 0:
            require(cursor == end, 'bytes after addressing terminator')
            return {'status': 'decoded-observed-addressing-53',
                    'cluster_selector': cluster, 'raw_auxiliary_word': auxiliary,
                    'ranges': ranges}
        require(cursor + 4 <= end, 'truncated addressing range count')
        count = u32(data, cursor)
        cursor += 4
        require(1 <= count <= 10000 and first + (count - 1) * 8 <= 0xffffffff,
                'invalid object addressing range')
        ranges.append({'selector_start': first, 'count': count, 'selector_stride': 8})


def link_heap_selectors(records):
    addresses = [r['object_addressing'] for r in records if 'object_addressing' in r]
    heaps = [r['heap'] for r in records if 'heap' in r]
    if len(addresses) != 1 or len(heaps) != 1:
        return {'status': 'unsupported-addressing-heap-combination'}
    addressing = addresses[0]
    objects = heaps[0]['objects']
    require(1 + sum(r['count'] for r in addressing['ranges']) == len(objects),
            'object addressing count differs from heap record count')
    selectors = [addressing['cluster_selector']]
    for r in addressing['ranges']:
        selectors.extend(r['selector_start'] + i * 8 for i in range(r['count']))
    require(len(set(selectors)) == len(selectors), 'overlapping object selectors')
    return {'status': 'linked-heap-selectors', 'objects': [
        {'selector': selector, 'heap_object_index': obj['index'],
         'record_offset': obj['record']['offset']}
        for selector, obj in zip(selectors, objects)]}


def decode_defined_components(data, start, end):
    kinds = {2: 'class', 3: 'operation', 4: 'class-operation', 5: 'intrinsic'}
    entries = []
    cursor = start
    while True:
        require(cursor + 4 <= end, 'missing defined component terminator')
        begin = cursor
        raw_kind = u32(data, cursor)
        kind = raw_kind & 255
        cursor += 4
        if kind == 0:
            require(cursor == end, 'bytes after defined component terminator')
            return {'status': 'decoded-defined-components', 'entries': entries,
                    'raw_terminator': raw_kind}
        require(kind in kinds, 'invalid defined component kind')
        require(cursor + 8 <= end, 'truncated defined component range')
        first, count = u32(data, cursor), u32(data, cursor + 4)
        require(count > 0 and first + count <= 0x100000000,
                'invalid defined component range')
        cursor += 8
        entries.append({'kind': kinds[kind], 'raw_kind_word': raw_kind,
                        'selector_start': first, 'count': count,
                        'record': span(data, begin, cursor)})


def decode_abbreviated_classes(data, start, end):
    entries = []
    cursor = start
    while True:
        require(cursor + 4 <= end, 'missing abbreviated class terminator')
        begin = cursor
        selector = u32(data, cursor)
        cursor += 4
        if selector == 0:
            require(cursor == end, 'bytes after abbreviated class terminator')
            return {'status': 'decoded-abbreviated-class-records', 'entries': entries}
        require(cursor < end, 'missing abbreviated class format count')
        count = data[cursor]
        size = (count + 1) // 2
        padded = (1 + size + 3) & ~3
        require(cursor + padded <= end, 'truncated abbreviated class formats')
        packed = data[cursor + 1:cursor + 1 + size]
        formats = [((packed[i // 2] >> (0 if i % 2 else 4)) & 15) for i in range(count)]
        entries.append({'class_selector': selector, 'format_count': count,
                        'raw_format_nibbles': formats, 'packed_formats_hex': packed.hex(),
                        'padding_hex': data[cursor + 1 + size:cursor + padded].hex(),
                        'record': span(data, begin, cursor + padded)})
        cursor += padded


def decode_heap(data, start, end):
    """Decode frozen object boundaries; selectors remain package-local and raw."""
    records = []
    cursor = start
    while True:
        require(cursor + 4 <= end, 'missing heap terminator')
        begin = cursor
        header = u32(data, cursor)
        cursor += 4
        if header == 0:
            require(cursor == end, 'unexpected bytes after heap terminator')
            return {'status': 'decoded-heap-boundaries', 'objects': records,
                    'terminator_offset': begin}
        kind = header >> 30
        record = {'index': len(records), 'raw_header': header, 'record_kind': kind}
        if kind == 1:
            record['raw_class_selector'] = header & 0xfffff
        elif kind == 3:
            require(cursor + 4 <= end, 'truncated heap reference')
            record['raw_locator_selector'] = u32(data, cursor)
            cursor += 4
        elif kind == 2:
            require(cursor + 4 <= end, 'truncated heap body length')
            size = u32(data, cursor)
            cursor += 4
            record['raw_class_selector'] = header & 0xfffff
            subtype = (header >> 28) & 3
            record['raw_subtype'] = subtype
            # Subtype 3 retains names within its body; other subtypes serialize
            # a separate counted Unicode name when bit 24 is set.
            if subtype != 3 and header & 0x01000000:
                require(cursor + 2 <= end, 'truncated heap name count')
                count = int.from_bytes(data[cursor:cursor + 2], 'big')
                length = 2 + count * 2
                padded = (length + 3) & ~3
                require(cursor + padded <= end, 'heap name exceeds attribute')
                raw = data[cursor + 2:cursor + length]
                record['external_name'] = {'code_units': count, 'hex': raw.hex(),
                    'text_utf16be': raw.decode('utf-16-be', errors='backslashreplace'),
                    'padding_hex': data[cursor + length:cursor + padded].hex()}
                cursor += padded
            padded = (size + 3) & ~3
            require(cursor + padded <= end, 'heap body exceeds attribute')
            record['body'] = span(data, cursor, cursor + size)
            record['padding_hex'] = data[cursor + size:cursor + padded].hex()
            cursor += padded
        else:
            raise FormatError('unsupported frozen object kind')
        record['record'] = span(data, begin, cursor)
        records.append(record)


def inspect_frozen(data):
    packages = []
    pos = 0
    while pos < len(data):
        start = pos
        require(data[pos:pos + 8] == SALT, f'expected SALTCOD header at {pos:#x}; trailing bytes are not ignored')
        version = u32(data, pos + 8)
        require(version == 152, f'unsupported frozen version {version} at {pos:#x}')
        pos += 12
        records = []
        while True:
            offset = pos
            word = u32(data, pos)
            pos += 4
            if word == 0:
                break
            length = word & 0x00ffffff
            tag = word >> 24
            stop = pos + length
            require(stop <= len(data), f'frozen record at {offset:#x} exceeds file')
            records.append({'header_offset': offset, 'raw_header': word,
                            'raw_tag_byte': tag, 'attribute_kind': ATTRIBUTE_KINDS.get(tag >> 4, 'unknown'),
                            'attribute_tag': tag >> 4, 'raw_flags_nibble': tag & 15,
                            'payload': span(data, pos, stop)})
            if tag >> 4 == 2 and tag & 15 == 0:
                records[-1]['imports'] = decode_imports(data, pos, stop)
            if tag == 0xa0:
                records[-1]['global_initialization'] = decode_global_init(data, pos, stop)
            if tag == 0x10:
                records[-1]['abbreviated_classes'] = decode_abbreviated_classes(data, pos, stop)
            if tag == 0x53:
                records[-1]['object_addressing'] = decode_object_addressing(data, pos, stop)
            if tag == 0x30:
                records[-1]['defined_components'] = decode_defined_components(data, pos, stop)
            if tag == 0x60:
                records[-1]['heap'] = decode_heap(data, pos, stop)
            if tag == 0xb0:
                records[-1]['function_offsets'] = decode_function_offsets(data, pos, stop)
            pos = stop
        packages.append({'index': len(packages), 'version': version,
                         'offset': start, 'length': pos - start,
                         'terminator_offset': offset, 'records': records,
                         'function_code': link_function_code(data, records),
                         'heap_selectors': link_heap_selectors(records)})
    require(bool(packages), 'empty frozen input')
    return {'format': 'saltcod-observed-v152', 'architecture': 'undetermined',
            'packages': packages}


def inspect(data):
    if data.startswith(SALT):
        result = inspect_frozen(data)
    elif data.startswith(b'\0\0\0y'):
        result = inspect_xfile(data)
    else:
        raise FormatError('unrecognized container (extensions do not identify architecture)')
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'scope': 'container boundaries and selected record prefixes; remaining payload semantics and runtime validity unchecked', **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    results = []
    failed = False
    for path in args.files:
        try:
            results.append({'path': str(path), **inspect(path.read_bytes())})
        except (OSError, FormatError) as exc:
            results.append({'path': str(path), 'error': str(exc)})
            failed = True
    json.dump(results, sys.stdout, indent=2)
    print()
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
