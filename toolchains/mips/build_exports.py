#!/usr/bin/env python3
"""Package export table with entries, mirroring Ne2000.pkg's tables.

PackageExportTable: hashEntries, hashEntrySize 12, lgCount, entryCount,
firstFreeEntry 0, min/max 0, cliqueNameTable; extra = bucket list (word
format 4, 1 << lgCount words of chain-head slot numbers, 0 = empty).
PackageExportHashEntries: slot count, then 16-byte slots (link to the next
slot in the chain or 0, kind << 24 | name offset, component count, first
package selector).  CliqueNameTable: 8 fixed bytes, then Pascal names.
With lgCount 0 every name hashes to the single bucket, so the loader's
chain walk finds any entry without the (undecoded) hash function.
"""
from build_object_values import fixed_body, integer
from inspect_format import require

KINDS = {'locator': 1, 'class': 2, 'operation': 3, 'class-operation': 4, 'intrinsic': 5}


def export_tables(layouts, selectors, entries):
    """entries: list of (kind, name, count, first_selector)."""
    names = bytearray(8)
    slots = b''
    for i, (kind, name, count, first) in enumerate(entries):
        raw = name.encode('latin1')
        require(0 < len(raw) < 256 and kind in KINDS and count > 0, 'invalid export entry')
        offset = len(names) - 8
        names += bytes([len(raw)]) + raw
        link = i + 2 if i + 1 < len(entries) else 0
        slots += integer(link, 32) + integer(KINDS[kind] << 24 | offset, 32) + integer(count, 32) + integer(first, 32)
    table = fixed_body(layouts['PackageExportTable'],
                       dict(hashEntries=selectors['exportEntries'], hashEntrySize=12, lgCount=0,
                            entryCount=len(entries), firstFreeEntry=0, minPercentFull=0, maxPercentFull=0,
                            cliqueNameTable=selectors['exportNames']))
    table += integer(0x04000001, 32) + integer(1 if entries else 0, 32)
    return {'exports': table, 'exportEntries': integer(len(entries), 32) + slots, 'exportNames': bytes(names)}
