#!/usr/bin/env python3
"""Trace selected ROM export objects by stored references, without runtime addresses."""
import hashlib
import json
import struct
from inspect_format import require, u32
from link_package_methods import ROOT, SDK
from package_exports import decode_entries
from resolve_global_sources import match_providers, provider_index

ANCHORS = ('genmagic.com/WCPackInterface1', 'genmagic.com/SpellFinder1')


def occurrences(data, needle):
    start = 0
    while (start := data.find(needle, start)) >= 0:
        yield start
        start += 1


def trace_table(data, string_offset):
    # Observed ROM layout: eight-byte object header, eight-byte name-table fields,
    # then Pascal bytes. Only a name at offset zero in that buffer is an anchor.
    names_header = string_offset - 17
    require(names_header >= 0 and names_header % 4 == 0, 'unaligned names anchor')
    require(u32(data, names_header) & 0x80000000, 'missing ROM names header')
    names_ref = u32(data, names_header + 4)
    require(names_ref & 0x80000001 == 0x80000001, 'unsupported names reference')
    tables = []
    for pos in occurrences(data, struct.pack('>I', names_ref)):
        body = pos - 0x18
        if pos % 4 or body < 8 or pos == names_header + 4:
            continue
        if not u32(data, body - 8) & 0x80000000:
            continue
        if u32(data, body + 4) != 12:
            continue
        entry_ref = u32(data, body)
        if entry_ref & 0x80000001 != 0x80000001:
            continue
        for refpos in occurrences(data, struct.pack('>I', entry_ref)):
            if refpos % 4 or refpos < 4 or refpos == body or refpos + 8 > len(data):
                continue
            if not u32(data, refpos - 4) & 0x80000000:
                continue
            start = refpos + 4
            count = u32(data, start)
            if not 0 < count <= (len(data) - start - 4) // 16:
                continue
            end = start + 4 + count * 16
            # Require the entry object to terminate before this name object,
            # as observed in these ROMs; do not scan arbitrary surrounding bytes.
            if end > names_header:
                continue
            names_start = names_header + 8
            name_end = names_start + 8
            for p in range(start + 4, end, 16):
                if u32(data, p) & 0x80000000:
                    continue
                at = names_start + 8 + (u32(data, p + 4) & 0xffffff)
                require(at < len(data), 'ROM export name outside image')
                name_end = max(name_end, at + 1 + data[at])
            exports = decode_entries(data, {'offset': start, 'length': end - start},
                                     {'offset': names_start, 'length': name_end - names_start})
            require(len(exports) == u32(data, body + 12), 'ROM export active count mismatch')
            tables.append({'table_body_offset': body, 'entries_body_offset': start,
                           'names_body_offset': names_start, 'names_reference': names_ref,
                           'entries_reference': entry_ref, 'exports': exports})
    require(len(tables) == 1, 'missing or ambiguous ROM export object chain')
    return tables[0]


def main():
    source = ROOT / 'out/rosemary-inspection/global-sources.json'
    sources = json.loads(source.read_text())
    missing = [(p, e) for p in sources['packages'] for e in p['entries']
               if e.get('provider_match', {}).get('status') == 'no-corpus-provider']
    reports = []
    for path in (SDK / 'Debugger/Apollo/MagicCap-USA.image', ROOT / 'roms/MagicCap-USA.image',
                 ROOT / 'roms/MagicCap-Japan.image'):
        if not path.is_file():
            continue
        data = path.read_bytes()
        identity = {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(), 'package': 'ROM'}
        tables, absent = [], []
        for anchor in ANCHORS:
            hits = list(occurrences(data, anchor.encode('ascii')))
            if not hits:
                absent.append(anchor)
                continue
            require(len(hits) == 1, 'ambiguous ROM interface anchor')
            tables.append({'anchor': anchor, **trace_table(data, hits[0])})
        exports = [e for t in tables for e in t['exports']]
        providers = provider_index([{**identity, 'exports': exports}])
        matches = [{'consumer_path': p['path'], 'consumer_package': p['package'],
                    'instruction_offset': e['instruction_offset'], 'interface': e['interface'],
                    'component_kind': e['component_kind'], **match_providers(e, providers)} for p, e in missing]
        reports.append({**identity, 'tables': tables, 'absent_anchors': absent, 'matches': matches})
    out = ROOT / 'out/rosemary-inspection/rom-interface-exports.json'
    out.write_text(json.dumps({'scope': 'selected ROM object chains and stored selectors; no runtime relocation',
                              'source_report_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                              'roms': reports}, indent=2) + '\n')
    for report in reports:
        print(report['path'], 'matched', sum(m['status'] == 'unique-corpus-provider' for m in report['matches']),
              '/', len(report['matches']), 'exports', sum(len(t['exports']) for t in report['tables']))


if __name__ == '__main__':
    main()
