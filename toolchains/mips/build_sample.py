#!/usr/bin/env python3
"""Build an SDK sample package from its source directory (.cpp, .cdef, .odef)."""
import argparse
import hashlib
import json
from pathlib import Path
from build_package import build_package
from build_sdk_package import compile_sdk
from odef_frontend import build_spec, package_headers, strip_comments
from inspect_format import require
from link_package_methods import ROOT, SDK
from trace_linked_methods import read_elf


def read(path):
    return path.read_bytes().decode('latin1').replace('\r\n', '\n').replace('\r', '\n')


def build_sample(sample_dir, name, out, locale='USA'):
    from odef_frontend import parse_phrases
    cdef = ''.join(read(p) for p in sorted(sample_dir.glob('*.cdef')))
    phrase_file = sample_dir / f'{locale}.Package.Phrases'
    phrases = parse_phrases(read(phrase_file), sample_dir) if phrase_file.exists() else []
    # definitions `read` from other samples (ImportSample reads ExportSample.cdef)
    import re
    foreign = []
    for ref in re.findall(r'read\s+"([^"]+\.cdef)"', cdef):
        if not (sample_dir / ref).exists() and ref != 'MagicCap.cdef':
            found = sorted(SDK.glob(f'Samples/*/{ref}'))
            require(found, f'cannot find {ref} read by the definitions')
            foreign.append(read(found[0]))
    odef = ''.join(read(p) for p in sorted(sample_dir.glob('*.odef')))
    cpps = sorted(sample_dir.glob('*.cpp'))
    if not cpps:                                   # objects only (Scenes): no code, init or function table
        spec, hdr = build_spec(cdef, odef, name, {}, sample_dir, foreign, phrases)
        raw, manifest = build_package(spec, None, None)
        out.mkdir(parents=True, exist_ok=True)
        (out / f'{name}.pkg').write_bytes(raw)
        manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw), methods={}, code_hex='', sample=str(sample_dir),
                        references={}, fixups={}, code_bytes=0, globals_bytes=0, source_sha256=[])
        out.mkdir(parents=True, exist_ok=True)
        (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return raw, manifest
    # first pass: headers from the definitions, compile, then function ids
    spec, hdr = build_spec(cdef, odef, name, {}, sample_dir, foreign, phrases)
    headers = out / 'pkgheaders'
    headers.mkdir(parents=True, exist_ok=True)
    generated = package_headers(name, hdr, hdr['cdef_classes'], hdr['layouts'])
    for fname, text in generated.items():
        (headers / fname).write_text(text)
    for stem in {p.stem for p in sample_dir.glob('*.cdef')} - {name}:     # e.g. PackageScene.cdef in PackageSceneSample
        for suffix in ('.xh', '.xph', 'Indexicals.xh', 'Indexicals.xph'):
            (headers / (stem + suffix)).write_text(f'#include "{name}.xh"\n')
    code, init, entry, extra = compile_sdk(cpps, out, name, None, package_headers=headers, runtime=True, interfaces=hdr['link_interfaces'])
    syms = {k: int(v, 16) for k, v in extra['symbols'].items()}
    methods = sorted(s for s in syms if any(s.startswith(c + '_') for c in hdr['classes']) and syms[s] >= 0x10000000)
    # ids in .cdef declaration order (overrides then operations), assigned by build_spec's method order
    spec, hdr = build_spec(cdef, odef, name, {m: None for m in methods}, sample_dir, foreign, phrases)
    order = [f'{c["name"]}_{op}' for c in spec['classes'] for op, _ in c['methods']]
    ids = {m: 3 + i for i, m in enumerate(order)}
    spec, hdr = build_spec(cdef, odef, name, ids, sample_dir, foreign, phrases)
    spec['function_offsets'] = {ids[m]: syms[m] - 0x10000000 for m in order}
    raw, manifest = build_package(spec, code, init)
    (out / f'{name}.pkg').write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw), methods=ids, code_hex=code.hex(),
                    sample=str(sample_dir), **{k: extra[k] for k in ('references', 'fixups', 'code_bytes', 'globals_bytes', 'source_sha256')})
    (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return raw, manifest


def _any_method(cpp, hdr):
    text = read(cpp)
    import re
    for c in hdr['classes']:
        m = re.search(rf'\b({c}_\w+)\s*\(', text)
        if m: return m.group(1)
    require(False, 'no method found in the source')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('sample', help='sample name under the SDK Samples directory, or a directory')
    ap.add_argument('--out')
    ap.add_argument('--locale', default='USA', help='phrase file to apply (<locale>.Package.Phrases)')
    args = ap.parse_args()
    d = Path(args.sample) if Path(args.sample).is_dir() else SDK / 'Samples' / args.sample
    name = d.name
    out = ROOT / (args.out or f'out/rosemary-sample-{name}')
    raw, m = build_sample(d, name, out, args.locale)
    print(json.dumps({k: m[k] for k in ('sha256', 'length', 'methods', 'selectors', 'exports', 'names')}, indent=1))


if __name__ == '__main__':
    main()
