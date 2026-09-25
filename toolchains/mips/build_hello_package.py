#!/usr/bin/env python3
"""HelloWorld on Linux: a Greeter class (Viewable subclass, native Draw
compiled from hello.c) and a Greeter instance inside the package's Scene."""
import hashlib
import json
from pathlib import Path
from build_c_package import compile_and_link
from build_empty_package import assemble
from build_native_class import native_subclass
from build_cluster import cluster_body
from build_frozen import imports as encode_imports, defined_components, object_addressing, function_offsets, abbreviated_classes, heap_object, heap, package
from build_object_values import fixed_body, object_list, pixel_units
from build_object_names import name_tables, name_dictionary, read_names
from build_exports import export_tables
from derive_fixed_formats import derive
from inspect_format import inspect, require
from link_package_methods import ROOT, SDK, declarations


def build(code, init, entry, name='HelloWorld'):
    baseline, manifest = assemble()
    parsed = inspect(baseline)['packages'][0]
    attrs = {a['raw_tag_byte']: a for a in parsed['records']}
    entries = [(e['raw_kind_word'], e['name']['text_latin1'], e['secondary_name']['text_latin1'],
                e['raw_component_word'], e['raw_range_word'], e['count']) for e in attrs[0x20]['imports']['entries']]
    public, pub = declarations((SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef').read_text())
    internal, private = declarations((SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef').read_text())
    def ordinal(ds, kind, label):
        matches = [i for (k, i), names in ds.items() if k == kind and names == [label]]
        require(len(matches) == 1, f'missing or ambiguous declaration {label}')
        return matches[0]
    root_class = manifest['imported_selectors']['PackageCluster']
    entries = [(kind, iface, secondary, sel, ordinal(private, 'class', 'CodePackageCluster') if kind == 2 and sel == root_class else offset, count)
               for kind, iface, secondary, sel, offset, count in entries]
    meta_class = root_class + 1          # UnlinkedClassWithInstances
    greeter_class = meta_class + 1       # package-defined
    viewable_class = greeter_class + 1   # imported Viewable
    draw_op = 1                          # imported Draw, package operation selector
    send_sound = max(sel for kind, iface, sec, sel, off, count in entries if kind == 1) + 8   # next locator slot
    entries += [(2, internal, '', meta_class, ordinal(private, 'class', 'UnlinkedClassWithInstances'), 1),
                (2, public, '', viewable_class, ordinal(pub, 'class', 'Viewable'), 1),
                (3, public, '', draw_op, ordinal(pub, 'operation', 'Draw'), 1),
                (1, public, '', send_sound, ordinal(pub, 'locator', 'iSendSound'), 1)]
    classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    layout = derive('CodePackageCluster', classes, {})
    values = dict(manifest['cluster_values'])
    for field in layout['fields']:
        values.setdefault(field['name'], False if field['type'] == 'Boolean' else 0)
    heap_objects = attrs[0x60]['heap']['objects']
    class_index = len(heap_objects)                    # appended after the baseline objects
    greeter_index = class_index + 1
    class_locator = 4 + 8 * class_index
    greeter_sel = 4 + 8 * greeter_index
    scene_sel = manifest['local_selectors']['packageScene']
    values.update(firstCompiledLocator=class_locator, classBase1=greeter_class, classCount=1)
    scene_layout = derive('Scene', classes, {'BackgroundWithBorder': 44})
    # pristine names cover consecutive locators from contents (12) up to the
    # greeter; Objects.odef names the contents, the scene and the greeter
    local = manifest['local_selectors']
    names = [None] * (greeter_index)          # index i <-> selector 12 + 8 i
    names[(local['contents'] - 12) // 8] = 'HelloWorld'
    names[(local['packageScene'] - 12) // 8] = 'AhoyWorld'
    names[(greeter_sel - 12) // 8] = 'Yo, world!'
    lookup, text_heap = name_tables(names)
    require(read_names(lookup, text_heap, len(names)) == names, 'generated names do not resolve')
    renamed = {local['nameLookup']: lookup, local['nameTextHeap']: text_heap,
               local['nameDictionary']: name_dictionary(local['nameLookup'], local['nameTextHeap'], local['contents'], len(names))}
    # export the class under its local name so code can obtain its runtime
    # number (ClassNameToNumber(Greeter) -> _classNumber_Greeter_)
    export_layouts = {n: derive(n, classes, {}) for n in ('PackageExportTable',)}
    for key, body in export_tables(export_layouts, local, [('class', '@Greeter', 1, greeter_class)]).items():
        renamed[local[key]] = body
    objects = []
    for obj in heap_objects:
        span = obj['body']
        body = baseline[span['offset']:span['offset'] + span['length']]
        header = obj['raw_header']
        if obj['index'] == 0:
            body = cluster_body(layout, values, name)
        if 4 + 8 * obj['index'] in renamed:
            body = renamed[4 + 8 * obj['index']]
        if 4 + 8 * obj['index'] == scene_sel:
            require(body[scene_layout['fixed_storage_bytes']:] == object_list([]), 'expected the empty subview list')
            body = body[:scene_layout['fixed_storage_bytes']] + object_list([greeter_sel])
        objects.append(heap_object(header, body))
    objects.append(heap_object(0xb0000000 | meta_class, native_subclass(viewable_class, draw_op, 3)))
    # instance Greeter greeter (Objects.odef); unnamed, sound nil (iSendSound not imported)
    viewable = derive('Viewable', classes, {})
    greeter = dict(superview=scene_sel, relativeOrigin=[pixel_units('0.0'), pixel_units('-14.0')],
                   contentSize=[pixel_units('90.0'), pixel_units('90.0')], viewFlags=0x7818D200,
                   labelStyle=manifest['imported_selectors']['iBook12'], color=0xFFFFFFFF, altColor=0xFF000000,
                   shadow=0, sound=send_sound)
    objects.append(heap_object(0xb1000000 | greeter_class, fixed_body(viewable, greeter) + object_list([])))  # named
    formats = attrs[0x10]['abbreviated_classes']['entries']
    for entry_ in formats:
        if entry_['class_selector'] == root_class:
            entry_.clear()
            entry_.update(class_selector=root_class, raw_format_nibbles=layout['raw_format_nibbles'])
    formats += [{'class_selector': meta_class, 'raw_format_nibbles': derive('UnlinkedClassWithInstances', classes, {})['raw_format_nibbles']},
                {'class_selector': greeter_class, 'raw_format_nibbles': viewable['raw_format_nibbles']}]
    raw = package([(0x20, encode_imports(entries)), (0x30, defined_components([(2, greeter_class, 1)])),
                   (0x10, abbreviated_classes(formats)), (0x53, object_addressing(4, 1, [(12, len(objects) - 1)])),
                   (0xb0, function_offsets([None, None, entry], 0)), (0x71, bytes(4) + code),
                   (0xa0, init.finish(len(code))), (0x60, heap(objects))])
    check = inspect(raw)['packages'][0]
    require(len(check['heap_selectors']['objects']) == len(objects), 'heap mapping mismatch')
    return raw, {'status': 'experimental HelloWorld candidate', 'class': 'Greeter (Viewable subclass)',
                 'class_selector': greeter_class, 'class_locator': class_locator, 'greeter_selector': greeter_sel,
                 'scene_selector': scene_sel, 'operation': 'Draw', 'function_id': 3, 'code_offset': entry, 'code_hex': code.hex(),
                 'baseline_sha256': hashlib.sha256(baseline).hexdigest(),
                 'names': names, 'send_sound_locator': send_sound,
                 'limitations': ['Single class and method']}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sdk', action='store_true', help='build the unmodified SDK HelloWorld.cpp with its own headers')
    ap.add_argument('--source', help='alternative .cpp for the --sdk build')
    args = ap.parse_args()
    if args.sdk:
        from build_sdk_package import compile_sdk
        out = ROOT / 'out/rosemary-hello-sdk'
        headers = out / 'pkgheaders'
        headers.mkdir(parents=True, exist_ok=True)
        (headers / 'HelloWorld.xh').write_text(
            '// generated for the package: class number resolved by the loader\n'
            '#define Greeter_ ({ extern int _classNumber_Greeter_; (ClassNumber)_classNumber_Greeter_; })\n')
        (headers / 'HelloWorld.xph').write_text('// generated placeholder: Greeter adds no fields\n')
        source = Path(args.source) if args.source else SDK / 'Samples/HelloWorld/HelloWorld.cpp'
        code, init, entry, extra = compile_sdk(source, out, 'HelloWorld', 'Greeter_Draw', package_headers=headers)
    else:
        out = ROOT / 'out/rosemary-hello'
        source = Path(__file__).with_name('hello.c')
        code, init, entry, extra = compile_and_link(source, out, 'HelloWorld', 'Greeter_Draw')
    raw, manifest = build(code, init, entry)
    (out / 'HelloWorld.pkg').write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw), **extra)
    (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('sha256', 'length', 'code_bytes', 'entry_offset', 'greeter_selector', 'class_selector') if k in manifest}, indent=2))


if __name__ == '__main__':
    main()
