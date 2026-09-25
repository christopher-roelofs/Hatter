#!/usr/bin/env python3
"""Verify representative compiled accessor bindings against class source declarations."""
import hashlib
import json
from pathlib import Path
import re
from inspect_format import inspect

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper/Interfaces'


def main():
    image_path = SDK / 'MagicCap.cx'
    image = inspect(image_path.read_bytes())
    classes = {r['name_latin1']: r for s in image['sections'] if s['raw_tag'] == 13
               for r in s['named_records']}
    targets = {'HasDate', 'HasAccountInfo', 'Form'}
    checks = []
    hashes = {str(image_path.relative_to(ROOT)): hashlib.sha256(image_path.read_bytes()).hexdigest()}
    for path in sorted((SDK / 'DefFiles').rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.def', '.cdef'):
            continue
        data = path.read_bytes()
        text = data.decode('mac_roman').replace('\r', '\n')
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
        for name, body in re.findall(r'define class (\w+);(.*?)end class;', text, re.S):
            if name not in targets:
                continue
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
            expected = []
            for field, type_name, options in re.findall(r'field\s+(\w+)\s*:\s*(\w+)([^;]*);', body):
                modifiers = {x.strip() for x in options.split(',')}
                operation = field[0].upper() + field[1:]
                if 'getter' in modifiers:
                    expected.append((operation, field, 'text-getter' if type_name == 'Text' else 'getter'))
                if 'setter' in modifiers:
                    expected.append(('Set' + operation, field, 'text-setter' if type_name == 'Text' else 'setter'))
                if 'sharedSetter' in modifiers:
                    expected.append(('Set' + operation, field, 'shared-setter'))
            actual = [(m['name_latin1'], m['binding']['field_name_latin1'], m['binding']['kind'])
                      for m in classes[name]['members']['methods'] if 'field_name_latin1' in m['binding']]
            checks.append({'class': name, 'source': str(path.relative_to(ROOT)),
                           'source_accessors': sorted(expected), 'compiled_accessors': sorted(actual),
                           'match': sorted(expected) == sorted(actual)})
    report = {'sources': hashes, 'checks': checks}
    output = ROOT / 'out/rosemary-inspection/accessor-comparison.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    count = sum(len(x['source_accessors']) for x in checks)
    failures = sum(not x['match'] for x in checks)
    print(f'{len(checks)} classes, {count} accessor bindings, {failures} mismatches')
    return int(failures > 0 or len(checks) != len(targets))


if __name__ == '__main__':
    raise SystemExit(main())
