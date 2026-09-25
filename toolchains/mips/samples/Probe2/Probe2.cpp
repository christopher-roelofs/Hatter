/*------------------------------------------------------------------------------
#
#   Probe2
#
#   Does this ROM still carry the colour raster functions?
#
#   The SDK enumerates pix555Color and pix888Color and marks only pix444Color
#   as unsupported, and the Package Development Guide says outright that
#   "Magic Cap supports true color" even though no communicator has a colour
#   screen. Whether THIS build kept those raster cases is the open question,
#   and it decides whether the emulator can ever show colour.
#
#   So: reallocate the current canvas at 24 bits, fill a box in it with red,
#   and read the pixel back. On a 2-bit grey canvas the readback is a grey
#   level; if the colour raster functions are there it is red. The answer is
#   left in RAM for --dump-ram to find, because reallocating the screen's
#   pixels leaves nothing to look at.
------------------------------------------------------------------------------*/
#include "Magic.h"
#include "Debug.h"
#include "Probe2.xh"
#include "Probe2.xph"

#undef CURRENTCLASS
#define CURRENTCLASS Probe2

#ifndef PROBE_DEPTH
#define PROBE_DEPTH 2
#endif

Method void
Probe2_Draw(Reference self)
{
    Box         box, bounds;
    Dot         at;
    PixelDot    resolution;
    Reference   probe;
    Unsigned    readback, answer;

    ContentBox(self, &box);

    /* A canvas of our own. Reallocating the screen's pixels takes the system
     * down at depth 2 as readily as at 24, so that route said nothing. */
    bounds.left = 0;
    bounds.top = 0;
    bounds.right = 16 * onePixel;
    bounds.bottom = 16 * onePixel;
    resolution.h = onePixel;
    resolution.v = onePixel;

    probe = New(PixelMap_, nil);
    if (probe == nilObject) {
        /* white: New itself gave us nothing */
        FillBox(CurrentCanvas(), CurrentClip(), &box, rgbWhite, pixelCopy);
        return;
    }

    AllocPixels(probe, &bounds, resolution, PROBE_DEPTH, nilObject, Pixels_);
    FillBox(probe, nilObject, &bounds, rgbRed, pixelCopy);

    at.h = 4 * onePixel;
    at.v = 4 * onePixel;
    readback = ReadPixel(probe, &at);

    /* Report on the real screen, which is the only instrument that works:
     * a package's static data is not findable in a RAM dump. */
    if (readback == rgbRed)            answer = rgbBlack;    /* colour kept */
    else if (readback != 0)            answer = rgbDkGray;   /* quantised */
    else                               answer = rgbGray20;   /* read gave 0 */
    FillBox(CurrentCanvas(), CurrentClip(), &box, answer, pixelCopy);
}

#undef CURRENTCLASS
