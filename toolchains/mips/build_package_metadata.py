#!/usr/bin/env python3
"""Empty package tables matching observed compiled-package representations."""
from build_object_values import fixed_body, object_list, integer
from inspect_format import require

METADATA_CLASSES = {
    'sharedTable': 'ObjectValueHashTable', 'sharedEntries': 'DataList', 'sharedObjects': 'ObjectList',
    'packageData': 'PackageData', 'exports': 'PackageExportTable',
    'exportEntries': 'PackageExportHashEntries', 'exportNames': 'CliqueNameTable',
    'missingNames': 'Text', 'missingIndexicals': 'ObjectList',
}


def empty_metadata(layouts, selectors):
    require(all(n in selectors for n in METADATA_CLASSES), 'missing metadata selectors')
    refs = [selectors[n] for n in METADATA_CLASSES]
    require(len(set(refs)) == len(refs) and all(type(v) is int and 0 < v <= 0xffffffff and v & 7 == 4 for v in refs),
            'metadata selectors must be distinct aligned locators')
    common = dict(lgCount=0, entryCount=0, firstFreeEntry=0, minPercentFull=0, maxPercentFull=0)
    values = {
        'sharedTable': dict(common, hashEntries=selectors['sharedEntries'], hashEntrySize=8,
                            renumberables=selectors['sharedObjects']),
        'exports': dict(common, hashEntries=selectors['exportEntries'], hashEntrySize=12,
                        cliqueNameTable=selectors['exportNames']),
        'packageData': dict(linkingPrefix=0, missingCliqueNames=selectors['missingNames'],
                            missingCliqueMessageIndexicals=selectors['missingIndexicals'], acclimatized=True),
        'exportNames': dict(deletedSize=0, cliqueTable=0),
        'sharedEntries': dict(stride=8),
    }
    bodies = {n: fixed_body(layouts[METADATA_CLASSES[n]], v) for n, v in values.items()}
    # HashTable extra is a one-word integer list: one empty bucket.
    bucket = integer(0x04000001, 32) + integer(0, 32)
    bodies['sharedTable'] += bucket
    bodies['exports'] += bucket
    # Empty DataList: fixed stride, then a zero element count.
    bodies['sharedEntries'] += integer(0, 32)
    bodies.update(sharedObjects=object_list([]), exportEntries=integer(0, 32),
                  missingNames=b'', missingIndexicals=object_list([]))
    return bodies, values
