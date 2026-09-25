#!/usr/bin/env python3
"""Validate static pristine name dictionaries in frozen package clusters."""
import collections
import json
from build_object_names import name_tables, read_names
from inspect_format import inspect, require
from link_package_methods import ROOT, SDK, declarations, resolve_import


def main():
    interface, decls = declarations((SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef').read_text())
    rows, counts = [], collections.Counter()
    for path in sorted((ROOT / 'software/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(8) != b'\0SALTCOD':
                continue
        data = path.read_bytes()
        parsed = inspect(data)
        for package in parsed['packages']:
            imports = [e for a in package['records'] for e in a.get('imports', {}).get('entries', [])]
            objects = [o for a in package['records'] for o in a.get('heap', {}).get('objects', [])]
            by_selector = {e['selector']: objects[e['heap_object_index']] for e in package['heap_selectors']['objects']}
            def body(obj):
                b = obj['body']
                return data[b['offset']:b['offset'] + b['length']]
            for obj in objects:
                names = resolve_import(imports, 'class', obj.get('raw_class_selector', 0), {interface: decls}).get('sdk_declared_names', [])
                if names != ['StaticObjectNameDictionary']:
                    continue
                raw = body(obj)
                require(len(raw) == 16, 'unexpected name dictionary size')
                lookup_ref, text_ref, base, count = [int.from_bytes(raw[i:i + 4], 'big') for i in range(0, 16, 4)]
                lookup, text = body(by_selector[lookup_ref]), body(by_selector[text_ref])
                decoded = read_names(lookup, text, count)
                rebuilt = name_tables(decoded)
                identical = rebuilt == (lookup, text)
                counts['dictionaries'] += 1
                counts['names'] += sum(n is not None for n in decoded)
                counts['identical'] += identical
                rows.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'],
                             'package': package['index'], 'dictionary_object': obj['index'],
                             'lookup_body': by_selector[lookup_ref]['body'], 'text_body': by_selector[text_ref]['body'],
                             'byte_identical': identical, 'names': [{'selector': base + i * 8, 'name': n}
                                                                   for i, n in enumerate(decoded) if n is not None]})
    out = ROOT / 'out/rosemary-inspection/object-names-validation.json'
    out.write_text(json.dumps({'summary': dict(counts), 'entries': rows}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
