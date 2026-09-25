import unittest
from magic_script import assemble, parse_prototype, signature_indexical
from odef_frontend import parse_odef, statements


def convert(raw):
    if raw.startswith('('): return ('ref', raw.split()[1].rstrip(')'))
    if raw.startswith('operation_'): return ('op', raw[len('operation_'):])
    return ('ix', raw)


class MagicScriptTests(unittest.TestCase):
    def test_prototypes(self):
        self.assertEqual(parse_prototype('[(Reference, UnsignedByte) -> void]'), (('Reference', 'UnsignedByte'), 'void'))
        self.assertEqual(signature_indexical(('Reference',), 'void'), 'iReferenceVoidType')
        self.assertEqual(signature_indexical(('Reference', 'Reference'), 'Reference'), 'iReferenceReferenceReferenceType')
        self.assertEqual(signature_indexical(('Reference', 'Reference', 'Reference', 'Unsigned', 'Reference', 'Reference', 'Unsigned'), 'void'),
                         'iPerformWithConfirmationType')

    def test_accessdemo_script(self):
        # WebBrowser35's form: ldc objects, invokevirtual through a method ref whose value
        # is the descriptor's index (operation index << 16 | signature index)
        r = assemble('t', ['script prototype is [(Reference) -> void]', 'push (DrawWatcher drawWatcher)',
                           'call HasBunny [(Reference) -> UnsignedByte]', 'if not 0, goto label1', 'push 1',
                           'pop into variable 1', 'goto label2', 'label1:\n\tpush 0', 'pop into variable 1',
                           'label2:\n\tpush (DrawWatcher drawWatcher)', 'push variable 1',
                           'call SetHasBunny [(Reference, UnsignedByte) -> void]'], convert)
        self.assertEqual(r['code'].hex(), '1202b600069a0008043ca70005033c12022bb60008b1')
        self.assertEqual(r['objects'], [('ix', 'iReferenceVoidType'), ('ref', 'drawWatcher'), ('ix', 'iReferenceUnsignedByteType'),
                                        ('ix', 'iReferenceUnsignedByteVoidType')])
        self.assertEqual(r['integers'], [0x90003, 5, 0xa0004, 7])
        self.assertEqual(r['operations'], [('op', 'HasBunny'), ('op', 'SetHasBunny')])
        self.assertEqual((r['signature_index'], r['variable_count']), (1, 2))

    def test_simple_call_and_literals(self):
        r = assemble('t', ['push (StackScene packageScene)', 'push iNewItemsGoHere', 'push 300', 'push 0x12345678',
                           'push operation_DeleteCard', 'call CreateNewCard [(Reference, Reference) -> Reference]', 'return object'],
                     convert)
        self.assertEqual(r['code'].hex(), '1202120311012c12051208b60007b0')
        self.assertEqual(r['integers'][:2], [0x12345678, 0x90004])

    def test_odef_scripts_and_arrow(self):
        self.assertEqual(statements("a: [(Reference) -> void]; b: <1.0,2.0>;"), ['a: [(Reference) -> void]', 'b: <1.0,2.0>'])
        scripts = {}
        inst, _ = parse_odef("instance Button b 'B' Action: (script s);\n\tcolor: 1;\nend instance;\n"
                             "script s;\n\tscript prototype is [(Reference) -> void];\n\tpush self;\n\tcall Draw [(Reference) -> void];\nend script;\n", scripts)
        self.assertEqual(inst[0]['scripts'], {'Action': 's'})
        self.assertEqual(inst[0]['fields'], [('color', '1')])
        self.assertEqual(scripts['s'], ['script prototype is [(Reference) -> void]', 'push self', 'call Draw [(Reference) -> void]'])


    def test_intrinsic_call_and_arithmetic(self):
        r = assemble('t', ['call intrinsic_Honk [() -> void]', 'push 3', 'push 4', 'add', 'pop into variable 1'], convert)
        # invokeinterface (0xb9) through a method ref whose descriptor names the intrinsics list entry
        self.assertEqual(r['code'].hex(), 'b900040607603cb1')
        self.assertEqual(r['intrinsics'], [('intrinsic', 'Honk')])
        self.assertEqual(r['integers'], [0x50002, 3])
        self.assertEqual(r['objects'], [('ix', 'iReferenceVoidType'), ('ix', 'iVoidType')])

    def test_phrases(self):
        from odef_frontend import parse_phrases, apply_phrases
        ph = parse_phrases('#include "CoreDefines.h"\n// c\nphrase for Main.scene field name\n\treplace \'Ahoy\'\n\twith \'Hello\';\n'
                           "phrase for info field text replace 'a' with 'b';\ndont require phrases for textual fields;\n")
        self.assertEqual(ph, [('scene', 'name', "'Ahoy'", "'Hello'"), ('info', 'text', "'a'", "'b'")])
        inst = [{'tag': 'scene', 'name': 'Ahoy', 'fields': []}, {'tag': 'info', 'name': None, 'fields': [('text', "'a'")]}]
        apply_phrases(inst, ph)
        self.assertEqual((inst[0]['name'], inst[1]['fields']), ('Hello', [('text', "'b'")]))


if __name__ == '__main__':
    unittest.main()
