#!/usr/bin/env python3
"""Compare empty metadata constructors with matching corpus objects."""
import collections
import json
from build_package_metadata import empty_metadata, METADATA_CLASSES
from derive_fixed_formats import derive
from inspect_format import inspect, require
from link_package_methods import ROOT, SDK, declarations, resolve_import


def main():
    classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    layouts = {n: derive(n, classes, {}) for n in set(METADATA_CLASSES.values())}
    interfaces = {}
    for fn in ('PublicInterface.cdef', 'InternalInterface.cdef'):
        name, decls = declarations((SDK / 'Interfaces/DefFiles/Interfaces' / fn).read_text())
        interfaces[name] = decls
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
            objects = [o for a in package['records'] for o in a.get('heap', {}).get('objects', [])]
            mapping = {e['selector']: objects[e['heap_object_index']] for e in package['heap_selectors']['objects']}
            imports = [e for a in package['records'] for e in a.get('imports', {}).get('entries', [])]
            def body(selector):
                span = mapping[selector]['body']
                return data[span['offset']:span['offset'] + span['length']]
            def ref(selector, offset):
                return int.from_bytes(body(selector)[offset:offset + 4], 'big')
            selectors = dict(sharedTable=ref(4, 60), packageData=ref(4, 80), exports=ref(4, 88))
            selectors.update(sharedEntries=ref(selectors['sharedTable'], 0), sharedObjects=ref(selectors['sharedTable'], 24),
                             exportEntries=ref(selectors['exports'], 0), exportNames=ref(selectors['exports'], 24),
                             missingNames=ref(selectors['packageData'], 4), missingIndexicals=ref(selectors['packageData'], 8))
            generated, _ = empty_metadata(layouts, selectors)
            shared_empty = ref(selectors['sharedTable'], 12) == 0
            exports_empty = ref(selectors['exports'], 12) == 0
            for name, encoded in generated.items():
                if name.startswith('shared') and not shared_empty:
                    continue
                if name in ('exports', 'exportEntries', 'exportNames') and not exports_empty:
                    continue
                obj = mapping[selectors[name]]
                require(resolve_import(imports, 'class', obj['raw_class_selector'], interfaces).get('sdk_declared_names') == [METADATA_CLASSES[name]], 'unexpected metadata class')
                original = body(selectors[name])
                same = encoded == original
                counts['identical' if same else 'different'] += 1
                counts[name] += 1
                rows.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'], 'package': package['index'],
                             'object': name, 'body': obj['body'], 'identical': same})
    out = ROOT / 'out/rosemary-inspection/package-metadata-validation.json'
    out.write_text(json.dumps({'summary': dict(counts), 'entries': rows}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
