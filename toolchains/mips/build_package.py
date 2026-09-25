#!/usr/bin/env python3
"""Generic frozen-package assembler: an object graph, package-defined
classes with native methods, names, exports and code, from a spec.

spec = {
  'internal_name': str,
  'classes': [{'name', 'supers': [SDK class names], 'methods': [(operation name, function id)],
               'layout': derive()-style dict, 'own_fields_word': int}],
  'objects': [{'tag', 'class', 'name'?, 'fields': {...}, 'list': [...]?, 'subviews': [...]?, 'text': str?}],
  'indexicals': {'iName': tag},          # package indexicals, exported as @iName
}
Field values: int/bool/[h, v]; ('ref', tag); ('ix', 'iSystemIndexical'); 0 for nilObject.
The first object must be the SoftwarePackageContents with tag 'contents'.
"""
from build_cluster import cluster_body
from build_exports import export_tables
from build_frozen import (imports as encode_imports, defined_components, object_addressing, function_offsets,
                          abbreviated_classes, heap_object, heap, package)
from build_object_names import name_tables, name_dictionary, read_names
from build_object_values import fixed_body, object_list, plain_text, integer
from build_package_metadata import METADATA_CLASSES, empty_metadata
from derive_fixed_formats import derive
from odef_frontend import sdk_layout
from inspect_format import inspect, require
from link_package_methods import SDK, declarations

LIST_CLASSES = {'ObjectList', 'DenseObjectList', 'Trigger', 'ObjectValueHashTable', 'DataList', 'PackageExportTable', 'PackageExportHashEntries', 'Scene',
                'IntegerList', 'OperationNumberList', 'ClassNumberList', 'IntrinsicNumberList', 'ClassOperationNumberList'}
BASES = {'Scene': {'BackgroundWithBorder': 44}, 'Box': {'BackgroundWithBorder': 44}, 'SoftwarePackageContents': {'HasDate': 0}}
META_ORDER = ('nameLookup', 'nameTextHeap', 'nameDictionary', 'sharedTable', 'sharedEntries', 'sharedObjects',
              'packageData', 'exports', 'exportEntries', 'exportNames', 'missingNames', 'missingIndexicals')
META_CLASS = dict(nameLookup='PristineLookupTable', nameTextHeap='TextHeap', nameDictionary='StaticObjectNameDictionary',
                  **METADATA_CLASSES)


def class_record(supers, methods, own_fields_word=0, accessors=()):
    """accessors: (type_index, operation selector, field byte offset) entries —
    the auto getter/setter form seen in CujoChat/Reversi records
    (0x16000635 0x00000000 = ObjectReference getter for op 0x635 at offset 0)."""
    """UnlinkedClassWithInstances body: header of six halfwords, the
    superclass selector list, then native method records."""
    sup = integer(len(supers), 16) + b''.join(integer(s, 16) for s in supers)
    sup += bytes(-len(sup) % 4)
    if not methods and not accessors:
        # no method table at all (corpus: CujoChat's 16-byte records, header
        # word 1 = 0).  A present table with count 0 makes the ROM's
        # AppendMethodListDataToExtraFormat walk past the record: it enters
        # its entry loop before testing the count and emits runs from
        # whatever follows until it has trampled the serial driver.
        return b''.join(integer(n, 16) for n in (12, 0, own_fields_word, 0, 0, 0)) + sup
    header = b''.join(integer(n, 16) for n in (12, 12 + len(sup), own_fields_word, 0, 0, 0))
    body = integer(0x8000 | (len(methods) + len(accessors)), 16) + integer(0, 16)
    body += b''.join(integer(0x41000000 | op, 32) + integer(fid, 32) for op, fid in methods)
    body += b''.join(integer(kind << 24 | op, 32) + integer(offset, 32) for kind, op, offset in accessors)
    return header + sup + body


def script_class_record(base, operation, method):
    """UnlinkedScriptClass body (WebBrowser35 objects 43..48): header halfwords
    (supers at 0x14, methods at 0x18, 0, 0, 0, 0), the method-scripts list
    (one ScriptedMethod), the single superclass, and one entry tagged 0x40
    for the scripted operation whose word is the 1-based script index."""
    header = b''.join(integer(n, 16) for n in (0x14, 0x18, 0, 0, 0, 0))
    scripts = integer(0x0d000001, 32) + integer(method, 32)
    sup = integer(1, 16) + integer(base, 16)
    return header + scripts + sup + integer(0x8001, 16) + integer(0, 16) + integer(0x40000000 | operation, 32) + integer(1, 32)


class Builder:
    def __init__(self):
        self.classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
                        if s['raw_tag'] == 13 for r in s['named_records']}
        self.public, self.pub = declarations((SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef').read_text())
        self.internal, self.priv = declarations((SDK / 'Interfaces/DefFiles/Interfaces/InternalInterface.cdef').read_text())
        self.imports = []          # (kind, iface, '', selector, offset, count)
        self.class_sel, self.locator_sel, self.op_sel, self.intrinsic_sel = {}, {}, {}, {}

    def ordinal(self, kind, name):
        for ds in (self.pub, self.priv):
            m = [i for (k, i), names in ds.items() if k == kind and names == [name]]
            if len(m) == 1:
                return (self.public if ds is self.pub else self.internal), m[0]
        require(False, f'missing or ambiguous {kind} {name}')

    def import_class(self, name):
        if name not in self.class_sel:
            iface, off = self.ordinal('class', name)
            self.class_sel[name] = 1 + len(self.class_sel)
            self.imports.append((2, iface, '', self.class_sel[name], off, 1))
        return self.class_sel[name]

    def import_locator(self, name):
        if name not in self.locator_sel:
            iface, off = self.ordinal('locator', name)
            self.locator_sel[name] = 0x10000004 + 8 * len(self.locator_sel)
            self.imports.append((1, iface, '', self.locator_sel[name], off, 1))
        return self.locator_sel[name]

    def import_intrinsic(self, name):
        if name not in self.intrinsic_sel:
            iface, off = self.ordinal('intrinsic', name)
            self.intrinsic_sel[name] = 1 + len(self.intrinsic_sel)
            self.imports.append((5, iface, '', self.intrinsic_sel[name], off, 1))
        return self.intrinsic_sel[name]

    def import_operation(self, name):
        if name not in self.op_sel:
            iface, off = self.ordinal('operation', name)
            self.op_sel[name] = 1 + len(self.op_sel)
            self.imports.append((3, iface, '', self.op_sel[name], off, 1))
        return self.op_sel[name]


def build_package(spec, code, init, name_tag='contents'):
    b = Builder()
    objects = spec['objects']
    require(objects and objects[0]['tag'] == 'contents' and objects[0]['class'] == 'SoftwarePackageContents',
            'first object must be the contents')
    tags = {o['tag']: i for i, o in enumerate(objects)}
    require(len(tags) == len(objects), 'duplicate tags')
    user_count = len(objects)
    sel = {o['tag']: 12 + 8 * i for i, o in enumerate(objects)}
    meta_sel = {n: 12 + 8 * (user_count + i) for i, n in enumerate(META_ORDER)}
    class_locators = {c['name']: 12 + 8 * (user_count + len(META_ORDER) + i) for i, c in enumerate(spec['classes'])}
    # imports in a fixed order: user classes, locators, metadata classes, cluster, meta class, supers, ops
    for o in objects:
        if o['class'] in b.classes:
            b.import_class(o['class'])
    package_ops = [op for c in spec['classes'] for op in c.get('operations', [])]
    def value(v):
        if isinstance(v, tuple):
            if v[0] == 'ref':
                require(v[1] in sel, f'unknown tag {v[1]}')
                return sel[v[1]]
            if v[0] == 'ix':
                return b.import_locator(v[1])
            if v[0] == 'op':
                require(v[1] in package_ops, f'unknown package operation {v[1]}')
                return ('op', v[1])
            if v[0] == 'sysop':
                return b.import_operation(v[1])
            if v[0] == 'intrinsic':
                return b.import_intrinsic(v[1])
        return v
    for o in objects:
        o['_values'] = {k: value(v) for k, v in o.get('fields', {}).items()}
        o['_list'] = [value(v) for v in o.get('list', [])]
        o['_subviews'] = [value(v) for v in o.get('subviews', [])]
    for n in META_ORDER:
        b.import_class(META_CLASS[n])
    code_free = code is None                      # objects only: corpus CujoChat pkg 1, GammonBundle pkg 1
    root_class = b.import_class('PackageCluster' if code_free else 'CodePackageCluster')
    meta_class = b.import_class('UnlinkedClassWithInstances')
    package_class_names = {c['name'] for c in spec['classes']}
    for c in spec['classes']:
        for s in c['supers']:
            if s not in package_class_names:
                b.import_class(s)
        for op, _ in c['methods']:
            if op not in package_ops:
                b.import_operation(op)
    first_op = 1 + len(b.op_sel)
    for i, op in enumerate(package_ops):
        b.op_sel[op] = first_op + i
    for o in objects:                    # package operation numbers in fields and lists
        o['_values'] = {k: (b.op_sel[v[1]] if isinstance(v, tuple) and v and v[0] == 'op' else v) for k, v in o['_values'].items()}
        o['_list'] = [b.op_sel[v[1]] if isinstance(v, tuple) and v and v[0] == 'op' else v for v in o['_list']]
    defined = {c['name']: 1 + len(b.class_sel) + i for i, c in enumerate(spec['classes'])}
    b.class_sel.update(defined)
    # other packages' interfaces: one import record per kind under the long
    # name, local selectors after the package's own (Ne2000: WCPackInterface1
    # classes 1359.. after its own 1355..1357, operations 5053.. after 5047..5051)
    for imp in spec.get('imports', []):
        for kind, names, table, first in ((2, imp['classes'], b.class_sel, 1 + len(b.class_sel)),
                                          (3, imp['operations'], b.op_sel, 1 + len(b.op_sel)),
                                          (1, imp['indexicals'], b.locator_sel, 0x10000004 + 8 * len(b.locator_sel))):
            if not names:
                continue
            for i, n in enumerate(names):
                require(n not in table, f'imported {n} clashes with a package or system component')
                table[n] = first + i * (8 if kind == 1 else 1)
            b.imports.append((kind, imp['long'], '', first, 0, len(names)))
    # layouts and bodies
    layouts = {}
    for cname in set(o['class'] for o in objects) | set(META_CLASS.values()) | {'CodePackageCluster', 'PackageCluster'}:
        if cname in b.classes:
            layouts[cname] = sdk_layout(b.classes, cname)
    for c in spec['classes']:
        layouts[c['name']] = c['layout']
    bodies = {}
    for o in objects:
        cname = o['class']
        if 'list' in o:
            fixed = fixed_body(layouts[cname], o['_values']) if 'fields' in o else b''
            bodies[o['tag']] = fixed + object_list(o['_list'], word_format=o.get('list_format', 13))
        elif cname == 'Text':
            bodies[o['tag']] = plain_text(o['text'])
        else:
            body = fixed_body(layouts[cname], o['_values'])
            if 'subviews' in o or cname == 'Scene' or (cname in defined):
                body += object_list(o['_subviews'])
            if o.get('extra'):
                body += o['extra']
            bodies[o['tag']] = body
    # names: consecutive locators from contents to the last user object
    names = [o.get('name') for o in objects]
    lookup, text_heap = name_tables(names)
    require(read_names(lookup, text_heap, len(names)) == names, 'names do not resolve')
    bodies.update(nameLookup=lookup, nameTextHeap=text_heap,
                  nameDictionary=name_dictionary(meta_sel['nameLookup'], meta_sel['nameTextHeap'], sel['contents'], len(names)))
    meta_bodies, _ = empty_metadata(layouts, meta_sel)
    bodies.update(meta_bodies)
    exports = [('class', '@' + c['name'], 1, defined[c['name']]) for c in spec['classes'] if not c.get('script')]
    exports += [('locator', '@' + ix, 1, sel[tag]) for ix, tag in spec.get('indexicals', {}).items()]
    exports += [('operation', '@' + op, 1, b.op_sel[op]) for op in package_ops]
    # `define interface`: one entry per kind under the long name (WCPack:
    # class/locator entries for AirSurferInterface1; MagicJavaScript: class 4,
    # operation 18, intrinsic 2 for JavaScriptInterface1); members must be
    # consecutive selectors in interface order
    for iface in spec.get('interfaces', []):
        for kind, names, table in (('class', iface['classes'], defined), ('operation', iface['operations'], b.op_sel),
                                   ('locator', iface['indexicals'], {ix: sel[tag] for ix, tag in spec.get('indexicals', {}).items()})):
            if not names:
                continue
            sels = [table[n] for n in names]
            step = 8 if kind == 'locator' else 1
            require(sels == list(range(sels[0], sels[0] + step * len(sels), step)),
                    f'interface {iface["name"]} {kind} members are not consecutive: {names}')
            exports.append((kind, iface['long'], len(names), sels[0]))
    bodies.update(export_tables(layouts, meta_sel, exports))
    if spec.get('missing'):                      # `import X or say iText`: PackageData's missing-clique tables
        bodies['missingNames'] = plain_text('\n'.join(long for long, _ in spec['missing']))
        bodies['missingIndexicals'] = object_list([sel[tag] for _, tag in spec['missing']])
    # cluster root
    cluster = layouts['PackageCluster'] if code_free else layouts['CodePackageCluster']
    values = dict(sharedObjectUnshared=False, isPackageCluster=True, isROMCluster=False, keep=False,
                  deleteChanges=False, keepAfterCommit=False, sourceRoster=0, firstPageIndex=0, lastPageIndex=0,
                  firstUncrowdedPageIndex=0xffffffff, nameDictionary=0, sharedObjects=0, sharedObjectReferenceCounts=0,
                  scriptClasses=0, scriptClassNumbers=0, scriptClassNumbersForRenumbering=0, shadowRoster=0,
                  committedTable=0, pristineTable=0, pristineNameDictionary=meta_sel['nameDictionary'],
                  pristineSharedObjects=meta_sel['sharedTable'], needReinitializeCallsList=0, needCommitCallsList=0,
                  commitCount=0, active=False, activateFailed=False, activeUncommitted=False,
                  packageData=meta_sel['packageData'], packageContents=sel['contents'], exportTable=meta_sel['exports'],
                  uniqueIntegrationID1=0, uniqueIntegrationID2=1,
                  firstCompiledLocator=min(class_locators.values()) if class_locators else sel['contents'],
                  classBase1=min(defined.values()) if defined else 0, classCount=len(defined),
                  # the loader maps package operation selectors to numbers through
                  # this range exactly as it does classes (corpus: 5047/80 for CujoChat)
                  operationBase1=first_op if package_ops else 0, operationCount=len(package_ops))
    for f in cluster['fields']:
        values.setdefault(f['name'], False if f['type'] == 'Boolean' else 0)
    values = {k: v for k, v in values.items() if k in {f['name'] for f in cluster['fields']}}   # PackageCluster has no code fields
    heap_objects = [heap_object(0xb0800000 | root_class, cluster_body(cluster, values, spec['internal_name']))]
    for o in objects:
        header = 0xb0000000 | b.class_sel[o['class']]
        # bit 0x08000000: the extra part is a reference list the loader must
        # relocate (corpus: Box/Scene with subviews 0xb9, ObjectLists 0xb8/0xb9;
        # Text 0xb0, Images 0xb2..0xb5).  A Box with subviews but without the
        # bit keeps raw selectors in its list and draws nothing.
        if o['class'] in LIST_CLASSES or o.get('subviews') or 'list' in o: header |= 0x08000000
        if o.get('name'): header |= 0x01000000
        heap_objects.append(heap_object(header, bodies[o['tag']]))
    for n in META_ORDER:
        header = 0xb0000000 | b.class_sel[META_CLASS[n]]
        if META_CLASS[n] in LIST_CLASSES: header |= 0x08000000
        heap_objects.append(heap_object(header, bodies[n]))
    for c in spec['classes']:
        supers = [b.class_sel[s] for s in c['supers']]
        if c.get('script'):
            sc = c['script']
            op = b.op_sel[sc['operation']] if sc['operation'] in package_ops else b.import_operation(sc['operation'])
            heap_objects.append(heap_object(0xb8000000 | b.import_class('UnlinkedScriptClass'),
                                            script_class_record(supers[0], op, sel[sc['method']])))
            continue
        methods = [(b.op_sel[op], fid) for op, fid in c['methods']]
        accessors = [(kind, b.op_sel[op] if op in package_ops else b.import_operation(op), off) for op, kind, off in c.get('accessors', [])]
        heap_objects.append(heap_object(0xb0000000 | meta_class, class_record(supers, methods, c.get('own_fields_word', 0), accessors)))
    formats = [{'class_selector': b.class_sel[n], 'raw_format_nibbles': layouts[n]['raw_format_nibbles']}
               for n in layouts if n in b.class_sel and n != 'CodePackageCluster' and n not in defined]
    formats.append({'class_selector': root_class, 'raw_format_nibbles': cluster['raw_format_nibbles']})
    formats = [f for f in formats if f['class_selector'] != root_class or f is formats[-1] or cluster is layouts.get('CodePackageCluster')]
    formats.append({'class_selector': meta_class, 'raw_format_nibbles': derive('UnlinkedClassWithInstances', b.classes, {})['raw_format_nibbles']})
    formats += [{'class_selector': defined[c['name']], 'raw_format_nibbles': c['layout']['raw_format_nibbles']} for c in spec['classes']]
    fids = sorted(fid for c in spec['classes'] for _, fid in c['methods'])
    table = [None, None] + [spec['function_offsets'][fid] for fid in fids] if not code_free else []
    require(fids == list(range(3, 3 + len(fids))), 'function ids must be 3.. consecutive')
    require(not (code_free and fids), 'a code-free package cannot have native methods')
    attrs = [(0x20, encode_imports(b.imports))]
    if defined:
        comps = [(2, min(defined.values()), len(defined))]
        if package_ops:
            comps.append((3, first_op, len(package_ops)))
        attrs.append((0x30, defined_components(comps)))
    attrs += [(0x10, abbreviated_classes(formats)), (0x53, object_addressing(4, 1, [(12, len(heap_objects) - 1)]))]
    if not code_free:
        attrs += [(0xb0, function_offsets(table, 0)), (0x71, bytes(4) + code), (0xa0, init.finish(len(code)))]
    attrs.append((0x60, heap(heap_objects)))
    raw = package(attrs)
    check = inspect(raw)['packages'][0]
    require(len(check['heap_selectors']['objects']) == len(heap_objects), 'heap mapping mismatch')
    return raw, {'selectors': sel, 'metadata_selectors': meta_sel, 'class_selectors': b.class_sel,
                 'locator_selectors': b.locator_sel, 'operation_selectors': b.op_sel, 'class_locators': class_locators,
                 'exports': exports, 'names': names, 'function_table': table}
