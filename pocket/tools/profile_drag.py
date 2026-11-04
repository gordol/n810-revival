"""Replay window-manager drags through Host.pointer and bounded native redraws.

Times exclude touch acquisition and terminal/display writes. Output hashes cover
all emitted ANSI; final rectangles verify the release coordinate is committed.
"""
import argparse,sys,time,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--shell',type=Path,default=Path(__file__).resolve().parents[1]/'shell')
p.add_argument('--native',type=Path,required=True)
p.add_argument('--snap',action='store_true')
p.add_argument('--hold',type=float,default=0.,help='seconds held between motion updates')
a=p.parse_args()
if not 0<=a.hold<=1:p.error('hold must be 0–1 second')
sys.path.insert(0,str(a.shell))
from core import Host,Window
for resize in (False,True):
 h=Host(100,29,[Window('Other',1,1,48,18,lines=['Retained other window']*16),Window('System',20,5,49,17,lines=['Observed host: Nokia','Sample age: 0s','Battery 65%']*5)])
 h.background_enabled=False;h.shadow_enabled=False;h.window_opacity=1;h.animate=False;h.snap_windows=a.snap;h.show_clock=False;h.show_connectivity=False
 assert h.enable_native(a.native),h.native_error
 while h.damage:h.flush(2900)
 w=h.window('System');x,y=(w.x+w.w-1,w.y+w.h-1) if resize else (w.x+25,w.y)
 h.pointer(0,x,y);assert h.drag,(resize,h.focus)
 rows=[]
 for step,(dx,dy) in enumerate(((0,0),(1,1),(2,2),(4,3),(6,2),(8,1),(9,0))):
  if a.hold:time.sleep(a.hold)
  start=time.monotonic();cpu=time.process_time();h.pointer(32,x+dx,y+dy);digest=hashlib.sha256();calls=0;backends=set();changed=0
  while h.damage or h.latest is not None:
   output,c,n=h.flush(2900,max_seconds=.012);digest.update(output.encode());calls+=1;changed+=c;backends.add(h.render_backend)
  rows.append(dict(step=step,cpu_seconds=time.process_time()-cpu,wall_seconds=time.monotonic()-start,batches=calls,changed=changed,backends=sorted(backends),output_sha256=digest.hexdigest()))
 release_start=time.monotonic();release_cpu=time.process_time();h.pointer(0,x+dx,y+dy,True);release_hash=hashlib.sha256()
 while h.damage:
  output,_,_=h.flush(2900,max_seconds=.012);release_hash.update(output.encode())
 print(json.dumps(dict(resize=resize,snap=a.snap,hold_seconds=a.hold,steps=rows,final_rect=h.window('System').rect,release_cpu_seconds=time.process_time()-release_cpu,release_wall_seconds=time.monotonic()-release_start,release_sha256=release_hash.hexdigest())),flush=True)
