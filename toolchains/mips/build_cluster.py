#!/usr/bin/env python3
"""Construct supported cluster bodies from explicit fixed fields and identity."""
from build_object_values import fixed_body
from inspect_format import require


def read_fixed_values(layout, body):
    """Decode supported SDK fields; reject unmodeled bits by reconstructing."""
    require(len(body) == layout['fixed_storage_bytes'], 'fixed body size mismatch')
    values = {}
    for field in layout['fields']:
        offset, width, kind = field['bit_offset'], field['bit_width'], field['type']
        start = offset // 8
        raw = body[start:start + width // 8]
        if kind == 'Boolean':
            value = bool(body[start] & (1 << (7 - offset % 8)))
        elif kind == 'Dot':
            value = [int.from_bytes(raw[:4], 'big', signed=True), int.from_bytes(raw[4:], 'big', signed=True)]
        else:
            value = int.from_bytes(raw, 'big', signed=kind == 'Signed')
        values[field['name']] = value
    require(fixed_body(layout, values) == body, 'unmodeled fixed bits or unsupported values')
    return values


def cluster_body(layout, values, internal_name):
    require(layout['class'] in ('PackageCluster', 'CodePackageCluster'), 'unsupported cluster class')
    require(isinstance(internal_name, str) and 1 <= len(internal_name) <= 128,
            'internal package name must contain 1..128 characters')
    require(all(0 < ord(c) < 128 for c in internal_name), 'only non-NUL ASCII internal names supported')
    extra = internal_name.encode('ascii') + b'\0'
    extra += bytes(-len(extra) % 4)
    return fixed_body(layout, values) + extra
