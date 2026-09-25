#!/usr/bin/env python3
"""Construct frozen envelopes and heap records; opaque object bodies stay explicit."""
import hashlib
import json
from pathlib import Path
from inspect_format import (inspect, require, decode_heap, decode_imports,
                            decode_defined_components, decode_object_addressing,
                            decode_function_offsets, decode_abbreviated_classes, SALT)

ROOT = Path(__file__).resolve().parents[2]


def word(value):
    require(0 <= value <= 0xffffffff, 'word outside unsigned 32-bit range')
    return value.to_bytes(4, 'big')


def padding(length, preserved=None):
    count = (-length) % 4
    if preserved is None:
        return bytes(count)
    require(len(preserved) == count, 'incorrect preserved padding length')
    return preserved


def heap_object(header, body=None, *, locator=None, name=None, body_padding=None, name_padding=None):
    require(header != 0, 'zero is the heap terminator')
    result = word(header)
    kind = header >> 30
    if kind == 1:
        require(body is None and locator is None and name is None, 'header-only object has payload')
    elif kind == 3:
        require(locator is not None and body is None and name is None, 'reference object needs only locator')
        result += word(locator)
    elif kind == 2:
        require(body is not None and locator is None, 'body object needs body, not locator')
        external = ((header >> 28) & 3) != 3 and bool(header & 0x01000000)
        require(external == (name is not None), 'external name disagrees with header')
        result += word(len(body))
        if external:
            require(len(name) % 2 == 0 and len(name) // 2 <= 65535, 'invalid UTF-16 code-unit bytes')
            encoded = (len(name) // 2).to_bytes(2, 'big') + name
            result += encoded + padding(len(encoded), name_padding)
        result += body + padding(len(body), body_padding)
    else:
        require(False, 'unsupported heap object kind')
    return result


def heap(objects):
    result = b''.join(objects) + word(0)
    decode_heap(result, 0, len(result))
    return result


def attribute(tag, payload):
    require(1 <= tag <= 255 and len(payload) <= 0xffffff, 'invalid attribute tag or size')
    return word((tag << 24) | len(payload)) + payload


def imports(entries):
    """Entries: (kind, interface, secondary_name, selector, interface_offset, count)."""
    result = bytearray()
    for kind, name, secondary, selector, offset, count in entries:
        require(1 <= kind <= 5, 'unsupported import kind')
        names = bytearray()
        for text in (name, secondary):
            encoded = text.encode('latin1')
            require(len(encoded) <= 255, 'import name too long')
            names.extend(bytes([len(encoded)]) + encoded)
        result.extend(word(kind) + names + padding(len(names)))
        result.extend(word(selector) + word(offset) + word(count))
    result.extend(word(0))
    decode_imports(result, 0, len(result))
    return bytes(result)


def defined_components(entries):
    result = b''.join(word(kind) + word(start) + word(count) for kind, start, count in entries) + word(0)
    decode_defined_components(result, 0, len(result))
    return result


def object_addressing(cluster, auxiliary, ranges):
    result = word(cluster) + word(auxiliary)
    result += b''.join(word(start) + word(count) for start, count in ranges) + word(0)
    decode_object_addressing(result, 0, len(result))
    return result


def function_offsets(offsets, trailing_word):
    result = word(len(offsets)) + b''.join(word(0xffffffff if x is None else x) for x in offsets) + word(trailing_word)
    decode_function_offsets(result, 0, len(result))
    return result


def abbreviated_classes(entries):
    result = bytearray()
    for entry in entries:
        selector, formats = entry['class_selector'], entry['raw_format_nibbles']
        require(selector != 0 and len(formats) <= 255, 'invalid abbreviated class selector/count')
        require(all(0 <= x <= 15 for x in formats), 'invalid class format nibble')
        packed = bytearray((len(formats) + 1) // 2)
        for i, value in enumerate(formats):
            packed[i // 2] |= value << (0 if i % 2 else 4)
        # Preserve the unused low nibble when rebuilding existing data.
        original = entry.get('packed_formats_hex')
        if original is not None:
            old = bytes.fromhex(original)
            require(len(old) == len(packed), 'packed format size mismatch')
            if len(formats) % 2:
                packed[-1] |= old[-1] & 15
        part = bytes([len(formats)]) + packed
        preserved = bytes.fromhex(entry['padding_hex']) if 'padding_hex' in entry else None
        result.extend(word(selector) + part + padding(len(part), preserved))
    result.extend(word(0))
    decode_abbreviated_classes(result, 0, len(result))
    return bytes(result)


def package(attributes):
    result = SALT + word(152) + b''.join(attribute(tag, payload) for tag, payload in attributes) + word(0)
    inspect(result)
    return result


def regenerate_heap(data, decoded):
    objects = []
    for obj in decoded['objects']:
        if obj['record_kind'] == 2:
            body = obj['body']
            name = obj.get('external_name')
            objects.append(heap_object(obj['raw_header'], data[body['offset']:body['offset'] + body['length']],
                name=bytes.fromhex(name['hex']) if name else None,
                name_padding=bytes.fromhex(name['padding_hex']) if name else None,
                body_padding=bytes.fromhex(obj['padding_hex'])))
        else:
            objects.append(heap_object(obj['raw_header'], locator=obj.get('raw_locator_selector')))
    return heap(objects)


def rebuild(data):
    parsed = inspect(data)
    require('packages' in parsed, 'expected frozen package')
    packages = []
    for pkg in parsed['packages']:
        attributes = []
        for record in pkg['records']:
            p = record['payload']
            payload = (regenerate_heap(data, record['heap']) if 'heap' in record
                       else data[p['offset']:p['offset'] + p['length']])
            if 'abbreviated_classes' in record:
                payload = abbreviated_classes(record['abbreviated_classes']['entries'])
            attributes.append((record['raw_tag_byte'], payload))
        packages.append(package(attributes))
    return b''.join(packages), parsed


def main():
    out = ROOT / 'out/rosemary-inspection/rebuilt'
    reports = []
    for path in sorted((ROOT / 'software/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(8) != SALT:
                continue
        original = path.read_bytes()
        result, parsed = rebuild(original)
        require(result == original, f'rebuilt bytes differ: {path}')
        relative = path.relative_to(ROOT / 'software/mips')
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result)
        reports.append({'source': str(path.relative_to(ROOT)), 'output': str(target.relative_to(ROOT)),
                        'sha256': hashlib.sha256(result).hexdigest(), 'packages': len(parsed['packages']),
                        'heap_objects': sum(len(a.get('heap', {}).get('objects', []))
                                            for p in parsed['packages'] for a in p['records'])})
    summary = {'files': len(reports), 'packages': sum(r['packages'] for r in reports),
               'heap_objects': sum(r['heap_objects'] for r in reports)}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps({'scope': 'byte-identical envelope and heap-record reconstruction; bodies and other attributes retained',
                                             'summary': summary, 'files': reports}, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
