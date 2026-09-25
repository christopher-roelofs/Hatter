#!/usr/bin/env python3
"""Describe initialization sources using SDK declarations, without runtime linking."""
import collections
import hashlib
import json
from inspect_format import inspect
from link_package_methods import ROOT, SDK, declarations
from package_exports import package_exports, resolve_local

# SDK interpreter tables at 0x13ebc378 and 0x13ebc3b8.
KINDS = {1: 'locator', 2: 'class', 3: 'operation', 4: 'class-operation',
         5: 'intrinsic', 6: 'intrinsic', 7: 'intrinsic', 8: 'class',
         9: 'class', 13: 'operation', 14: 'class-operation', 15: 'intrinsic'}
FORMS = {6: 'intrinsic-code-and-gp', 7: 'intrinsic-gp', 8: 'class-runtime-value',
         9: 'class-fields-offset', 13: 'object-method-code-and-gp',
         14: 'class-method-code-and-gp', 15: 'intrinsic-code-and-gp'}


def describe(state, interfaces):
    raw = state.get('raw_source_kind', 0)
    kind = raw & 0x3f
    index = state.get('raw_index', 0)
    name = state.get('interface_latin1', '')
    count = state.get('raw_field_a4', 1)
    result = {'raw_source_kind': raw, 'index': index, 'required_count': count,
              'interface': name, 'runtime_resolved': False}
    # These immediate/base-relative cases require the exact byte, not masked kind.
    if raw in (0, 10, 11, 12):
        return {**result, 'status': 'symbolic-source',
                'form': {0: 'immediate', 10: 'globals-relative',
                         11: 'code-relative', 12: 'external-relative'}[raw]}
    if kind not in KINDS:
        return {**result, 'status': 'unsupported-source-kind'}
    result.update(component_kind=KINDS[kind], form=FORMS.get(kind, 'selector'),
                  missing_interface_returns_zero=bool(raw & 0x80))
    if name.startswith('@'):
        return {**result, 'status': 'package-local-interface', 'local_name': name[1:]}
    if name == 'Dispatchers':
        # Interpreter fallback requires exact kind 6 and word destination mode.
        valid = raw == 6 and 0 <= index < 7 and 0 <= count <= 7 and state.get('raw_destination_mode', 4) == 4
        return {**result, 'status': 'dispatcher-fallback' if valid else 'unsupported-dispatcher-fallback'}
    if name not in interfaces:
        return {**result, 'status': 'external-interface-unavailable'}
    names = sorted(set(interfaces[name].get((KINDS[kind], index), [])))
    return {**result, 'status': 'sdk-declaration-match' if len(names) == 1 else
            'ambiguous-sdk-declaration' if names else 'sdk-declaration-unavailable',
            'sdk_declared_names': names}


def provider_index(packages):
    result = collections.defaultdict(list)
    for package in packages:
        for export in package['exports']:
            if export['local']:
                continue
            result[(export['kind'], export['name'])].append({
                'path': package['path'], 'package': package['package'],
                'sha256': package['sha256'], 'export': export})
    return result


def match_providers(source, providers):
    candidates, rejected = [], []
    index, count = source['index'], source['required_count']
    for provider in providers.get((source['component_kind'], source['interface']), []):
        export = provider['export']
        if index < 0 or count < 0 or index + count > export['count']:
            rejected.append(provider)
            continue
        stride = 8 if export['kind'] == 'locator' else 1
        candidates.append({**provider, 'provider_selector': export['selector_start'] + index * stride})
    status = ('unique-corpus-provider' if len(candidates) == 1 else
              'multiple-corpus-providers' if candidates else
              'provider-range-mismatch' if rejected else 'no-corpus-provider')
    return {'status': status, 'candidates': candidates, 'range_rejected': rejected,
            'runtime_resolved': False}


def interface_occurrences(data, names):
    result = {}
    for name in sorted(names):
        needle = name.encode('latin1')
        offsets, cursor = [], 0
        while needle and (cursor := data.find(needle, cursor)) >= 0:
            offsets.append(cursor)
            cursor += 1
        result[name] = offsets
    return result


def main():
    interfaces, sources = {}, []
    for filename in ('InternalInterface.cdef', 'PublicInterface.cdef', 'ConditionalInterface.cdef'):
        path = SDK / 'Interfaces/DefFiles/Interfaces' / filename
        name, decls = declarations(path.read_text())
        interfaces[name] = decls
        sources.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    reports, counts = [], collections.Counter()
    for path in sorted((ROOT / 'software/mips').rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(8) != b'\0SALTCOD':
                continue
        data = path.read_bytes()
        parsed = inspect(data)
        for package in parsed['packages']:
            exports = package_exports(data, package)
            entries = []
            for attr in package['records']:
                for ins in attr.get('global_initialization', {}).get('instructions', []):
                    for index, entry in enumerate(ins.get('entries', [])):
                        result = describe(entry['state'], interfaces)
                        if result['status'] == 'package-local-interface':
                            result['local_export'] = resolve_local(result, exports)
                            counts[result['local_export']['status']] += 1
                        entries.append({'instruction_offset': ins['offset'], 'entry_index': index,
                                        'raw_state': entry['state'], **result})
                        counts[result['status']] += 1
            # Data-only packages can provide interfaces too.
            reports.append({'path': str(path.relative_to(ROOT)), 'sha256': parsed['sha256'],
                            'package': package['index'], 'exports': exports, 'entries': entries})
    providers = provider_index(reports)
    missing = set()
    for package in reports:
        for entry in package['entries']:
            if entry['status'] == 'external-interface-unavailable':
                entry['provider_match'] = match_providers(entry, providers)
                counts[entry['provider_match']['status']] += 1
                candidates = entry['provider_match']['candidates']
                if candidates:
                    same = any(p['path'] == package['path'] and p['package'] == package['package']
                               for p in candidates)
                    scope = 'includes-same-package' if same else 'other-packages-only'
                    entry['provider_match']['candidate_scope'] = scope
                    counts[scope] += 1
                if entry['provider_match']['status'] == 'no-corpus-provider':
                    missing.add(entry['interface'])
    rom_evidence = []
    for path in (SDK / 'Debugger/Apollo/MagicCap-USA.image', ROOT / 'roms/MagicCap-USA.image',
                 ROOT / 'roms/MagicCap-Japan.image'):
        if path.is_file():
            data = path.read_bytes()
            rom_evidence.append({'path': str(path.relative_to(ROOT)),
                                 'sha256': hashlib.sha256(data).hexdigest(),
                                 'interface_string_offsets': interface_occurrences(data, missing)})
    out = ROOT / 'out/rosemary-inspection/global-sources.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'scope': 'source classification and literal SDK declaration names; no runtime addresses',
                              'sources': sources, 'summary': dict(counts), 'packages': reports,
                              'rom_string_evidence_only': rom_evidence}, indent=2) + '\n')
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()
