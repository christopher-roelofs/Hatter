"""Derived class formats must match the formats the original tools wrote for
the same SDK classes in the corpus packages (the guest rejects a package
whose abbreviated class format disagrees with the ROM's)."""
import collections
import glob
import unittest
from inspect_format import inspect, FormatError
from link_package_methods import ROOT, SDK, declarations
from odef_frontend import sdk_layout


class FormatOracleTests(unittest.TestCase):
    def test_corpus_formats(self):
        _, pub = declarations((SDK / 'Interfaces/DefFiles/Interfaces/PublicInterface.cdef').read_text())
        cname = {i: n[0] for (k, i), n in pub.items() if k == 'class'}
        classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
                   if s['raw_tag'] == 13 for r in s['named_records']}
        oracle = collections.defaultdict(set)
        for path in glob.glob(str(ROOT / 'packages/*.pkg')):
            try:
                with open(path, 'rb') as package:
                    pk = inspect(package.read())['packages'][0]
            except FormatError:
                continue
            attrs = {a['raw_tag_byte']: a for a in pk['records']}
            if 0x10 not in attrs:
                continue
            imps = [e for e in attrs[0x20]['imports']['entries'] if e['kind'] == 'class' and e['name']['text_latin1'] == 'SystemPublic']
            for e in attrs[0x10]['abbreviated_classes']['entries']:
                for im in imps:
                    if im['raw_component_word'] <= e['class_selector'] < im['raw_component_word'] + im['count']:
                        n = cname.get(im['raw_range_word'] + e['class_selector'] - im['raw_component_word'])
                        if n:
                            oracle[n].add(tuple(e['raw_format_nibbles']))
        self.assertGreater(len(oracle), 50)
        mismatches, derived = [], 0
        for n, fmts in oracle.items():
            if n not in classes:
                continue
            try:
                mine = tuple(sdk_layout(classes, n)['raw_format_nibbles'])
            except FormatError as e:
                mismatches.append((n, 'derive failed', str(e)))
                continue
            derived += 1
            if mine not in fmts:
                mismatches.append((n, mine, sorted(fmts)))
        self.assertGreater(derived, 50)
        self.assertEqual(mismatches, [])


if __name__ == '__main__':
    unittest.main()
