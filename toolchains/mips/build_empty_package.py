#!/usr/bin/env python3
"""Assemble an experimental code-free EmptyPackage for isolated guest testing."""
import argparse
import hashlib
import json
from build_empty_objects import construct
from build_cluster import cluster_body
from build_frozen import imports as encode_imports, abbreviated_classes, heap_object, heap, package, object_addressing
from build_package_metadata import METADATA_CLASSES
from build_object_values import object_list
from derive_fixed_formats import derive
from inspect_format import inspect, decode_imports, decode_abbreviated_classes, require
from link_package_methods import ROOT, SDK, declarations


def assemble(first_page=0, last_page=0):
    require(type(first_page) is int and type(last_page) is int and 0 <= first_page <= last_page <= 0xffffffff,
            'invalid experimental source page range')
    bodies, imports, formats, manifest = construct()
    local, symbols = manifest['local_selectors'], manifest['imported_selectors']
    records = decode_imports(imports, 0, len(imports))['entries']
    imports_list = [(e['raw_kind_word'], e['name']['text_latin1'], e['secondary_name']['text_latin1'],
                     e['raw_component_word'], e['raw_range_word'], e['count']) for e in records]
    interface, decls = declarations((SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef').read_text())
    offsets = [offset for (kind, offset), names in decls.items() if kind == 'class' and names == ['PackageCluster']]
    require(len(offsets) == 1, 'ambiguous PackageCluster declaration')
    symbols['PackageCluster'] = max(e[3] for e in imports_list if e[0] == 2) + 1
    imports_list.append((2, interface, '', symbols['PackageCluster'], offsets[0], 1))
    classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    layout = derive('PackageCluster', classes, {})
    values = dict(sharedObjectUnshared=False, isPackageCluster=True, isROMCluster=False, keep=False,
                  deleteChanges=False, keepAfterCommit=False, sourceRoster=0, firstPageIndex=first_page,
                  lastPageIndex=last_page, firstUncrowdedPageIndex=0xffffffff, nameDictionary=0,
                  sharedObjects=0, sharedObjectReferenceCounts=0, scriptClasses=0, scriptClassNumbers=0,
                  scriptClassNumbersForRenumbering=0, shadowRoster=0, committedTable=0, pristineTable=0,
                  pristineNameDictionary=local['nameDictionary'], pristineSharedObjects=local['sharedTable'],
                  needReinitializeCallsList=0, needCommitCallsList=0, commitCount=0, active=False,
                  activateFailed=False, activeUncommitted=False, packageData=local['packageData'],
                  packageContents=local['contents'], exportTable=local['exports'],
                  uniqueIntegrationID1=0, uniqueIntegrationID2=1, firstCompiledLocator=local['contents'])
    root = cluster_body(layout, values, 'EmptyPackage')
    class_formats = decode_abbreviated_classes(formats, 0, len(formats))['entries']
    class_formats.append({'class_selector': symbols['PackageCluster'], 'raw_format_nibbles': layout['raw_format_nibbles']})
    object_classes = dict(contents='SoftwarePackageContents', installationList='ObjectList', packageScene='Scene',
                          helpForObjects='ObjectList', packageSceneInfo='Text', nameLookup='PristineLookupTable',
                          nameTextHeap='TextHeap', nameDictionary='StaticObjectNameDictionary', **METADATA_CLASSES)
    list_classes = {'ObjectList', 'ObjectValueHashTable', 'DataList', 'PackageExportTable', 'PackageExportHashEntries', 'Scene'}
    objects = [heap_object(0xb0800000 | symbols['PackageCluster'], root)]
    manifest['heap_objects'] = [{'selector': 4, 'class': 'PackageCluster', 'name': 'cluster'}]
    for name, selector in sorted(local.items(), key=lambda item: item[1]):
        cls = object_classes[name]
        header = 0xb0000000 | symbols[cls]
        if cls in list_classes:
            header |= 0x08000000
        if name in manifest['object_names']:
            header |= 0x01000000
        body = bodies[name]
        if name == 'packageScene':
            body += object_list([])  # Empty inherited Viewable subview list.
        objects.append(heap_object(header, body))
        manifest['heap_objects'].append({'selector': selector, 'class': cls, 'name': name})
    raw = package([(0x20, encode_imports(imports_list)), (0x53, object_addressing(4, 1, [(12, len(bodies))])),
                   (0x10, abbreviated_classes(class_formats)), (0x60, heap(objects))])
    parsed = inspect(raw)
    require(len(parsed['packages'][0]['heap_selectors']['objects']) == len(objects), 'assembled heap mapping mismatch')
    manifest.update(status='experimental-package-assembled', cluster_values=values,
                    page_range_policy='explicit trial values; source-page semantics pending guest validation',
                    limitations=['Guest validation is recorded separately by package SHA-256',
                                 'Page range and integration ID trial values are not a general compiler policy',
                                 'Single sample transcription; no native code'])
    return raw, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-page', type=int, default=0)
    parser.add_argument('--last-page', type=int, default=0)
    args = parser.parse_args()
    raw, manifest = assemble(args.first_page, args.last_page)
    output = ROOT / 'out/rosemary-inspection/empty-package-candidate'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'EmptyPackage.pkg').write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'output': str(output.relative_to(ROOT)), 'length': len(raw), 'status': manifest['status']}, indent=2))


if __name__ == '__main__':
    main()
