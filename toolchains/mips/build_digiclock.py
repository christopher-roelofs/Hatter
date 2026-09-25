#!/usr/bin/env python3
"""DigiClock (SDK sample): Digitalis = Box + HasDestination + CanInstallSelf
with five native methods, built from the unmodified DigiClock.cpp."""
import hashlib
import json
from pathlib import Path
from build_package import build_package
from build_sdk_package import compile_sdk
from build_object_values import pixel_units
from derive_fixed_formats import derive
from inspect_format import inspect
from link_package_methods import ROOT, SDK
from trace_linked_methods import read_elf

METHODS = ['InstallSelf', 'Tap', 'Draw', 'Idle', 'AutoMove']      # function ids 3..7


def main():
    out = ROOT / 'out/rosemary-digiclock'
    headers = out / 'pkgheaders'
    headers.mkdir(parents=True, exist_ok=True)
    (headers / 'DigiClock.xph').write_text(
        '// generated: the loader resolves the class number from the package export @Digitalis\n'
        'extern "C" int _classNumber_Digitalis_;\n#define Digitalis_ ((ClassNumber)_classNumber_Digitalis_)\n')
    (headers / 'DigiClockIndexicals.xph').write_text(
        '// generated: package indexical, resolved from the export @iDigitalis\n'
        'extern "C" int _localLocator_iDigitalis_;\n#define iDigitalis ((Reference)_localLocator_iDigitalis_)\n')
    source = SDK / 'Samples/DigiClock/DigiClock.cpp'
    code, init, entry, extra = compile_sdk(source, out, 'DigiClock', 'Digitalis_Draw', package_headers=headers)
    syms = {k: int(v, 16) for k, v in extra['symbols'].items()}
    offsets = {3 + i: syms['Digitalis_' + m] - 0x10000000 for i, m in enumerate(METHODS)}
    classes = {r['name_latin1']: r for s in inspect((SDK / 'Interfaces/MagicCap.cx').read_bytes())['sections']
               if s['raw_tag'] == 13 for r in s['named_records']}
    box = derive('Box', classes, {'BackgroundWithBorder': 44})
    # Digitalis: Box's 48 fixed bytes, then HasDestination's leaf (destination: Reference)
    layout = {'class': 'Digitalis', 'fixed_storage_bytes': 52, 'raw_format_nibbles': box['raw_format_nibbles'] + [13],
              'fields': box['fields'] + [{'owner': 'HasDestination', 'name': 'destination', 'type': 'Reference',
                                          'bit_offset': 48 * 8, 'bit_width': 32, 'word_format': 13}]}
    spec = {
        'internal_name': 'DigiClock',
        'classes': [{'name': 'Digitalis', 'supers': ['Box', 'HasDestination', 'CanInstallSelf'],
                     'methods': [(m, 3 + i) for i, m in enumerate(METHODS)], 'layout': layout,
                     'own_fields_word': 0x9004}],
        'objects': [
            {'tag': 'contents', 'class': 'SoftwarePackageContents', 'name': 'DigiClock', 'fields': dict(
                dateCreated=0, timeCreated=0, dateModified=0, timeModified=0, autoActivate=True,
                installationList=('ref', 'installationList'), author=('ix', 'iGeneralMagic'), publisher=('ix', 'iGeneralMagic'),
                versionText=0, helpOnObjects=0, sceneIndexicalList=0, stackIndexicalList=0, startupScene=0, startupItem=0,
                creditsScene=0, logo=0, responseCardStationery=('ix', 'iDefaultStationery'), dontDeactivate=False)},
            {'tag': 'installationList', 'class': 'ObjectList', 'list': [('ix', 'iInstallationQueue'), ('ref', 'clock')]},
            {'tag': 'clock', 'class': 'Digitalis', 'fields': dict(
                superview=0, relativeOrigin=[pixel_units('9.0'), pixel_units('-52.0')],
                contentSize=[pixel_units('103.0'), pixel_units('19.0')], viewFlags=0x50080000,
                labelStyle=('ix', 'iBook14Center'), color=0xFF000000, altColor=0xFFFFFFFF, shadow=0, sound=0,
                border=('ix', 'iRoundedButtonBorderUp'), destination=('ix', 'iClockScene')), 'subviews': []},
        ],
        'indexicals': {'iDigitalis': 'clock'},
        'function_offsets': offsets,
    }
    raw, manifest = build_package(spec, code, init)
    (out / 'DigiClock.pkg').write_bytes(raw)
    manifest.update(sha256=hashlib.sha256(raw).hexdigest(), length=len(raw), method_offsets=offsets,
                    code_hex=code.hex(), **{k: extra[k] for k in ('references', 'fixups', 'code_bytes', 'globals_bytes', 'source_sha256')})
    (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('sha256', 'length', 'method_offsets', 'selectors', 'class_selectors', 'exports')}, indent=1))


if __name__ == '__main__':
    main()
