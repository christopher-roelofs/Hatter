/* Declarations for the HelloWorld port; selectors come from the SDK .cdef
 * files through the stub generator.  Types follow SDK Generic.h. */
typedef unsigned int Reference;
typedef unsigned char Boolean;
typedef unsigned int Unsigned;
typedef int Signed;
typedef int Micron;
typedef unsigned long ulong;
typedef struct { Micron left, top, right, bottom; } Box;
#define Method
enum { partContent = 1, partAltContent = 3 };          /* Utilities.h */
enum { pixelCopy = 0x0, pixelDither = 0x20 };           /* Graphics.h */
Unsigned PartColor(Reference self, Signed part);
Boolean Highlighted(Reference self);
void ContentBox(Reference self, Box *box);
void FillBox(Reference canvas, Reference clip, const Box *box, Unsigned colorant, Signed mode);
Reference CurrentCanvas(void);
Reference CurrentClip(void);
