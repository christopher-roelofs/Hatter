#include "Magic.h"
#include "Debug.h"

#include "StarshipCourier.xh"
#include "StarshipCourier.xph"

#define kGridWidth 10
#define kGridHeight 6
#define kMissionScore 50

typedef CourierBoard_Fields* CourierBoardPtr;

#undef CURRENTCLASS
#define CURRENTCLASS CourierBoard

Private long
CourierAbs(long value)
{
    return value < 0 ? -value : value;
}

Private void
CourierSetStatus(Reference text)
{
    ReplaceText(iStatus, text);
}

Private void
DrawNumber(long value, Dot *where)
{
    Reference text;
    TextRange range;

    text = Numeral(value);
    EntireTextRange(text, &range);
    TextDraw(text, &range, iBook12, where);
}

// Keep drawing and hit testing on the same grid; reserve the footer for counters.
Private Boolean
CourierGridBounds(Reference self, Box *bounds)
{
    ContentBox(self, bounds);
    bounds->bottom -= 20 * onePixel;
    return bounds->right - bounds->left >= kGridWidth * 16 * onePixel &&
           bounds->bottom - bounds->top >= kGridHeight * 16 * onePixel;
}

Method void
CourierBoard_ResetGame(Reference self)
{
    CourierBoardPtr fields = BeginModifyFields(self);
    fields->playerX = 1;
    fields->playerY = 1;
    fields->enemyX = 8;
    fields->enemyY = 4;
    fields->score = 0;
    fields->energy = 20;
    fields->turn = 0;
    fields->gameOver = false;
    fields->pulse = 0;
    EndModifyFields(self);
    CourierSetStatus(iInitialStatus);
    DirtyContent(self);
    PlaySound(iTouchSound);
}

Method void
CourierBoard_Draw(Reference self)
{
    CourierBoard_Fields fields;
    Box bounds, cell;
    long cellWidth, cellHeight;
    long x, y;
    Dot where;
    ulong cellColor;

    InheritedDraw(self);
    ReadFields(self, &fields);
    if (!CourierGridBounds(self, &bounds)) return;
    cellWidth = (bounds.right - bounds.left) / kGridWidth;
    cellHeight = (bounds.bottom - bounds.top) / kGridHeight;

    FillBox(CurrentCanvas(), CurrentClip(), &bounds, rgbGray20, pixelCopy);

    for (y = 0; y < kGridHeight; ++y) {
        for (x = 0; x < kGridWidth; ++x) {
            cell.left = bounds.left + x * cellWidth;
            cell.top = bounds.top + y * cellHeight;
            cell.right = cell.left + cellWidth;
            cell.bottom = cell.top + cellHeight;
            cellColor = ((x + y) & 1) ? rgbLtGray : rgbGray20;
            FillBox(CurrentCanvas(), CurrentClip(), &cell, cellColor, pixelCopy);
            FrameBox(CurrentCanvas(), CurrentClip(), &cell, onePixel, rgbBlack, pixelCopy);
        }
    }

    cell.left = bounds.left + fields.playerX * cellWidth + 4 * onePixel;
    cell.top = bounds.top + fields.playerY * cellHeight + 4 * onePixel;
    cell.right = bounds.left + (fields.playerX + 1) * cellWidth - 4 * onePixel;
    cell.bottom = bounds.top + (fields.playerY + 1) * cellHeight - 4 * onePixel;
    FillBox(CurrentCanvas(), CurrentClip(), &cell, rgbBlack, pixelCopy);

    cell.left = bounds.left + fields.enemyX * cellWidth + 7 * onePixel;
    cell.top = bounds.top + fields.enemyY * cellHeight + 7 * onePixel;
    cell.right = bounds.left + (fields.enemyX + 1) * cellWidth - 7 * onePixel;
    cell.bottom = bounds.top + (fields.enemyY + 1) * cellHeight - 7 * onePixel;
    FrameBox(CurrentCanvas(), CurrentClip(), &cell, 2 * onePixel,
             fields.gameOver ? rgbGray20 : rgbBlack, pixelCopy);

    where.h = bounds.left;
    where.v = bounds.bottom + 12 * onePixel;
    DrawNumber(fields.score, &where);
    where.h = bounds.left + 70 * onePixel;
    DrawNumber(fields.energy, &where);
    where.h = bounds.left + 140 * onePixel;
    DrawNumber(fields.turn, &where);
}

Method void
CourierBoard_Tap(Reference self, Reference touchInput)
{
    CourierBoard_Fields state;
    CourierBoardPtr fields = &state;
    Box bounds;
    Dot point;
    long cellWidth, cellHeight;
    long x, y, dx, dy;
    long enemyX, enemyY;
    Reference statusText;
    Reference sound;

    LatestPoint(touchInput, &point);
    if (!CourierGridBounds(self, &bounds)) return;
    cellWidth = (bounds.right - bounds.left) / kGridWidth;
    cellHeight = (bounds.bottom - bounds.top) / kGridHeight;
    if (cellWidth <= 0 || cellHeight <= 0) {
        return;
    }
    x = (point.h - bounds.left) / cellWidth;
    y = (point.v - bounds.top) / cellHeight;

    ReadFields(self, &state);
    if (state.gameOver || point.h < bounds.left || point.h >= bounds.right ||
        point.v < bounds.top || point.v >= bounds.bottom ||
        x < 0 || x >= kGridWidth || y < 0 || y >= kGridHeight) {
        return;
    }

    dx = x - state.playerX;
    dy = y - state.playerY;
    if (CourierAbs(dx) + CourierAbs(dy) != 1) {
        CourierSetStatus(iBlocked);
        PlaySound(iErrorSound);
        return;
    }

    // Mutate a local copy, then commit before text, sound or redraw operations.
    if (x == fields->enemyX && y == fields->enemyY) {
        fields->score += 10;
        enemyX = (fields->enemyX + 3 + fields->turn) % kGridWidth;
        enemyY = (fields->enemyY + 2) % kGridHeight;
        fields->enemyX = enemyX;
        fields->enemyY = enemyY;
        statusText = iAttack;
        sound = iMagicSound;
    } else {
        fields->playerX = x;
        fields->playerY = y;
        fields->energy -= 1;
        statusText = iMoved;
        sound = iTouchSound;

        if (fields->energy <= 0) {
            fields->gameOver = true;
            statusText = iLost;
            sound = iErrorSound;
        }
    }

    fields->turn += 1;
    if (fields->score >= kMissionScore) {
        fields->gameOver = true;
        statusText = iWon;
    }
    WriteFields(self, &state);
    CourierSetStatus(statusText);
    PlaySound(sound);
    DirtyContent(self);
}

#undef CURRENTCLASS
