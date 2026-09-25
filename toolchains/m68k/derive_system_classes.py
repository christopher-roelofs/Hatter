#!/usr/bin/env python3
"""What the system classes are worth, read out of the packages that use them.

Three numbers in a `Class` record are sums over the classes it inherits from:
`wirelineDepth`, `totalCopyReferences` and `wirelineBaseClassNumber`. The SDK
states none of them for the system's own classes, so they are recovered the
way the system instance sizes were -- a record whose implementation parents
are all known bar one says what that one must be worth -- and the result is
written to `system_classes.json` for the builder to use.

    python3 derive_system_classes.py            # print what it finds
    python3 derive_system_classes.py --write    # and save it
    python3 derive_system_classes.py --fields   # re-check the field numbers

`--fields` is a separate check on `class_records.field_number`: it holds the
encoding to `NoDebug/FieldNumbers.h`, which states the number of every field
in the system, rather than to anything derived here.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import struct
import sys

from class_records import field_kind, field_number
from classdefs import Definitions, read, strip_comments
from inspect_package import SDK_INTERFACES, inspect, load_numbers
from objects_def import project_order

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'software/68k/extracted/cookbook/Cookbook Examples'
PACKAGES = ROOT / 'software/68k/extracted/installable/cookbook'
OUTPUT = Path(__file__).with_name('system_classes.json')

DEFINE_CLASS = re.compile(r'Define\s+Class\s+(\w+)\s*;')
PACKAGE_CLASS = re.compile(r'package class (\d+)$')


def class_records(definitions, tables):
    """Every class record in the cookbook, with its parents named.

    A parent that is another class of the same package comes back from the
    decode as "package class 2"; it is turned into that class's name here, so
    that everything downstream deals in names.
    """
    for directory in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
        package = PACKAGES / f'{directory.name}.pkg'
        if not package.exists():
            continue
        raw = package.read_bytes()
        decoded = inspect(raw, tables, definitions)
        declared = []
        for filename in project_order(directory):
            declared += DEFINE_CLASS.findall(
                strip_comments(read(directory / filename)))
        records = sorted((o for o in decoded['objects']
                          if o.get('class_name') == 'Class'),
                         key=lambda o: o['class_record']['number'])
        local = {}
        for entry, name in zip(records, declared):
            at = entry['offset']
            payload = raw[at + 12:at + entry['length']]
            flags, base, depth = struct.unpack_from('>HBB', payload, 0x14)
            references, copies, total = struct.unpack_from(
                '>III', payload, 0x24)
            record = entry['class_record']
            local[record['number']] = {
                'package': directory.name, 'name': name, 'flags': flags,
                'base': base, 'depth': depth, 'copy_mask': copies,
                'reference_mask': references, 'copies': total,
                'number': record['number'],
                'size': record['instance_size'],
                'own': record['own_bytes'],
                'interfaces': [i['class_number']
                               for i in record['interfaces']],
                'supers': [s['class_name']
                           for s in record.get('inherits_from', [])],
            }
        for number, value in local.items():
            value['parents'] = [
                local[0x8000 | int(m.group(1))]['name']
                if (m := PACKAGE_CLASS.match(s or '')) else s
                for s in value['supers']]
        yield directory.name, local


def solve(rows, by_name=None):
    """The system classes, and the records that do not come out.

    Each pass looks for a record with exactly one parent it does not yet know
    and reads that parent's worth off it. Repeating settles everything the
    corpus can reach; what is left is a class nothing pins down.
    """
    by_name = by_name or {}
    known = {(r['package'], r['name']): r for r in rows}
    system = {}

    def worth(package, name):
        if (package, name) in known:
            entry = known[(package, name)]
            return {'depth': entry['depth'], 'copies': entry['copies'],
                    'base': entry['base'], 'size': entry['size'],
                    'answers': entry['interfaces'] + [entry['number']]}
        return system.get(name)

    for _ in range(8):
        for row in rows:
            unknown = [p for p in row['parents']
                       if worth(row['package'], p) is None]
            if len(unknown) != 1:
                continue
            others = [worth(row['package'], p) for p in row['parents']
                      if p != unknown[0]]
            found = {
                'depth': row['depth'] - 1 - sum(o['depth'] for o in others),
                'copies': (row['copies']
                           - bin(row['copy_mask']).count('1')
                           - sum(o['copies'] for o in others)),
                'base': row['base'],
                # An instance is its parents' instances end to end plus what
                # the class adds, so the same subtraction gives the size.
                'size': row['size'] - row['own'] - sum(o['size']
                                                       for o in others),
            }
            found['answers'] = None
            system[unknown[0]] = found

    # The interface lists go in a pass of their own, over every record with
    # one parent, because each such record is only an upper bound: a class
    # may answer as more than its parent does, with `inherits interface
    # from`. Intersecting what the records say leaves what the parent itself
    # answers as, and there is nowhere else to get it -- `EditsTarget` and
    # `FormElement` have class numbers and no declaration anywhere in the
    # SDK. BizNote is the case that needs it: its `PeopleTextField` carries
    # one interface more than its two siblings, and the siblings agree.
    for row in rows:
        if len(row['parents']) != 1:
            continue
        parent = row['parents'][0]
        if parent not in system:
            continue
        candidate = set(row['interfaces']) - {by_name.get(parent)}
        settled = system[parent].get('answers')
        system[parent]['answers'] = sorted(
            candidate if settled is None else candidate & set(settled))

    disagree = []
    for row in rows:
        values = [worth(row['package'], p) for p in row['parents']]
        if any(v is None for v in values):
            disagree.append((row, 'a parent nothing in the corpus pins down'))
            continue
        depth = 1 + sum(v['depth'] for v in values)
        copies = (bin(row['copy_mask']).count('1')
                  + sum(v['copies'] for v in values))
        base = values[0]['base'] if values else 0
        size = row['own'] + sum(v['size'] for v in values)
        answers = set()
        for value, parent in zip(values, row['parents']):
            if value.get('answers') is None:
                answers = None
                break
            answers |= set(value['answers'])
            number = by_name.get(parent)
            if number:
                answers.add(number)
        trouble = []
        if (depth, copies, base, size) != (row['depth'], row['copies'],
                                           row['base'], row['size']):
            trouble.append(f'depth {depth} copies {copies} base {base} '
                           f'size {size} against {row["depth"]} '
                           f'{row["copies"]} {row["base"]} {row["size"]}')
        # A record may answer as more than its parents account for, because
        # a class can add interfaces with `inherits interface from`; it can
        # never answer as fewer.
        if answers is not None and not answers <= set(row['interfaces']):
            trouble.append(f'{len(answers - set(row["interfaces"]))} '
                           f'interfaces its record does not carry')
        if trouble:
            disagree.append((row, '; '.join(trouble)))
    return system, disagree


def check_field_numbers(definitions):
    """`field_number` against every field number the SDK states."""
    text = read(SDK_INTERFACES / 'NoDebug' / 'FieldNumbers.h')
    stated = defaultdict(dict)
    for klass, field, value in re.findall(
            r'#\s*define\s+(\w+)_(\w+)\s+\(0x([0-9A-Fa-f]{8})\s*\|'
            r'\s*ClassToFieldNumber', text):
        stated[klass][field] = int(value, 16)
    agreed = differed = 0
    examples = []
    for klass, fields in stated.items():
        try:
            layout = definitions.layout(klass)
        except Exception:
            continue
        # A field number counts from the class's own fields, so the inherited
        # part is dropped and what is left is rebased on the first of them.
        own = [f for f in layout['fields'] if f['owner'] == klass]
        if not own:
            continue
        base = min(f['offset'] for f in own)
        for field in own:
            if field['name'] not in fields:
                continue
            want = fields[field['name']]
            rebased = dict(field, offset=field['offset'] - base,
                           kind=field_kind(field['type'], definitions))
            got = field_number(rebased, 0)
            if got == want:
                agreed += 1
            else:
                differed += 1
                if len(examples) < 8:
                    where = f'{field["type"]} at {rebased["offset"]}'
                    if field['bit'] is not None:
                        where += f' bit {field["bit"]}'
                    examples.append(f'{klass}.{field["name"]} ({where}) '
                                    f'{got:#010x} against {want:#010x}')
    return agreed, differed, examples


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--fields', action='store_true')
    args = parser.parse_args(argv)

    definitions = Definitions(SDK_INTERFACES / 'DefFiles', SDK_INTERFACES)
    tables = load_numbers()

    if args.fields:
        agreed, differed, examples = check_field_numbers(definitions)
        print(f'field numbers: {agreed} agree, {differed} differ')
        for line in examples:
            print(f'  {line}')
        return 1 if differed else 0

    rows = [row for _, local in class_records(definitions, tables)
            for row in local.values()]
    by_name = {name: number for number, name in tables['class'].items()}
    system, disagree = solve(rows, by_name)
    print(f'{len(rows)} class records, {len(system)} system classes derived, '
          f'{len(disagree)} records do not come out')
    for row, why in disagree:
        print(f'  {row["package"]}:{row["name"]}: {why}')
    for name in sorted(system):
        value = system[name]
        answers = value.get('answers')
        print(f'  {name:24s} depth={value["depth"]:2d} '
              f'copies={value["copies"]:2d} base={value["base"]:3d} '
              f'size={value["size"]:4d} '
              f'answers={len(answers) if answers is not None else "?"}')
    if args.write:
        OUTPUT.write_text(json.dumps(
            {k: system[k] for k in sorted(system)}, indent=1) + '\n')
        print(f'wrote {OUTPUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
