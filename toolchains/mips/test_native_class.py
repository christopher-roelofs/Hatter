import unittest
from build_native_class import native_subclass
from inspect_format import FormatError
from link_package_methods import method_list


class NativeClassTests(unittest.TestCase):
    def test_cujo_ident_actor_golden(self):
        body = native_subclass(3, 996, 17)
        self.assertEqual(body.hex(), '000c001000000000000000000001000380010000410003e400000011')
        methods = method_list(body, {'offset': 0, 'length': len(body)})
        self.assertEqual(len(methods), 1)
        self.assertTrue(methods[0]['native'])
        self.assertEqual(methods[0]['operation_selector'], 996)
        self.assertEqual(methods[0]['raw_value'], 17)

    def test_invalid_inputs(self):
        for args in ((0, 1, 1), (65536, 1, 1), (1, 0x100000, 1), (1, 1, 0), (True, 1, 1)):
            with self.assertRaises(FormatError):
                native_subclass(*args)


if __name__ == '__main__':
    unittest.main()
