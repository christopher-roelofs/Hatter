#!/usr/bin/env python3
"""Rebuild a package from what was read of it, and diff it against itself.

Reading a format and understanding it are different things, and the second one
is hard to claim honestly. This is the test: take the decode and write the
bytes back out. Whatever comes back identical is understood; whatever does not
is a gap, and it says exactly where.

Two levels, because they fail differently.

The container level rebuilds the file from the header, the record list and the
trailer, with each object's payload carried across as bytes. It cannot fail on
anything inside an object, so what it tests is that the walk accounted for
every byte of the file -- no padding skipped, no gap between records, nothing
after the trailer.

The field level rebuilds each object's payload from the fields the layout
engine claims to have read: the values back into their offsets, Booleans back
into their bits, a list's elements back into the extra part. This one has
teeth. A field placed a word out, a Boolean packed from the wrong end, a
reference written without its tag -- none of that survives a byte comparison,
and none of it is visible from reading alone.

Usage:
    roundtrip.py <package> [...]        what does not come back
    roundtrip.py --summary <package>    counts only
"""
import argparse
from pathlib import Path
import struct
import sys

from classdefs import Definitions, WORD
from inspect_package import (HEAP_START, SDK_INTERFACES, find_cluster, inspect,
                             load_numbers)


def rebuild_container(data, result):
    """The whole file, from the header, the records and the trailer."""
    header = result['header']
    out = bytearray(data[:HEAP_START])          # the header is carried whole
    for entry in result['objects']:
        out += struct.pack('>IHHHH', entry['length'], entry['class_number'],
                           entry['tag'], entry['flags'], entry['id'])
        body = entry['payload']
        out += data[body['offset']:body['offset'] + body['length']]
    # Either a zero word or nothing, whichever the chain left room for.
    if len(out) < header['heap_end']:
        out += bytes(header['heap_end'] - len(out))
    out += data[header['heap_end']:]
    return bytes(out)


def rebuild_payload(data, entry):
    """One object's payload, from the fields that were read out of it.

    Returns the bytes rebuilt and which of them a decoded field actually
    accounts for. Bytes nothing claims are left as they were found, so the
    comparison is about what the decode asserts and not about what it has
    not looked at -- and the coverage says how much of that there is.
    """
    body = entry['payload']
    start, length = body['offset'], body['length']
    out = bytearray(data[start:start + length])
    covered = bytearray(length)
    # Instances of the package's own classes, read with the class definition
    # recovered from the package itself.
    for field in entry.get('instance_fields', {}).get('fields', []):
        at = field['offset']
        if field.get('bit') is not None:
            mask = 0x80 >> field['bit']
            out[at] = (out[at] & ~mask) | (mask if field['value'] else 0)
            covered[at] = 1
            continue
        size = field['bytes']
        out[at:at + size] = field['raw'].to_bytes(size, 'big')
        for i in range(at, at + size):
            covered[i] = 1

    contents = entry.get('contents')
    if not contents or 'unresolved' in contents:
        return bytes(out), covered

    for field in contents['fields']:
        if field.get('absent'):
            continue
        at = field['offset']
        if field.get('bit') is not None:
            if at >= length:
                continue
            mask = 0x80 >> field['bit']
            out[at] = (out[at] & ~mask) | (mask if field['value'] else 0)
            covered[at] = 1          # a byte is covered once any bit of it is
            continue
        raw, size = field.get('raw'), field.get('bytes')
        if raw is None or size is None or at + size > length:
            continue
        out[at:at + size] = raw.to_bytes(size, 'big')
        for i in range(at, at + size):
            covered[i] = 1

    extra = contents.get('extra')
    if extra and extra.get('raw_elements'):
        at, stride = extra['offset'], extra['stride']
        for index, value in enumerate(extra['raw_elements']):
            where = at + index * stride
            if where + stride > length:
                break
            out[where:where + stride] = value.to_bytes(stride, 'big')
            for i in range(where, where + stride):
                covered[i] = 1
    return bytes(out), covered



def check(path, tables, definitions):
    raw = path.read_bytes()
    data, _ = find_cluster(raw)
    result = inspect(raw, tables, definitions)
    report = {'package': path.stem, 'bytes': len(data)}

    rebuilt = rebuild_container(data, result)
    report['container_identical'] = rebuilt == data
    if not report['container_identical']:
        report['container_first_difference'] = first_difference(data, rebuilt)

    payload_bytes = covered_total = 0
    mismatched = []
    unaccounted = {}
    for entry in result['objects']:
        body = entry['payload']
        original = data[body['offset']:body['offset'] + body['length']]
        out, covered = rebuild_payload(data, entry)
        payload_bytes += len(original)
        covered_total += sum(covered)
        missing = len(original) - sum(covered)
        if missing:
            name = entry['class_name'] or f"class {entry['class_number']}"
            unaccounted[name] = unaccounted.get(name, 0) + missing
        if out != original:
            mismatched.append({
                'id': entry['id'], 'class': entry['class_name'],
                'at': first_difference(original, out),
            })
    report.update({'payload_bytes': payload_bytes,
                   'payload_covered': covered_total,
                   'objects_mismatched': mismatched,
                   'unaccounted_by_class': unaccounted})
    return report


def first_difference(a, b):
    for index in range(min(len(a), len(b))):
        if a[index] != b[index]:
            return index
    return min(len(a), len(b)) if len(a) != len(b) else None


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('packages', nargs='+', type=Path)
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args(argv)

    tables = load_numbers()
    deffiles = SDK_INTERFACES / 'DefFiles'
    definitions = Definitions(deffiles, SDK_INTERFACES) if deffiles.is_dir() else None

    worst = 0
    for path in args.packages:
        report = check(path, tables, definitions)
        covered = report['payload_covered']
        total = report['payload_bytes']
        share = 100.0 * covered / total if total else 0.0
        print(f"{report['package']:<24} container "
              f"{'identical' if report['container_identical'] else 'DIFFERS'}"
              f"   payload {covered}/{total} bytes accounted ({share:.0f}%)"
              f"   {len(report['objects_mismatched'])} objects differ")
        if not report['container_identical']:
            worst = 1
            print(f"    first difference at {report['container_first_difference']:#x}")
        if report['objects_mismatched'] and not args.summary:
            for bad in report['objects_mismatched'][:5]:
                print(f"    id={bad['id']} {bad['class']} differs at +{bad['at']:#x}")
            worst = 1
    return worst


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
