#!/usr/bin/env python3
"""Audit initial-load globals writes with symbolic runtime values (mask 0x0f)."""
import collections
import json
from pathlib import Path
from inspect_format import inspect, require

ROOT = Path(__file__).resolve().parents[2]


def validate(data, script, code_size):
    require(script['status'] == 'decoded-global-init-boundaries', 'incomplete script')
    size = script['global_data_bytes']
    cursor = 0
    memory = {}
    writes = []
    targets = []
    for ins in script['instructions']:
        op = ins['raw_opcode'] & 15
        if ins['kind'] == 'control':
            require(op in (0, 1, 2, 5, 6, 7, 8, 9, 10), 'unsupported audit control')
            if op in (1, 2):
                cursor = 0
            if op == 0:
                break
            continue
        count = ins['count']
        if op in (2, 3):
            cursor += count if op == 2 else -count
            continue
        if op in (12, 13):
            values = []
            for entry in ins['entries']:
                mode = entry['state'].get('raw_destination_mode', 4)
                require(mode in (4, 0x11), 'unsupported resolution write mode')
                values.append((8 if mode == 0x11 else 4, 4, None, entry.get('destination_delta', 0)))
        else:
            require(op in (1, 4, 5, 6, 7, 8, 9, 10, 11, 15), 'unsupported audit opcode')
            width = {5: 2, 6: 4, 7: 8, 9: 4, 10: 4, 11: 4, 15: 4}.get(op, 1)
            # Bound expansion before allocating repeated literal bytes.
            require(count * width <= size, 'globals write larger than allocation')
            literal = None
            if op in (1, 4, 5, 6, 7):
                end = ins['record']['offset'] + ins['record']['length']
                n = count if op == 1 else width
                literal = data[end - n:end]
                if op != 1:
                    literal *= count
            elif op == 8:
                literal = bytes(count)
            values = [(count * width, width, literal, 0)]
        for length, alignment, literal, delta in values:
            require(0 <= cursor and cursor + length <= size, f'globals write out of bounds at {ins["offset"]:#x}: {cursor}+{length}>{size}')
            require(cursor % alignment == 0, 'unaligned globals write')
            if op in (9, 10, 11, 15):
                for i, operand in enumerate(ins['bnum_operands']):
                    target = operand
                    kind = 'code' if op == 10 else 'globals' if op in (9, 15) else 'external-base'
                    if op == 15:
                        old = [memory.get(cursor + i * 4 + j) for j in range(4)]
                        target = (int.from_bytes(bytes(old), 'big') + operand) & 0xffffffff if all(x is not None for x in old) else None
                    limit = code_size if kind == 'code' else size if kind == 'globals' else None
                    targets.append({'instruction_offset': ins['offset'], 'destination_offset': cursor + i * 4,
                                    'base': kind, 'offset': target,
                                    'within_extent_or_one_past': None if target is None or limit is None else 0 <= target <= limit})
            writes.append({'instruction_offset': ins['offset'], 'destination_offset': cursor,
                           'length': length, 'symbolic': literal is None})
            for i in range(length):
                memory[cursor + i] = literal[i] if literal is not None else None
            cursor += length + delta
    return {'status': 'validated-supported-initial-load-writes', 'global_data_bytes': size,
            'write_spans': writes, 'relative_targets': targets,
            'unresolved_target_count': sum(t['within_extent_or_one_past'] is None for t in targets),
            'outside_target_count': sum(t['within_extent_or_one_past'] is False for t in targets)}


def main():
    reports = []
    totals = collections.Counter()
    for path in sorted((ROOT / 'sdk/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as f:
            if f.read(8) != b'\0SALTCOD':
                continue
        data = path.read_bytes()
        parsed = inspect(data)
        for package in parsed['packages']:
            scripts = [a['global_initialization'] for a in package['records'] if 'global_initialization' in a]
            if not scripts:
                continue
            codes = [a for a in package['records'] if a['raw_tag_byte'] == 0x71]
            require(len(scripts) == len(codes) == 1, 'unsupported script/code combination')
            result = validate(data, scripts[0], codes[0]['payload']['length'] - 4)
            reports.append({'path': str(path.relative_to(ROOT)), 'package': package['index'],
                            'sha256': parsed['sha256'], **result})
            totals['packages'] += 1
            totals['write_spans'] += len(result['write_spans'])
            totals['relative_targets'] += len(result['relative_targets'])
            totals['unresolved_targets'] += result['unresolved_target_count']
            totals['outside_targets'] += result['outside_target_count']
    out = ROOT / 'out/rosemary-inspection/global-init-validation.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'scope': 'initial load write bounds; symbolic runtime resolution; pointer targets may be one-past',
                              'summary': dict(totals), 'packages': reports}, indent=2) + '\n')
    print(json.dumps(dict(totals), indent=2))


if __name__ == '__main__':
    main()
