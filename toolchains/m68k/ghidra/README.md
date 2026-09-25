# Reading ObjectMaker with Ghidra

ObjectMaker is a PowerPC PEF binary. Ghidra loads it, finds 612 functions and
decompiles them to readable pseudo-C, which answers the first question: the
tool that wrote the package format can be read.

    G=/snap/ghidra/current/ghidra/support/analyzeHeadless
    cp "software/68k/.../MagicDeveloper/Tools/ObjectMaker" /tmp/ObjectMaker.pef
    $G /tmp/proj ObjMaker -import /tmp/ObjectMaker.pef -overwrite
    $G /tmp/proj ObjMaker -process ObjectMaker.pef -noanalysis \
        -scriptPath toolchains/m68k/ghidra \
        -postScript Decomp.java /tmp/out/top.c 20

`Decomp.java` decompiles the largest functions, `FindMsg.java` locates a
diagnostic message and reports what reaches it, and `RefStats.java` says how
much of the program analysis actually connected up.

## Telling it what r2 holds

Out of the box only 17 of the 932 strings had a cross-reference, because every
one of the 1600 table-of-contents accesses is `lwz rN,disp(r2)` and Ghidra has
no idea what r2 is. CFM sets it from the main transition vector, and that is
in the file: the loader header's `mainSection`/`mainOffset` point at a pair of
words in the data section, the second of which is the TOC offset. For
ObjectMaker that is data+`0x694`, so r2 = `0x1001f874` with Ghidra's layout.

`SetToc.java` writes that into the register context over the code block; a
re-analysis then resolves the loads. **589 of 956 strings become referenced.**

    $G /tmp/proj ObjMaker -process ObjectMaker.pef -noanalysis \
        -scriptPath toolchains/m68k/ghidra -postScript SetToc.java 1001f874
    $G /tmp/proj ObjMaker -process ObjectMaker.pef          # re-analyse

Ghidra's PEF loader does apply the data relocations -- 478 of them, all
`APPLIED`. An earlier note here said it did not; that was wrong, and so was a
reading of the loader header that reported no relocations at all (the
relocation headers sit after the imported library and symbol tables).

## What it says so far

`FindMsg.java` locates the padding warning in `FUN_100043a8`, which is where a
class is finished off. It confirms the instance layout from the writer's side:
a pending bit count is flushed to a whole byte, and then the size is rounded
up to a multiple of four -- exactly the model derived from the packages.

It also keeps **two** size counters per class, at `+0x12` and `+0x16` in its
class structure, each with its own pending-bit count. What the second area is
for is not yet established.
