#!/usr/bin/env python3
"""Read ObjectMaker's `Objects.Def` and say what objects it declares.

This is the front end: the part that decides what goes in a package, rather
than how it is written down. `write_package.py` takes a list of objects and
emits a cluster; this turns a definition file into that list.

The syntax is small. An instance names its class, optionally a name, and a
number the file uses to refer to it:

    Instance Citation 10;
        title: (Identifier 'Template' 12);
       author: (Telename 2);
    minorEdition: 0;
    End Instance;

The numbers are the file's own, not the package's: ObjectMaker renumbers as
it writes, and so does this, so `(Telename 2)` is resolved through the
declarations rather than written out as 2.

Two field names are not fields. `data` and `extra` are the variable part that
follows a class's fields -- text for a Text, bytes for an OctetString -- and
`entryN` on a package is element N of the list it is.
"""
from pathlib import Path
import re

# A name may carry an escaped quote of its own -- Circuits declares
# `Instance BookPage 'What\\'s A Circuit?' 176;` -- so the name is matched the
# way a quoted value is. Reading it as "anything but a quote" skipped the
# declaration silently, and the only sign of it was a later reference to an
# instance that looked undeclared.
INSTANCE = re.compile(
    r"^\s*Instance\s+(\w+)\s*(?:'((?:[^'\\]|\\.)*)')?\s*(\d+)\s*;", re.M)
END = re.compile(r"^\s*End\s+Instance\s*;", re.M)
ENTRY = re.compile(r'^entry(\d+)$')

# The name in a reference is quoted and may contain an escaped quote of its
# own -- Circuits refers to a page called 'What\'s A Circuit?' -- so the
# quoted part is matched the same way a string value is rather than as
# "anything but a quote".
REFERENCE = re.compile(
    r"^\(\s*(\w+)\s*(?:'(?:[^'\\]|\\.)*')?\s*(\d+)\s*\)$", re.S)
HEX_PIECES = re.compile(r'\$\s*([0-9A-Fa-f][0-9A-Fa-f\s]*)')
QUOTED_PIECES = re.compile(r"'((?:[^'\\]|\\.)*)'", re.S)
SIZED = re.compile(r'^(-?\d+)\.[bwls]$')
POINT = re.compile(r'^<\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*>$')
# Four in brackets is a Box -- left, top, right and bottom -- which the SDK's
# own types say is sixteen bytes to a Dot's eight, so it is four coordinates
# scaled the same way rather than two Dots of something else. The corpus has
# it only as `stepTargetBox`, six times.
BOX = re.compile(r'^<\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,'
                 r'\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*>$')
# One number in angle brackets is a single coordinate -- a scroll amount, an
# offset from an edge -- scaled the way a Dot's halves are.
COORDINATE = re.compile(r'^<\s*(-?[\d.]+)\s*>$')
# Two plain numbers are a PixelDot: whole pixels, sixteen bits each, which is
# how an Image writes its size and its centre.
PIXEL_DOT = re.compile(r'^(-?\d+)\s*,\s*(-?\d+)$')
# An indexical written out: {list,entry} is MakeIndexical, so `{60,1}` is
# 0x83078001, which is what Template's NameCard carries for its label style.
# {{n}} is the PACKAGE indexical MakePackageIndexical(n, 0) -- entry n of the
# package's own list -- not MakeFlatIndexical, which Generic.h also defines
# and which nothing in the corpus uses: all eight `{{n}}` in the cookbook
# sources come out with bit 23 set, and the flat form appears nowhere.
BRACED = re.compile(r'^\{\s*(\d+)\s*,\s*(\d+)\s*\}$')
BRACED_FLAT = re.compile(r'^\{\{\s*(\d+)\s*\}\}$')

# A Dot is two thirty-two bit numbers with eight fractional bits, packed into
# the eight bytes of the field. Template's Scene says its content is
# <480.0,256.0> and carries 0x0001E000 0x00010000, which is those two times
# 256; its origin is <0.0,-8.0> and carries 0 and -2048.
DOT_SCALE = 256
# A Fixed keeps sixteen fractional bits rather than a coordinate's eight:
# Snake's rattle says `sampleRate: 22254.54546` and carries 0x56EE8BA3, which
# is 22254 and 35747/65536. So the brackets are what say which -- <15.0> is a
# coordinate and 3840, a bare 22254.54546 is a Fixed.
FIXED_SCALE = 65536


def dot(horizontal, vertical):
    """A written point as the doubleword a Dot field holds."""
    def part(number):
        return int(round(number * DOT_SCALE)) & 0xFFFFFFFF
    return (part(horizontal) << 32) | part(vertical)


# Generic.h: MakeIndexical(list, entry) is four flag bits, the list shifted
# up thirteen, and the entry. The flags come to 0x83000000, which is what
# iHallway -- MakeIndexical(40, 7) -- reads as in a package: 0x83050007.
# MakePackageIndexical adds one more bit on top. Its position is not in any
# shipped header -- the kIDBit constants are not there -- but
# IndexicalListNumber masks with (1<<kIDBitPackageIndexical)-1 and shifts by
# 13, which puts it above the list field, and bit 23 is the bit the packages
# actually carry.
INDEXICAL_FLAGS = 0x83000000
PACKAGE_INDEXICAL_FLAG = 1 << 23
MAKE_INDEXICAL = re.compile(
    r'#\s*define\s+(\w+)\s+MakeIndexical\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)')
MAKE_FLAT = re.compile(
    r'#\s*define\s+(\w+)\s+MakeFlatIndexical\s*\(\s*(\d+)\s*\)')


def make_indexical(list_number, entry, package=False):
    word = INDEXICAL_FLAGS | (list_number << 13) | entry
    return word | PACKAGE_INDEXICAL_FLAG if package else word


def read_indexicals(text):
    """Every indexical the SDK's header names, as the word it stands for."""
    text = text.replace('\r', '\n')
    out = {}
    for match in MAKE_INDEXICAL.finditer(text):
        out[match.group(1)] = make_indexical(int(match.group(2)),
                                             int(match.group(3)))
    for match in MAKE_FLAT.finditer(text):
        out[match.group(1)] = make_indexical(int(match.group(2)), 0)
    return out


#: An example's project file lists its definition files twice: once as the
#: files it contains and once, after, as the order it builds them in. The
#: second listing is the one that matters, because it is the order the object
#: numbering and the operation numbering both follow.
PROJECT_DEF = re.compile(r'[A-Za-z0-9 ]+\.Def')
INSTANCE_DECLARATION = re.compile(r'^[ \t]*Instance[ \t]', re.M)


def project_order(directory, built_only=False):
    """An example's definition files, in the order its project builds them.

    The `.\u00b5` is a CodeWarrior project and is not parsed; the file names in
    it are found as text. They appear several times over -- once as the files
    the project contains and again in each listing that follows -- and it is
    the LAST of those listings that gives the build order. It is found by
    walking the names backwards and stopping at the first repeat, which is
    where that listing began.

    A file the earlier listings name but the last one does not is a file the
    project refers to without building: Spreadsheet's `BarChartPublic.Def`
    is BarChart's declarations copied in so that Spreadsheet can talk to a
    bar chart, and its six classes are numbered after Spreadsheet's own five
    but none of them is written into Spreadsheet's package. So those files
    come after, in the order they were first named.

    This is checked against the packages rather than against a reading of
    the project format: with it, every class's and every operation's name
    hash in all nine cookbook packages that define any comes out right.
    Circuits is the one example whose project omits a file it builds --
    `BookTemplate.Def` -- so what comes back is what the project names, not
    everything in the directory.
    """
    directory = Path(directory)
    projects = sorted(directory.glob('*.\u00b5'))
    if not projects:
        return []
    listed = [name for name in PROJECT_DEF.findall(
        projects[0].read_bytes().decode('mac-roman'))
        if (directory / name).is_file()]
    # A file the project builds is named in every listing; one it only refers
    # to is named once. That count is what separates them, and it is steadier
    # than trying to find where one listing ends and the next begins.
    times = {name: listed.count(name) for name in listed}
    built = [name for name in listed if times[name] > 1]
    last = []
    for name in reversed(built or listed):
        if name in last:
            break
        last.insert(0, name)
    for name in listed:
        if name not in last:
            last.append(name)
    # A file the project only refers to is numbered along with the rest but
    # nothing in it is written into the package: Spreadsheet's copy of
    # BarChart's declarations gives its six classes numbers 6 to 11 and
    # Spreadsheet's package carries a record for none of them.
    return [name for name in last if times.get(name, 0) > 1] \
        if built_only else last


def instance_sources(directory, order=None):
    """Just the definition files that declare instances, in that order.

    A file with no `Instance` in it is a class definition and is read for its
    classes rather than parsed for objects, so handing it to `parse` would
    only produce nothing slowly.
    """
    directory = Path(directory)
    order = order if order is not None else project_order(directory)
    # These files are Macintosh text: the lines end in a carriage return, so
    # a line-anchored search finds nothing until they are turned into the
    # newlines the rest of this module already reads them as.
    return [name for name in order
            if INSTANCE_DECLARATION.search(
                (directory / name).read_bytes()
                .decode('mac-roman').replace('\r', '\n'))]


class DefinitionError(ValueError):
    pass


def strip_comments(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)


def assignments(body):
    """`name: value;` pairs, where a ';' inside a string is not the end.

    Snake's help text says "and walk around; sometimes it will sleep", and a
    regular expression that stops at the first semicolon truncates it there
    and silently writes a shorter string than the file asked for. So the
    value is scanned with the quoting taken into account.
    """
    out, at = [], 0
    while at < len(body):
        colon = body.find(':', at)
        if colon < 0:
            break
        name = body[at:colon].strip()
        if not name.isidentifier():
            at = colon + 1
            continue
        at, quoted, start = colon + 1, False, colon + 1
        while at < len(body):
            char = body[at]
            if char == '\\' and quoted:
                at += 2
                continue
            if char == "'":
                quoted = not quoted
            elif char == ';' and not quoted:
                break
            at += 1
        out.append((name, body[start:at].strip()))
        at += 1
    return out


def parse(text):
    """Every instance the file declares, in the order it declares them."""
    text = strip_comments(text.replace('\r', '\n'))
    instances = []
    for match in INSTANCE.finditer(text):
        end = END.search(text, match.end())
        body = text[match.end():end.start()] if end else ''
        fields = [(name, ' '.join(written.split()))
                  for name, written in assignments(body)]
        instances.append({'class': match.group(1), 'name': match.group(2),
                          'number': int(match.group(3)), 'fields': fields})
    return instances


def resolve(value, numbers, names=None):
    """One written value as the number that goes in the record.

    References become the object id the referenced instance was given, which
    is why they cannot be read without the whole file: `(Telename 2)` is the
    instance numbered 2, and what id that ends up with is this module's
    business rather than the definition file's.
    """
    if value in ('nilObject', 'nil'):
        return 0
    if value == 'true':
        return True
    if value == 'false':
        return False
    reference = REFERENCE.match(value)
    if reference:
        target = int(reference.group(2))
        if target not in numbers:
            raise DefinitionError(f'reference to undeclared instance {target}')
        return 0xB0000000 | numbers[target]
    braced = BRACED.match(value)
    if braced:
        return make_indexical(int(braced.group(1)), int(braced.group(2)))
    flat = BRACED_FLAT.match(value)
    if flat:
        return make_indexical(int(flat.group(1)), 0, package=True)
    box = BOX.match(value)
    if box:
        whole = 0
        for edge in box.groups():
            whole = (whole << 32) \
                | (int(round(float(edge) * DOT_SCALE)) & 0xFFFFFFFF)
        return whole
    point = POINT.match(value)
    if point:
        return dot(float(point.group(1)), float(point.group(2)))
    coordinate = COORDINATE.match(value)
    if coordinate:
        return int(round(float(coordinate.group(1)) * DOT_SCALE))
    pixels = PIXEL_DOT.match(value)
    if pixels:
        return ((int(pixels.group(1)) & 0xFFFF) << 16) \
            | (int(pixels.group(2)) & 0xFFFF)
    sized = SIZED.match(value)
    if sized:
        return int(sized.group(1))
    # A Fixed can be written without its brackets -- Spreadsheet's cells say
    # `cellValue: 0.0` -- and is scaled the same way either way.
    if re.fullmatch(r'-?\d+\.\d+', value):
        return int(round(float(value) * FIXED_SCALE)) & 0xFFFFFFFF
    if re.fullmatch(r'-?\d+', value):
        return int(value)
    # A word can be written as hex with the digits grouped, `$ 0000 0040`;
    # longer runs than a word are content rather than a value, and are read
    # by `content_of` instead.
    hexadecimal = re.fullmatch(r'\$\s*([0-9A-Fa-f][0-9A-Fa-f\s]*)', value)
    if hexadecimal:
        digits = re.sub(r'\s+', '', hexadecimal.group(1))
        if len(digits) <= 8:
            return int(digits, 16)
    if re.fullmatch(r'0[xX][0-9A-Fa-f]+', value):
        return int(value, 16)
    if names and value in names:
        return names[value]
    raise DefinitionError(f'cannot read the value {value!r}')


ESCAPES = {'n': '\n', 'r': '\r', 't': '\t', '0': '\0',
           "'": "'", '\\': '\\'}


def unescape(text):
    out, index = [], 0
    while index < len(text):
        char = text[index]
        if char == '\\' and index + 1 < len(text):
            following = text[index + 1]
            out.append(ESCAPES.get(following, following))
            index += 2
            continue
        out.append(char)
        index += 1
    return ''.join(out)


def content_of(value):
    """The bytes a `data` or `extra` assignment stands for.

    A long string is written as several quoted pieces with a backslash
    between them, and carries the usual escapes, so the pieces are joined
    rather than one of them taken.
    """
    quoted = QUOTED_PIECES.findall(value)
    if quoted:
        return unescape(''.join(quoted)).encode('mac-roman')
    # Hex runs long, so a file writes it as several `$ ...` pieces with a
    # backslash between them, the same way it breaks a long string.
    pieces = HEX_PIECES.findall(value)
    if pieces and not HEX_PIECES.sub('', value).strip(' \\'):
        return bytes.fromhex(re.sub(r'\s+', '', ''.join(pieces)))
    raise DefinitionError(f'cannot read the content {value!r}')


def references_of(instance):
    """The instances this one names, in the order it writes them.

    Both a field and a list's `entry` lines count, and they are taken in
    file order rather than in the class's field order, because that is the
    order the numbering below turns out to follow.
    """
    out = []
    for _, written in instance['fields']:
        match = REFERENCE.match(written)
        if match:
            out.append(int(match.group(2)))
    return out


def number(instances):
    """The object ids ObjectMaker gives a definition file's instances.

    Ids are not the numbers the file uses and not declaration order. An
    instance is numbered when it is first *referred to*: the declarations are
    walked in order, and each one's references are given the next id each in
    turn, the first time they are seen. So Template's package is walked
    first, and its `author`, `installList`, `receivers`, `citation` and its
    three list entries become ids 1 to 7; then Citation is walked and its
    title and author become 8 and 9; and so on to 19.

    This reproduces every id in thirteen of the fourteen cookbook packages
    exactly -- 19 in Template, 146 in Whitehouse, 127 in BizNote -- where the
    examples built from several definition files are concatenated in the
    order their project file lists them. The fourteenth, Circuits, agrees for
    110 ids and then slips, and it is the one example with a definition file
    that is not in that list.

    A package is not returned here: nothing refers to the SoftwarePackage, so
    it is never numbered by the walk. It takes its id from the root list,
    which is the first thing built afterwards and which refers to it.
    """
    declared = {instance['number'] for instance in instances}
    ids, next_id = {}, 1
    for instance in instances:
        for target in references_of(instance):
            if target in declared and target not in ids:
                ids[target] = next_id
                next_id += 1
    return ids


def resolve_element(written, numbers, names=None):
    """One list element, which may be wider than a word.

    A `DataList` says how wide its elements are -- Snake's behaviour speeds
    declare `stride: 8` -- and writes each as hex. Anywhere else that much
    hex would be content, so the wide form is read here rather than in
    `resolve`, where a long run means an OctetString's bytes.
    """
    try:
        return resolve(written, numbers, names)
    except DefinitionError:
        digits = HEX_PIECES.findall(written)
        if digits and not HEX_PIECES.sub('', written).strip(' \\'):
            return int(re.sub(r'\s+', '', ''.join(digits)), 16)
        raise


def to_spec(definitions, instances, numbers=None, names=None):
    """The instances as entries `write_package.build_from_spec` accepts.

    Ids are assigned in declaration order unless a mapping is given. Nothing
    here invents an object: a package needs several that no definition file
    mentions -- its class and operation lists, its name tables -- and those
    are the caller's to add.
    """
    numbers = numbers or {inst['number']: index + 1
                          for index, inst in enumerate(instances)}
    spec = []
    for instance in instances:
        values, elements, content = {}, {}, b''
        try:
            declared = {f['name'] for f in
                        definitions.layout(instance['class'])['fields']}
        except Exception:
            declared = set()
        appended = 0
        for name, written in instance['fields']:
            # A list writes its contents as repeated `entry:` lines, taken in
            # order; a package numbers them, `entry6:` being its sixth.
            if name == 'entry':
                appended += 1
                elements[appended] = resolve_element(written, numbers, names)
                continue
            entry = ENTRY.match(name)
            if entry:
                elements[int(entry.group(1))] = resolve_element(
                    written, numbers, names)
                continue
            # A name the class does not declare is its variable part --
            # `data` on an OctetString, `text` on a Text -- but the layouts
            # here do not carry every field a definition file assigns, so
            # what the value looks like decides rather than the name alone.
            if name in declared:
                values[name] = resolve(written, numbers, names)
                continue
            try:
                values[name] = resolve(written, numbers, names)
            except DefinitionError:
                content = content_of(written)
        # Telecard's variable data begins with a one-byte format-header
        # value. The shipped 68k definitions omit this private prefix from
        # the class layout, but ObjectMaker places it immediately before the
        # data1 bytes. Keeping it with the variable payload preserves the
        # object length and the offsets of the text that follows it.
        if (instance['class'] == 'Telecard' and 'header1' in values
                and content):
            header = values.pop('header1')
            if not 0 <= header <= 0xFF:
                raise DefinitionError(f'Telecard header1 is not a byte: {header}')
            content = bytes([header]) + content
        # A value the class's layout does not account for would be written
        # nowhere at all, and a record that is quietly short is worse than
        # one that says what it could not place -- so it is recorded.
        unplaced = sorted(set(values) - declared) if declared else []
        item = {'id': numbers[instance['number']], 'class': instance['class'],
                'values': values}
        if unplaced:
            item['unplaced'] = unplaced
        if elements:
            highest = values.get('length') or max(elements)
            item['elements'] = [elements.get(i, 0)
                                for i in range(1, int(highest) + 1)]
            # A list that says how wide its elements are means it.
            if values.get('stride'):
                item['stride'] = int(values['stride'])
        elif content:
            item['bytes'] = content
        spec.append(item)
    return spec
