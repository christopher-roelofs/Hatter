#!/usr/bin/env python3
"""Replay all twelve puzzles in an installed 68k guest.

Supply a snapshot showing a freshly opened Magic Sokoban level one. Screens,
logs and checkpoints go only to --out. Expected state comes from the shared
rules compiled for the host; it must appear in guest RAM after each action.
"""
import argparse
import ctypes
import re
import struct
import subprocess
import tempfile
import shlex
from pathlib import Path
from build import ROOT, SAMPLE, rules_c


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,default=ROOT/'out/magic-sokoban-68k/open.state')
    p.add_argument('--out',type=Path,default=ROOT/'out/magic-sokoban-68k/replay')
    p.add_argument('--engine',default='jit',choices=('jit','interpreter'))
    p.add_argument('--rom',type=Path,default=ROOT/'roms/Sony PIC 2000/PIC-2000.rom')
    p.add_argument('--adb-transport',type=int,help='Run APK libraries through android_runner on this ADB transport')
    p.add_argument('--resume-after',help='Resume after a previously passed checkpoint in --out')
    p.add_argument('--remote-dir',help='Existing dedicated /data/local/tmp directory with runner and APK libraries')
    args=p.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    adb=['adb','-t',str(args.adb_transport)] if args.adb_transport else None
    remote=args.remote_dir
    if adb:
        if not remote or not remote.startswith('/data/local/tmp/') or '..' in remote:
            p.error('--remote-dir must be a dedicated /data/local/tmp subdirectory')
        for source,name in ((args.rom,'test.rom'),(args.state,'initial.state')):
            subprocess.run(adb+['push',str(source),remote+'/'+name],check=True,stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix='soko68k-replay-') as tmp:
        tmp=Path(tmp)
        (tmp/'rules.c').write_text(rules_c()+'''
void reset(Soko_State *s,int n){Soko_reset(s,n);}
int move(Soko_State *s,int x,int y){return Soko_move(s,x,y);}
int undo(Soko_State *s){return Soko_undo(s);}
int advance(Soko_State *s){return Soko_advance(s);}
int won(Soko_State *s){return Soko_won(s);}
''')
        subprocess.run(['cc','-shared','-fPIC',str(tmp/'rules.c'),'-o',str(tmp/'rules.so')],check=True)
        rules=ctypes.CDLL(str(tmp/'rules.so'))
        state=(ctypes.c_int*12)(); rules.reset(state,0)
        subprocess.run(['g++','-std=c++98',str(SAMPLE/'tests/rules_test.cpp'),'-o',str(tmp/'solver')],check=True)
        solved=subprocess.check_output([str(tmp/'solver')],text=True)
        paths=re.findall(r'Level \d+: ([URDL]+)',solved)
        assert len(paths)==12
        current=args.state
        resuming=args.resume_after

        def run(tag,taps,engine=None):
            nonlocal current, resuming
            output=args.out/tag
            if resuming:
                if tag == resuming:
                    current=Path(str(output)+'.state')
                    if not current.is_file():
                        raise FileNotFoundError(current)
                    if adb:
                        subprocess.run(adb+['push',str(current),remote+'/current.state'],check=True)
                    resuming=None
                return
            command=[str(ROOT/'build/mcap'),'--rom',str(args.rom),
                     '--headless','--no-host-battery','--cpu-engine',engine or args.engine,
                     '--load-state',str(current),'-n',str(max(12000000,len(taps)*10000000+10000000)),
                     '--dump-fb',str(output)+'.pgm','--save-state',str(output)+'.state',
                     '--dump',f'0,4194304,{tmp}/ram.bin']
            for i,(x,y) in enumerate(taps):
                command+=['--tap',f'{1000000+i*10000000},1000000,{x},{y}']
            with Path(str(output)+'.log').open('w') as log:
                if adb:
                    command[0]=remote+'/android_runner'
                    replacements={str(args.rom):remote+'/test.rom',str(current):remote+('/initial.state' if current==args.state else '/current.state'),
                                  str(output)+'.pgm':remote+'/screen.pgm',str(output)+'.state':remote+'/next.state',
                                  f'0,4194304,{tmp}/ram.bin':f'0,4194304,{remote}/ram.bin'}
                    command=[replacements.get(arg,arg) for arg in command]
                    shell='cd '+shlex.quote(remote)+' && LD_LIBRARY_PATH='+shlex.quote(remote)+' '+shlex.join(command)
                    subprocess.run(adb+['shell',shell],stdout=log,stderr=subprocess.STDOUT,check=True)
                    for source,target in (('ram.bin',tmp/'ram.bin'),('screen.pgm',Path(str(output)+'.pgm')),('next.state',Path(str(output)+'.state'))):
                        subprocess.run(adb+['pull',remote+'/'+source,str(target)],check=True,stdout=subprocess.DEVNULL,stderr=log)
                    subprocess.run(adb+['shell','mv',remote+'/next.state',remote+'/current.state'],check=True)
                else:
                    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
            expected=struct.pack('>12i',*state)
            if expected not in (tmp/'ram.bin').read_bytes():
                raise AssertionError(f'{tag}: guest does not contain expected fields {list(state)}')
            current=Path(str(output)+'.state')
            print(f'PASS {tag}: level={state[0]+1} moves={state[4]} pushes={state[5]}',flush=True)

        def move(direction):
            dx,dy={'U':(0,-1),'R':(1,0),'D':(0,1),'L':(-1,0)}[direction]
            x,y=state[1]%8+dx,state[1]//8+dy
            assert rules.move(state,dx,dy)
            return round(45+(x+.5)*37.5),round(49+(y+.5)*(178/6))

        run('premature-next',[(410,198)])
        run('push',[move('U')])
        assert rules.undo(state); run('undo',[(410,153)])
        run('restore-interpreter',[],engine='interpreter')
        run('push-again',[move('U')])
        rules.reset(state,0); run('restart',[(410,108)])
        for level,path in enumerate(paths):
            for start in range(0,len(path),12):
                taps=[move(d) for d in path[start:start+12]]
                run(f'level{level+1}-part{start//12+1}',taps)
            assert rules.won(state)
            if level==0:
                assert rules.undo(state); run('undo-win',[(410,153)])
                run('win-again',[move(path[-1])]); assert rules.won(state)
            assert rules.advance(state)
            run('wrap' if level==11 else f'next{level+2}',[(410,198)])
        run('wrap-restore',[],engine='interpreter')
        if resuming:
            raise ValueError(f'Unknown checkpoint: {resuming}')
        print('PASS: all 12 levels, Next gating, Undo, Restart, wrap and cross-engine restore')


if __name__=='__main__': main()
