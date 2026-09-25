import struct
import unittest
from inspect_format import FormatError
from trace_linked_methods import read_elf


def fixture():
    blob = bytearray(52)
    blob[:7] = b'\x7fELF\x01\x02\x01'
    struct.pack_into('>HHI', blob, 16, 2, 8, 1)
    names = b'\0.shstrtab\0.symtab\0.strtab\0.text\0'
    payloads = [b'', names, bytes(16) + struct.pack('>IIIBBH', 1, 0x1000, 4, 0x12, 0, 4),
                b'\0Example_Draw\0', b'\x03\xe0\x00\x08']
    sections = [(0,) * 10]
    for i in range(1, 5):
        offset = len(blob)
        blob.extend(payloads[i])
        name = [b'', b'.shstrtab', b'.symtab', b'.strtab', b'.text'][i]
        sections.append((names.index(name), {1: 3, 2: 2, 3: 3, 4: 1}[i],
                         6 if i == 4 else 0, 0x1000 if i == 4 else 0, offset,
                         len(payloads[i]), 3 if i == 2 else 0, 0, 1, 16 if i == 2 else 0))
    table = len(blob)
    for section in sections:
        blob.extend(struct.pack('>10I', *section))
    struct.pack_into('>I', blob, 32, table)
    struct.pack_into('>HHH', blob, 46, 40, len(sections), 1)
    return blob, table


class LinkedELFTests(unittest.TestCase):
    def test_named_function_and_code_section(self):
        sections, symbols = read_elf(fixture()[0])
        self.assertEqual(sections[4]['name'], '.text')
        self.assertEqual(symbols[1]['name'], 'Example_Draw')
        self.assertEqual(symbols[1]['address'], 0x1000)
        self.assertEqual(symbols[1]['section_index'], 4)

    def test_truncated_directory(self):
        data, _ = fixture()
        with self.assertRaises(FormatError):
            read_elf(data[:-1])

    def test_wrong_architecture(self):
        data, _ = fixture()
        struct.pack_into('>H', data, 18, 3)
        with self.assertRaises(FormatError):
            read_elf(data)

    def test_section_bounds_and_bad_symbol_string_link(self):
        for section, field, value in [(4, 4, 0xfffffff0), (2, 6, 99), (2, 9, 8)]:
            data, table = fixture()
            struct.pack_into('>I', data, table + section * 40 + field * 4, value)
            with self.subTest(section=section, field=field), self.assertRaises(FormatError):
                read_elf(data)

    def test_unterminated_symbol_string(self):
        data, table = fixture()
        offset, size = struct.unpack_from('>II', data, table + 3 * 40 + 16)
        data[offset + size - 1] = ord('X')
        with self.assertRaises(FormatError):
            read_elf(data)


if __name__ == '__main__':
    unittest.main()
