#!/usr/bin/env python3
"""Derive a Clang-compilable copy of the SDK's Apollo C/C++ headers.

The originals (classic Mac line endings, 1997 C++: implicit int on `const`
and on `extern "C"` declarations) are copied, not modified, into
out/rosemary-sdk-headers/ with the minimal edits below.  Every edit is
recorded in edits.json so the derivation is reviewable.
"""
import json
import re
from pathlib import Path
from link_package_methods import ROOT, SDK

SRC = SDK / 'Interfaces'
OUT = ROOT / 'out/rosemary-sdk-headers'
RULES = [
    ('implicit-int const', re.compile(r'^(\s*)const\s+(\w+)\s*=', re.M), r'\1const int \2 ='),
    ('implicit-int extern C', re.compile(r'^(\s*extern "C")\s+(\w+)\(\);', re.M), r'\1 int \2();'),
    # Intrinsics are called through a CodePointer (a transition-vector
    # address) with a plain function-pointer call, which only the historical
    # compiler's -mtransition-vectors could turn into a code/GP load.  Route
    # them through a named stub the package build supplies instead.
    ('tv-call to stub', re.compile(r'\)_functionPointer_Wildcard_(\w+?)_(\d+)_\)\('), r')__tv_\1_\2)('),
    ('tv-stub declaration', re.compile(r'^extern CodePointer _functionPointer_Wildcard_(\w+?)_(\d+)_;', re.M),
     r'extern CodePointer _functionPointer_Wildcard_\1_\2_;\nextern "C" void __tv_\1_\2();'),
]
# Indexicals are `({ extern int _indexical_Wildcard_X_0_; ... })` inside
# functions of both C and C++ linkage; Clang rejects the linkage clash, so
# declare each base once at namespace scope where the file starts.
INDEXICAL_BASE = re.compile(r'extern int (_indexical_Wildcard_\w+?_0_);')
PSEUDO_PROTO = re.compile(r'^\t([\w ]+?\s?\*?) (__[12]d_\w+)\(([^)]*)\); \\$', re.M)
INDEXICAL_MACRO = re.compile(r'\(\{ extern int (_indexical_Wildcard_\w+?_0_); (\(Reference\)\(\1 \+ \d+\)); \}\)')


def derive():
    edits = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for sub in ('', 'Apollo', 'Apollo/ExtraInterfaces', 'MipsHeaders'):
        src = SRC / sub if sub else SRC
        dst = OUT / sub if sub else OUT
        dst.mkdir(parents=True, exist_ok=True)
        for path in src.iterdir():
            if not path.is_file() or path.suffix not in ('.h', '.xh', '.xph', '.e') or path.name.endswith('.rsrc'):
                continue
            text = path.read_bytes().decode('latin1').replace('\r\n', '\n').replace('\r', '\n')
            counts = {}
            for name, pattern, repl in RULES:
                text, n = pattern.subn(repl, text)
                if n:
                    counts[name] = n
            # hoist every __Nd_ pseudo-function prototype to namespace scope
            # with C linkage, so uses inside static (C++) helpers and extern
            # "C" methods agree (the block-scope declarations then inherit it)
            protos = sorted(set(PSEUDO_PROTO.findall(text)))
            if protos:
                decl = ''.join(f'extern "C" {ret} {name}({args});\n' for ret, name, args in protos)
                text = re.sub(r'^(#define \w+\n)', r'\1' + decl, text, count=1, flags=re.M)
                counts['hoisted pseudo-function prototypes'] = len(protos)
            bases = sorted(set(INDEXICAL_BASE.findall(text)))
            if bases:
                # drop the block-scope redeclarations (C vs C++ linkage clash
                # between extern "C" methods and static helpers) in favour of
                # one namespace-scope C declaration per base
                text, n = INDEXICAL_MACRO.subn(r'(\2)', text)
                counts['indexical macros without block declaration'] = n
                decl = ''.join(f'extern "C" int {b};\n' for b in bases)
                text = re.sub(r'^(#define \w+\n)', r'\1' + decl, text, count=1, flags=re.M)
                counts['indexical-base declarations'] = len(bases)
            (dst / path.name).write_text(text, encoding='latin1')
            if counts:
                edits[str(Path(sub) / path.name)] = counts
    (OUT / 'edits.json').write_text(json.dumps(edits, indent=1, sort_keys=True) + '\n')
    return edits


if __name__ == '__main__':
    e = derive()
    print(json.dumps(e, indent=1, sort_keys=True))
