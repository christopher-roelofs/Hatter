#!/usr/bin/env python3
"""Front end: SDK .cdef / .odef sources -> build_package spec + package headers.

Grammar as documented in the Guide to Development Tools ch. 6 and used by
the samples.  Supported: define class (inherits from, overrides, field,
operation/attribute declarations are recorded), indexical declarations,
instance definitions with int/hex/Boolean/'string'/<pixel dot>/<pixel box>/
(Class tag)/iIndexical/nilObject/N.s/N.b/operation_X values, ObjectList
entries, viewable `subview:` pseudo-fields, `indexical iX = (Class tag)`.
"""
import re
from build_object_values import pixel_units
from derive_fixed_formats import derive
from inspect_format import inspect, require
from link_package_methods import SDK, declarations

BASES = {'Scene': {'BackgroundWithBorder': 44}, 'Box': {'BackgroundWithBorder': 44}, 'SoftwarePackageContents': {'HasDate': 0}}


def strip_comments(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'//[^\n]*', '', text)
    # release build: drop #ifdef DEBUG sections, keep #else branches
    text = re.sub(r'^#ifdef\s+DEBUG\b.*?^(?:#else\n(.*?))?#endif[^\n]*$', lambda m: m.group(1) or '', text, flags=re.S | re.M)
    return text


def statements(text):
    """Split on ';' outside quotes/parentheses; keep statement text."""
    out, cur, depth, quote = [], [], 0, False
    esc = False
    for ch in text:
        if quote and esc: esc = False; cur.append(ch); continue
        if quote and ch == '\\': esc = True; cur.append(ch); continue
        if ch == "'" and not quote: quote = True
        elif ch == "'" and quote: quote = False
        elif not quote and ch in '(<': depth += 1
        elif not quote and ch == ')': depth -= 1
        elif not quote and ch == '>' and not (cur and cur[-1] == '-'): depth -= 1   # '->' in script prototypes
        if ch == ';' and not quote and depth == 0:
            s = ''.join(cur).strip()
            if s: out.append(s)
            cur = []
        else:
            cur.append(ch)
    return out


def parse_cdef(text, extras=None):
    """extras (optional dict) receives 'interfaces' {name: {'long', 'classes',
    'operations', 'indexicals'}}, 'imports' [{'name', 'say'}] and 'reads'."""
    classes, indexicals, cur = [], {}, None
    if extras is None: extras = {}
    extras.setdefault('interfaces', {}); extras.setdefault('imports', []); extras.setdefault('reads', [])
    for st in statements(strip_comments(text)):
        words = st.split()
        if st.startswith('read '):
            extras['reads'].append(st[5:].strip().strip('"\'')); continue
        if st.startswith('import '):
            m = re.match(r'import\s+(\w+)(?:\s+or\s+say\s+(\w+))?', st)
            extras['imports'].append({'name': m.group(1), 'say': m.group(2)}); continue
        if st.startswith('define interface'):
            m = re.match(r'define\s+interface\s+(\w+)(?:\s+"([^"]*)")?', st)
            cur = {'long': m.group(2) or m.group(1), 'classes': [], 'operations': [], 'indexicals': [], 'name': m.group(1)}
            extras['interfaces'][m.group(1)] = cur; continue
        if st == 'end interface': cur = None; continue
        if st.startswith('define class'):
            cur = {'name': words[2], 'supers': [], 'overrides': [], 'fields': [], 'operations': [], 'attributes': []}
            classes.append(cur); continue
        if st == 'end class': cur = None; continue
        if isinstance(cur, dict) and 'long' in cur:          # interface members
            kind = {'class': 'classes', 'operation': 'operations', 'indexical': 'indexicals'}.get(words[0])
            require(kind is not None and len(words) == 2, f'unsupported interface statement: {st}')
            cur[kind].append(words[1]); continue
        if st.startswith('indexical '):
            name, _, cls = st[len('indexical '):].partition(':')
            indexicals[name.strip()] = cls.strip(); continue
        require(cur is not None, f'statement outside a class: {st}')
        if re.match(r'inherits\s+from\s', st): cur['supers'].append(words[2])
        elif re.match(r'overrides\s', st): cur['overrides'].append(words[1])
        elif re.match(r'field\s', st):
            m = re.match(r'field\s+(\w+)\s*:\s*(\w+)(?:\s*,(.*))?', st, re.S)
            cur['fields'].append({'name': m.group(1), 'type': m.group(2), 'flags': [f.strip() for f in (m.group(3) or '').split(',') if f.strip()]})
        elif re.match(r'(class\s+)?operation\s', st):
            m = re.match(r'(class\s+)?operation\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*(\w+))?', st, re.S)
            cur['operations'].append(m.group(2))
            cur.setdefault('signatures', {})[m.group(2)] = {'class_op': bool(m.group(1)), 'params': m.group(3).strip(), 'returns': m.group(4)}
        elif re.match(r'attribute\s', st):
            m = re.match(r'attribute\s+(\w+)\s*:\s*(\w+)(?:\s*,(.*))?', st, re.S)
            flags = [f.strip() for f in (m.group(3) or '').split(',') if f.strip()]
            cur['attributes'].append(m.group(1))
            cur.setdefault('signatures', {})[m.group(1)] = {'class_op': False, 'params': '', 'returns': m.group(2)}
            cur['operations'].append(m.group(1))
            if 'readOnly' not in flags and 'noSetter' not in flags:
                cur['signatures']['Set' + m.group(1)] = {'class_op': False, 'params': f'v: {m.group(2)}', 'returns': None}
                cur['operations'].append('Set' + m.group(1))
        elif re.match(r'intrinsic\s', st):
            m = re.match(r'intrinsic\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*(\w+))?', st, re.S)
            cur.setdefault('intrinsics', []).append(m.group(1))
            cur.setdefault('intrinsic_signatures', {})[m.group(1)] = {'params': m.group(2).strip(), 'returns': m.group(3)}
        elif st.startswith('mixes in with'):
            cur['mixes_in_with'] = st.split()[3]
        elif st in ('abstract', 'mixin'):
            cur.setdefault('modifiers', []).append(st)
        else:
            require(False, f'unsupported class statement: {st}')
    return classes, indexicals


def unescape(s):
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)),
                  s.replace('\\n', '\n').replace('\\t', '\t').replace("\\'", "'").replace('\\\\', '\\'))


def parse_odef(text, scripts=None):
    """scripts (optional dict) receives {tag: [statements]} for `script tag; …
    end script;` blocks; an instance's `Op: (script tag)` attachments land in
    its 'scripts' {operation: tag}."""
    instances, bindings, cur = [], {}, None
    if scripts is None: scripts = {}
    script = None
    for st in statements(strip_comments(text)):
        if script is not None:
            if st == 'end script': script = None
            else: scripts[script].append(st)
            continue
        if st.startswith('read '): continue
        m = re.match(r'script\s+(\w+)$', st)
        if m:
            script = m.group(1); scripts[script] = []; continue
        m = re.match(r"instance (\w+) ([\w.]+)(?:\s+'((?:[^'\\]|\\.)*)')?(.*)$", st, re.S)
        if m:
            flags = m.group(4).strip()
            attached = {op: tag for op, tag in re.findall(r'(\w+)\s*:\s*\(script\s+(\w+)\)', flags)}
            flags = re.sub(r'(?:operation\s+script\s+overrides\s+)?\w+\s*:\s*\(script\s+\w+\)', '', flags).strip()
            cur = {'class': m.group(1), 'tag': m.group(2), 'name': unescape(m.group(3)) if m.group(3) else None,
                   'fields': [], 'flags': flags, 'scripts': attached}
            instances.append(cur); continue
        if st == 'end instance': cur = None; continue
        m = re.match(r'indexical (\w+)\s*=\s*\((\w+) ([\w.]+)\)$', st)
        if m:
            bindings[m.group(1)] = (m.group(2), m.group(3)); continue
        m = re.match(r'indexical (\w+)\s*=\s*nilObject$', st)
        if m:
            bindings[m.group(1)] = (None, None); continue
        require(cur is not None, f'statement outside an instance: {st}')
        name, _, value = st.partition(':')
        cur['fields'].append((name.strip(), value.strip()))
    return instances, bindings


def parse_phrases(text, base_dir=None):
    """`<Locale>.Package.Phrases` (Guide ch. 7): `phrase for OBJ field FIELD
    replace 'old' with 'new';` records, `#include "file"`, and the
    `dont require phrases for textual fields` switch (ignored)."""
    out = []
    lines = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        m = re.match(r'\s*#include\s+"([^"]+)"', line)
        if m:                                   # nested phrase files; the SDK's *Defines.h includes are not phrases
            if base_dir is not None and (base_dir / m.group(1)).exists() and m.group(1).lower().endswith('phrases'):
                lines.append(parse_phrases((base_dir / m.group(1)).read_bytes().decode('latin1'), base_dir))
            continue
        lines.append(line)
    text = '\n'.join(l if isinstance(l, str) else '' for l in lines)
    out += [x for l in lines if not isinstance(l, str) for x in l]
    for m in re.finditer(r"phrase\s+for\s+([\w.]+)\s+field\s+(\w+)\s+replace\s+('(?:[^'\\]|\\.)*')\s+with\s+('(?:[^'\\]|\\.)*')\s*;",
                         strip_comments(text), re.S):
        out.append((m.group(1).split('.')[-1], m.group(2), m.group(3), m.group(4)))
    return out


def apply_phrases(instances, phrases):
    """Replace instance names and field values as the phrase file directs."""
    by_tag = {i['tag'].split('.')[-1]: i for i in instances}
    for tag, field, old, new in phrases:
        inst = by_tag.get(tag)
        require(inst is not None, f'phrase for unknown object {tag}')
        if field == 'name':
            require(inst['name'] == unescape(old[1:-1]), f'phrase for {tag} name does not match {inst["name"]!r}')
            inst['name'] = unescape(new[1:-1])
        else:
            hits = [i for i, (n, v) in enumerate(inst['fields']) if n == field and ' '.join(v.split()) == ' '.join(old.split())]
            require(hits, f'phrase for {tag} field {field}: value not found')
            for i in hits:
                inst['fields'][i] = (field, new)


def extra_data(raw, sample_dir):
    """`data: $hex words` or `include 'file' [start[:end]]` (Guide ch. 6)."""
    raw = raw.strip()
    m = re.match(r"include\s+'([^']+)'(?:\s+(\d+)(?::(\d+))?)?$", raw)
    if m:
        require(sample_dir is not None, 'include needs the sample directory')
        data = (sample_dir / m.group(1)).read_bytes()
        start = int(m.group(2) or 0)
        end = int(m.group(3)) if m.group(3) else len(data)
        return data[start:end]
    hexs = re.sub(r'[\s\\$]|0x', '', raw)
    require(re.fullmatch(r'[0-9A-Fa-f]*', hexs) and len(hexs) % 2 == 0, f'unsupported extra data {raw[:40]!r}')
    return bytes.fromhex(hexs)


class Values:
    def __init__(self, bindings, package_indexicals, operations, sample_dir=None, tags=()):
        self.bindings, self.package_indexicals, self.operations, self.sample_dir = bindings, package_indexicals, operations, sample_dir
        self.tags = set(tags)

    def tag(self, t):
        if t not in self.tags and '.' in t and t.split('.', 1)[1] in self.tags:
            return t.split('.', 1)[1]           # namespace prefix (Main.tag)
        return t

    def convert(self, raw, field_type):
        if raw == 'nilObject': return 0
        if raw == 'nilOperation': return 0
        if raw in ('true', 'false'): return raw == 'true'
        m = re.match(r'\((\w+) ([\w.]+)\)$', raw)
        if m: return ('ref', self.tag(m.group(2)))
        m = re.match(r'(-?\d+)\s*,\s*(-?\d+)$', raw)
        if m: return [int(m.group(1)), int(m.group(2))]        # PixelDot: two pixel shorts
        m = re.match(r'(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)$', raw)
        if m: return [int(x) for x in m.groups()]
        if re.match(r'i[A-Z]\w*$', raw):
            if raw in self.bindings: return ('ref', self.bindings[raw][1]) if self.bindings[raw][1] else 0
            return ('ix', raw)
        m = re.match(r'<([^>]*)>$', raw)
        if m:
            parts = [p.strip() for p in m.group(1).split(',')]
            require(len(parts) in (1, 2, 4), f'unsupported pixel literal {raw}')
            vals = [pixel_units(p) for p in parts]
            return vals[0] if len(vals) == 1 else vals
        if raw.startswith('operation_'):
            return self.operations(raw[len('operation_'):])
        if raw.startswith("'"):
            parts = re.findall(r"'((?:[^'\\]|\\.)*)'", raw)
            require(parts and re.fullmatch(r"(\s*'(?:[^'\\]|\\.)*')+\s*", raw), f'unsupported string {raw[:40]!r}')
            return unescape(''.join(parts))
        m = re.match(r'(-?\d+)\.([sb])$', raw)
        if m: return int(m.group(1))
        m = re.match(r'(-?\d+)\.(\d+)$', raw)
        if m:                                   # Fixed: 16.16
            from fractions import Fraction
            v = Fraction(raw) * 65536
            require(v.denominator == 1, f'inexact Fixed literal {raw}')
            return int(v) & 0xffffffff
        m = re.match(r'(?:0x|\$)([0-9A-Fa-f]+)$', raw)
        if m: return int(m.group(1), 16)
        m = re.match(r'-?\d+$', raw)
        if m:
            v = int(raw)
            return v & 0xffffffff if v < 0 and field_type not in ('Signed',) else v
        require(False, f'unsupported value {raw!r}')


TYPE_FORMAT = {'Boolean': (0, 1), 'SignedByte': (0, 8), 'UnsignedByte': (0, 8), 'Signed': (4, 32), 'Unsigned': (4, 32), 'Flags': (4, 32), 'Dot': (4, 64), 'PixelDot': (4, 32), 'PixelBox': (1, 64), 'Micron': (4, 32), 'Fixed': (4, 32),
               'UnsignedShort': (2, 16), 'ClassNumber': (9, 32), 'OperationNumber': (10, 32), 'Pointer': (7, 32), 'Function': (4, 32)}


def mixin_fields(classes, name, cursor_bytes):
    """A mixin's leaf fields placed at cursor (after the flavor's fixed part)."""
    cls = classes[name]
    fields, size = [], 0
    for base in cls['layout']['inherits_from']:
        sub, n = mixin_fields(classes, base['name_latin1'], cursor_bytes + size)
        fields += sub; size += n
    for f in cls['members'].get('fields', []):
        kind, flags = f['type_name_latin1'], f['raw_flags_byte']
        if kind in TYPE_FORMAT: fmt, width = TYPE_FORMAT[kind]
        elif kind in classes: fmt, width = (14 if flags & 128 else 13), 32
        else: require(False, f'unsupported mixin field type {kind}')
        fields.append({'owner': name, 'name': f['name_latin1'], 'type': kind, 'bit_offset': (cursor_bytes + size) * 8 + f['fixed_bit_offset'],
                       'bit_width': width, 'word_format': fmt})
    size += cls['layout']['leaf_storage_bytes']
    return fields, size


def auto_bases(classes, name):
    """Mixin field-access bases for an SDK class.  The flavor chain's fixed
    part comes first; then each mixin group is placed at the running cursor:
    a mixin's inherited mixins are laid out first (recursively, each at its
    own base), then its own leaf, all addressed relative to the field-access
    base its fields name (Door: Box 48, then HasDoorway's group Swallower/
    Entrance/HasLock 48..55, HasDoorway's own fields at 56, Door's at 64)."""
    bases = {}
    def place(mixin, base):
        cls = classes[mixin]
        cursor = base
        for a in cls['layout']['inherits_from']:
            place(a['name_latin1'], cursor)
            cursor += classes[a['name_latin1']]['layout']['fixed_storage_bytes']
        fab = cls['layout']['field_access_base']['name_latin1']
        if fab != 'Object':
            bases.setdefault(fab, base if fab != mixin else cursor)
    def visit(cname):
        cls = classes[cname]
        inherits = [b['name_latin1'] for b in cls['layout']['inherits_from']]
        if not inherits:
            return 0
        size = visit(inherits[0])
        for mixin in inherits[1:]:
            place(mixin, size)
            size += classes[mixin]['layout']['fixed_storage_bytes']
        return cls['layout']['fixed_storage_bytes']
    visit(name)
    return bases


def sdk_layout(classes, name):
    return derive(name, classes, {**auto_bases(classes, name), **BASES.get(name, {})})


def pack_own_fields(fields, start_bytes, classes, package_classes=()):
    """Own fields in declaration order: Booleans take successive bits,
    halfwords align to 2, words to 4 (the layout the class compiler gives
    Scene's own fields)."""
    out, bit = [], start_bytes * 8
    for f in fields:
        kind = f['type']
        if kind == 'Boolean':
            fmt, width = 0, 1
        elif kind in ('UnsignedShort', 'SignedShort'):
            fmt, width = None, 16
        elif kind in TYPE_FORMAT:
            fmt, width = TYPE_FORMAT[kind]
        elif kind in classes or kind in package_classes:
            fmt, width = (14 if 'weak' in f['flags'] else 13), 32
        else:
            require(False, f'unsupported own field type {kind}')
        align = 1 if width == 1 else width
        bit = (bit + align - 1) // align * align
        if width == 16:
            fmt = 2 if bit % 32 == 0 else 3
        out.append({'owner': f.get('owner', '?'), 'name': f['name'], 'type': kind, 'bit_offset': bit, 'bit_width': width, 'word_format': fmt})
        bit += width
    return out, (bit + 31) // 32 * 4 - start_bytes


def class_layout(classes, cdef_class, package_classes=(), package_layouts=None):
    """Flavor superclass layout, then each mixin's leaf, then own fields."""
    # a package mixin (`mixes in with X`) is laid out on X, and its record
    # lists X as its only superclass (corpus: CujoChat's class 1361, mixed
    # into class 1355, has the single superclass TextField)
    supers = cdef_class['supers'] or [cdef_class['mixes_in_with']]
    flavor = supers[0]
    if package_layouts and flavor in package_layouts:
        base = package_layouts[flavor]
    else:
        base = sdk_layout(classes, flavor)
    fields, nibbles, size = list(base['fields']), list(base['raw_format_nibbles']), base['fixed_storage_bytes']
    leaf = 0
    for mixin in supers[1:]:
        if package_layouts and mixin in package_layouts:
            own_of_mixin = [f for f in package_layouts[mixin]['fields'] if f['owner'] == mixin]
            require(not own_of_mixin, f'package mixin {mixin} with fields is not supported yet')
            continue
        sub, n = mixin_fields(classes, mixin, size)
        fields += sub; size += n; leaf += n
        for f in sub:
            for w in range(f['bit_offset'] // 32, (f['bit_offset'] + f['bit_width'] - 1) // 32 + 1):
                while len(nibbles) <= w: nibbles.append(0)
                if f['word_format']: nibbles[w] = f['word_format']
    own, own_bytes = pack_own_fields([dict(f, owner=cdef_class['name']) for f in cdef_class['fields']], size, classes, package_classes)
    for f in own:
        for w in range(f['bit_offset'] // 32, (f['bit_offset'] + f['bit_width'] - 1) // 32 + 1):
            while len(nibbles) <= w: nibbles.append(0)
            if f['word_format']:
                old = nibbles[w]
                nibbles[w] = f['word_format'] if old in (0, f['word_format']) else (1 if {old, f['word_format']} == {2, 3} else nibbles[w])
    fields += own; size += own_bytes; leaf += own_bytes
    while len(nibbles) < size // 4: nibbles.append(0)
    return {'class': cdef_class['name'], 'fixed_storage_bytes': size, 'raw_format_nibbles': nibbles, 'fields': fields,
            'own_fields_word': 0x9000 | leaf if leaf else 0}


def build_spec(cdef_text, odef_text, internal_name, function_ids, sample_dir=None, foreign_cdefs=(), phrases=()):
    """function_ids: {'Class_Op': id} for the native methods present in the code.
    foreign_cdefs: texts of other packages' definitions this package `read`s
    (their `define interface` blocks satisfy `import` statements)."""
    classes_img = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
                   if s['raw_tag'] == 13 for r in s['named_records']}
    _, pub = declarations((SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef').read_text())
    extras = {}
    cdef_classes, cdef_indexicals = parse_cdef(cdef_text, extras)
    foreign_interfaces, foreign_classes = {}, {}
    for text in foreign_cdefs:
        fx = {}
        for c in parse_cdef(text, fx)[0]:
            foreign_classes[c['name']] = c
        foreign_interfaces.update(fx['interfaces'])
    imports = []
    for imp in extras['imports']:
        iface = foreign_interfaces.get(imp['name'])
        require(iface is not None, f'imported interface {imp["name"]} is not defined by a read definition file')
        sigs = {op: c['signatures'][op] for c in foreign_classes.values() for op in iface['operations'] if op in c.get('signatures', {})}
        imports.append(dict(iface, say=imp['say'], weak=bool(imp['say']), signatures=sigs))
    class_ops = {op for c in cdef_classes for op, sig in c.get('signatures', {}).items() if sig['class_op']}
    package_ops = {op for c in cdef_classes for op in c['operations']} - class_ops
    def op_number(name):
        if name in package_ops:
            return ('op', name)                   # package selector, assigned by the assembler
        m = [i for (k, i), n in pub.items() if k == 'operation' and n == [name]]
        require(len(m) == 1, f'unsupported operation number {name}')
        return m[0] + 1
    scripts = {}
    instances, bindings = parse_odef(odef_text, scripts)
    apply_phrases(instances, phrases)
    tags = {i['tag'] for i in instances}
    values = Values(bindings, cdef_indexicals, op_number, sample_dir, tags)
    def script_value(raw):
        raw = raw.strip()
        if raw.startswith('operation_'):
            name = raw[len('operation_'):]
            return ('op', name) if name in package_ops else ('sysop', name)
        return values.convert(raw, 'Reference')
    package_classes = {c['name'] for c in cdef_classes}
    layouts, pending = {}, list(cdef_classes)
    while pending:                       # flavors defined by the package first
        c = pending.pop(0)
        bases = c['supers'] or [c.get('mixes_in_with')]
        require(bases[0], f'{c["name"]} neither inherits from nor mixes in with a class')
        if any(b in package_classes and b not in layouts for b in bases):
            pending.append(c); continue
        layouts[c['name']] = class_layout(classes_img, c, package_classes, layouts)
    spec_classes = []
    for c in cdef_classes:
        # package class operations are direct calls (like intrinsics): no corpus
        # package defines one, so their method-record form is unknown
        methods = [(op, function_ids[f'{c["name"]}_{op}']) for op in c['overrides'] + c['operations']
                   if f'{c["name"]}_{op}' in function_ids and op not in class_ops]
        # `field x: T, getter, setter` -> auto accessor method entries (type index
        # from the ROM's AutoGet*/AutoSet* table, field byte offset); a native
        # Class_Op in the code takes precedence
        accessors = []
        for f in c['fields']:
            cap = f['name'][0].upper() + f['name'][1:]
            for flag, op in (('getter', cap), ('setter', 'Set' + cap)):
                if flag not in f['flags'] or f'{c["name"]}_{op}' in function_ids:
                    continue
                # the accessor may implement a system operation (SpeedScroller's
                # `field image: Image, getter` overrides Viewable's Image)
                require(op in c['operations'] or any(k == 'operation' and n == [op] for (k, _), n in pub.items()),
                        f'{c["name"]}.{f["name"]} {flag} needs an attribute {op}')
                lf = [x for x in layouts[c['name']]['fields'] if x['name'] == f['name'] and x['owner'] == c['name']]
                require(len(lf) == 1, f'no layout field for {c["name"]}.{f["name"]}')
                accessors.append((op, accessor_type(f['type'], lf[0]['bit_offset']) + (flag == 'setter'), lf[0]['bit_offset'] // 8))
        spec_classes.append({'name': c['name'], 'supers': c['supers'] or [c['mixes_in_with']], 'methods': methods, 'layout': layouts[c['name']],
                             'accessors': accessors,
                             'own_fields_word': layouts[c['name']]['own_fields_word'],
                             'operations': [op for op in c['operations'] if not c.get('signatures', {}).get(op, {}).get('class_op')]})
    def is_list(cname):
        n = cname
        while n in classes_img:
            if n == 'ObjectList': return True
            inh = classes_img[n]['layout']['inherits_from']
            n = inh[0]['name_latin1'] if inh else None
        return False
    objects = []
    for inst in instances:
        cname = inst['class']
        obj = {'tag': inst['tag'], 'class': cname, 'name': inst['name'], 'scripts': inst.get('scripts') or {}}
        if is_list(cname) and (cname in layouts or sdk_layout(classes_img, cname)['fixed_storage_bytes'] == 0):
            obj['list'] = [values.convert(v, 'Reference') for _, v in inst['fields']]
        elif is_list(cname):                     # a list class with fixed fields (StackOfCards): fields, then entries
            layout = sdk_layout(classes_img, cname)
            types = {f['name']: f['type'] for f in layout['fields']}
            fields = {name: values.convert(raw, types[name]) for name, raw in inst['fields'] if name in types}
            for name in types:
                fields.setdefault(name, 0)
            obj['fields'] = fields
            obj['list'] = [values.convert(raw, 'Reference') for name, raw in inst['fields'] if name not in types]
        elif cname == 'Text':
            require(all(n == 'text' for n, _ in inst['fields']), 'Text needs only text fields')
            obj['text'] = ''.join(values.convert(v, 'Text') for _, v in inst['fields'])   # several text: lines concatenate
        else:
            layout = layouts[cname] if cname in layouts else sdk_layout(classes_img, cname)
            types = {f['name']: f['type'] for f in layout['fields']}
            fields, subviews = {}, []
            for name, raw in inst['fields']:
                if name == 'subview':
                    subviews.append(values.convert(raw, 'Reference'))
                elif name in ('data', 'extra') and name not in types:
                    obj['extra'] = extra_data(raw, values.sample_dir)
                else:
                    require(name in types, f'{cname}.{name} is not a fixed field')
                    fields[name] = values.convert(raw, types[name])
            for name in types:
                fields.setdefault(name, 0)       # the sample omits inherited fields it leaves nil
            obj['fields'] = fields
            if subviews or cname in layouts or cname == 'Scene':
                obj['subviews'] = subviews
        objects.append(obj)
    # string literals in reference fields and list entries are implicit Text objects
    implicit = []
    def text_ref(v):
        if not isinstance(v, str):
            return v
        implicit.append({'tag': f'_text{len(implicit)}', 'class': 'Text', 'name': None, 'text': v})
        return ('ref', implicit[-1]['tag'])
    for obj in objects:
        if 'fields' in obj:
            obj['fields'] = {k: text_ref(v) for k, v in obj['fields'].items()}
        if 'list' in obj:
            obj['list'] = [text_ref(v) for v in obj['list']]
    objects += implicit
    # a subview's superview field refers to its parent (corpus: every
    # subview in CujoChat/Reversi); scenes set it on opening, a Box installed
    # into a tool page does not draw its subviews without it
    by_tag = {o['tag']: o for o in objects}
    for obj in objects:
        for ref in obj.get('subviews', []):
            child = by_tag.get(ref[1]) if isinstance(ref, tuple) and ref[0] == 'ref' else None
            if child and 'fields' in child and 'superview' in child['fields'] and not child['fields']['superview']:
                child['fields']['superview'] = ('ref', obj['tag'])
    # the contents object first, as the assembler requires
    objects.sort(key=lambda o: 0 if o['tag'] == 'contents' else 1)
    indexicals = {ix: tag for ix, (_, tag) in bindings.items() if tag}
    # Magic Script: each attached script becomes a ScriptedMethod + ConstantPool
    # (+ its three lists) and an UnlinkedScriptClass record subclassing the
    # object's class; the object becomes that class's instance (WebBrowser35)
    from magic_script import assemble
    for obj in [o for o in objects if o.get('scripts')]:
        base = obj['class']
        for op, tag in obj['scripts'].items():
            require(tag in scripts, f'script {tag} is not defined')
            proto = next((st.split('is', 1)[1] for st in scripts[tag] if st.strip().startswith('script prototype is')), None)
            asm = assemble(tag, scripts[tag], script_value, proto)
            objects += [
                {'tag': f'_script_{tag}', 'class': 'ScriptedMethod', 'name': None,
                 'fields': {'constantPool': ('ref', f'_pool_{tag}'), 'typeSignatureIndex': asm['signature_index'],
                            'variableCount': asm['variable_count']}, 'extra': asm['code']},
                {'tag': f'_pool_{tag}', 'class': 'ConstantPool', 'name': None,
                 'fields': {'objects': ('ref', f'_poolobjects_{tag}'), 'integers': ('ref', f'_poolints_{tag}'),
                            'operations': ('ref', f'_poolops_{tag}'),
                            'intrinsics': ('ref', f'_poolintr_{tag}') if asm['intrinsics'] else 0, 'classes': 0, 'classOperations': 0}},
                {'tag': f'_poolobjects_{tag}', 'class': 'ObjectList', 'name': None, 'list': asm['objects'], 'list_format': 14},
                {'tag': f'_poolints_{tag}', 'class': 'IntegerList', 'name': None, 'list': asm['integers'], 'list_format': 4},
                {'tag': f'_poolops_{tag}', 'class': 'OperationNumberList', 'name': None, 'list': asm['operations'], 'list_format': 10}]
            if asm['intrinsics']:
                objects.append({'tag': f'_poolintr_{tag}', 'class': 'IntrinsicNumberList', 'name': None,
                                'list': asm['intrinsics'], 'list_format': 12})
            cname = f'_Script_{tag}'
            layout = layouts[base] if base in layouts else sdk_layout(classes_img, base)
            spec_classes.append({'name': cname, 'supers': [base], 'methods': [], 'layout': layout, 'own_fields_word': 0,
                                 'operations': [], 'script': {'operation': op, 'method': f'_script_{tag}'}})
            layouts[cname] = layout
            obj['class'] = cname
    for imp in imports:
        require(not imp['say'] or imp['say'] in indexicals, f'"or say" indexical {imp["say"]} is not bound to an object')
    spec = {'internal_name': internal_name, 'classes': spec_classes, 'objects': objects, 'indexicals': indexicals,
            'interfaces': list(extras['interfaces'].values()), 'imports': imports,
            'missing': [(imp['long'], indexicals[imp['say']]) for imp in imports if imp['say']]}
    headers = {'classes': [c['name'] for c in cdef_classes], 'indexicals': sorted(indexicals),
               'nil_indexicals': sorted(ix for ix, (_, tag) in bindings.items() if not tag),
               'cdef_classes': cdef_classes, 'layouts': layouts, 'imports': imports,
               'link_interfaces': {imp['name']: {'long': imp['long'], 'weak': imp['weak'],
                                                 'counts': {2: len(imp['classes']), 3: len(imp['operations']), 1: len(imp['indexicals'])}}
                                   for imp in imports}}
    return spec, headers


def accessor_type(type_name, bit_offset):
    """Getter index into the ROM's auto accessor table (GetAutoGetterOrSetterAddress,
    0x13EBAC64: Word 0, Halfword 2, Byte 4, Bit0..7 6..20, ObjectReference 0x16,
    ClassSelector 0x18, OperationSelector 0x1a, TextReference 0x20, Pointer 0x22);
    the setter is the next index."""
    if type_name == 'Boolean': return 6 + 2 * (bit_offset % 8)
    if type_name in ('UnsignedShort', 'SignedShort'): return 2
    if type_name in ('UnsignedByte', 'SignedByte'): return 4
    if type_name == 'ClassNumber': return 0x18
    if type_name == 'OperationNumber': return 0x1a
    if type_name in ('Pointer', 'ReadOnlyPointer'): return 0x22
    if type_name == 'Text': return 0x20
    if type_name in SCALARS: return 0
    return 0x16


STRUCTS = {'Dot', 'Box', 'PixelDot', 'PixelBox'}
SCALARS = {'Boolean', 'Unsigned', 'Signed', 'Micron', 'Fixed', 'UnsignedShort', 'SignedShort', 'UnsignedByte',
           'SignedByte', 'Dot', 'Box', 'PixelDot', 'PixelBox', 'Pointer', 'ClassNumber', 'OperationNumber', 'Time', 'Date',
           'Function', 'Flags', 'Unicode', 'ReadOnlyPointer'}


def c_type(t):
    t = t.strip()
    var = t.startswith('var ')
    if var: t = t[4:].strip()
    if t in STRUCTS:                        # the system header passes structures by pointer
        return t + ' *' if var else 'const ' + t + ' *'
    base = t if t in SCALARS else 'Reference'
    return base + (' *' if var else '')


def field_kind(kind):
    if kind == 'Boolean': return 'Bit', 'Boolean'
    if kind in ('UnsignedShort', 'SignedShort'): return 'Halfword', kind
    if kind in ('UnsignedByte', 'SignedByte'): return 'Byte', kind
    if kind == 'ClassNumber': return 'ClassSelector', kind
    if kind == 'OperationNumber': return 'OperationSelector', kind
    if kind in SCALARS: return 'Word', kind
    return 'Reference', 'Reference'


def sig_types(sig):
    types = []
    for p in [p for p in sig['params'].split(';') if p.strip()]:
        names, _, t = p.partition(':')
        types += [c_type(t)] * len([n for n in names.split(',') if n.strip()])
    return types


def call_macros(op, sig):
    """Prototypes and call macros for an operation in the system header's form."""
    types = sig_types(sig)
    ret = c_type(sig['returns']) if sig['returns'] else 'void'
    first = 'ClassNumber' if sig['class_op'] else 'Reference'
    disp = 'ClassMethodDispatcher' if sig['class_op'] else 'ObjectMethodDispatcher'
    args = ', '.join(['DispatcherAddress', 'int', first] + types)
    args2 = ', '.join(['DispatcherAddress', 'int', 'int', first] + types)
    names = ', '.join(['self'] + [f'a{i}' for i in range(len(types))])
    return (f'extern "C" {ret} __1d_{op}({args});\nextern "C" {ret} __2d_{op}({args2});\n'
            f'#define {op}({names}) __1d_{op}({disp}, (int)operation_{op}, {names})\n'
            f'#define Inherited{op}({names}) __2d_{op}(Inherited{disp}, (int)operation_{op}, (int)(ClassNameToNumber(CURRENTCLASS)), {names})\n')


def package_headers(name, headers, cdef_classes=None, layouts=None):
    """The class compiler's .xh/.xph for the package: class numbers, package
    indexicals and operation numbers as loader-resolved words, call macros
    for package operations in the system header's form, and the field
    access tokens Accessors.h expects (Field/SetField)."""
    xh = f'#ifndef INCLUDED_{name}_xh_HEADER\n#define INCLUDED_{name}_xh_HEADER\n// generated by odef_frontend.py\n'
    for cls in headers['classes']:
        xh += f'extern "C" int _classNumber_{cls}_;\n#define {cls}_ ((ClassNumber)_classNumber_{cls}_)\n'
    for ix in headers['indexicals']:
        xh += f'extern "C" int _localLocator_{ix}_;\n#define {ix} ((Reference)_localLocator_{ix}_)\n'
    for ix in headers.get('nil_indexicals', []):
        xh += f'#define {ix} ((Reference)0)\n'
    for imp in headers.get('imports', []):          # another package's interface, resolved by long name
        tag = imp['name']
        for n, cls in enumerate(imp['classes']):
            xh += f'extern "C" int _importClass_{tag}_{n}_;\n#define {cls}_ ((ClassNumber)_importClass_{tag}_{n}_)\n'
        if imp['indexicals']:
            xh += f'extern "C" int _importLocator_{tag}_0_;\n'
            for n, ix in enumerate(imp['indexicals']):
                xh += f'#define {ix} ((Reference)(_importLocator_{tag}_0_ + {8 * n}))\n'
        for n, op in enumerate(imp['operations']):
            sig = imp['signatures'].get(op, {'params': '', 'returns': None, 'class_op': False})
            xh += f'extern "C" int _importOp_{tag}_{n}_;\n#define operation_{op} ((OperationNumber)_importOp_{tag}_{n}_)\n'
            xh += call_macros(op, sig)
    for c in cdef_classes or []:
        for op, sig in c.get('signatures', {}).items():
            if sig['class_op']:                       # package class operations: direct calls (see build_spec)
                types = sig_types(sig)
                ret = c_type(sig['returns']) if sig['returns'] else 'void'
                xh += f'extern "C" {ret} {c["name"]}_{op}({", ".join(["ClassNumber"] + types)});\n#define {op} {c["name"]}_{op}\n'
                continue
            params = [p for p in sig['params'].split(';') if p.strip()]
            types = []
            for p in params:
                names, _, t = p.partition(':')
                types += [c_type(t)] * len([n for n in names.split(',') if n.strip()])
            ret = c_type(sig['returns']) if sig['returns'] else 'void'
            first = 'ClassNumber' if sig['class_op'] else 'Reference'
            disp = 'ClassMethodDispatcher' if sig['class_op'] else 'ObjectMethodDispatcher'
            args = ', '.join(['DispatcherAddress', 'int', first] + types)
            args2 = ', '.join(['DispatcherAddress', 'int', 'int', first] + types)
            names = ', '.join(['self'] + [f'a{i}' for i in range(len(types))])
            xh += (f'extern "C" int _operationNumber_{op}_;\n#define operation_{op} ((OperationNumber)_operationNumber_{op}_)\n'
                   f'extern "C" {ret} __1d_{op}({args});\nextern "C" {ret} __2d_{op}({args2});\n'
                   f'#define {op}({names}) __1d_{op}({disp}, (int)operation_{op}, {names})\n'
                   f'#define Inherited{op}({names}) __2d_{op}(Inherited{disp}, (int)operation_{op}, (int)(ClassNameToNumber(CURRENTCLASS)), {names})\n')
        for intr in c.get('intrinsics', []):    # package intrinsics: direct calls within the package
            sig = c.get('intrinsic_signatures', {}).get(intr, {'params': '', 'returns': None})
            params = [p for p in sig['params'].split(';') if p.strip()]
            types = []
            for p in params:
                names, _, t = p.partition(':')
                types += [c_type(t)] * len([n for n in names.split(',') if n.strip()])
            ret = c_type(sig['returns']) if sig['returns'] else 'void'
            xh += f'extern "C" {ret} {c["name"]}_{intr}({", ".join(types) or "void"});\n#define {intr} {c["name"]}_{intr}\n'
        if layouts and c['name'] in layouts:
            L = layouts[c['name']]
            own = [f for f in L['fields'] if f['owner'] == c['name']]
            start = min([f['bit_offset'] // 8 for f in own], default=L['fixed_storage_bytes'])
            xh += (f'#define _{c["name"]}_linkage_ Flavor\n#define _{c["name"]}_base_ Object\n'
                   f'#define _{c["name"]}_fixedOffset_ {start}\n#define _{c["name"]}_leafSize_ {L["fixed_storage_bytes"] - start}\n')
            xh += f'struct {c["name"]}_Fields\n\t{{\n'
            for f in own:
                kind, ctype = field_kind(f['type'])
                ct = {'Bit': 'Boolean', 'Reference': 'StorableReference'}.get(kind, ctype)
                xh += f'\t{ct} {f["name"]}' + (' : 1' if kind == 'Bit' else '') + ';\n'
            xh += '\t};\n'
            for f in own:
                kind, ctype = field_kind(f['type'])
                byte = f['bit_offset'] // 8
                if f['type'] == 'Dot':          # accessed as two Micron words
                    for i, sub in enumerate(('h', 'v')):
                        fn = f'{c["name"]}_{f["name"]}_{sub}'
                        xh += f'#define _{fn}_kind_ Word\n#define _{fn}_type_ Micron\n#define _{fn}_fixedOffset_ {byte + 4 * i}\n#define _{fn}_class_ {c["name"]}\n'
                    continue
                fn = f'{c["name"]}_{f["name"]}'
                off = f'{byte},{f["bit_offset"] % 8}' if kind == 'Bit' else str(byte)
                xh += f'#define _{fn}_kind_ {kind}\n#define _{fn}_type_ {ctype}\n#define _{fn}_fixedOffset_ {off}\n#define _{fn}_class_ {c["name"]}\n'
    xh += '#endif\n'
    inc = f'#include "{name}.xh"\n'
    return {f'{name}.xh': xh, f'{name}.xph': inc, f'{name}Indexicals.xh': inc, f'{name}Indexicals.xph': inc}
