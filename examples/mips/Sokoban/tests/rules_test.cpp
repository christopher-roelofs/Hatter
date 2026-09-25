#include "../SokobanRules.h"
#include <cassert>
#include <iostream>
#include <map>
#include <queue>
#include <string>
static int key(const Soko::State &s) {
    int a=s.boxA<s.boxB?s.boxA:s.boxB, b=s.boxA<s.boxB?s.boxB:s.boxA;
    return (s.player*48+a)*48+b;
}
static const int dx[4]={0,1,0,-1}, dy[4]={-1,0,1,0};
int main() {
    assert(Soko::Levels==12);
    Soko::State s; Soko::reset(s,0);
    assert(!Soko::undo(s));
    assert(!Soko::move(s,1,1) && s.moves==0);
    assert(Soko::move(s,0,-1) && s.boxA==11 && s.pushes==1 && s.moves==1);
    assert(!Soko::move(s,0,-1) && s.moves==1 && s.canUndo==1);
    assert(Soko::undo(s) && s.boxA==19 && s.player==27 && s.moves==0 && s.pushes==0);
    assert(!Soko::undo(s));
    s.boxA=19; s.boxB=11;
    assert(!Soko::move(s,0,-1)); // cannot push two crates
    Soko::reset(s,0); s.player=8; // boundary guard, even for malformed position
    assert(!Soko::move(s,-1,0));
    Soko::reset(s,99); assert(s.level==0 && !s.canUndo);
    for (int level=0; level<Soko::Levels; ++level) {
        Soko::reset(s,level);
        assert(!Soko::advance(s) && s.level==level);
        assert(std::string(Soko::maps[level]).size()==48);
        for (int previous=0; previous<level; ++previous)
            assert(std::string(Soko::maps[level])!=Soko::maps[previous]);
        assert(!Soko::wall(level,s.player) && s.boxA!=s.boxB);
        int goals=0, crates=0, players=0;
        for(int i=0;i<48;++i) {
            assert(std::string("# .$@").find(Soko::maps[level][i])!=std::string::npos);
            if(i<8 || i>=40 || i%8==0 || i%8==7) assert(Soko::wall(level,i));
            goals+=Soko::maps[level][i]=='.';
            crates+=Soko::maps[level][i]=='$';
            players+=Soko::maps[level][i]=='@';
        }
        assert(goals==2 && crates==2 && players==1);
        std::queue<Soko::State> q; std::map<int,std::string> paths;
        q.push(s); paths[key(s)]="";
        bool solved=false;
        while(!q.empty()) {
            s=q.front(); q.pop();
            std::string path=paths[key(s)];
            if(Soko::won(s)) {
                assert(!Soko::move(s,0,1));
                assert(Soko::undo(s) && !Soko::won(s));
                int d=std::string("URDL").find(path[path.size()-1]);
                assert(Soko::move(s,dx[d],dy[d]) && Soko::won(s));
                std::cout<<"Level "<<level+1<<": "<<path<<" ("<<s.moves<<" moves, "<<s.pushes<<" pushes)\n";
                assert(Soko::advance(s));
                assert(s.level==(level+1)%Soko::Levels);
                assert(!s.canUndo && !s.moves && !s.pushes && !Soko::won(s));
                solved=true; break;
            }
            for(int d=0;d<4;++d) {
                Soko::State n=s;
                if(Soko::move(n,dx[d],dy[d]) && !paths.count(key(n))) {
                    paths[key(n)]=path+"URDL"[d]; q.push(n);
                }
            }
        }
        assert(solved);
        Soko::reset(s,level); assert(s.moves==0 && s.pushes==0 && !s.canUndo && !Soko::won(s));
    }
}
