/* HelloWorld's Greeter_Draw (SDK Samples/HelloWorld/HelloWorld.cpp), as C. */
#include "mcap_hello.h"

Method void
Greeter_Draw(Reference self)
{
    Box     ourContentBox;
    ulong   color;

    color = PartColor(self, Highlighted(self) ? partAltContent : partContent);
    ContentBox(self, &ourContentBox);
    FillBox(CurrentCanvas(), CurrentClip(), &ourContentBox, color, pixelDither | pixelCopy);
}
