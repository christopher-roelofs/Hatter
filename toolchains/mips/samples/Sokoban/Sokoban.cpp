#include "Magic.h"
#include "Debug.h"
#include "Sokoban.xh"
#include "Sokoban.xph"
#include "SokobanRules.h"
#undef CURRENTCLASS
#define CURRENTCLASS SokobanBoard

Private void SokoRead(Reference self, Soko::State &s) {
    SokobanBoard_Fields f;
    ReadFields(self, &f);
    s.level=f.level;
    s.player=f.player;
    s.boxA=f.boxA;
    s.boxB=f.boxB;
    s.moves=f.moves;
    s.pushes=f.pushes;
    s.undoPlayer=f.undoPlayer;
    s.undoA=f.undoA;
    s.undoB=f.undoB;
    s.undoMoves=f.undoMoves;
    s.undoPushes=f.undoPushes;
    s.canUndo=f.canUndo;
}
Private void SokoWrite(Reference self, const Soko::State &s) {
    SokobanBoard_Fields f;
    ReadFields(self, &f);
    f.level=s.level;
    f.player=s.player;
    f.boxA=s.boxA;
    f.boxB=s.boxB;
    f.moves=s.moves;
    f.pushes=s.pushes;
    f.undoPlayer=s.undoPlayer;
    f.undoA=s.undoA;
    f.undoB=s.undoB;
    f.undoMoves=s.undoMoves;
    f.undoPushes=s.undoPushes;
    f.canUndo=s.canUndo;
    WriteFields(self, &f);
}
Private void SokoStatus(const char *message) {
    ReplaceText(iStatus, NewTextFromLiteral((char *)message));
}
Private void SokoLabel(const char *message, Box *box) {
    PaintTextInBox(NewTextFromLiteral((char *)message), box, iBook12Center, kCenter);
}
Private void SokoCounter(const char *label, int value, Box *box) {
    char text[48], digits[12]; int n=0, d=0;
    while (*label && n<30) text[n++]=*label++;
    do { digits[d++]=(char)('0'+value%10); value/=10; } while(value && d<11);
    while(d) text[n++]=digits[--d];
    text[n]=0; SokoLabel(text,box);
}
Private Boolean SokoBounds(Reference self, Box *bounds) {
    ContentBox(self,bounds);
    bounds->bottom-=20*onePixel;
    return bounds->right-bounds->left>=8*16*onePixel &&
           bounds->bottom-bounds->top>=6*16*onePixel;
}
Method void SokobanBoard_Restart(Reference self) {
    Soko::State s; SokoRead(self,s); Soko::reset(s,s.level); SokoWrite(self,s);
    SokoStatus("Tap beside the player. Push every crate onto a dot.");
    DirtyContent(self);
}
Method void SokobanBoard_UndoMove(Reference self) {
    Soko::State s; SokoRead(self,s);
    if (Soko::undo(s)) {
        SokoWrite(self,s); SokoStatus("Last move undone. Undo keeps one move.");
        DirtyContent(self);
    } else SokoStatus("No move to undo.");
}
Method void SokobanBoard_NextPuzzle(Reference self) {
    Soko::State s; SokoRead(self,s);
    if (!Soko::advance(s)) { SokoStatus("Finish this puzzle before choosing Next."); return; }
    SokoWrite(self,s);
    SokoStatus("Tap beside the player. Push every crate onto a dot.");
    DirtyContent(self);
}
Method void SokobanBoard_Draw(Reference self) {
    InheritedDraw(self);
    Soko::State s; SokoRead(self,s);
    Box bounds, cell;
    if (!SokoBounds(self,&bounds)) return;
    long cw=(bounds.right-bounds.left)/8, ch=(bounds.bottom-bounds.top)/6;
    for (int p=0; p<48; ++p) {
        cell.left=bounds.left+(p%8)*cw; cell.top=bounds.top+(p/8)*ch;
        cell.right=cell.left+cw; cell.bottom=cell.top+ch;
        FillBox(CurrentCanvas(),CurrentClip(),&cell,
                Soko::wall(s.level,p)?rgbBlack:rgbWhite,pixelCopy);
        FrameBox(CurrentCanvas(),CurrentClip(),&cell,onePixel,rgbLtGray,pixelCopy);
        cell.left+=5*onePixel; cell.right-=5*onePixel;
        cell.top+=5*onePixel; cell.bottom-=5*onePixel;
        if (p==s.boxA || p==s.boxB) {
            FillBox(CurrentCanvas(),CurrentClip(),&cell,rgbLtGray,pixelCopy);
            FrameBox(CurrentCanvas(),CurrentClip(),&cell,2*onePixel,rgbBlack,pixelCopy);
            SokoLabel(Soko::goal(s.level,p)?"*":"X",&cell);
        } else if (p==s.player) {
            cell.left+=4*onePixel; cell.right-=4*onePixel;
            FillBox(CurrentCanvas(),CurrentClip(),&cell,rgbBlack,pixelCopy);
            SokoLabel("@",&cell);
        } else if (Soko::goal(s.level,p)) {
            long h=(cell.left+cell.right)/2, v=(cell.top+cell.bottom)/2;
            cell.left=h-3*onePixel; cell.right=h+3*onePixel;
            cell.top=v-3*onePixel; cell.bottom=v+3*onePixel;
            FillBox(CurrentCanvas(),CurrentClip(),&cell,rgbBlack,pixelCopy);
        }
    }
    cell.top=bounds.bottom; cell.bottom=bounds.bottom+20*onePixel;
    cell.left=bounds.left; cell.right=cell.left+100*onePixel;
    SokoCounter("Level ",s.level+1,&cell);
    cell.left=cell.right; cell.right+=100*onePixel; SokoCounter("Moves ",s.moves,&cell);
    cell.left=cell.right; cell.right=bounds.right; SokoCounter("Pushes ",s.pushes,&cell);
}
Method void SokobanBoard_Tap(Reference self, Reference touchInput) {
    Box bounds; Dot point;
    LatestPoint(touchInput,&point);
    if (!SokoBounds(self,&bounds) || point.h<bounds.left || point.h>=bounds.right ||
        point.v<bounds.top || point.v>=bounds.bottom) return;
    long cw=(bounds.right-bounds.left)/8, ch=(bounds.bottom-bounds.top)/6;
    int x=(point.h-bounds.left)/cw, y=(point.v-bounds.top)/ch;
    Soko::State s; SokoRead(self,s);
    if (Soko::won(s)) { SokoStatus("Puzzle complete! Choose Next, Undo or Restart."); return; }
    if (!Soko::move(s,x-s.player%8,y-s.player/8)) {
        SokoStatus("Tap one adjacent square. Crates can only be pushed."); return;
    }
    SokoWrite(self,s);
    SokoStatus(Soko::won(s)?
        (s.level==Soko::Levels-1?"All puzzles complete! Next starts again.":"Puzzle complete! Choose Next.") :
        "Push every crate onto a dot. Restart if a crate gets stuck.");
    DirtyContent(self);
}
#undef CURRENTCLASS
