import unittest
from resolve_global_sources import provider_index, match_providers, interface_occurrences


class ProviderTests(unittest.TestCase):
    def package(self, path='provider.pkg', local=False, count=3):
        return {'path': path, 'package': 0, 'sha256': 'test-hash', 'exports': [
            {'kind': 'locator', 'name': 'Interface', 'local': local,
             'count': count, 'selector_start': 12, 'record_offset': 100}]}

    def source(self, **updates):
        return {'component_kind': 'locator', 'interface': 'Interface',
                'index': 2, 'required_count': 1, **updates}

    def test_single_provider_uses_provider_selector_stride(self):
        result = match_providers(self.source(), provider_index([self.package()]))
        self.assertEqual(result['status'], 'unique-corpus-provider')
        self.assertEqual(result['candidates'][0]['provider_selector'], 28)
        self.assertFalse(result['runtime_resolved'])

    def test_variants_and_duplicate_exports_remain_explicit(self):
        p = self.package()
        result = match_providers(self.source(), provider_index([p, self.package('other.pkg')]))
        self.assertEqual(result['status'], 'multiple-corpus-providers')
        p['exports'] *= 2
        self.assertEqual(match_providers(self.source(), provider_index([p]))['status'], 'multiple-corpus-providers')

    def test_range_failure_and_local_exclusion(self):
        result = match_providers(self.source(), provider_index([self.package(count=1)]))
        self.assertEqual(result['status'], 'provider-range-mismatch')
        self.assertEqual(len(result['range_rejected']), 1)
        self.assertEqual(match_providers(self.source(), provider_index([self.package(local=True)]))['status'], 'no-corpus-provider')

    def test_kind_and_negative_range(self):
        providers = provider_index([self.package()])
        self.assertEqual(match_providers(self.source(component_kind='class'), providers)['status'], 'no-corpus-provider')
        self.assertEqual(match_providers(self.source(index=-1), providers)['status'], 'provider-range-mismatch')

    def test_rom_strings_are_offsets_only(self):
        self.assertEqual(interface_occurrences(b'XabcYabc', {'abc', 'missing'}),
                         {'abc': [1, 5], 'missing': []})


if __name__ == '__main__':
    unittest.main()
