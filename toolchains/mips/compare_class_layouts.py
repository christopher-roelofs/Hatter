#!/usr/bin/env python3
"""Check decoded class layout against private headers and selected source definitions."""
import hashlib
import json
from pathlib import Path
import re
from inspect_format import inspect

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Interfaces'


def main():
    results = {'header_checks': [], 'source_checks': [], 'field_checks': [], 'method_checks': [], 'source_hashes': {}}

    def read(path):
        data = path.read_bytes()
        results['source_hashes'][str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
        return data

    for profile in ('Apollo', 'Sputnik', 'Simulator'):
        folder = SDK / profile / 'ExtraInterfaces'
        for path in sorted(folder.iterdir()):
            if path.suffix not in ('.x', '.cx'):
                continue
            for section in inspect(read(path))['sections']:
                if section['raw_tag'] != 13:
                    continue
                for record in section['named_records']:
                    layout = record['layout']
                    name = record['name_latin1']
                    header = folder / (name + '.xph')
                    if layout['status'] != 'decoded-observed-prefix-1' or not header.is_file():
                        continue
                    text = read(header).decode('mac_roman')
                    expected = dict(re.findall(r'#define _' + re.escape(name)
                                              + r'_(base|fixedOffset|leafSize)_ (\w+)', text))
                    if set(expected) != {'base', 'fixedOffset', 'leafSize'}:
                        continue
                    actual = {'base': layout['field_access_base']['name_latin1'],
                              'fixedOffset': str(layout['fixed_offset_bytes']),
                              'leafSize': str(layout['leaf_storage_bytes'])}
                    results['header_checks'].append({'file': str(path.relative_to(ROOT)),
                                                     'class': name, 'expected': expected,
                                                     'actual': actual, 'match': expected == actual})
                    for field in record['members']['fields']:
                        prefix = re.escape('_' + name + '_' + field['name_latin1'])
                        match = re.search(r'#define ' + prefix + r'_fixedOffset_ ([0-9]+)(?:,([0-9]+))?', text)
                        if not match:
                            continue
                        header_bits = int(match.group(1)) * 8 + int(match.group(2) or 0)
                        results['field_checks'].append({'file': str(header.relative_to(ROOT)),
                                                       'class': name, 'field': field['name_latin1'],
                                                       'decoded_fixed_bit_offset': field['fixed_bit_offset'],
                                                       'header_fixed_bit_offset': header_bits,
                                                       'decoded_type_name': field['type_name_latin1'],
                                                       'match': field['fixed_bit_offset'] == header_bits})
                    prototypes = set(re.findall(r'\b' + re.escape(name) + r'_(\w+)\(', text))
                    bindings = {method['name_latin1'] for method in record['members']['methods']}
                    results['method_checks'].append({'file': str(header.relative_to(ROOT)), 'class': name,
                                                    'binding_names': sorted(bindings),
                                                    'prototype_names': sorted(prototypes),
                                                    'match': bindings == prototypes})
    image = inspect(read(SDK / 'MagicCap.cx'))
    classes = {r['name_latin1']: r for s in image['sections'] if s['raw_tag'] == 13
               for r in s['named_records']}
    for path in sorted((SDK / 'Apollo/ExtraInterfaces').glob('*.x')):
        for section in inspect(read(path))['sections']:
            if section['raw_tag'] == 13:
                for record in section['named_records']:
                    if record['layout']['status'] == 'decoded-observed-prefix-1':
                        classes[record['name_latin1']] = record
    targets = {'FilingChoice', 'HasReinitialize', 'HasDate', 'MagicBeam', 'DisplayServer', 'BacklightButton'}
    for path in sorted((SDK / 'DefFiles').rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.def', '.cdef'):
            continue
        text = path.read_bytes().decode('mac_roman').replace('\r', '\n')
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
        for name, body in re.findall(r'define class (\w+);(.*?)end class;', text, re.S):
            if name not in targets or name not in classes:
                continue
            read(path)
            layout = classes[name]['layout']
            expected = {}
            for phrase, label in [('inherits from', 'inherits_from'), ('mixes in with', 'mixes_in_with')]:
                expected[label] = [n.strip() for clause in re.findall(phrase + r'\s+([^;]+);', body)
                                   for n in clause.split(',')]
            actual = {key: [item['name_latin1'] for item in layout[key]] for key in expected}
            results['source_checks'].append({'class': name, 'file': str(path.relative_to(ROOT)),
                                             'expected': expected, 'actual': actual,
                                             'match': expected == actual})
    # Preserve alternative conditional definitions; do not pretend to preprocess
    # the platform-specific source or require every branch to describe one build.
    grouped = {}
    for check in results['source_checks']:
        key = (check['file'], check['class'])
        group = grouped.setdefault(key, {'file': check['file'], 'class': check['class'],
                                         'actual': check['actual'], 'source_variants': [],
                                         'match': False})
        group['source_variants'].append(check['expected'])
        group['match'] |= check['match']
    results['source_checks'] = list(grouped.values())
    output = ROOT / 'out/rosemary-inspection/layout-comparison.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + '\n')
    failed = False
    for key in ('header_checks', 'source_checks', 'field_checks', 'method_checks'):
        checks = results[key]
        bad = sum(not x['match'] for x in checks)
        print(f'{key}: {len(checks)} comparisons, {bad} mismatches')
        failed |= bad > 0 or not checks
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
