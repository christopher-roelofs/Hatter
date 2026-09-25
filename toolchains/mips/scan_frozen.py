#!/usr/bin/env python3
"""Inspect all SALTCOD files under software/mips; retain hashed read-only reports."""
import collections
import json
from pathlib import Path
from inspect_format import SALT, inspect


def main():
    root = Path(__file__).resolve().parents[2]
    reports = []
    kinds = collections.Counter()
    heap_kinds = collections.Counter()
    initialization = collections.Counter()
    tables = slots = linked = nulls = 0
    for path in sorted((root / 'software/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(8) != SALT:
                continue
        report = {'path': str(path.relative_to(root)), **inspect(path.read_bytes())}
        reports.append(report)
        for package in report['packages']:
            for entry in package['function_code'].get('entries', []):
                linked += entry['status'] == 'located-in-code-attribute'
                nulls += entry['status'] == 'null-method'
            for record in package['records']:
                if 'global_initialization' in record:
                    script = record['global_initialization']
                    initialization[script['status']] += 1
                    initialization['instructions'] += len(script['instructions'])
                    initialization['resolution_entries'] += sum(len(i.get('entries', [])) for i in script['instructions'])
                for obj in record.get('heap', {}).get('objects', []):
                    heap_kinds[str(obj['record_kind'])] += 1
                for entry in record.get('imports', {}).get('entries', []):
                    kinds[entry['kind']] += 1
                if 'function_offsets' in record:
                    tables += 1
                    slots += record['function_offsets']['count']
    summary = {'files': len(reports), 'packages': sum(len(r['packages']) for r in reports),
               'import_entries': sum(kinds.values()), 'import_kinds': dict(kinds),
               'function_offset_tables': tables, 'function_offset_slots': slots,
               'located_code_entries': linked, 'null_method_entries': nulls,
               'heap_records': sum(heap_kinds.values()), 'heap_record_kinds': dict(heap_kinds), 'global_initialization': dict(initialization)}
    output = root / 'out/rosemary-inspection'
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('frozen-corpus.json', reports), ('import-summary.json', summary)]:
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
