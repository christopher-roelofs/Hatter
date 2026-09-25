#!/usr/bin/env python3
"""Magic Script assembler: the Guide to Development Tools ch. 6 stack language
-> the ROM's JVM-subset bytecode (InterpretByteCodes' 0xC8-entry table) plus
a ConstantPool, as WebBrowser35's ScriptedMethod objects carry them.

A script becomes a ScriptedMethod (constantPool, typeSignatureIndex,
variableCount, bytecode as extra bytes).  The pool's lists are indexed as one
1-based sequence: objects (weak list: instances, indexicals and the type
signature indexicals such as iReferenceVoidType), integers (call descriptors
`operationIndex << 16 | signatureIndex` reached through a one-word
"method ref" whose value is the descriptor's index, and large literals),
then operation numbers.  Calls are invokevirtual (0xb6) with the method
ref's index; the ROM's invokedispatcher pops the arguments the signature
object declares and dispatches (0xb7 inherited, 0xb8 class, 0xb9 intrinsic).
"""
import re
from inspect_format import require

TYPES = {'void', 'UnsignedByte', 'SignedByte', 'UnsignedShort', 'SignedShort', 'Unsigned', 'Signed', 'Reference'}
BRANCHES = {'equal': 0x9f, 'not equal': 0xa0, '0': 0x99, 'not 0': 0x9a, '< 0': 0x9b, '>= 0': 0x9c, '> 0': 0x9d, '<= 0': 0x9e,
            'nilObject': 0xc6, 'not nilObject': 0xc7}
ARITH = {'add': 0x60, 'subtract': 0x64, 'multiply': 0x68, 'divide': 0x6c, 'remainder': 0x70, 'negate': 0x74,
         'bitwise and': 0x7e, 'bitwise or': 0x80, 'bitwise xor': 0x82}
SPECIAL_SIGNATURES = {('Reference', 'Reference', 'Reference', 'Unsigned', 'Reference', 'Reference', 'Unsigned', 'void'): 'iPerformWithConfirmationType'}


def parse_prototype(text):
    m = re.fullmatch(r'\s*\[\s*\(([^)]*)\)\s*->\s*(\w+)\s*\]\s*', text)
    require(m, f'bad prototype {text!r}')
    params = tuple(p.strip() for p in m.group(1).split(',') if p.strip())
    ret = m.group(2)
    require(all(p in TYPES for p in params) and ret in TYPES, f'unknown type in prototype {text!r}')
    return params, ret


def signature_indexical(params, ret):
    """The system indexical holding this prototype's type signature object."""
    key = params + (ret,)
    if key in SPECIAL_SIGNATURES:
        return SPECIAL_SIGNATURES[key]
    return 'i' + ''.join(params) + (ret if ret != 'void' else 'Void') + 'Type'


class Pool:
    def __init__(self):
        self.objects, self.integers, self.operations, self.intrinsics = [], [], [], []

    def obj(self, value):
        if value not in self.objects:
            self.objects.append(value)
        return self.objects.index(value)             # position; unified index computed later

    def index(self, kind, position):
        base = {'objects': 0, 'integers': len(self.objects), 'operations': len(self.objects) + len(self.integers),
                'intrinsics': len(self.objects) + len(self.integers) + len(self.operations)}[kind]
        return base + position + 1


def assemble(tag, statements, convert, prototype=None):
    """statements: the script's statements (without 'script tag' / 'end script').
    convert(raw) -> ('ref', tag) | ('ix', name) | ('op', name) | ('sysop', name).
    Returns dict(code, objects, integers, operations, signature_index, variable_count)."""
    params, ret = parse_prototype(prototype or '[(Reference) -> void]')
    pool = Pool()
    pool.obj(('ix', signature_indexical(params, ret)))          # index 1: the script's own signature
    calls, ints = [], []                                        # deferred integer entries
    items, labels = [], {}
    variables = 0
    for st in statements:
        st = st.strip()
        while True:                                             # 'label:' prefixes
            m = re.match(r'(\w+):\s*(.*)$', st, re.S)
            if not m or m.group(1) in ('push', 'pop', 'call', 'if', 'goto', 'return', 'script'):
                break
            labels[m.group(1)] = len(items); st = m.group(2).strip()
        if not st:
            continue
        if st.startswith('script prototype is'):
            continue
        m = re.match(r'push\s+(.*)$', st, re.S)
        if m:
            raw = m.group(1).strip()
            if raw == 'nilObject': items.append(('op1', 0x01)); continue
            if raw == 'self': items.append(('op1', 0x2a)); continue
            mm = re.match(r'(variable|argument)\s+(\d+)$', raw)
            if mm:
                n = int(mm.group(2)); variables = max(variables, n + 1)
                items.append(('op1', 0x2a + n) if n < 4 else ('op2', 0x15, n)); continue
            mm = re.match(r'0x([0-9A-Fa-f]+)$', raw)
            if mm:
                ints.append(('literal', int(mm.group(1), 16) & 0xffffffff)); items.append(('ldc', ('integers', len(ints) - 1))); continue
            mm = re.match(r'-?\d+$', raw)
            if mm:
                n = int(raw)
                if -1 <= n <= 5: items.append(('op1', 0x03 + n))
                elif -128 <= n <= 127: items.append(('op2', 0x10, n & 0xff))
                elif -32768 <= n <= 32767: items.append(('op3', 0x11, n & 0xffff))
                else:
                    ints.append(('literal', n & 0xffffffff)); items.append(('ldc', ('integers', len(ints) - 1)))
                continue
            if raw.startswith('operation_'):
                v = convert(raw)
                require(isinstance(v, tuple) and v[0] in ('op', 'sysop'), f'unsupported operation value {raw}')
                if v not in pool.operations: pool.operations.append(v)
                items.append(('ldc', ('operations', pool.operations.index(v)))); continue
            v = convert(raw)
            require(isinstance(v, tuple) and v[0] in ('ref', 'ix'), f'unsupported push value {raw!r}')
            items.append(('ldc', ('objects', pool.obj(v)))); continue
        m = re.match(r'pop into variable\s+(\d+)$', st)
        if m:
            n = int(m.group(1)); variables = max(variables, n + 1)
            items.append(('op1', 0x3b + n) if n < 4 else ('op2', 0x36, n)); continue
        m = re.match(r'copy into variable\s+(\d+)$', st)
        if m:
            n = int(m.group(1)); variables = max(variables, n + 1)
            items.append(('op1', 0x59)); items.append(('op1', 0x3b + n) if n < 4 else ('op2', 0x36, n)); continue
        if st == 'pop': items.append(('op1', 0x57)); continue
        if st == 'dup': items.append(('op1', 0x59)); continue
        if st == 'swap': items.append(('op1', 0x5f)); continue
        if st in ARITH: items.append(('op1', ARITH[st])); continue
        if st == 'return': items.append(('op1', 0xb1)); continue
        if st == 'return integer': items.append(('op1', 0xac)); continue
        if st == 'return object': items.append(('op1', 0xb0)); continue
        m = re.match(r'goto\s+(\w+)$', st)
        if m: items.append(('branch', 0xa7, m.group(1))); continue
        m = re.match(r'if\s+(.+?)\s*,\s*goto\s+(\w+)$', st)
        if m:
            cond = ' '.join(m.group(1).split())
            require(cond in BRANCHES, f'unsupported condition {cond!r}')
            items.append(('branch', BRANCHES[cond], m.group(2))); continue
        m = re.match(r'call\s+(intrinsic_)?(\w+)\s*(\[.*\])$', st, re.S)
        if m:
            cp, cr = parse_prototype(m.group(3))
            sig = pool.obj(('ix', signature_indexical(cp, cr)))
            if m.group(1):                                  # invokeinterface -> CallIntrinsicMethod
                v = ('intrinsic', m.group(2))
                if v not in pool.intrinsics: pool.intrinsics.append(v)
                ints.append(('descriptor', ('intrinsics', pool.intrinsics.index(v)), sig))
                ints.append(('methodref', len(ints) - 1))
                items.append(('call', 0xb9, len(ints) - 1)); continue
            v = convert('operation_' + m.group(2))
            require(isinstance(v, tuple) and v[0] in ('op', 'sysop'), f'unknown operation {m.group(2)}')
            if v not in pool.operations: pool.operations.append(v)
            ints.append(('descriptor', ('operations', pool.operations.index(v)), sig))
            ints.append(('methodref', len(ints) - 1))
            items.append(('call', 0xb6, len(ints) - 1)); continue
        require(False, f'unsupported script statement {st!r}')
    # unified indices (the integers list length is known before its values are)
    pool.integers = [0] * len(ints)
    for i, (kind, *rest) in enumerate(ints):
        if kind == 'literal': pool.integers[i] = rest[0]
        elif kind == 'descriptor': pool.integers[i] = pool.index(*rest[0]) << 16 | pool.index('objects', rest[1])
        else: pool.integers[i] = pool.index('integers', rest[0])
    # layout
    sizes = {'op1': 1, 'op2': 2, 'op3': 3, 'ldc': 2, 'branch': 3, 'call': 3}
    offsets, pos = [], 0
    for it in items:
        offsets.append(pos); pos += sizes[it[0]]
    code = bytearray()
    for it, off in zip(items, offsets):
        if it[0] == 'op1': code.append(it[1])
        elif it[0] == 'op2': code += bytes([it[1], it[2]])
        elif it[0] == 'op3': code += bytes([it[1], it[2] >> 8, it[2] & 0xff])
        elif it[0] == 'ldc':
            idx = pool.index(*it[1]); require(idx < 256, 'constant pool index does not fit ldc')
            code += bytes([0x12, idx])
        elif it[0] == 'branch':
            require(it[2] in labels, f'unknown label {it[2]}')
            rel = offsets[labels[it[2]]] - off if labels[it[2]] < len(offsets) else pos - off
            code += bytes([it[1], (rel >> 8) & 0xff, rel & 0xff])
        elif it[0] == 'call':
            idx = pool.index('integers', it[2]); code += bytes([it[1], idx >> 8, idx & 0xff])
    if not code or code[-1] not in (0xb1, 0xac, 0xb0):
        code.append(0xb1)
    return {'code': bytes(code), 'objects': pool.objects, 'integers': pool.integers, 'operations': pool.operations,
            'intrinsics': pool.intrinsics, 'signature_index': 1, 'variable_count': variables}
