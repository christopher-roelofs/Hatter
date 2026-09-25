#!/usr/bin/env python3
"""Match ordinary SDK methods to ELF symbols and the paired SDK ROM bytes.

This is read-only evidence from the SDK build, not a map for the current guest ROM.
"""
import collections
import hashlib
import json
from pathlib import Path
import struct
from inspect_format import FormatError, inspect, require

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'software/mips/sdk/extracted/MagicDeveloper/MagicDeveloper'


def read_elf(data, *, expected_type=2):
    require(len(data) >= 52 and data[:6] == b'\x7fELF\x01\x02', 'expected ELF32 big-endian')
    require(expected_type in (1, 2), 'unsupported requested ELF type')
    require(struct.unpack_from('>HH', data, 16) == (expected_type, 8), 'unexpected ELF type or non-MIPS machine')
    table = struct.unpack_from('>I', data, 32)[0]
    entry_size, count, name_index = struct.unpack_from('>HHH', data, 46)
    require(entry_size == 40 and 0 < count and name_index < count, 'unsupported ELF section directory')
    require(table + count * entry_size <= len(data), 'truncated ELF section directory')
    sections = []
    for i in range(count):
        values = struct.unpack_from('>10I', data, table + i * entry_size)
        section = dict(zip(('name_offset', 'type', 'flags', 'address', 'offset', 'size',
                            'link', 'info', 'alignment', 'entry_size'), values))
        if section['type'] != 8:  # NOBITS has no file payload.
            require(section['offset'] + section['size'] <= len(data), 'ELF section exceeds file')
        sections.append(section)

    def payload(section):
        require(section['type'] != 8, 'NOBITS has no file payload')
        return data[section['offset']:section['offset'] + section['size']]

    def string(blob, offset):
        require(offset < len(blob), 'ELF string offset out of bounds')
        end = blob.find(b'\0', offset)
        require(end >= 0, 'unterminated ELF string')
        return blob[offset:end].decode('ascii', errors='backslashreplace')

    require(sections[name_index]['type'] == 3, 'invalid ELF section-name table')
    names = payload(sections[name_index])
    for section in sections:
        section['name'] = string(names, section['name_offset'])
    symbols = []
    for section in sections:
        if section['type'] != 2:
            continue
        require(section['entry_size'] == 16 and section['size'] % 16 == 0, 'bad ELF symbol table')
        require(section['link'] < count and sections[section['link']]['type'] == 3, 'bad ELF symbol names')
        strings = payload(sections[section['link']])
        for offset in range(section['offset'], section['offset'] + section['size'], 16):
            name, value, size, info, other, index = struct.unpack_from('>IIIBBH', data, offset)
            symbols.append({'name': string(strings, name), 'address': value, 'size': size,
                            'type': info & 15, 'section_index': index})
    return sections, symbols


def main():
    paths = {'classes': SDK / 'Interfaces/MagicCap.cx',
             'elf': SDK / 'Debugger/Apollo/MagicCap-USA',
             'rom': SDK / 'Debugger/Apollo/MagicCap-USA.image'}
    blobs = {key: path.read_bytes() for key, path in paths.items()}
    sections, symbols = read_elf(blobs['elf'])
    executable = {i: s for i, s in enumerate(sections) if s['flags'] & 4 and s['type'] == 1}
    functions = collections.defaultdict(list)
    for symbol in symbols:
        if symbol['type'] == 2 and symbol['section_index'] in executable:
            functions[symbol['name']].append(symbol)
    text = next(s for s in sections if s['name'] == '.text')
    # SDK Apollo ROM address from its .monitortext section, not the emulator.
    rom_base = next(s['address'] for s in sections if s['name'] == '.monitortext')
    rom_offset = text['address'] - rom_base
    require(0 <= rom_offset and rom_offset + text['size'] <= len(blobs['rom']), 'SDK text outside paired ROM')
    text_blob = blobs['elf'][text['offset']:text['offset'] + text['size']]
    require(text_blob == blobs['rom'][rom_offset:rom_offset + text['size']], 'ELF .text differs from SDK ROM')
    matches, unresolved = [], []
    for section in inspect(blobs['classes'])['sections']:
        if section['raw_tag'] != 13:
            continue
        for record in section['named_records']:
            for method in record['members'].get('methods', []):
                if method['binding']['kind'] != 'ordinary-unresolved':
                    continue
                name = record['name_latin1'] + '_' + method['name_latin1']
                candidates = functions.get(name, [])
                if len(candidates) != 1:
                    unresolved.append({'symbol': name, 'reason': 'missing' if not candidates else 'ambiguous'})
                    continue
                symbol = candidates[0]
                segment = executable[symbol['section_index']]
                delta = symbol['address'] - segment['address']
                require(0 <= delta < segment['size'], 'function address outside ELF section')
                size = min(16, segment['size'] - delta)
                elf_offset = segment['offset'] + delta
                rom_pos = symbol['address'] - rom_base
                code = blobs['elf'][elf_offset:elf_offset + size]
                require(0 <= rom_pos and rom_pos + size <= len(blobs['rom']), 'method outside SDK ROM')
                require(code == blobs['rom'][rom_pos:rom_pos + size], 'method bytes differ from SDK ROM')
                matches.append({'class': record['name_latin1'], 'method': method['name_latin1'],
                                'operation_number': method['operation_number'], 'symbol': name,
                                'address': symbol['address'], 'elf_offset': elf_offset,
                                'sdk_rom_offset': rom_pos, 'prefix_hex': code.hex(),
                                'elf_symbol_size': symbol['size']})
    tv = next(s for s in sections if s['name'] == '.tvtab')
    require(tv['size'] % 8 == 0, 'unaligned transition-vector section')
    vectors = []
    by_address = collections.defaultdict(list)
    for name, entries in functions.items():
        for symbol in entries:
            by_address[symbol['address']].append(name)
    for offset in range(tv['offset'], tv['offset'] + tv['size'], 8):
        code, gp = struct.unpack_from('>II', blobs['elf'], offset)
        vectors.append({'address': tv['address'] + offset - tv['offset'], 'code_address': code,
                        'global_pointer': gp, 'matching_function_symbols': by_address.get(code, [])})
    report = {'scope': 'SDK Apollo build only; addresses are not validated against the current guest ROM',
              'sources': {str(paths[k].relative_to(ROOT)): hashlib.sha256(v).hexdigest() for k, v in blobs.items()},
              'sdk_rom_base': rom_base, 'text_bytes_verified': len(text_blob),
              'ordinary_method_matches': matches, 'unresolved': unresolved,
              'transition_vectors': vectors,
              'gp_symbols': [s for s in symbols if s['name'] == '_gp']}
    out = ROOT / 'out/rosemary-inspection/linked-methods.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(matches)} ordinary methods matched; {len(unresolved)} unresolved')
    print(f'{len(text_blob)} .text bytes match SDK ROM; {len(vectors)} transition-vector entries')
    print(f'{sum(bool(v["matching_function_symbols"]) for v in vectors)} vectors point to named ELF functions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
