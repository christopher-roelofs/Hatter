#!/usr/bin/env python3
"""Check plain Text decoding against imported Text objects in the package corpus."""
import collections
import json
from build_object_values import plain_text, read_plain_text
from inspect_format import FormatError, inspect
from link_package_methods import ROOT, SDK, declarations, resolve_import


def main():
    interfaces = {}
    for name in ('InternalInterface.cdef', 'PublicInterface.cdef', 'ConditionalInterface.cdef'):
        key, entries = declarations((SDK / 'Interfaces/DefFiles/Interfaces' / name).read_text())
        interfaces[key] = entries
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
            for attr in package['records']:
                for obj in attr.get('heap', {}).get('objects', []):
                    if 'body' not in obj or 'raw_class_selector' not in obj:
                        continue
                    names = resolve_import(imports, 'class', obj['raw_class_selector'], interfaces).get('sdk_declared_names', [])
                    if names != ['Text'] or 'body' not in obj:
                        continue
                    location = obj['body']
                    body = data[location['offset']:location['offset'] + location['length']]
                    row = {'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'],
                           'package': package['index'], 'object': obj['index'], 'body': location}
                    try:
                        value = read_plain_text(body)
                    except FormatError as error:
                        row.update(status='unsupported', reason=str(error))
                    else:
                        encoded = plain_text(value)
                        assert read_plain_text(encoded) == value
                        row.update(status='identical' if encoded == body else 'equivalent-plain-text', text=value)
                    counts[row['status']] += 1
                    rows.append(row)
    output = ROOT / 'out/rosemary-inspection/text-validation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'summary': dict(counts), 'entries': rows}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
