#!/usr/bin/env python3
"""Restricted unlinked class: one superclass, no new fields, one native method."""
from build_object_values import integer
from inspect_format import require


def native_subclass(superclass_selector, operation_selector, function_id):
    require(type(superclass_selector) is int and 0 < superclass_selector <= 0xffff,
            'superclass must fit the halfword selector list')
    require(type(operation_selector) is int and 0 < operation_selector <= 0xfffff,
            'operation must fit the 20-bit method selector')
    require(type(function_id) is int and 0 < function_id <= 0xffffffff,
            'native function IDs are one-based')
    # Six halfwords: implementation-superclass list, object methods,
    # own fields format, intrinsics, class methods, extra interface list.
    header = b''.join(integer(n, 16) for n in (12, 16, 0, 0, 0, 0))
    supers = integer(1, 16) + integer(superclass_selector, 16)
    methods = integer(0x8001, 16) + integer(0, 16)
    methods += integer(0x41000000 | operation_selector, 32) + integer(function_id, 32)
    return header + supers + methods
