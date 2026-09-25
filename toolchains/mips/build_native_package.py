#!/usr/bin/env python3
"""Experimental native CanGoTo override on the working EmptyPackage graph."""
import hashlib
import json
from build_empty_package import assemble
from build_native_class import native_subclass
from build_native_leaf import extract_leaf
from build_cluster import cluster_body
from build_global_init import GlobalInitBuilder
from build_frozen import imports as encode_imports, defined_components, object_addressing, function_offsets, abbreviated_classes, heap_object, heap, package
from derive_fixed_formats import derive
from inspect_format import inspect, require
from link_package_methods import ROOT, SDK, declarations


LEAF = bytes.fromhex('03e0000824020001')


def build(code, init=None, name='NativeLeafProbe', entry_offset=0):
    """init: a finished GlobalInitBuilder, or None for the leaf's four zero
    bytes of globals.  Any other code must come with its own init."""
    if init is None:
        require(code == LEAF, 'only validated true-returning leaf supported without an init script')
    require(len(code) > 0 and len(code) % 4 == 0, 'code must be whole MIPS words')
    baseline, manifest = assemble()
    parsed = inspect(baseline)['packages'][0]
    attrs = {a['raw_tag_byte']: a for a in parsed['records']}
    imports = attrs[0x20]['imports']['entries']
    entries = [(e['raw_kind_word'], e['name']['text_latin1'], e['secondary_name']['text_latin1'],
                e['raw_component_word'], e['raw_range_word'], e['count']) for e in imports]
    public, pub = declarations((SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef').read_text())
    internal, private = declarations((SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef').read_text())
    def ordinal(ds, kind, name):
        matches = [i for (k, i), names in ds.items() if k == kind and names == [name]]
        require(len(matches) == 1, 'missing or ambiguous declaration')
        return matches[0]
    root_class = manifest['imported_selectors']['PackageCluster']
    entries = [(kind, iface, secondary, sel, ordinal(private, 'class', 'CodePackageCluster') if kind == 2 and sel == root_class else offset, count)
               for kind, iface, secondary, sel, offset, count in entries]
    meta_class = root_class + 1
    contents_class = meta_class + 1
    operation = 1
    entries += [(2, internal, '', meta_class, ordinal(private, 'class', 'UnlinkedClassWithInstances'), 1),
                (3, public, '', operation, ordinal(pub, 'operation', 'CanGoTo'), 1)]
    classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    layout = derive('CodePackageCluster', classes, {})
    values = dict(manifest['cluster_values'])
    for field in layout['fields']:
        if field['name'] not in values:
            values[field['name']] = False if field['type'] == 'Boolean' else 0
    class_locator = 148
    values.update(firstCompiledLocator=class_locator, classBase1=contents_class, classCount=1)
    objects = []
    for obj in attrs[0x60]['heap']['objects']:
        span = obj['body']
        body = baseline[span['offset']:span['offset'] + span['length']]
        header = obj['raw_header']
        if obj['index'] == 0:
            body = cluster_body(layout, values, name)
        if obj['index'] == 1:  # contents, selector 12
            header = (header & ~0xfffff) | contents_class
        objects.append(heap_object(header, body))
    objects.append(heap_object(0xb0000000 | meta_class,
                               native_subclass(manifest['imported_selectors']['SoftwarePackageContents'], operation, 3)))
    formats = attrs[0x10]['abbreviated_classes']['entries']
    for entry in formats:
        if entry['class_selector'] == root_class:
            entry.clear()
            entry.update(class_selector=root_class, raw_format_nibbles=layout['raw_format_nibbles'])
    formats += [{'class_selector': meta_class, 'raw_format_nibbles': derive('UnlinkedClassWithInstances', classes, {})['raw_format_nibbles']},
                {'class_selector': contents_class, 'raw_format_nibbles': derive('SoftwarePackageContents', classes, {'HasDate': 0})['raw_format_nibbles']}]
    if init is None:
        init = GlobalInitBuilder(4, 0)
        init.zeros(4)
    result = package([(0x20, encode_imports(entries)), (0x30, defined_components([(2, contents_class, 1)])),
                      (0x10, abbreviated_classes(formats)), (0x53, object_addressing(4, 1, [(12, 18)])),
                      (0xb0, function_offsets([None, None, entry_offset], 0)), (0x71, bytes(4) + code),
                      (0xa0, init.finish(len(code))), (0x60, heap(objects))])
    return result, {'status': 'experimental-native-candidate', 'class_selector': contents_class,
                    'class_locator': class_locator, 'superclass': 'SoftwarePackageContents', 'operation_selector': operation, 'operation': 'CanGoTo',
                    'function_id': 3, 'code_offset': entry_offset, 'code_hex': code.hex(),
                    'initialization_trial': {'globals_size': int.from_bytes(init.header[:4], 'big'), 'second_header_word': int.from_bytes(init.header[4:], 'big')},
                    'validated_leaf': code == LEAF,
                    'baseline_sha256': hashlib.sha256(baseline).hexdigest(),
                    'limitations': ['One native method only', 'Guest execution evidence is recorded separately by package SHA-256',
                                    'Display names retained as EmptyPackage; internal name ' + name]}


def main():
    obj = ROOT / 'out/rosemary-native-probe/native_leaf.o'
    code = extract_leaf(obj.read_bytes())
    raw, manifest = build(code)
    out = ROOT / 'out/rosemary-native-probe'
    (out / 'NativeLeafProbe.pkg').write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw))
    (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
