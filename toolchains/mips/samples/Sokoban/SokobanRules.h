#ifndef SOKOBAN_RULES_H
#define SOKOBAN_RULES_H
// Freestanding C++98: shared by the guest and host tests. No ROM dependencies.
namespace Soko {
enum { Width = 8, Height = 6, Levels = 12 };
struct State {
    int level;
    int player;
    int boxA;
    int boxB;
    int moves;
    int pushes;
    int undoPlayer;
    int undoA;
    int undoB;
    int undoMoves;
    int undoPushes;
    int canUndo;
};
static const char maps[Levels][49] = {
    "########" "#  . . #" "#  $ $ #" "#  @   #" "#      #" "########",
    "########" "# .  . #" "# $  $ #" "#  ##  #" "#  @   #" "########",
    "########" "#   .  #" "# $ #  #" "# . $  #" "#  @   #" "########",
    "########" "#      #" "#  #@  #" "# .$ $##" "#   . ##" "########",
    "########" "#  #   #" "## $  @#" "#.. $  #" "#   #  #" "########",
    "########" "# ## #.#" "#      #" "# $  $ #" "#    @.#" "########",
    "########" "##  .  #" "#     @#" "# $ ## #" "# $  . #" "########",
    "########" "#    . #" "#  $ # #" "#  # # #" "#@$.  ##" "########",
    "########" "#@ #  .#" "#$ $ # #" "#.     #" "#      #" "########",
    "########" "# @    #" "# $ #  #" "# #$   #" "#  ..# #" "########",
    "########" "# @.   #" "#  $   #" "#.# $  #" "#  ##  #" "########",
    "########" "# .. # #" "# $    #" "# $#   #" "# @    #" "########"
};
static inline bool wall(int level, int pos) {
    return pos < 0 || pos >= Width * Height || maps[level][pos] == '#';
}
static inline bool goal(int level, int pos) { return maps[level][pos] == '.'; }
static inline bool won(const State &s) { return goal(s.level,s.boxA) && goal(s.level,s.boxB); }
static inline void reset(State &s, int level) {
    s.level = level < 0 || level >= Levels ? 0 : level;
    s.player = s.boxA = s.boxB = 0;
    for (int p = 0; p < Width * Height; ++p) {
        if (maps[s.level][p] == '@') s.player = p;
        if (maps[s.level][p] == '$') { if (!s.boxA) s.boxA=p; else s.boxB=p; }
    }
    s.moves=s.pushes=s.canUndo=0;
    s.undoPlayer=s.player; s.undoA=s.boxA; s.undoB=s.boxB;
    s.undoMoves=s.undoPushes=0;
}
static inline bool advance(State &s) {
    if (!won(s)) return false;
    reset(s, (s.level + 1) % Levels);
    return true;
}
static inline bool move(State &s, int dx, int dy) {
    if (won(s) || !((dx == 0 && (dy == 1 || dy == -1)) ||
                   (dy == 0 && (dx == 1 || dx == -1)))) return false;
    int x=s.player%Width+dx, y=s.player/Width+dy;
    if (x<0 || x>=Width || y<0 || y>=Height) return false;
    int next=y*Width+x, beyond=next+dy*Width+dx;
    if (wall(s.level,next)) return false;
    bool push=next==s.boxA || next==s.boxB;
    if (push && (x+dx<0 || x+dx>=Width || y+dy<0 || y+dy>=Height ||
        wall(s.level,beyond) || beyond==s.boxA || beyond==s.boxB)) return false;
    s.undoPlayer=s.player; s.undoA=s.boxA; s.undoB=s.boxB;
    s.undoMoves=s.moves; s.undoPushes=s.pushes; s.canUndo=1;
    if (push) { if (next==s.boxA) s.boxA=beyond; else s.boxB=beyond; ++s.pushes; }
    s.player=next; ++s.moves;
    return true;
}
static inline bool undo(State &s) {
    if (!s.canUndo) return false;
    s.player=s.undoPlayer; s.boxA=s.undoA; s.boxB=s.undoB;
    s.moves=s.undoMoves; s.pushes=s.undoPushes; s.canUndo=0;
    return true;
}
}
#endif
