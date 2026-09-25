#!/usr/bin/env python3
"""Build a 68k Magic Cap package from an example's sources.

    build_example.py <example directory> [-o package.pkg]

`objects_def.py` reads what the definitions declare; this adds the nine
objects they do not, and emits the cluster. Those nine are ObjectMaker's own
bookkeeping rather than anything an author writes:

    root list          slot N is the instance the file numbers N
    load list          what to bring in at activation
    class list         empty without code, and likewise
    operation list       the operation and intrinsic lists
    intrinsic list
    string table       the names the instances are given
    empty string table
    string dictionary  those names against the objects carrying them
    package boot       the lists, the package, and the cluster checksum

Nothing here is copied from an existing package. Where a value could not be
worked out it is taken from what Template carries, and said so.
"""
import argparse
from pathlib import Path
import struct
import sys

from classdefs import (Definitions, package_class_numbers,
                       package_numbers, read)
from inspect_package import SDK_INTERFACES, load_numbers
from profiles import resolve
from objects_def import (instance_sources, number, parse,
                         project_order, read_indexicals, to_spec)
from write_package import (CLUSTER_CONSTANTS, build, cluster_checksum,
                           encode_string_table, make_object)

# The root list lives in the package's own list at this element. Template puts
# it at 24 and so does every other example here.
ROOT_LIST_ELEMENT = 24

# The name ObjectMaker gives the root list. No definition file mentions it,
# and every package's name table carries it against that list's own id.
ROOT_LIST_NAME = 'Reference Numbers List'

# A record whose object has a name carries bit 1 in its tag.
NAMED_TAG = 0x8A

# The name ObjectMaker gives the Code object. No definition file mentions it
# either, and every package that has one calls it this.
CODE_NAME = 'Headers'


def reference(object_id):
    return 0xB0000000 | object_id


def assign_ids(instances, described=None):
    """Every object's id, in the order ObjectMaker hands them out.

    `objects_def.number` gives the declared instances their ids; this carries
    on through the ones a build makes for itself. The order is not a choice:
    it is what all fourteen cookbook packages have, without exception --

        root list        the instances at the slots their numbers name
        package          numbered here because the root list refers to it
        string list      the field names, empty in a package with no classes
        (a free id)      an object made and dropped while building
        code             the compiled procedures, if there are any
        field list       per class, in class-number order, where it has
        class              fields, and its Class record either way
        class list
        magic operation  one per operation the package defines
        operation list
        direct dispatch  the system operations its classes override
        intrinsic list
        load list
        string list      the names
        (a free id)      in a package with a long name table, a Buffer
        string dictionary
        package boot

    Returns the instance-number-to-id mapping, a namespace of the generated
    ids, and the two ids left free.
    """
    numbers = dict(number(instances))
    root_id = len(numbers) + 1
    made = {'root': root_id}
    next_id = root_id + 1

    # Nothing refers to a package, so the walk never numbered it; the root
    # list does refer to it, and is built first, so it is numbered next.
    for instance in instances:
        if instance['number'] not in numbers:
            numbers[instance['number']] = next_id
            next_id += 1

    def take():
        nonlocal next_id
        next_id += 1
        return next_id - 1

    made['field_names'] = take()
    free = [take()]
    classes = (described or {}).get('classes') or {}
    operations = (described or {}).get('operations') or []
    if classes:
        made['code'] = take()
        made['class_records'] = {}
        for name, klass in sorted(classes.items(),
                                  key=lambda kv: kv[1]['number']):
            entry = {}
            if klass['fields']:
                entry['fields'] = take()
            entry['record'] = take()
            made['class_records'][name] = entry
    made['classes'] = take()
    made['magic_operations'] = {operation['number']: take()
                                for operation in operations}
    made['operations'] = take()
    if (described or {}).get('direct_dispatch'):
        made['direct_dispatch'] = take()
    intrinsic_operations = (described or {}).get('intrinsics') or []
    made['intrinsic_operations'] = {
        operation['number']: take() for operation in intrinsic_operations}
    made['intrinsics'] = take()
    made['load'] = take()
    made['strings'] = take()
    free.append(take())
    made['dictionary'] = take()
    made['boot'] = take()
    return numbers, made, free


def code_objects(definitions, tables, made, described, blob):
    """The records that describe a package's own classes and operations.

    Everything here is written by `class_records.py`; what it needs is in
    `package_classes.describe`. The only thing this adds is the ids, which
    `assign_ids` has already handed out.
    """
    import class_records
    from package_classes import ELEMENT_NO_COPY

    generated = []
    if not described['classes']:
        return generated, [], []

    # The Code object is two zero words -- `Code.Def` calls them `unused`
    # and `kind`, and says 68K is 0 -- and then the compiled procedures.
    generated.append({'id': made['code'], 'class': 'Code',
                      'values': {'unused': 0, 'kind': 0}, 'bytes': blob,
                      'tag_low': NAMED_TAG})
    lead = class_records.FIXED_BYTES and 8

    field_names, class_entries = [], []
    for name, klass in sorted(described['classes'].items(),
                              key=lambda kv: kv[1]['number']):
        where = made['class_records'][name]
        field_list = where.get('fields', 0)
        if field_list:
            first = len(field_names) + 1
            elements = []
            for field in klass['fields']:
                field_names.append(field['name'])
                elements.append(
                    (field['class_number'] << 16)
                    | (field['element_type'] << 8)
                    | (ELEMENT_NO_COPY if field['no_copy'] else 0))
            generated.append({
                'id': field_list, 'class': 'FieldList',
                'payload': class_records.field_list(
                    [{'class_number': f['class_number'],
                      'element_type': f['element_type'],
                      'no_copy': f['no_copy']} for f in klass['fields']],
                    made['field_names'], first)})

        methods = []
        for method in klass['methods']:
            if 'accessor' in method:
                methods.append(class_records.method_entry(
                    method['selector'], accessor=method['accessor'],
                    field=klass['fields'][method['field']],
                    class_number=klass['number']))
                continue
            methods.append(class_records.method_entry(
                method['selector'], made['code'],
                lead + (method['code_offset'] or 0),
                method.get('flags', 0)))
        references, copies = class_records.reference_masks(klass['fields'])
        payload = class_records.class_record(
            klass['number'], where['record'], field_list,
            klass['instance_size'], klass['fields'], klass['parents'],
            klass['parent_numbers'], methods, klass['interfaces'],
            klass['derived'])
        generated.append({'id': where['record'], 'class': 'Class',
                          'payload': payload, 'flags': 0x0100,
                          'tag_low': NAMED_TAG})
        class_entries.append({
            'record': where['record'], 'own_bytes': klass['own_bytes'],
            'instance_size': klass['instance_size'], 'mixin': klass['mixin'],
            'inherits_from': (klass['parent_numbers'][0]
                              if len(klass['parent_numbers']) == 1 else 0),
            'name_hash': klass['name_hash'],
            'inherited_bytes': klass['inherited_bytes']})

    generated.append({'id': made['classes'], 'class': 'ClassList',
                      'payload': class_records.class_list(class_entries)})

    entries, highest = [], 0x8000
    for operation in described['operations']:
        record = made['magic_operations'][operation['number']]
        generated.append({
            'id': record, 'class': 'MagicOperation', 'tag_low': NAMED_TAG,
            'flags': 0x0100,
            'payload': class_records.magic_operation(
                operation['number'], operation.get('flags', 0),
                operation.get('signature') or [{}])})
        entries.append({'number': operation['number'], 'record': record,
                        'kind': operation.get('kind', 0),
                        'name_hash': operation['name_hash'],
                        'flags': operation.get('entry_flags', 0)})
        highest = max(highest, operation['number'])
    generated.append({'id': made['operations'], 'class': 'OperationList',
                      'payload': class_records.operation_list(entries,
                                                              highest)})
    if 'direct_dispatch' in made:
        generated.append({
            'id': made['direct_dispatch'], 'class': 'DirectDispatchList',
            'payload': class_records.direct_dispatch_list(
                described['direct_dispatch'])})

    for intrinsic in described.get('intrinsics', []):
        record = made['intrinsic_operations'][intrinsic['number']]
        generated.append({
            'id': record, 'class': 'MagicOperation', 'tag_low': NAMED_TAG,
            'flags': 0x0100,
            'payload': class_records.magic_operation(
                intrinsic['number'], intrinsic.get('flags', 0),
                intrinsic.get('signature') or [{}])})

    # ObjectMaker calls the Code object `Headers`, in every package that
    # has one, and names it the way it names the root list.
    named = [(CODE_NAME, made['code'])]
    named += [(name, made['class_records'][name]['record'])
              for name in described['classes']]
    named += [(operation['name'],
               made['magic_operations'][operation['number']])
              for operation in described['operations']]
    named += [(intrinsic['name'],
               made['intrinsic_operations'][intrinsic['number']])
              for intrinsic in described.get('intrinsics', [])]
    return generated, field_names, named


def synthesise(definitions, tables, spec, instances, numbers, made,
               described=None, blob=b''):
    """The objects a definition file does not declare, and the wiring.

    Ids are not handed out here -- `assign_ids` has already decided them --
    so this only says what each of those objects contains.
    """
    spec = [dict(entry) for entry in spec]
    package = next(e for e in spec if e['class'] == 'SoftwarePackage')

    # Every instance, at the slot its own number names.
    highest = max(numbers)
    generated = [{'id': made['root'], 'class': 'ObjectList',
                  'values': {'length': highest},
                  'elements': [reference(numbers[n]) if n in numbers else 0
                               for n in range(1, highest + 1)]}]

    described = described or {'classes': {}, 'operations': [],
                              'intrinsics': [], 'direct_dispatch': []}
    records, field_names, class_names = code_objects(
        definitions, tables, made, described, blob)
    if records:
        generated += records
    else:
        # A package with no code still carries all three, empty. The class
        # list's header is a count twice, a zero and 0x8000; the other two
        # are a count and a word.
        generated += [
            {'id': made['classes'], 'class': 'ClassList',
             'payload': struct.pack('>IIII', 0, 0, 0, 0x8000)},
            {'id': made['operations'], 'class': 'OperationList',
             'payload': struct.pack('>II', 0, 0)},
        ]
    # The load list brings in the direct dispatch list where there is one,
    # and the intrinsics either way.
    load = ([reference(made['direct_dispatch'])]
            if 'direct_dispatch' in made else []) \
        + [reference(made['intrinsics'])]
    intrinsic_entries = described.get('intrinsics', [])
    intrinsic_payload = struct.pack('>II', len(intrinsic_entries) * 2, 0)
    for intrinsic in intrinsic_entries:
        intrinsic_payload += struct.pack(
            '>II', intrinsic['intrinsic_number'],
            reference(made['intrinsic_operations'][intrinsic['number']]))
    for intrinsic in intrinsic_entries:
        intrinsic_payload += struct.pack(
            '>II', reference(made['code'],),
            8 + (intrinsic['method_offset'] or 0))

    generated += [
        {'id': made['intrinsics'], 'class': 'IntrinsicList',
         'payload': intrinsic_payload, 'flags': 0x0100},
        {'id': made['load'], 'class': 'ObjectList',
         'values': {'length': len(load)}, 'elements': load},
    ]

    # The named objects, in id order -- which is the order the table is in,
    # not the order the file declares them. The root list is named too, and
    # its name is not in any definition file: ObjectMaker calls it the
    # reference numbers list, which is what it is.
    named = [(inst['name'], numbers[inst['number']])
             for inst in instances if inst['name']]
    named.append((ROOT_LIST_NAME, made['root']))
    # A class and an operation are named too, and their records carry the
    # name bit; Counter's table has CounterScene and its four operations
    # after the instances.
    named += class_names
    named.sort(key=lambda pair: pair[1])

    generated += [
        {'id': made['strings'], 'class': 'StringList',
         'payload': encode_string_table(definitions, [n for n, _ in named])},
        {'id': made['field_names'], 'class': 'StringList',
         'payload': encode_string_table(definitions, field_names)},
        {'id': made['dictionary'], 'class': 'StringDictionary',
         'values': {'length': len(named), 'strings': made['strings'],
                    'firstStringEntry': 1},
         'elements': [object_id for _, object_id in named]},
        {'id': made['boot'], 'class': 'PackageBoot', 'values': {
            'globalsSize': 0,
            'classList': reference(made['classes']),
            'operationList': reference(made['operations']),
            'intrinsicList': reference(made['intrinsics']),
            'directDispatchList': (reference(made['direct_dispatch'])
                                   if 'direct_dispatch' in made else 0),
            'package': reference(package['id']),
            'loadList': reference(made['load']),
            'clusterCRC': 0,      # filled in once the records are laid out
        }},
    ]

    # A named object says so in its own record: bit 1 of the tag, which is
    # the bit ObjectMaker sets when it is given a name. The nine objects
    # Template marks that way are exactly the nine in its name table.
    carries_name = {object_id for _, object_id in named}
    for entry in spec + generated:
        if entry['id'] in carries_name:
            entry['tag_low'] = NAMED_TAG

    elements = package.setdefault('elements', [])
    while len(elements) < ROOT_LIST_ELEMENT:
        elements.append(0)
    elements[ROOT_LIST_ELEMENT - 1] = reference(made['root'])
    package['values']['length'] = max(package['values'].get('length', 0),
                                      len(elements))

    # The three code lists come first in the heap and the boot record last,
    # which is the shape every cookbook package has.
    head = [e for e in generated if e['id'] in
            (made['classes'], made['operations'], made['intrinsics'])
            and 'payload' in e and len(e.get('payload', b'')) <= 16]
    tail = [e for e in generated if e not in head]
    return head + [package] + [e for e in spec if e is not package] + tail


def to_objects(definitions, tables, spec):
    objects = []
    for entry in spec:
        if 'payload' in entry:
            number = entry.get('class_number') or next(
                n for n, name in tables['class'].items()
                if name == entry['class'])
            from write_package import Object
            objects.append(Object(entry['id'], number, entry['payload'],
                                  tag_low=entry.get('tag_low', 0x88),
                                  flags=entry.get('flags', 0)))
            continue
        objects.append(make_object(
            definitions, tables, entry['id'], entry['class'],
            values=entry.get('values'), elements=entry.get('elements'),
            extra=entry.get('bytes', b''), stride=entry.get('stride', 4),
            length=entry.get('length'), tag_low=entry.get('tag_low', 0x88),
            flags=entry.get('flags', 0)))
    return objects


def unplaced_fields(spec):
    """Values a definition file states that no layout can place.

    A class the SDK's definition files do not describe -- ContentListView is
    one -- has fields this cannot find an offset for, and a record built from
    it comes out short. That is worth saying rather than discovering later
    from a byte count.
    """
    return {entry['id']: entry['unplaced'] for entry in spec
            if entry.get('unplaced')}


def build_example(directory, definitions=None, tables=None, names=None,
                  report=False, sources=None, compile_code=True,
                  interfaces=SDK_INTERFACES, compiler='clang'):
    interfaces = Path(interfaces)
    definitions = definitions or Definitions(interfaces / 'DefFiles',
                                             interfaces)
    tables = tables or load_numbers(interfaces)
    system = set(tables.get('operation', {}).values()) \
        | set(tables.get('attribute', {}).values())
    if names is None:
        names = read_indexicals(read(interfaces / 'Indexicals.h'))
        # A definition file can write an operation's number by name, which is
        # how a card says which operation a key stands for.
        for kind in ('operation', 'attribute'):
            names.update({f'operation_{n}': number
                          for number, n in tables.get(kind, {}).items()})

    # A handful of classes the examples use are declared with no fields in
    # the SDK that shipped, and what they hold was recovered from the
    # packages instead. See recovered.Def, which says for each one what the
    # bytes were that fixed it.
    recovered = Path(__file__).with_name('recovered.Def')
    if recovered.is_file():
        definitions.add(recovered, override=True)

    # An example's own classes are declared in the same syntax the SDK uses,
    # so they are read the same way. Instance files carry no class blocks, so
    # handing over every definition file in the directory costs nothing.
    directory = Path(directory)
    for path in sorted(directory.glob('*.Def')):
        definitions.add(path)

    # A package's own classes have numbers of their own, from 0x8001, and
    # `make_object` looks a class up by name in the same table the SDK's are
    # in -- so they are added to a copy of it rather than handled apart.
    classes = package_class_numbers([read(directory / f)
                                     for f in project_order(directory)])
    if classes:
        tables = {**tables,
                  'class': {**tables['class'],
                            **{number: name
                               for name, number in classes.items()}}}

    # A package's own operations are written by name too -- Hanoi's reset
    # button says `operation: operation_ResetGame;` -- and those names exist
    # nowhere but the example, so they are numbered here and added on top of
    # the system's. Its own numbers win where a name is in both.
    order = project_order(directory)
    if order:
        names.update(package_numbers([read(directory / f) for f in order],
                                     system))

    instances = []
    for filename in sources or instance_sources(directory, order) \
            or ('Objects.Def',):
        instances += parse(read(directory / filename))

    # A package that declares classes of its own needs a Code object, so its
    # C is compiled and linked before anything else: the method tables want
    # to know where each procedure ended up.
    described, blob = None, b''
    if classes and compile_code:
        from compile_example import code as compile_example_code
        from package_classes import describe
        blob, relocations, procedures = compile_example_code(
            directory, interfaces=interfaces, compiler=compiler)
        if relocations:
            raise RuntimeError(f'{directory.name}: {relocations} references '
                               'the link did not resolve')
        described = describe(directory, definitions, tables,
                             procedures=procedures, order=order)

    numbers, made, free = assign_ids(instances, described)
    spec = to_spec(definitions, instances, numbers=numbers,
                   names=names)
    spec = synthesise(definitions, tables, spec, instances, numbers, made,
                      described, blob)
    boot_id = made['boot']

    objects = to_objects(definitions, tables, spec)
    # The checksum is over the records as they will be written, so it is
    # worked out once they exist and then put back.
    checksum = cluster_checksum(objects, boot_id)
    for entry in spec:
        if entry['id'] == boot_id:
            entry['values']['clusterCRC'] = checksum
    objects = to_objects(definitions, tables, spec)
    package = build(objects, constant_words=CLUSTER_CONSTANTS, free_ids=free)
    return (package, unplaced_fields(spec)) if report else package


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('example', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    # An example built from several definition files must be given them in
    # the order its project lists them, because that is the order the object
    # numbering follows. `strings -a` on the project's .µ shows it: the
    # second listing of the .Def names is the build order.
    parser.add_argument('-d', '--define', action='append', metavar='FILE',
                        help='a definition file, in project order '
                             '(default: Objects.Def)')
    parser.add_argument('--profile', default='1.0-original',
                        help='68k interface profile: 1.0-original, 1.0, 1.5, '
                             'universal, or an interface directory')
    args = parser.parse_args(argv)
    try:
        interfaces = resolve(args.profile)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    package, missing = build_example(args.example, report=True,
                                     sources=args.define,
                                     interfaces=interfaces)
    for object_id, fields in sorted(missing.items()):
        print(f'object {object_id}: no layout for {", ".join(fields)}',
              file=sys.stderr)
    out = args.output or Path(f'{args.example.name}.pkg')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(package)
    print(f'{out}: {len(package)} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
