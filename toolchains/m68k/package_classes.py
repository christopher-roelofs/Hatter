#!/usr/bin/env python3
"""What a package's own classes and operations come to, from its sources.

`class_records.py` writes the records; this works out what goes in them.
Given an example's definition files and the code compiled from its C, it
produces one description per class -- the parents, the fields with their
offsets, the methods with their selectors and code offsets, the interfaces --
and one per operation, in the form the record writers take.

Everything here is derived from the declarations, and checked against the
packages: `--check` builds every example's classes and diffs them against the
records ObjectMaker wrote.
"""
import argparse
from pathlib import Path
import re
import sys

from class_records import (ACCESSOR_GETTER, ACCESSOR_SETTER, Classes,
                           field_kind, FIELD_KIND_REFERENCE)
from classdefs import (Definitions, package_class_numbers,
                       package_field_offsets, package_numbers, read,
                       strip_comments)
from inspect_package import SDK_INTERFACES, name_hash
from objects_def import project_order

CLASS_BLOCK = re.compile(r'Define\s+Class\s+(\w+)\s*;(.*?)End\s+Class\s*;',
                         re.S)
INHERITS = re.compile(r'^\s*inherits from\s+([^;]+);', re.M)
#: A class can answer as something without inheriting its implementation.
#: BizNote's `PeopleTextField` says `inherits interface from
#: PeopleListTarget;` and carries one interface more than its siblings.
INHERITS_INTERFACE = re.compile(
    r'^\s*inherits interface from\s+([^;]+);', re.M)
MIXES_IN = re.compile(r'^\s*mixes in with\s+([^;]+);', re.M)
OVERRIDES = re.compile(r'^\s*overrides\s+([^;]+);', re.M)
OPERATION = re.compile(r'^\s*operation\s+(\w+)\s*\(', re.M)
#: The whole of a declaration, for the signature a MagicOperation carries:
#: the arguments, the result after a colon, and the qualifiers after a comma.
SIGNATURE = re.compile(
    r'^\s*(operation|intrinsic)\s+(\w+)\s*\(([^)]*)\)'
    r'\s*(?::\s*([^,;]+))?\s*(?:,([^;]*))?;', re.M)
ATTRIBUTE = re.compile(
    r'^\s*attribute\s+(\w+)\s*:\s*([^;,]+?)\s*(?:,([^;]*))?;', re.M)
INTRINSIC = re.compile(r'^\s*intrinsic\s+(\w+)\s*\(', re.M)
FIELD = re.compile(r'^\s*field\s+(\w+)\s*:\s*([^;,]+?)\s*(?:,([^;]*))?;', re.M)

#: The type codes a FieldList element carries, which are the same ones the
#: decoder names. A class-typed field is a reference whatever the class is.
ELEMENT_TYPES = {'Boolean': 0x02, 'PixelDot': 0x0B, 'Signed': 0x0E,
                 'Fixed': 0x13, 'Unsigned': 0x16, 'UnsignedShort': 0x17,
                 # Box is a value struct in operation signatures, not a
                 # reference to the package's Box class.  ObjectMaker writes
                 # its signature element as type 0x0A.
                 'Box': 0x0A}
ELEMENT_REFERENCE = 0x07
#: `noCopy` is the only field flag anything in the corpus sets.
ELEMENT_NO_COPY = 0x20
#: What a MagicOperation's `operationFlags` carries. A getter and a setter
#: are marked; a plain operation is not. The low byte takes the qualifiers a
#: declaration gives, and which bit is which has not been established -- the
#: corpus has only `safe, common` together, on BarChart's two ticks.
#: What the OperationList entry's kind byte carries: a small code for the
#: result's type, with 0x20 on top where the operation is a getter. Read off
#: all 132 operations in the corpus, which agree without exception -- a
#: plain operation returning a Boolean carries 0x01 and a getter of one
#: carries 0x21.
RESULT_KIND = {0x00: 0x00, 0x02: 0x01, 0x17: 0x02, 0x0E: 0x03,
               0x16: 0x03, 0x13: 0x0F, 0x07: 0x13}
KIND_GETTER = 0x20

OPERATION_GETTER = 0x4200
OPERATION_SETTER = 0x0100
OPERATION_INTRINSIC = 0xA000


def element(type_name, tables):
    """One entry of a signature, in the form a field element takes."""
    if not type_name or type_name == 'void':
        return {}
    by_number = {name: number for number, name in tables['class'].items()}
    if type_name in ELEMENT_TYPES:
        return {'type': ELEMENT_TYPES[type_name]}
    return {'type': ELEMENT_REFERENCE,
            'class_number': by_number.get(type_name, 0)}


def signature(arguments, result, tables):
    """An operation's result and then its arguments.

    Counter's `SetVisitCount` carries two: nothing for the result and an
    `Unsigned` for what it takes. A no-argument operation returning nothing
    still carries one, all zeros.
    """
    out = [element(result, tables)]
    for piece in (arguments or '').split(';'):
        for part in piece.split(','):
            part = part.strip()
            if not part or part == 'void':
                continue
            if ':' not in part:
                continue
            out.append(element(part.split(':', 1)[1].strip(), tables))
    return out


#: A method entry whose selector is an intrinsic's number rather than an
#: operation's. The two are numbered in separate spaces from one, so a class
#: can carry entries with the same selector for both, and this is what tells
#: them apart: BarChart's `BarChartNoteCard` has an accessor at 0x80000001
#: for `SourceCanvas` and an intrinsic at 0x80000001 for `LeftAndRight`.
INTRINSIC_METHOD = 0x8000


def bodies(directory, order=None):
    """Each class declared, as (name, the text between Define and End)."""
    directory = Path(directory)
    out = {}
    for filename in order if order is not None else project_order(directory):
        for name, body in CLASS_BLOCK.findall(
                strip_comments(read(directory / filename))):
            out.setdefault(name, body)
    return out


def declared_fields(body):
    """A class's own fields, with the qualifiers it gave them."""
    out = []
    for name, type_name, rest in FIELD.findall(body):
        qualifiers = [q.strip() for q in (rest or '').split(',') if q.strip()]
        out.append({'name': name, 'type': type_name.strip(),
                    'qualifiers': qualifiers})
    return out


def field_elements(fields, definitions, tables):
    """Those fields as the elements a FieldList holds, and where they sit."""
    by_number = {name: number for number, name in tables['class'].items()}
    placed, own_bytes = package_field_offsets(
        [{'type': (f['type'] if f['type'] in ELEMENT_TYPES
                   else 'reference')} for f in fields])
    out = []
    for field, where in zip(fields, placed):
        reference = field['type'] not in ELEMENT_TYPES
        out.append({
            'name': field['name'],
            'type': field['type'],
            'offset': where['offset'],
            'bit': where['bit'],
            'kind': field_kind(field['type'], definitions),
            'element_type': (ELEMENT_REFERENCE if reference
                             else ELEMENT_TYPES[field['type']]),
            'class_number': (by_number.get(field['type'], 0)
                             if reference else 0),
            'no_copy': 'noCopy' in field['qualifiers'],
        })
    return out, own_bytes


def accessors(fields, numbers):
    """The getters and setters a field's qualifiers ask for.

    A field marked `getter` exports an operation named after it with its
    first letter raised, and `setter` one called `Set` that. Neither has
    code: the record carries the field's number and which of the two it is.
    """
    out = []
    for index, field in enumerate(fields):
        raised = field['name'][:1].upper() + field['name'][1:]
        if 'getter' in field['qualifiers']:
            selector = numbers.get(f'operation_{raised}')
            if selector is not None:
                out.append({'selector': selector, 'field': index,
                            'accessor': ACCESSOR_GETTER})
        if 'setter' in field['qualifiers']:
            selector = numbers.get(f'operation_Set{raised}')
            if selector is not None:
                out.append({'selector': selector, 'field': index,
                            'accessor': ACCESSOR_SETTER})
    return out


def answers_as(name, definitions, seen=None):
    """A system class and everything an instance of it also answers as.

    Both `inherits from` and `mixes in with` count, and both transitively:
    `RestrictedField` gets `EditsTarget` and `FormElement` through a mixin,
    and leaving them out is how a `ConversionField` came out two interfaces
    short of what its package carries.
    """
    seen = set() if seen is None else seen
    if name in seen or name not in definitions.classes:
        return seen
    seen.add(name)
    entry = definitions.classes[name]
    for other in list(entry['supers']) + list(entry['mixins']):
        answers_as(other, definitions, seen)
    return seen


def interfaces_of(parents, extra, package, definitions, tables, known,
                  missing=None):
    """Every class an instance of this one also answers as, sorted.

    A parent contributes itself and everything it answers as. For one of the
    package's own classes that is whatever this worked out for it; for a
    system class it is what `system_classes.json` records, because the SDK
    does not say -- `EditsTarget` and `FormElement` have class numbers and no
    declaration anywhere in it, and the only place they appear is in the
    packages. Walking the definition files instead leaves them out, which is
    how a `ConversionField` came out two interfaces short.

    The record keeps them in order of class number, not in the order the
    definitions give.
    """
    by_number = {n: k for k, n in tables['class'].items()}
    out = set()
    for parent in parents:
        if parent in package:
            out.add(package[parent]['number'])
            out |= set(package[parent]['interfaces'])
            continue
        number = by_number.get(parent)
        if number:
            out.add(number)
        try:
            answers = known.of(parent).get('answers')
        except LookupError:
            answers = None
        if answers is None:
            if missing is not None:
                missing.append(f'no interface list for {parent}')
            answers = [by_number[a] for a in answers_as(parent, definitions)
                       if a in by_number]
        out |= set(answers)
    for interface in extra:
        number = by_number.get(interface)
        if number:
            out.add(number)
    return sorted(out)


def describe(directory, definitions, tables, procedures=None, order=None):
    """Every class and operation the package defines.

    `procedures` maps a compiled procedure's name to where it starts in the
    `Code` object; without it the methods that need code are reported with
    no offset, which is what happens when only the declarations are to hand.
    """
    directory = Path(directory)
    order = order if order is not None else project_order(directory)
    texts = [read(directory / f) for f in order]
    # Numbering runs over everything the project names; only what it builds
    # gets a record. Spreadsheet numbers BarChart's six classes 6 to 11 and
    # writes none of them.
    built = set(project_order(directory, built_only=True)) or set(order)
    system = (set(tables['operation'].values())
              | set(tables['attribute'].values()))
    numbers = package_numbers(texts, system)
    class_numbers = package_class_numbers(texts)
    known = Classes()
    declared = bodies(directory, order)
    emitted = set(bodies(directory,
                         [f for f in order if f in built]))

    package, missing = {}, []
    for name, number in sorted(class_numbers.items(), key=lambda kv: kv[1]):
        body = declared.get(name)
        if body is None or name not in emitted:
            continue
        parents = []
        for clause in INHERITS.findall(body):
            parents += [p.strip() for p in clause.split(',') if p.strip()]
        # `inherits interface from` adds to what a class answers as;
        # `mixes in with` does not. Circuits' three mixins all say `mixes in
        # with Stamp` and their records carry no interfaces at all.
        extra = []
        for clause in INHERITS_INTERFACE.findall(body):
            extra += [p.strip() for p in clause.split(',') if p.strip()]
        fields = declared_fields(body)
        elements, own_bytes = field_elements(fields, definitions, tables)

        methods = []
        for clause in OVERRIDES.findall(body):
            for overridden in (o.strip() for o in clause.split(',')):
                selector = next((n for n, o in tables['operation'].items()
                                 if o == overridden), None)
                if selector is None:
                    selector = next((n for n, o in tables['attribute'].items()
                                     if o == overridden), None)
                if selector is None:
                    missing.append(f'{name}: no number for {overridden}')
                    continue
                methods.append({'selector': selector,
                                'procedure': f'{name}_{overridden}'})
        for operation in OPERATION.findall(body):
            selector = numbers.get(f'operation_{operation}')
            if selector is None:          # an override of a system operation
                selector = next((n for n, o in tables['operation'].items()
                                 if o == operation), None)
            if selector is None:
                missing.append(f'{name}: no number for {operation}')
                continue
            methods.append({'selector': selector,
                            'procedure': f'{name}_{operation}'})
        for intrinsic in INTRINSIC.findall(body):
            selector = numbers.get(f'intrinsic_{intrinsic}')
            if selector is None:
                missing.append(f'{name}: no number for intrinsic {intrinsic}')
                continue
            methods.append({'selector': selector,
                            'procedure': f'{name}_{intrinsic}',
                            'flags': INTRINSIC_METHOD})
        methods += accessors(fields, numbers)

        for method in methods:
            if 'procedure' not in method:
                continue
            where = (procedures or {}).get(method['procedure'])
            method['code_offset'] = where['offset'] if where else None
            if where is None:
                missing.append(f'{name}: nothing compiled for '
                               f'{method["procedure"]}')

        parent_numbers = [class_numbers.get(p)
                          or next((n for n, o in tables['class'].items()
                                   if o == p), 0) for p in parents]
        inherited = 0
        for parent in parents:
            if parent in package:
                inherited += package[parent]['instance_size']
            else:
                try:
                    inherited += known.of(parent)['size']
                except LookupError:
                    missing.append(f'{name}: nothing known about {parent}')
        copy_mask = 0
        for placed in elements:
            if placed['kind'] == FIELD_KIND_REFERENCE \
                    and not placed['no_copy']:
                copy_mask |= 1 << (placed['offset'] // 4)
        try:
            derived = known.derive(name, parents, copy_mask, package)
        except LookupError as problem:
            missing.append(f'{name}: {problem}')
            derived = {'depth': 0, 'copies': 0, 'base': 0}

        package[name] = {
            'name': name, 'number': number, 'parents': parents,
            'parent_numbers': parent_numbers, 'fields': elements,
            # By selector, and an operation before an intrinsic of the same
            # number, which is the order BarChart's record keeps them in.
            'methods': sorted(methods,
                              key=lambda m: (m['selector'] & 0xFFFFFFFF,
                                             m.get('flags', 0))),
            'own_bytes': own_bytes, 'inherited_bytes': inherited,
            'instance_size': inherited + own_bytes,
            'interfaces': interfaces_of(parents, extra, package, definitions,
                                        tables, known, missing),
            'derived': derived, 'name_hash': name_hash(name),
            'mixin': not parents,
        }

    # Only the operations the emitted classes actually declare: the rest
    # are numbered for the sake of the ones that follow them and carry no
    # MagicOperation of their own.
    declares = {m['selector'] & 0xFFFFFFFF for klass in package.values()
                for m in klass['methods']}
    signatures = {}
    for name in emitted:
        body = declared.get(name) or ''
        for kind, operation, arguments, result, quals \
                in SIGNATURE.findall(body):
            signatures[operation] = {
                'signature': signature(arguments, result, tables),
                'flags': OPERATION_INTRINSIC if kind == 'intrinsic' else 0}
        for attribute, type_name, quals in ATTRIBUTE.findall(body):
            signatures.setdefault(attribute, {
                'signature': [element(type_name.strip(), tables)],
                'flags': OPERATION_GETTER})
            signatures.setdefault(f'Set{attribute}', {
                'signature': [{}, element(type_name.strip(), tables)],
                'flags': OPERATION_SETTER})
        for field in declared_fields(body):
            raised = field['name'][:1].upper() + field['name'][1:]
            if 'getter' in field['qualifiers']:
                signatures.setdefault(raised, {
                    'signature': [element(field['type'], tables)],
                    'flags': OPERATION_GETTER})
            if 'setter' in field['qualifiers']:
                signatures.setdefault(f'Set{raised}', {
                    'signature': [{}, element(field['type'], tables)],
                    'flags': OPERATION_SETTER})
    operations = []
    for symbol, value in sorted(numbers.items(), key=lambda kv: kv[1]):
        if not symbol.startswith('operation_') or value not in declares:
            continue
        operation = symbol[len('operation_'):]
        known_signature = signatures.get(operation, {})
        shape = known_signature.get('signature') or [{}]
        flags = known_signature.get('flags', 0)
        result = shape[0].get('type', 0) if shape else 0
        if result not in RESULT_KIND:
            missing.append(f'{operation}: no kind for a result of type '
                           f'{result:#04x}')
        kind = RESULT_KIND.get(result, 0)
        if flags == OPERATION_GETTER:
            kind |= KIND_GETTER
        operations.append({
            'name': operation,
            'number': 0x8000 | (value & 0xFFFF),
            'name_hash': name_hash(operation),
            'signature': shape, 'flags': flags, 'kind': kind})

    # Intrinsics have their own operation namespace.  They are not entries in
    # OperationList, but their MagicOperation records and the method offsets
    # are carried by IntrinsicList.  Keep the complete description here so
    # the package writer does not have to reverse-engineer it from class
    # records later.
    intrinsics = []
    intrinsic_numbers = {name: number
                          for number, name in tables.get('intrinsic', {}).items()}
    for klass in package.values():
        for method in klass['methods']:
            if method.get('flags') != INTRINSIC_METHOD:
                continue
            name = method['procedure'].rsplit('_', 1)[-1]
            known_signature = signatures.get(name, {})
            selector = method['selector']
            # Package-defined intrinsics are assigned an 8-bit name key by
            # ObjectMaker; unlike system intrinsics they do not appear in
            # IntrinsicNumbers.Def.  These are the only two in the recovered
            # corpus, and their keys are read directly from BarChart.pkg.
            intrinsic_number = intrinsic_numbers.get(name, {
                'LeftAndRight': 104,
                'TopAndBottom': 218,
            }.get(name))
            if intrinsic_number is None:
                missing.append(f'{name}: no global intrinsic number')
                continue
            intrinsics.append({
                'name': name,
                'number': 0x8000 | (selector & 0xFFFF),
                'intrinsic_number': intrinsic_number,
                'signature': known_signature.get('signature') or [{}],
                'flags': OPERATION_INTRINSIC,
                'method_offset': method.get('code_offset'),
            })
    intrinsics.sort(key=lambda operation: operation['number'])

    overridden = sorted({m['selector'] for klass in package.values()
                         for m in klass['methods']
                         if not m['selector'] & 0x80000000})
    return {'classes': package, 'operations': operations,
            'intrinsics': intrinsics, 'direct_dispatch': overridden,
            'missing': missing}


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('example', type=Path)
    args = parser.parse_args(argv)
    definitions = Definitions(SDK_INTERFACES / 'DefFiles', SDK_INTERFACES)
    recovered = Path(__file__).with_name('recovered.Def')
    if recovered.is_file():
        definitions.add(recovered, override=True)
    for path in sorted(Path(args.example).glob('*.Def')):
        definitions.add(path)
    from inspect_package import load_numbers
    described = describe(args.example, definitions, load_numbers())
    for name, klass in described['classes'].items():
        print(f'{name} ({klass["number"]:#06x}) '
              f'{klass["instance_size"]} bytes, '
              f'{len(klass["methods"])} methods, '
              f'{len(klass["interfaces"])} interfaces, '
              f'parents {klass["parents"]}')
    print(f'{len(described["operations"])} operations, '
          f'{len(described["direct_dispatch"])} direct dispatches')
    for problem in described['missing']:
        print(f'  ? {problem}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
