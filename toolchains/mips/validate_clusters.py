#!/usr/bin/env python3
"""Rebuild corpus cluster fields and identities; record metadata dependencies."""
import collections
import json
from build_cluster import read_fixed_values, cluster_body
from derive_fixed_formats import derive
from inspect_format import inspect, require
from link_package_methods import ROOT, SDK, declarations, resolve_import


def main():
    source = SDK / 'Interfaces/MagicCap.cx'
    classes = {r['name_latin1']: r for s in inspect(source.read_bytes())['sections'] if s['raw_tag'] == 13 for r in s['named_records']}
    layouts = {n: derive(n, classes, {}) for n in ('PackageCluster', 'CodePackageCluster', 'PackageData')}
    interface, decls = declarations((SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef').read_text())
    counts, rows = collections.Counter(), []
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
            root = objects[0]
            names = resolve_import(imports, 'class', root.get('raw_class_selector', 0), {interface: decls}).get('sdk_declared_names', [])
            require(len(names) == 1 and names[0] in ('PackageCluster', 'CodePackageCluster'), 'unexpected cluster class')
            layout = layouts[names[0]]
            def body(obj):
                b = obj['body']
                return data[b['offset']:b['offset'] + b['length']]
            raw = body(root)
            values = read_fixed_values(layout, raw[:layout['fixed_storage_bytes']])
            extra = raw[layout['fixed_storage_bytes']:]
            require(b'\0' in extra, 'unterminated cluster name')
            name = extra.split(b'\0', 1)[0].decode('ascii')
            require(cluster_body(layout, values, name) == raw, 'cluster reconstruction mismatch')
            by_selector = {e['selector']: objects[e['heap_object_index']] for e in package['heap_selectors']['objects']}
            pd = by_selector[values['packageData']]
            require(resolve_import(imports, 'class', pd['raw_class_selector'], {interface: decls}).get('sdk_declared_names') == ['PackageData'], 'wrong packageData class')
            pd_values = read_fixed_values(layouts['PackageData'], body(pd))
            counts[names[0]] += 1
            counts['byte_identical'] += 1
            rows.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'], 'package': package['index'],
                         'class': names[0], 'body': root['body'], 'internal_name': name, 'fields': values,
                         'package_data_body': pd['body'], 'package_data_fields': pd_values})
    out = ROOT / 'out/rosemary-inspection/cluster-validation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'summary': dict(counts), 'clusters': rows}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
