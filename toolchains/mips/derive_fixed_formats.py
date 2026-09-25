#!/usr/bin/env python3
"""Derive conservative fixed-word formats from SDK fields; reject unresolved mixins."""
import collections
import hashlib
import json
from inspect_format import inspect, require, FormatError
from link_package_methods import ROOT, SDK, declarations, resolve_import


def derive(name, classes, base_offsets=None):
    base_offsets = base_offsets or {}
    root = classes[name]
    size = root['layout']['fixed_storage_bytes']
    require(size % 4 == 0, 'unaligned fixed storage')
    words = [None] * (size // 4)
    occupied = set()
    fields, visited = [], set()
    def visit(class_name):
        if class_name in visited:
            return
        visited.add(class_name)
        cls = classes[class_name]
        layout = cls['layout']
        for base in layout['inherits_from']:
            visit(base['name_latin1'])
        own = cls['members'].get('fields', [])
        field_base = layout['field_access_base']['name_latin1']
        require(not own or field_base == 'Object' or field_base in base_offsets,
                f'unresolved field-access base for {class_name}')
        for field in own:
            kind = field['type_name_latin1']
            offset = field['fixed_bit_offset'] + base_offsets.get(field_base, 0) * 8
            flags = field['raw_flags_byte']
            require(flags in (0, 128), f'unsupported field flags for {class_name}.{field["name_latin1"]}')
            if kind == 'Boolean':
                fmt, width = 0, 1
            elif kind in ('UnsignedByte', 'SignedByte'):
                fmt, width = 0, 8               # byte fields: the word stays unstructured
            elif kind == 'PixelBox':
                # four SignedShort halves: two words of halfword pairs (format 1)
                require(offset % 32 == 0, 'unaligned PixelBox')
                for w in range(offset // 32, offset // 32 + 2):
                    bits = set(range(w * 32, w * 32 + 32))
                    require(not occupied.intersection(bits), 'overlapping fixed fields')
                    occupied.update(bits)
                    words[w] = 1
                fields.append({'owner': class_name, 'name': field['name_latin1'], 'type': kind,
                               'bit_offset': offset, 'bit_width': 64, 'word_format': 1})
                continue
            elif kind == 'PixelDot':
                # two SignedShort halves; may start on a halfword boundary
                require(offset % 16 == 0, 'unaligned PixelDot')
                for half in range(2):
                    o = offset + 16 * half
                    f2 = 2 if o % 32 == 0 else 3
                    bits = set(range(o, o + 16))
                    require(not occupied.intersection(bits), 'overlapping fixed fields')
                    occupied.update(bits)
                    w = o // 32
                    old_ = words[w]
                    words[w] = f2 if old_ in (None, f2, 0) else (1 if {old_, f2} == {2, 3} else old_)
                fields.append({'owner': class_name, 'name': field['name_latin1'], 'type': kind,
                               'bit_offset': offset, 'bit_width': 32, 'word_format': 4})
                continue
            elif kind in ('Signed', 'Unsigned', 'Flags', 'Micron', 'Fixed', 'Pointer', 'Function'):
                fmt, width = 4, 32
            elif kind == 'SignedShort':
                require(offset % 32 in (0, 16), 'unaligned halfword field')
                fmt, width = (2 if offset % 32 == 0 else 3), 16
            elif kind == 'Dot':
                fmt, width = 4, 64
            elif kind == 'UnsignedShort':
                require(offset % 32 in (0, 16), 'unaligned halfword field')
                fmt, width = (2 if offset % 32 == 0 else 3), 16
            elif kind in ('VolumeRosterPointer', 'MethodCodeAddress'):
                require(flags == 0, 'unsupported pointer flags')
                fmt, width = 8, 32
            elif kind in ('ClassNumber', 'OperationNumber', 'ClassOperationNumber', 'IntrinsicNumber'):
                fmt, width = {'ClassNumber': 9, 'OperationNumber': 10,
                              'ClassOperationNumber': 11, 'IntrinsicNumber': 12}[kind], 32
            elif kind in classes:
                fmt, width = (14 if flags & 128 else 13), 32
            else:
                raise FormatError(f'unsupported field type {kind}')
            require(offset >= 0 and offset + width <= size * 8, 'field outside target fixed part')
            require(width in (1, 8, 16) or offset % 32 == 0, 'unaligned word field')
            bits = set(range(offset, offset + width))
            require(not occupied.intersection(bits), 'overlapping fixed fields')
            occupied.update(bits)
            for word_index in range(offset // 32, (offset + width - 1) // 32 + 1):
                old = words[word_index]
                if old in (None, fmt):
                    words[word_index] = fmt
                elif old == 0 and fmt in (2, 3):
                    words[word_index] = fmt
                elif fmt == 0 and old in (2, 3):
                    pass
                elif {old, fmt} == {2, 3}:
                    words[word_index] = 1
                else:
                    raise FormatError('conflicting word formats')
            fields.append({'owner': class_name, 'name': field['name_latin1'], 'type': kind,
                           'bit_offset': offset, 'bit_width': width, 'word_format': fmt})
    visit(name)
    return {'class': name, 'fixed_storage_bytes': size,
            'raw_format_nibbles': [0 if x is None else x for x in words],
            'fields': fields, 'unassigned_words': [i for i, x in enumerate(words) if x is None]}


def main():
    source = SDK / 'Interfaces/MagicCap.cx'
    data = source.read_bytes()
    classes = {r['name_latin1']: r for s in inspect(data)['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    results = {}
    for name in ('SoftwarePackageContents', 'CodePackageCluster', 'Scene', 'ObjectList', 'Text'):
        try:
            # Explicit candidate placement: PackageContents inherits zero-size
            # Object plus HasDate, whose 16 bytes fill its fixed prefix.
            bases = {'HasDate': 0} if name == 'SoftwarePackageContents' else {}
            if name == 'Scene':
                bases = {'BackgroundWithBorder': 44}
            results[name] = {'status': 'derived', 'explicit_base_offsets': bases,
                             **derive(name, classes, bases)}
        except FormatError as error:
            results[name] = {'status': 'unsupported-layout', 'reason': str(error)}
    interfaces = {}
    for name in ('InternalInterface.cdef', 'PublicInterface.cdef', 'ConditionalInterface.cdef'):
        key, decls = declarations((SDK / 'Interfaces/DefFiles/Interfaces' / name).read_text())
        interfaces[key] = decls
    comparisons = []
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
                    names = resolve_import(imports, 'class', entry['class_selector'], interfaces).get('sdk_declared_names', [])
                    if len(names) != 1 or results.get(names[0], {}).get('status') != 'derived':
                        continue
                    comparisons.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'],
                                        'package': package['index'], 'class': names[0],
                                        'match': results[names[0]]['raw_format_nibbles'] == entry['raw_format_nibbles']})
    sources = []
    for path in (source, SDK / 'Interfaces/Generic.h', SDK / 'Interfaces/ObjectFormat.h',
                 SDK / 'Interfaces/DefFiles/Interfaces/Types.Def'):
        sources.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {'sdk_sha256': hashlib.sha256(data).hexdigest(), 'sources': sources,
              'classes': results, 'comparisons': comparisons}
    out = ROOT / 'out/rosemary-inspection/derived-fixed-formats.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: r['status'] + (': ' + r['reason'] if 'reason' in r else '') for name, r in results.items()}, indent=2))
    print('Comparisons:', len(comparisons), 'mismatches:', sum(not c['match'] for c in comparisons))


if __name__ == '__main__':
    main()
