#!/usr/bin/env python3
"""Compare abbreviated fixed sizes to named SDK class layouts."""
import collections
import hashlib
import json
from inspect_format import inspect
from link_package_methods import ROOT, SDK, declarations, resolve_import


def main():
    path = SDK / 'Interfaces/MagicCap.cx'
    data = path.read_bytes()
    classes = {r['name_latin1']: r['layout'] for s in inspect(data)['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    interfaces, sources = {}, [{'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest()}]
    for name in ('InternalInterface.cdef', 'PublicInterface.cdef', 'ConditionalInterface.cdef'):
        path = SDK / 'Interfaces/DefFiles/Interfaces' / name
        key, entries = declarations(path.read_text())
        interfaces[key] = entries
        sources.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    reports, counts = [], collections.Counter()
    for path in sorted((ROOT / 'software/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as f:
            if f.read(8) != b'\0SALTCOD':
                continue
        parsed = inspect(path.read_bytes())
        for package in parsed['packages']:
            imports = [e for a in package['records'] for e in a.get('imports', {}).get('entries', [])]
            for attr in package['records']:
                for entry in attr.get('abbreviated_classes', {}).get('entries', []):
                    mapped = resolve_import(imports, 'class', entry['class_selector'], interfaces)
                    names = mapped.get('sdk_declared_names', [])
                    layout = classes.get(names[0], {}) if len(names) == 1 else {}
                    size = layout.get('fixed_storage_bytes')
                    status = 'sdk-size-match' if size == 4 * entry['format_count'] else 'sdk-size-mismatch' if size is not None else 'no-sdk-size-comparison'
                    counts[status] += 1
                    reports.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'],
                                    'package': package['index'], **entry, 'import': mapped,
                                    'sdk_fixed_bytes': size, 'comparison': status})
    out = ROOT / 'out/rosemary-inspection/abbreviated-classes.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'sources': sources, 'summary': dict(counts), 'entries': reports}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
