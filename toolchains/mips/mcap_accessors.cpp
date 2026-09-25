/* Field accessor runtime for host-built packages: a port of the SDK's
 * SeparatePackageLib.o helpers (out/rosemary-inspection/accessor-helpers.txt).
 *
 * A Reference points at a word holding the object's address; the word
 * before it is a tag.  Reads: tag bit 31 clear -> direct; (tag >> 24) & 7
 * == 1 -> follow the indirection; otherwise the ROM's Internal* intrinsic.
 * Writes test tag bit 30 instead.  Reads of references and selectors that
 * come back negative are converted with InternalMake*UsableByAddress(objectPointer, value).
 */
#include "Magic.h"

#define TAG(ref) (((Signed *)(ref))[-1])
#define OBJ(ref) (*(char **)(ref))
#define INDIRECT(tag) ((((Unsigned)(tag)) >> 24 & 7) == 1)

#define READER(NAME, T, LOAD, SLOW, MASK)                                    \
    extern "C" T NAME(Reference ref, int offset)                             \
    {                                                                        \
        for (;;) {                                                           \
            if (!ref) return 0;                                              \
            Signed tag = TAG(ref);                                           \
            if (tag >= 0) return LOAD(OBJ(ref) + offset);                    \
            if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }        \
            return (T)(SLOW(ref, offset) MASK);                              \
        }                                                                    \
    }
#define LDB(p) (*(uchar *)(p))
#define LDH(p) (*(ushort *)(p))
#define LDW(p) (*(Unsigned *)(p))
#define LDP(p) (*(Pointer *)(p))
READER(ReadByteField, uchar, LDB, InternalReadByteField, & 0xff)
READER(ReadHalfwordField, ushort, LDH, InternalReadHalfwordField, & 0xffff)
READER(ReadWordField, Unsigned, LDW, InternalReadWordField, )
READER(ReadPointerField, Pointer, LDP, InternalReadPointerField, )

extern "C" Boolean ReadBitField(Reference ref, int offset, int bitNum)
{
    for (;;) {
        if (!ref) return 0;
        Signed tag = TAG(ref);
        if (tag >= 0) return (LDB(OBJ(ref) + offset) >> bitNum) & 1;
        if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }
        return InternalReadBitField(ref, offset, bitNum) & 0xff;
    }
}

/* Reference-like fields: negative stored values are ROM references made usable by address. */
#define REFREADER(NAME, T, ID, CONVERT, SLOW)                                    \
    extern "C" T NAME(Reference ref, int offset)                             \
    {                                                                        \
        for (;;) {                                                           \
            if (!ref) return (T)0;                                           \
            Signed tag = TAG(ref);                                           \
            if (tag >= 0) {                                                  \
                char *obj = OBJ(ref);                                        \
                Signed v = *(Signed *)(obj + offset);                        \
                if (v >= 0) return (T)v;                                     \
                return (T)CONVERT((ReadOnlyPointer)obj, (ID)v);                  \
            }                                                                \
            if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }        \
            return (T)SLOW(ref, offset);                                     \
        }                                                                    \
    }
REFREADER(ReadReferenceField, Reference, ROMReference, InternalMakeROMReferenceUsableByAddress, InternalReadReferenceField)
REFREADER(ReadClassSelectorField, ClassNumber, ClassID, InternalMakeClassIDUsableByAddress, InternalReadClassSelectorField)
REFREADER(ReadOperationSelectorField, OperationNumber, OperationID, InternalMakeOperationIDUsableByAddress, InternalReadOperationSelectorField)
REFREADER(ReadClassOperationSelectorField, ClassOperationNumber, ClassOperationID, InternalMakeClassOperationIDUsableByAddress, InternalReadClassOperationSelectorField)
REFREADER(ReadIntrinsicSelectorField, IntrinsicNumber, IntrinsicID, InternalMakeIntrinsicIDUsableByAddress, InternalReadIntrinsicSelectorField)

#define WRITER(NAME, T, STORE, SLOW)                                         \
    extern "C" void NAME(Reference ref, int offset, T value)                 \
    {                                                                        \
        for (;;) {                                                           \
            if (!ref) return;                                                \
            Signed tag = TAG(ref);                                           \
            if (!(tag & 0x40000000)) { STORE(OBJ(ref) + offset, value); return; } \
            if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }        \
            SLOW(ref, offset, value); return;                                \
        }                                                                    \
    }
#define STB(p, v) (*(uchar *)(p) = (uchar)(v))
#define STH(p, v) (*(ushort *)(p) = (ushort)(v))
#define STW(p, v) (*(Unsigned *)(p) = (Unsigned)(v))
#define STP(p, v) (*(Pointer *)(p) = (Pointer)(v))
WRITER(WriteByteField, uchar, STB, InternalWriteByteField)
WRITER(WriteHalfwordField, ushort, STH, InternalWriteHalfwordField)
WRITER(WriteWordField, Unsigned, STW, InternalWriteWordField)
WRITER(WritePointerField, Pointer, STP, InternalWritePointerField)
WRITER(WriteReferenceField, Reference, STW, InternalWriteReferenceField)
WRITER(WriteClassSelectorField, ClassNumber, STW, InternalWriteClassSelectorField)
WRITER(WriteOperationSelectorField, OperationNumber, STW, InternalWriteOperationSelectorField)
WRITER(WriteClassOperationSelectorField, ClassOperationNumber, STW, InternalWriteClassOperationSelectorField)
WRITER(WriteIntrinsicSelectorField, IntrinsicNumber, STW, InternalWriteIntrinsicSelectorField)

extern "C" void WriteBitField(Reference ref, int offset, int bitNum, Boolean value)
{
    for (;;) {
        if (!ref) return;
        Signed tag = TAG(ref);
        if (!(tag & 0x40000000)) {
            uchar *p = (uchar *)(OBJ(ref) + offset);
            *p = (*p & ~(1 << bitNum)) | ((value & 0xff) << bitNum);
            return;
        }
        if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }
        InternalWriteBitField(ref, offset, bitNum, value & 0xff); return;
    }
}

/* Object body access (Accessors.h BeginModifyFields / PeekFields): the
 * object pointer for direct RAM objects, else the ROM's Internal* helpers;
 * a nil reference reports iCannotFindObject. */
extern "C" uchar * BeginModifyFlavor(Reference ref)
{
    for (;;) {
        if (!ref) { Fail(iCannotFindObject); return 0; }
        Signed tag = TAG(ref);
        if (!(tag & 0x40000000)) return (uchar *)OBJ(ref);
        if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }
        return (uchar *)InternalBeginModifyFlavor(ref);
    }
}

extern "C" const uchar * PeekFlavor(Reference ref)
{
    for (;;) {
        if (!ref) { Fail(iCannotFindObject); return 0; }
        Signed tag = TAG(ref);
        if (tag >= 0) return (uchar *)OBJ(ref);
        if (INDIRECT(tag)) { ref = *(Reference *)ref; continue; }
        return (const uchar *)InternalPeekFlavor(ref);
    }
}

extern "C" const uchar * PeekUsableFlavor(Reference ref)
{
    for (;;) {
        if (!ref) { Fail(iCannotFindObject); return 0; }
        Signed tag = TAG(ref);
        if (!(tag & 0x40000000)) return (uchar *)OBJ(ref);
        Unsigned k = ((Unsigned)tag >> 24) & 7;
        if (k == 1) { ref = *(Reference *)ref; continue; }
        if (k == 2) return (uchar *)OBJ(ref);
        return (const uchar *)InternalPeekUsableFlavor(ref);
    }
}
