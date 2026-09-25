#!/usr/bin/env python3
"""Read-only SDK interface and frozen method-list linkage; no runtime ROM addresses."""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
from inspect_format import inspect, require, span, u32
from package_exports import package_exports

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper'


def declarations(text):
    """Literal interface declarations only; preserve conditional/duplicate names."""
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    name = re.search(r'define interface (\w+)\s*;', text)
    require(name is not None, 'missing interface declaration')
    # A cdef can contain further interfaces; they must not pollute the first.
    text = text[name.end():].split('end interface;', 1)[0]
    result = collections.defaultdict(list)
    for kind, label, ordinal in re.findall(
            r'^\s*(class operation|class|operation|intrinsic|indexical)\s+(\w+)\s*=\s*(\d+)\s*;', text, re.M):
        kind = 'locator' if kind == 'indexical' else kind.replace(' ', '-')
        result[(kind, int(ordinal) - 1)].append(label)
    return name[1], result


def resolve_import(entries, kind, selector, interfaces):
    matches = []
    for entry in entries:
        start = entry['raw_component_word']
        stride = 8 if kind == 'locator' else 1
        delta = selector - start
        if entry['kind'] != kind or not 0 <= delta < entry['count'] * stride or delta % stride:
            continue
        offset = entry['raw_range_word'] + delta // stride
        interface = entry['name']['text_latin1']
        names = interfaces.get(interface, {}).get((kind, offset), [])
        matches.append({'interface': interface, 'interface_offset': offset,
                        'sdk_declared_names': sorted(set(names))})
    if not matches:
        return {'status': 'not-imported'}
    if len(matches) != 1:
        return {'status': 'ambiguous-import', 'matches': matches}
    return {'status': 'mapped-to-interface', **matches[0]}


def resolve_component(imports, definitions, kind, selector, interfaces):
    imported = resolve_import(imports, kind, selector, interfaces)
    local = [e for e in definitions if e['kind'] == kind
             and e['selector_start'] <= selector < e['selector_start'] + e['count']]
    if not local:
        return imported
    if len(local) != 1 or imported['status'] != 'not-imported':
        return {'status': 'ambiguous-component'}
    entry = local[0]
    return {'status': 'package-defined', 'selector': selector,
            'range_start': entry['selector_start'],
            'range_offset': selector - entry['selector_start']}


def method_list(data, body, field_offset=2):
    start, length = body['offset'], body['length']
    end = start + length
    require(0 <= field_offset and length >= field_offset + 2 and end <= len(data), 'truncated class flavor')
    offset = struct.unpack_from('>H', data, start + field_offset)[0]
    if offset == 0:
        return []
    cursor = start + offset
    require(cursor + 4 <= end, 'method list header outside class body')
    count, skip = struct.unpack_from('>HH', data, cursor)
    count &= 0x7fff
    cursor += 4 + skip
    require(cursor + count * 8 <= end, 'method records outside class body')
    records = []
    for index in range(count):
        pos = cursor + index * 8
        header, value = u32(data, pos), u32(data, pos + 4)
        records.append({'raw_header': header, 'operation_selector': header & 0xfffff,
                        'raw_value': value, 'native': header >> 24 > 0x40,
                        'record': span(data, pos, pos + 8)})
    return records


def class_array(data, package, imports, definitions, interfaces):
    objects = [o for a in package['records'] for o in a.get('heap', {}).get('objects', [])]
    selectors = {e['selector']: e['heap_object_index']
                 for e in package.get('heap_selectors', {}).get('objects', [])}
    if not objects or not selectors:
        return {}
    cluster = objects[0]
    mapped = resolve_import(imports, 'class', cluster.get('raw_class_selector', 0), interfaces)
    if mapped.get('interface') != 'SystemInternal' or mapped.get('sdk_declared_names') != ['CodePackageCluster']:
        return {}
    body = cluster.get('body', {})
    require(body.get('length', 0) >= 0x98, 'truncated code package cluster fields')
    start = body['offset']
    array, base, count = (u32(data, start + offset) for offset in (0x64, 0x8c, 0x94))
    require(count <= len(objects), 'class array count exceeds heap')
    result = {}
    for index in range(count):
        selector = base + index
        definition = resolve_component(imports, definitions, 'class', selector, interfaces)
        require(definition['status'] == 'package-defined', 'class array outside local class definitions')
        locator = array + index * 8
        require(locator in selectors, 'class array locator absent from heap map')
        object_index = selectors[locator]
        require(object_index not in result, 'duplicate class array locator')
        result[object_index] = {'selector': selector, 'class_range': definition,
                                'locator_selector': locator, 'array_index': index}
    return result


def link_package(data, package, interfaces):
    exports = package_exports(data, package)
    def local_names(kind, selector):
        return sorted(set(e['name'][1:] for e in exports if e['local']
                          and e['kind'] == kind and e['count'] == 1
                          and e['selector_start'] == selector))
    imports = [e for a in package['records'] for e in a.get('imports', {}).get('entries', [])]
    definitions = [e for a in package['records']
                   for e in a.get('defined_components', {}).get('entries', [])]
    code = {e['function_id']: e for e in package['function_code'].get('entries', [])}
    identities = class_array(data, package, imports, definitions, interfaces)
    classes = []
    for attr in package['records']:
        for obj in attr.get('heap', {}).get('objects', []):
            if 'body' not in obj:
                continue
            mapped = resolve_import(imports, 'class', obj['raw_class_selector'], interfaces)
            if mapped.get('sdk_declared_names') != ['UnlinkedClassWithInstances']:
                continue
            if mapped['interface'] != 'SystemInternal':
                continue
            methods = []
            for kind, field_offset in [('operation', 2), ('class-operation', 8), ('intrinsic', 6)]:
                for method in method_list(data, obj['body'], field_offset):
                    method['component_kind'] = kind
                    methods.append(method)
            for method in methods:
                method['operation'] = resolve_component(imports, definitions, method['component_kind'], method['operation_selector'], interfaces)
                method['operation']['package_exported_names'] = local_names(method['component_kind'], method['operation_selector'])
                if method['native']:
                    method['function'] = code.get(method['raw_value'], {'status': 'function-id-not-in-decoded-table'})
            if obj['index'] in identities:
                identities[obj['index']]['package_exported_names'] = local_names('class', identities[obj['index']]['selector'])
            classes.append({'heap_object_index': obj['index'], 'body': obj['body'],
                            'metaclass': mapped, 'represented_class': identities.get(obj['index'], {'status': 'not-in-class-array'}),
                            'methods': methods})
    return classes


def main():
    interfaces = {}
    sources = []
    for filename in ['InternalInterface.cdef', 'PublicInterface.cdef', 'ConditionalInterface.cdef']:
        path = SDK / 'Interfaces/DefFiles/Interfaces' / filename
        name, decls = declarations(path.read_text())
        interfaces[name] = decls
        sources.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    reports = []
    counts = collections.Counter()
    for path in sorted((ROOT / 'software/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(8) != b'\0SALTCOD':
                continue
        data = path.read_bytes()
        parsed = inspect(data)
        for package in parsed['packages']:
            classes = link_package(data, package, interfaces)
            expected = {e['function_id'] for e in package['function_code'].get('entries', [])
                        if e['status'] == 'located-in-code-attribute'}
            observed = {m['raw_value'] for cls in classes for m in cls['methods'] if m['native']}
            coverage = {'unreferenced_function_ids': sorted(expected - observed),
                        'unlocated_function_ids': sorted(observed - expected)}
            counts['packages_with_complete_function_coverage'] += not any(coverage.values())
            counts['class_flavors'] += len(classes)
            counts['identified_class_selectors'] += sum('selector' in c['represented_class'] for c in classes)
            for cls in classes:
                for method in cls['methods']:
                    counts['methods'] += 1
                    counts['native' if method['native'] else 'non_native'] += 1
                    counts['operation_' + method['operation']['status']] += 1
                    if method['operation'].get('sdk_declared_names'):
                        counts['sdk_named_operations'] += 1
                    if method['native']:
                        counts[method['function']['status']] += 1
            reports.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'],
                            'package': package['index'], 'function_coverage': coverage, 'class_flavors': classes})
    out = ROOT / 'out/rosemary-inspection/package-methods.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'scope': 'SDK-declared interface names; represented class names and runtime binding unchecked',
                              'sources': sources, 'summary': dict(counts), 'packages': reports}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
