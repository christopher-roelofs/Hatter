#!/usr/bin/env python3
"""Build native 68k Magic Sokoban from the shared Rosemary game sources.

This is a deliberately narrow adapter, not a general C++/ODEF translator.
Generated C and ObjectMaker definitions remain in the output's source folder
for inspection. The original MIPS game and its build pipeline are unchanged.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / 'toolchains/mips/samples/Sokoban'
sys.path.insert(0, str(ROOT / 'toolchains/m68k'))
from build_example import build_example
from profiles import resolve


def rules_c():
    text = (SAMPLE / 'SokobanRules.h').read_text()
    text = text.replace('namespace Soko {', '').replace('\n}\n#endif', '\n#endif')
    text = text.replace('const State &s', 'const State *s').replace('State &s', 'State *s')
    text = re.sub(r'\bs\.', 's->', text)
    text = text.replace('struct State {', 'typedef struct State {').replace('\n};\nstatic const', '\n} State;\nstatic const', 1)
    text = re.sub(r'\b(Width|Height|Levels|State|maps|wall|goal|won|reset|advance|move|undo)\b', r'Soko_\1', text)
    text = re.sub(r'\bbool\b', 'int', text).replace('return false;', 'return 0;').replace('return true;', 'return 1;')
    text = text.replace('for (int p =', 'int p; for (p =')
    # Avoid a libgcc signed-remainder helper in this freestanding package.
    text = text.replace('(s->level + 1) % Soko_Levels',
                        '(s->level + 1 == Soko_Levels ? 0 : s->level + 1)')
    return text


def guest_c():
    text = (SAMPLE / 'Sokoban.cpp').read_text()
    text = text.replace('#include "Sokoban.xh"\n#include "Sokoban.xph"', '#include "Package.h"')
    text = text.replace('Reference', 'ObjectID').replace('Private ', 'static ')
    text = text.replace('Soko::', 'Soko_')
    text = text.replace('const Soko_State &s', 'const Soko_State *s').replace('Soko_State &s', 'Soko_State *s')
    # Only the field-copy helpers receive a pointer; methods keep local state.
    before, after = text.split('static void SokoStatus', 1)
    text = re.sub(r'\bs\.', 's->', before) + 'static void SokoStatus' + after
    text = text.replace('SokoRead(self,s)', 'SokoRead(self,&s)').replace('SokoWrite(self,s)', 'SokoWrite(self,&s)')
    text = re.sub(r'\b(Soko_(?:reset|undo|advance|won|move))\(s\b', r'\1(&s', text)
    text = text.replace('for (int p=0;', 'int p; for (p=0;')
    text = text.replace('ReplaceText(iStatus, NewTextFromLiteral((char *)message));',
                        'unsigned char p[256]; SokoPascal(message,p); ReplaceTextWithString(iStatus,p);')
    text = text.replace('PaintTextInBox(NewTextFromLiteral((char *)message), box, iBook12Center, kCenter);',
                        'unsigned char p[256]; SokoPascal(message,p);\n    PaintStringInBox(p,CurrentCanvas(),CurrentClip(),box,iBook12Center,kCenter);')
    text = text.replace('SokobanBoard_Draw(ObjectID self)', 'SokobanBoard_Draw(ObjectID self, ObjectID canvas, ObjectID clip)')
    text = text.replace('InheritedDraw(self)', 'InheritedDraw(self,canvas,clip)')
    text = text.replace('CurrentCanvas()', 'canvas').replace('CurrentClip()', 'clip')
    text = text.replace('SokoLabel(', 'SokoLabel(canvas,clip,')
    text = text.replace('void SokoLabel(canvas,clip,', 'void SokoLabel(ObjectID canvas,ObjectID clip,')
    # Native 68k text fields own their redraw/clip state. Keep the counters
    # out of the custom board's drawing pass, like the cookbook Counter app.
    text = re.sub(r'static void SokoCounter\(.*?\n}\n', '', text, flags=re.S)
    text = re.sub(r'    cell.top=bounds.bottom;.*?\n}\nMethod void SokobanBoard_Tap',
                  '}\nMethod void SokobanBoard_Tap', text, flags=re.S)
    text = text.replace('WriteFields(self, &f);',
        'WriteFields(self, &f);\n    SokoCountText(MakePackageIndexical(25,2),"Level ",s->level+1);\n'
        '    SokoCountText(MakePackageIndexical(25,3),"Moves ",s->moves);\n'
        '    SokoCountText(MakePackageIndexical(25,4),"Pushes ",s->pushes);')
    helper = '''#define iStatus MakePackageIndexical(25,1)
static void SokoPascal(const char *s, unsigned char *p) {
    unsigned n=0; while(s[n] && n<255) { p[n+1]=(unsigned char)s[n]; ++n; } p[0]=(unsigned char)n;
}
static void SokoCountText(ObjectID field, const char *label, int value) {
    unsigned char text[64], digits[12]; unsigned n=0,d=0;
    while(*label && n<30) text[++n]=(unsigned char)*label++;
    do { digits[d++]=(unsigned char)('0'+value-(value/10)*10); value/=10; } while(value && d<11);
    while(d) text[++n]=digits[--d]; text[0]=(unsigned char)n;
    ReplaceTextWithString(field,text);
}
'''
    return text.replace('static void SokoRead', helper + '\nstatic void SokoRead', 1)


def stage(destination):
    destination.mkdir(parents=True, exist_ok=True)
    headers = destination / 'PackageInterfaces'
    headers.mkdir(exist_ok=True)
    fields = re.findall(r'field (\w+): Signed', (SAMPLE / 'Sokoban.cdef').read_text())
    definition = 'Operation Restart 1;\nOperation UndoMove 2;\nOperation NextPuzzle 3;\nDefine Class SokobanBoard;\n inherits from Box;\n'
    definition += ''.join(f' field {f}: Signed;\n' for f in fields)
    definition += ' operation Restart();\n operation UndoMove();\n operation NextPuzzle();\n overrides Draw;\n overrides Tap;\nEnd Class;\n'
    (destination / 'Sokoban.Def').write_text(definition)
    # The legacy builder uses this textual build-order listing, not a CW IDE.
    (destination / 'Sokoban.µ').write_text('Sokoban.Def\nObjects.Def\n')
    (headers / 'PackageClassNumbers.h').write_text('#define SokobanBoard_ 0x8001\n')
    (headers / 'PackageFields.h').write_text('typedef struct {\n' + ''.join(f' Signed {f};\n' for f in fields) + '} SokobanBoard_Fields;\n')
    for name in ('PackageFieldNumbers.h', 'PackageImports.h', 'PackageOperationNumbers.h', 'PackageOperations.h', 'PackagePatching.h'):
        (headers / name).write_text('/* No generated declarations needed. */\n')
    (destination / 'SokobanRules.h').write_text(rules_c())
    (destination / 'Sokoban.c').write_text(guest_c())
    (destination / 'Objects.Def').write_text(objects())


def objects():
    source = (SAMPLE / 'Objects.odef').read_text()
    def block(kind, name):
        match = re.search(r'instance '+kind+' '+name+r'(?: \'[^\']*\')?;\n(.*?)end instance;', source, re.S)
        if not match:
            raise ValueError('missing source object ' + name)
        return re.sub(r'\s*//[^\n]*', '', match[1])
    names = {'packageScene': ('Scene',8), 'board': ('SokobanBoard',20), 'statusField': ('TextField',15),
             'resetButton': ('SimpleActionButton',18), 'undoButton': ('SimpleActionButton',19),
             'nextButton': ('SimpleActionButton',21), 'initialStatus': ('Text',16), 'crateIcon': ('Image',23),
             'gameIcon': ('Icon',22)}
    result = '''Instance SoftwarePackage 'Magic Sokoban' 1;
 length: 32;
 author: (AddressCard 101);
 installList: (ObjectList 3);
 receivers: (ObjectList 4);
 autoActivate: true;
 citation: (Citation 10);
 publisher: (AddressCard 101);
 gotoActionSelector: 3.w;
 entry6: (ObjectList 5);
 entry9: (ObjectList 6);
 entry10: (ObjectList 7);
 entry13: iGameRoomScene;
 entry25: (ObjectList 17);
End Instance;
Instance Citation 10;
 title: (Identifier 'Magic Sokoban' 12);
 author: (Telename 2);
 majorEdition: 1;
 minorEdition: 0;
End Instance;
Instance Identifier 'Magic Sokoban' 12;
End Instance;
Instance Telename 2;
 authority: (OctetString 9);
 identity: (OctetString 13);
End Instance;
Instance OctetString 9;
 data: 'magicrecomp.org';
End Instance;
Instance OctetString 13;
 data: 'Magic Sokoban 68k';
End Instance;
Instance AddressCard 101;
 assignedName: (Telename 2);
End Instance;
Instance ObjectList 3;
 length: 1;
 entry: (Icon 'Magic Sokoban' 22);
End Instance;
Instance ObjectList 4;
 length: 1;
 entry: iGameRoomShelf;
End Instance;
Instance ObjectList 5;
 length: 1;
 entry: (Scene 'Magic Sokoban' 8);
End Instance;
Instance ObjectList 6;
 length: 1;
 entry: (Scene 'Magic Sokoban' 8);
End Instance;
Instance ObjectList 7;
 length: 1;
 entry: (Text 11);
End Instance;
Instance Text 11;
 text: 'Magic Sokoban\\nPush all crates onto the dots. Tap next to the player. Undo keeps one move. Restart retries; Next requires a solved puzzle. Twelve levels.';
End Instance;
Instance ObjectList 17;
 length: 4;
 entry: (TextField 15);
 entry: (TextField 30);
 entry: (TextField 31);
 entry: (TextField 32);
End Instance;
'''
    for index,(label,value) in enumerate((('Level',1),('Moves',0),('Pushes',0))):
        result += f'''Instance TextField {30+index};
 previous: ({'SokobanBoard 20' if index==0 else 'TextField '+str(29+index)});
 next: (TextField {31+index if index<2 else 15});
 superview: (Scene 8);
 relativeOrigin: <{-145+index*100}.0,80.0>;
 contentSize: <100.0,20.0>;
 viewFlags: 0x70019200;
 color: 0xFF000000;
 altColor: 0xFFFFFFFF;
 fieldFlags: 0x41040010;
 dataStore: (Text {40+index});
 baseStyle: iBook12Center;
End Instance;
Instance Text {40+index};
 text: '{label} {value}';
End Instance;
'''
    children = ['board','statusField','resetButton','undoButton','nextButton']
    for name,(kind,number) in names.items():
        body = block(kind,name)
        if name == 'packageScene':
            body = re.sub(r'    subview:.*?;\n', '', body)
            body = re.sub(r'    \w+: (?:true|false);\n', '', body)
            body += ' sceneFlags: 0;\n subview: (SokobanBoard 20);\n'
        if name in children:
            index = children.index(name)
            def ref(n):
                k,i = names[n]; return f'({k} {i})'
            body += ' superview: (Scene 8);\n'
            body += f' previous: {ref(children[index-1]) if index else "nilObject"};\n'
            body += f' next: {ref(children[index+1]) if index+1<len(children) else "nilObject"};\n'
            if name == 'board': body = body.replace('next: (TextField 15);', 'next: (TextField 30);')
            if name == 'statusField': body = body.replace('previous: (SokobanBoard 20);', 'previous: (TextField 32);')
        if name == 'crateIcon':
            body = re.sub(r'    (rectImage|hasMask|allBlack|containsName|packed|aligned32|finePointing):.*?;\n', '', body)
            body = body.replace('data:', 'extra:')
            body = body.replace('nextImage:', 'next:').replace('previousImage:', 'previous:')
            body += ' imageFlags: 0;\n'
        for other,(k,i) in names.items():
            body = body.replace(f'({k} {other})', f'({k} {i})')
        label = " 'Magic Sokoban'" if name in ('packageScene','gameIcon') else (f" '{ {'resetButton':'Restart','undoButton':'Undo','nextButton':'Next'}[name] }'" if name.endswith('Button') else '')
        result += f'Instance {kind}{label} {number};\n{body}End Instance;\n'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/magic-sokoban-68k')
    parser.add_argument('--profile', default='1.5')
    args = parser.parse_args()
    source = args.out / 'source'
    stage(source)
    package, missing = build_example(source, interfaces=resolve(args.profile), report=True, compiler='gcc')
    if missing:
        raise RuntimeError(f'unplaced object fields: {missing}')
    output = args.out / 'Magic Sokoban.pkg'
    output.write_bytes(package)
    print(f'{output}: {len(package)} bytes, profile {args.profile}')


if __name__ == '__main__':
    main()
