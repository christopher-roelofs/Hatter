import unittest
from build_cluster import read_fixed_values, cluster_body
from inspect_format import FormatError


class ClusterTests(unittest.TestCase):
    def setUp(self):
        self.layout = {'class': 'PackageCluster', 'fixed_storage_bytes': 4, 'fields': [
            {'name': 'isPackageCluster', 'type': 'Boolean', 'bit_offset': 1, 'bit_width': 1, 'word_format': 0}]}

    def test_corpus_package_flag_and_identity(self):
        values = read_fixed_values(self.layout, bytes.fromhex('40000000'))
        self.assertEqual(values, {'isPackageCluster': True})
        self.assertEqual(cluster_body(self.layout, values, 'App'), bytes.fromhex('40000000') + b'App\0')
        self.assertEqual(cluster_body(self.layout, values, 'AB'), bytes.fromhex('40000000') + b'AB\0\0')

    def test_unmodeled_bits_rejected(self):
        for body in (bytes.fromhex('02000000'), bytes.fromhex('41000000'), bytes(3)):
            with self.assertRaises(FormatError):
                read_fixed_values(self.layout, body)

    def test_internal_name_limits(self):
        for name in ('', 'x' * 129, 'a\0b', '\u00e9'):
            with self.assertRaises(FormatError):
                cluster_body(self.layout, {'isPackageCluster': True}, name)


if __name__ == '__main__':
    unittest.main()
