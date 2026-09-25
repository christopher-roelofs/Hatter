#!/usr/bin/env python3
"""Check restricted native subclass construction against original package bytes."""
import json
from build_native_class import native_subclass
from inspect_format import require
from link_package_methods import ROOT


def main():
    report = json.loads((ROOT / 'out/rosemary-inspection/package-methods.json').read_text())
    rows = []
    for package in report['packages']:
        data = (ROOT / package['path']).read_bytes()
        for cls in package['class_flavors']:
            b = cls['body']
            raw = data[b['offset']:b['offset'] + b['length']]
            # Exact supported topology; other class layouts are not generalized.
            if len(raw) != 28 or raw[:14] != bytes.fromhex('000c001000000000000000000001'):
                continue
            if raw[16:20] != bytes.fromhex('80010000') or int.from_bytes(raw[20:24], 'big') >> 20 != 0x410:
                continue
            superclass = int.from_bytes(raw[14:16], 'big')
            operation = int.from_bytes(raw[20:24], 'big') & 0xfffff
            function = int.from_bytes(raw[24:28], 'big')
            require(native_subclass(superclass, operation, function) == raw, 'native class reconstruction mismatch')
            rows.append({'path': package['path'], 'sha256': package['sha256'], 'package': package['package'],
                         'body': b, 'superclass_selector': superclass, 'operation_selector': operation,
                         'function_id': function})
    output = ROOT / 'out/rosemary-inspection/native-class-validation.json'
    output.write_text(json.dumps({'byte_identical': len(rows), 'classes': rows}, indent=2) + '\n')
    print('Byte-identical restricted native classes:', len(rows))


if __name__ == '__main__':
    main()
