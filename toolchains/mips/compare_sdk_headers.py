#!/usr/bin/env python3
"""Compare decoded system class/operation numbers with SDK-generated headers."""
import collections
import hashlib
import json
from pathlib import Path
import re
from inspect_format import inspect

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Interfaces'


def main():
    header_path = SDK / 'Apollo/MagicCap.gnu.xh'
    image_path = SDK / 'MagicCap.cx'
    header = header_path.read_bytes().decode('mac_roman')
    classes = {name: {int(number)} for name, number in re.findall(
        r'#define (\w+)_ \(\(ClassNumber\)(\d+)\)', header)}
    operations = collections.defaultdict(set)
    for name, number in re.findall(
            r'#define (?:operation|intrinsic)_(\w+) \(\((?:ClassOperationNumber|OperationNumber|IntrinsicNumber)\)(\d+)\)', header):
        operations[name].add(int(number))
    result = {'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (header_path, image_path)}, 'sections': {}}
    for section in inspect(image_path.read_bytes())['sections']:
        tag = section['raw_tag']
        if tag not in (13, 16):
            continue
        definitions = classes if tag == 13 else operations
        number_key = 'class_number' if tag == 13 else 'operation_number'
        comparison = {'records': len(section['named_records']), 'matched': 0,
                      'not_in_header': [], 'mismatches': []}
        for record in section['named_records']:
            name = record['name_latin1']
            values = definitions.get(name, set())
            if not values:
                comparison['not_in_header'].append(name)
            elif record[number_key] in values:
                comparison['matched'] += 1
            else:
                comparison['mismatches'].append({'name': name, 'record_number': record[number_key],
                                                'header_numbers': sorted(values)})
        result['sections'][str(tag)] = comparison
    output = ROOT / 'out/rosemary-inspection/header-comparison.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    for tag, section in result['sections'].items():
        print(f'Section {tag}: {section["matched"]} match, '
              f'{len(section["not_in_header"])} absent from header, '
              f'{len(section["mismatches"])} mismatches')
    return int(any(s['mismatches'] for s in result['sections'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
