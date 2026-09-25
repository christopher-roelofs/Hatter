#!/usr/bin/env python3
"""Build EmptyPackage's object values and imports, not an installable package.

Values are an explicit transcription of the SDK sample. Cluster metadata and
complete heap records remain separate assembly work.
"""
import hashlib
import json
from build_frozen import imports as encode_imports, abbreviated_classes
from build_object_values import fixed_body, object_list, plain_text, pixel_units
from derive_fixed_formats import derive
from inspect_format import inspect, require, decode_imports
from link_package_methods import ROOT, SDK, declarations, resolve_import
from build_object_names import name_tables, name_dictionary, read_names
from build_package_metadata import METADATA_CLASSES, empty_metadata


def construct():
    source = SDK / 'Interfaces/MagicCap.cx'
    classes = {r['name_latin1']: r for s in inspect(source.read_bytes())['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    interface_path = SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef'
    interface, decls = declarations(interface_path.read_text())
    class_names = ('SoftwarePackageContents', 'Scene', 'ObjectList', 'Text')
    indexicals = ('iGeneralMagic', 'iDefaultStationery', 'iInstallationQueue', 'iBook12')
    entries, symbols = [], {}
    for kind, names in (('class', class_names), ('locator', indexicals)):
        for index, name in enumerate(names):
            matches = [offset for (k, offset), labels in decls.items() if k == kind and name in labels]
            require(len(matches) == 1 and decls[(kind, matches[0])] == [name], 'ambiguous SDK declaration')
            selector = index + 1 if kind == 'class' else 0x10000004 + index * 8
            symbols[name] = selector
            entries.append((2 if kind == 'class' else 1, interface, '', selector, matches[0], 1))
    import_body = encode_imports(entries)
    parsed = decode_imports(import_body, 0, len(import_body))['entries']
    for name, selector in symbols.items():
        kind = 'class' if name in class_names else 'locator'
        require(resolve_import(parsed, kind, selector, {interface: decls})['sdk_declared_names'] == [name],
                'generated import does not resolve to requested name')

    # Reserve selector 4 for the future cluster root; use the observed stride 8.
    local = dict(zip(('contents', 'installationList', 'packageScene', 'helpForObjects', 'packageSceneInfo'),
                     range(12, 52, 8)))
    local.update(nameLookup=52, nameTextHeap=60, nameDictionary=68)
    local.update({n: 76 + 8 * i for i, n in enumerate(METADATA_CLASSES)})
    scene_layout = derive('Scene', classes, {'BackgroundWithBorder': 44})
    contents_layout = derive('SoftwarePackageContents', classes, {'HasDate': 0})
    scene = dict(superview=0, relativeOrigin=[pixel_units('0.0'), pixel_units('-8.0')],
                 contentSize=[pixel_units('480.0'), pixel_units('256.0')], viewFlags=0x11005200,
                 labelStyle=symbols['iBook12'], color=0xff555555, altColor=0xff000000,
                 shadow=0, sound=0, border=0, isPlace=False, frozen=False, useCardName=False,
                 visited=False, blankTitle=False, messageViewer=False, suppressGrayLine=False,
                 stepBackWhenEmpty=False, canDrawIn=False, autoPencil=False, sceneDrawer=False,
                 oneCardOnly=False, ephemeral=False, addToHistory=True, suppressDateTime=False,
                 sceneDrawerBank=False, locked=False, expandMiniCards=False, sceneTools=False,
                 heightResizable=False, ignoreCardDefaultTool=False, stepBackScene=0,
                 stepBackSpot=0, image=0, additions=0, screen=0)
    contents = dict(dateCreated=0, timeCreated=0, dateModified=0, timeModified=0,
                    autoActivate=True, installationList=local['installationList'],
                    author=symbols['iGeneralMagic'], publisher=symbols['iGeneralMagic'], versionText=0,
                    helpOnObjects=local['helpForObjects'], sceneIndexicalList=0, stackIndexicalList=0,
                    startupScene=0, startupItem=0, creditsScene=0, logo=0,
                    responseCardStationery=symbols['iDefaultStationery'], dontDeactivate=False)
    lists = {'installationList': [symbols['iInstallationQueue'], local['packageScene']],
             'helpForObjects': [local['packageScene'], local['packageSceneInfo']]}
    text = 'About EmptyPackage\nEmptyPackage is ... empty'
    bodies = {'contents': fixed_body(contents_layout, contents), 'packageScene': fixed_body(scene_layout, scene),
              'packageSceneInfo': plain_text(text), **{n: object_list(v) for n, v in lists.items()}}
    layouts = {'SoftwarePackageContents': contents_layout, 'Scene': scene_layout,
               'Text': derive('Text', classes, {}), 'ObjectList': derive('ObjectList', classes, {})}
    internal_path = SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef'
    internal, internal_decls = declarations(internal_path.read_text())
    metadata_classes = tuple(dict.fromkeys(('PristineLookupTable', 'TextHeap', 'StaticObjectNameDictionary') +
                                         tuple(n for n in METADATA_CLASSES.values() if n not in class_names)))
    for index, name in enumerate(metadata_classes, start=5):
        matches = [(iface, offset) for iface, ds in ((internal, internal_decls), (interface, decls))
                   for (kind, offset), labels in ds.items() if kind == 'class' and labels == [name]]
        require(len(matches) == 1, 'missing or ambiguous metadata class')
        symbols[name] = index
        entries.append((2, matches[0][0], '', index, matches[0][1], 1))
        layouts[name] = derive(name, classes, {})
    import_body = encode_imports(entries)
    parsed = decode_imports(import_body, 0, len(import_body))['entries']
    for name in metadata_classes:
        require(resolve_import(parsed, 'class', symbols[name], {internal: internal_decls, interface: decls})['sdk_declared_names'] == [name],
                'generated metadata class import does not resolve')
    formats = abbreviated_classes([{'class_selector': symbols[n], 'raw_format_nibbles': layouts[n]['raw_format_nibbles']}
                                   for n in class_names + metadata_classes])
    ordered_names = ['EmptyPackage', None, 'EmptyPackage', None, None]
    lookup, text_heap = name_tables(ordered_names)
    require(read_names(lookup, text_heap, 5) == ordered_names, 'generated names do not resolve')
    bodies.update(nameLookup=lookup, nameTextHeap=text_heap,
                  nameDictionary=name_dictionary(local['nameLookup'], local['nameTextHeap'], local['contents'], 5))
    metadata_bodies, metadata_values = empty_metadata(layouts, local)
    bodies.update(metadata_bodies)
    known = {0: 'nilObject', **{v: k for k, v in local.items()},
             **{symbols[n]: n for n in indexicals}}
    references = []
    for name, values, layout in (('contents', contents, contents_layout), ('packageScene', scene, scene_layout)):
        for field in layout['fields']:
            if field['word_format'] in (13, 14):
                value = values[field['name']]
                require(value in known, 'dangling fixed-field reference')
                references.append({'object': name, 'field': field['name'], 'selector': value, 'target': known[value]})
    for name, values in lists.items():
        for index, value in enumerate(values):
            require(value in known, 'dangling list reference')
            references.append({'object': name, 'entry': index, 'selector': value, 'target': known[value]})
    for field, target in (('hashTable', 'nameLookup'), ('textHeap', 'nameTextHeap'), ('locatorRAMArrayOffset', 'contents')):
        references.append({'object': 'nameDictionary', 'field': field, 'selector': local[target], 'target': target})
    for name, values in metadata_values.items():
        for field in layouts[METADATA_CLASSES[name]]['fields']:
            if field['word_format'] in (13, 14):
                value = values[field['name']]
                require(value in known, 'dangling metadata reference')
                references.append({'object': name, 'field': field['name'], 'selector': value, 'target': known[value]})
    sample = SDK / 'Samples/EmptyPackage/Objects.odef'
    sources = [source, interface_path, internal_path, sample, SDK / 'Interfaces/Graphics.h']
    manifest = {'status': 'object-value-fragments-only', 'local_selectors': local, 'imported_selectors': symbols,
                'reserved_cluster_selector': 4, 'values': {'contents': contents, 'packageScene': scene, **lists,
                                                         'packageSceneInfo': text, **metadata_values}, 'references': references,
                'object_names': {'contents': 'EmptyPackage', 'packageScene': 'EmptyPackage'},
                'name_dictionary_selector': local['nameDictionary'],
                'explicit_omitted_field_defaults': {'packageScene.superview': 0},
                'sources': [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
                'limitations': ['No cluster root or connection to pristineNameDictionary', 'No complete heap or installable package',
                                'No guest execution validation', 'Sample values transcribed, not a general .odef compiler']}
    return bodies, import_body, formats, manifest


def main():
    bodies, imports, formats, manifest = construct()
    out = ROOT / 'out/rosemary-inspection/empty-package-objects'
    out.mkdir(parents=True, exist_ok=True)
    files = {**{n + '.bin': b for n, b in bodies.items()}, 'imports.bin': imports, 'abbreviated-classes.bin': formats}
    manifest['files'] = []
    for name, data in files.items():
        (out / name).write_bytes(data)
        manifest['files'].append({'file': name, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'output': str(out.relative_to(ROOT)), 'objects': len(bodies),
                      'checked_references': len(manifest['references']), 'status': manifest['status']}, indent=2))


if __name__ == '__main__':
    main()
