#!/usr/bin/env python3
"""Read frozen package export tables; selectors remain package-relative."""
from inspect_format import require, u32

KINDS = {1: 'locator', 2: 'class', 3: 'operation', 4: 'class-operation', 5: 'intrinsic'}


def decode_entries(data, entries_body, names_body):
    start, length = entries_body['offset'], entries_body['length']
    ns, nl = names_body['offset'], names_body['length']
    require(start >= 0 and length >= 4 and start + length <= len(data), 'truncated export entries')
    require(ns >= 0 and nl >= 8 and ns + nl <= len(data), 'truncated export names')
    count = u32(data, start)
    require(length == 4 + count * 16, 'unsupported export entries layout')
    result = []
    for i in range(count):
        pos = start + 4 + i * 16
        link = u32(data, pos)
        if link & 0x80000000:  # Iterator ignores unused/deleted slots.
            continue
        packed, size, selector = (u32(data, pos + j) for j in (4, 8, 12))
        kind, offset = packed >> 24, packed & 0xffffff
        require(kind in KINDS, 'unsupported export kind')
        p = ns + 8 + offset
        require(p < ns + nl, 'export name offset outside buffer')
        n = data[p]
        require(p + 1 + n <= ns + nl, 'truncated export name')
        name = data[p + 1:p + 1 + n].decode('latin1')
        result.append({'slot': i + 1, 'record_offset': pos, 'raw_link': link,
                       'kind': KINDS[kind], 'name': name, 'count': size,
                       'selector_start': selector, 'local': name.startswith('@')})
    return result


def package_exports(data, package):
    objects = [o for a in package['records'] for o in a.get('heap', {}).get('objects', [])]
    selectors = {e['selector']: e['heap_object_index'] for e in package.get('heap_selectors', {}).get('objects', [])}
    if not objects:
        return []
    imports = [e for a in package['records'] for e in a.get('imports', {}).get('entries', [])]
    def check_class(obj, allowed):
        selector = obj['raw_class_selector']
        matches = [(e['name']['text_latin1'], e['raw_range_word'] + selector - e['raw_component_word'])
                   for e in imports if e['kind'] == 'class'
                   and e['raw_component_word'] <= selector < e['raw_component_word'] + e['count']]
        require(len(matches) == 1 and matches[0][0] == 'SystemInternal'
                and matches[0][1] in allowed, 'unsupported export object class')
    def body(selector, class_offset):
        require(selector in selectors, 'export object missing from heap map')
        obj = objects[selectors[selector]]
        check_class(obj, (class_offset,))
        result = obj.get('body')
        require(result is not None, 'export object has no body')
        return result
    check_class(objects[0], (6, 7))  # SimpleDataPackageCluster / CodePackageCluster.
    cluster = objects[0].get('body', {})
    require(cluster.get('length', 0) >= 0x5c, 'cluster lacks export table field')
    table_selector = u32(data, cluster['offset'] + 0x58)
    if table_selector == 0:
        return []
    table = body(table_selector, 11)
    require(table['length'] >= 0x1c, 'truncated export table')
    entries = body(u32(data, table['offset']), 47)
    names = body(u32(data, table['offset'] + 0x18), 12)
    return decode_entries(data, entries, names)


def resolve_local(source, exports):
    matches = [e for e in exports if e['kind'] == source['component_kind'] and e['name'] == source['interface']]
    if len(matches) != 1:
        return {'status': 'missing-local-export' if not matches else 'ambiguous-local-export'}
    export = matches[0]
    index, count = source['index'], source['required_count']
    if index < 0 or count < 0 or index + count > export['count']:
        return {'status': 'local-export-range-mismatch', 'export': export}
    stride = 8 if export['kind'] == 'locator' else 1
    return {'status': 'mapped-local-export', 'selector': export['selector_start'] + index * stride,
            'export_record_offset': export['record_offset']}
