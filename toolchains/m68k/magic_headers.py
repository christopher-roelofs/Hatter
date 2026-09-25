#!/usr/bin/env python3
"""The SDK's headers, rewritten into something a compiler here will take.

`Device/Universal/NoDebug/Operations.h` declares the system's operations
twelve and a half thousand times over like this:

    void ResetVisitCount(ObjectID self)={0x343C,0x8001,0x4EAD,0xFFFA};

That is not a function. It is four instruction words for MPW C to paste at
the call site, with the arguments already pushed, and it is the one thing
between an example's `.c` and a `Code` object: everything else in the SDK's
headers compiles under `clang-18` unchanged, and the only error it reports
is "illegal initializer" on these.

So each one is rewritten as a `static inline` function that pushes the
arguments itself and then emits the same four words. Nothing is invented:
the words come from the declaration, and the convention around them was read
off the cookbook's own compiled code rather than assumed.

    ARGUMENTS ARE PUSHED RIGHT TO LEFT, EACH AS A FOUR-BYTE LONG.
    BizNote calls `AutoFile(card, false, true)` as `pea 1`, `clr.l -(a7)`,
    then the two objects -- so a Boolean takes a whole long like everything
    else.

    THE CALLER POPS THEM. Counter's `UpdateDisplay` calls `VisitCount(self)`
    and the next word is `584f`, `addq.w #4,a7`; BizNote pops sixteen and
    more with `lea d(a7),a7`. Its `ResetVisitCount` looks at first as though
    the callee cleans, because it pushes twice, calls twice and leaves the
    whole frame to `unlk` -- which inline asm cannot do, since clang does not
    know what was pushed.

    A CLASS NUMBER GOES IN D0. That is what `#pragma parameter F(__D0)`
    says, and it is on the inherited and delegate forms.

Three of the words cannot be written as mnemonics because LLVM's m68k
assembler does not parse `jsr -6(%a5)`, `jsr (-6,%a5)`, or `%sp` and `%a7`
in `addq.l`. They go in as `.short`, which it assembles without complaint --
and `.short` is what the declaration states anyway.

    python3 magic_headers.py <header> -o <header>     one file
    python3 magic_headers.py --all -o <directory>     the SDK's, normalised
"""
import argparse
from pathlib import Path
import re
import sys

from inspect_package import SDK_INTERFACES

#: Where the declarations this rewrites live. The device's non-debug build is
#: the one a package is compiled against.
OPERATIONS = SDK_INTERFACES / 'Device/Universal/NoDebug/Operations.h'

#: `RET NAME(ARGS)={W,W,W,W};`, once comments are out of the way. These
#: files are Macintosh text and several declarations often share one line,
#: so a declaration is anchored to whatever ended the one before it rather
#: than to the start of a line; anchoring to the line start finds only the
#: first of each run. Some carry no selector word at all --
#: `void EndRead(ObjectID self)={0x4EAD,0xFF9C};` is a slot of its own -- so
#: the number of words is not fixed either.
DECLARATION = re.compile(
    r'(?:^|(?<=\})|(?<=;))[ \t]*'
    r'([A-Za-z_][\w \t]*?[\w])[ \t]*((?:\*[ \t]*)*)(\w+)[ \t]*'
    r'\(([^;()\n]*)\)[ \t]*=[ \t]*'
    r'(?:\{[ \t]*([0-9A-Fa-fx,\t ]*?)[ \t]*\}|(0[xX][0-9A-Fa-f]+))[ \t]*;',
    re.M)
PARAMETER_PRAGMA = re.compile(r'^#\s*pragma\s+parameter\s+(\w+)\s*\('
                              r'\s*__D0\s*\)', re.M)
COMMENT = re.compile(r'/\*.*?\*/', re.S)

#: A struct passed by value cannot be cast to a long -- `PixelDot` is two
#: shorts -- so it is pushed as the four bytes it occupies instead. Which
#: names are structs is read out of the headers rather than listed here,
#: following `typedef OLD NEW;` chains, because `TextPoint` is an
#: `ArrayPoint` is a struct.
STRUCT_TYPEDEF = re.compile(
    r'\}\s*(\w+)\s*;|typedef\s+struct\s+\w+\s+(\w+)\s*;')
ALIAS_TYPEDEF = re.compile(r'^typedef\s+([A-Za-z_]\w*)\s+(\w+)\s*;', re.M)


def struct_types(texts):
    """Every typedef name that ends up naming a struct."""
    structs, aliases = set(), {}
    for text in texts:
        text = COMMENT.sub(' ', text)
        for ended, named in STRUCT_TYPEDEF.findall(text):
            structs.add(ended or named)
        for old, new in ALIAS_TYPEDEF.findall(text):
            aliases.setdefault(new, old)
    changed = True
    while changed:
        changed = False
        for new, old in aliases.items():
            if old in structs and new not in structs:
                structs.add(new)
                changed = True
    structs.discard('')
    return structs

#: A few opcodes have to be spelled as words. `addq` takes 1..8, so anything
#: larger pops with `lea`.
ADDQ_W_A7 = {4: 0x584F, 8: 0x504F}
LEA_D_A7 = 0x4FEF


def pop(count):
    """The words that take `count` bytes back off the stack.

    Every argument is a long, so the count is always a multiple of four:
    one `addq` for four or eight bytes, and `lea` past that, which is what
    BizNote does when it takes sixteen and twenty-four back.
    """
    if not count:
        return []
    if count in ADDQ_W_A7:
        return [ADDQ_W_A7[count]]
    return [LEA_D_A7, count]


def arguments(text):
    """The declared parameters, as (type, name).

    MPW writes them the way C does once the definition files have been
    through the generator, so this is an ordinary parameter list; `void` and
    an empty list both mean none.
    """
    text = COMMENT.sub(' ', text).strip()
    if not text or text == 'void':
        return []
    out = []
    for piece in text.split(','):
        piece = piece.strip()
        if not piece:
            continue
        words = piece.replace('*', '* ').split()
        out.append((' '.join(words[:-1]), words[-1]))
    return out


def short(words):
    return '.short ' + ','.join(f'{w:#06x}' for w in words)


def push(type_name, argument, structs):
    """One argument as the long that goes on the stack.

    Everything is pushed as a four-byte long, whatever it is: BizNote calls
    `AutoFile(card, false, true)` with `pea 1` and `clr.l -(a7)`, so a
    Boolean takes a whole long. A scalar is cast, which promotes it; a
    struct cannot be cast and is read as the four bytes it occupies.
    """
    bare = type_name.replace('const', '').strip()
    if '*' not in bare and bare in structs:
        return f'(*(const unsigned long *)&({argument}))'
    return f'(unsigned long)({argument})'


#: Past this many stack arguments, they go through an array rather than
#: through registers. Each `"r"` operand has to be live at once, and with
#: D0, D1, D2, A0 and A1 already spoken for, clang runs out and says
#: "inline assembly requires more registers than available" -- which is what
#: Hanoi's and Positioning's six-argument calls did.
REGISTER_ARGUMENTS = 3


def rewrite(returns, name, args, words, class_in_d0, structs=frozenset()):
    """One declaration as a function clang will compile.

    The result comes back in D0, which is why the output is a register
    variable pinned there rather than an ordinary `"=d"`: the same register
    carries the class number in on the inherited forms, and tying the two
    together is what keeps clang from putting the class somewhere else.

    A long argument list is gathered into an array first and pushed from
    there through one base register. It cannot be pushed from memory
    operands directly: clang would address them relative to A7, and A7 moves
    with every push.
    """
    stack = args[1:] if class_in_d0 else args
    lines, inputs, before = [], [], []

    if len(stack) > REGISTER_ARGUMENTS:
        values = ', '.join(push(t, n, structs) for t, n in stack)
        before.append(f'    unsigned long _v[{len(stack)}] = {{{values}}};')
        before.append('    register unsigned long *_p = _v;')
        for index in range(len(stack) - 1, -1, -1):
            lines.append(f'"move.l {index * 4}(%[p]),-(%%sp)\\n\\t"')
        # An address register: `12(%d3)` is not an addressing mode, and
        # `"r"` is free to hand back a data one.
        inputs.append('[p] "+a"(_p)')
    else:
        for index, (type_name, argument) in enumerate(reversed(stack)):
            lines.append(f'"move.l %[a{index}],-(%%sp)\\n\\t"')
            value = push(type_name, argument, structs)
            inputs.append(f'[a{index}] "r"({value})')

    body = words + pop(4 * len(stack))
    lines.append(f'"{short(body)}"')

    out = [f'static inline {returns} {name}(' +
           (', '.join(f'{t} {n}' for t, n in args) or 'void') + ')', '{']
    out += before
    outputs = []
    if class_in_d0:
        out.append(f'    register unsigned long _d0 __asm__("d0")'
                   f' = (unsigned long)({args[0][1]});')
        outputs.append('"+r"(_d0)')
    elif returns != 'void':
        out.append('    register unsigned long _d0 __asm__("d0");')
        outputs.append('"=r"(_d0)')
    # The array's base register is written by the asm as far as clang is
    # concerned, so it is an output too; otherwise clang may expect the old
    # value to survive the call.
    pointer = [i for i in inputs if i.startswith('[p] ')]
    inputs = [i for i in inputs if not i.startswith('[p] ')]
    outputs += pointer
    out.append('    __asm__ __volatile__(')
    out += [f'        {line}' for line in lines]
    out.append('        : ' + ', '.join(outputs))
    out.append('        : ' + ', '.join(inputs))
    clobbers = ['"d1"', '"d2"', '"a0"', '"a1"', '"memory"', '"cc"']
    if not class_in_d0 and returns == 'void':
        clobbers.insert(0, '"d0"')
    out.append('        : ' + ', '.join(clobbers) + ');')
    if returns != 'void':
        out.append(f'    return ({returns})_d0;')
    out.append('}')
    return '\n'.join(out)


def convert(text, structs=frozenset()):
    """A header with every inline-code declaration rewritten.

    Everything else is left exactly as it is: the types, the macros and the
    class and field numbers all compile already, and the less of the SDK
    that is restated here the better.
    """
    pragmas = set(PARAMETER_PRAGMA.findall(text))
    # The pragma is CodeWarrior's and clang warns about it; the register it
    # asks for is honoured below instead.
    text = PARAMETER_PRAGMA.sub('', text)
    # Comments go first, because a declaration carries them inside the
    # return type -- `ObjectID /* Object */ Next(...)` -- and leaving them
    # in means matching only the ones that happen not to.
    text = COMMENT.sub(' ', text)
    count = 0
    omitted = []

    def one(match):
        nonlocal count
        base, stars, name, args, braced, single = match.groups()
        words = braced if braced is not None and braced != '' else single
        # A pointer return binds its star to the name -- `uchar *CtoPString`
        # -- so the star is matched separately and put back on the type.
        returns = (COMMENT.sub(' ', base).strip()
                   + ' ' + stars.replace(' ', '')).strip()
        try:
            values = [int(w, 16) for w in words.replace(' ', '').split(',')]
            parsed = arguments(args)
        except (ValueError, AttributeError):
            return match.group(0)
        # A variadic one cannot be given a fixed run of pushes. Thirty-two of
        # the sixteen thousand are, and they are left out rather than
        # approximated, so that calling one fails at the link instead of
        # quietly passing the wrong thing.
        if any(argument == '...' for _, argument in parsed):
            nonlocal omitted
            omitted.append(name)
            return f'\n/* {name}: variadic, not rewritten */\n'
        count += 1
        return '\n' + rewrite(returns, name, parsed, values,
                              name in pragmas, structs) + '\n'

    # Repeated until it settles: a declaration that shared a line with the
    # one before it only becomes anchorable once that one has been replaced.
    while True:
        text, done = DECLARATION.subn(one, text)
        if not done:
            return text, count, omitted


def normalise(path):
    """A Macintosh text file as something a compiler will read."""
    return path.read_bytes().decode('mac-roman') \
        .replace('\r\n', '\n').replace('\r', '\n')


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('header', type=Path, nargs='?')
    parser.add_argument('-o', '--output', type=Path, required=True)
    parser.add_argument('--all', action='store_true',
                        help="the whole of the SDK's interfaces")
    args = parser.parse_args(argv)

    if args.all:
        args.output.mkdir(parents=True, exist_ok=True)
        sources, seen = {}, set()
        for directory in ('.', 'NoDebug', 'Device/Universal/NoDebug'):
            for path in sorted((SDK_INTERFACES / directory).glob('*.h')):
                if path.name not in seen:
                    seen.add(path.name)
                    sources[path.name] = normalise(path)
        structs = struct_types(sources.values())
        total, left_out = 0, []
        for name, text in sources.items():
            rewritten, count, omitted = convert(text, structs)
            (args.output / name).write_text(rewritten)
            total += count
            left_out += omitted
        print(f'{len(sources)} headers, {total} declarations rewritten, '
              f'{len(structs)} struct types, {len(left_out)} variadic '
              f'left out, into {args.output}')
        return 0

    if not args.header:
        parser.error('a header, or --all')
    text = normalise(args.header)
    rewritten, count, omitted = convert(text, struct_types([text]))
    args.output.write_text(rewritten)
    print(f'{count} declarations rewritten, {len(omitted)} variadic left out,'
          f' into {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
