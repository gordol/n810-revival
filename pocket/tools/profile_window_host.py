"""Compare retained-window preparation through the actual Host.flush path."""
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--shell',type=Path,default=Path(__file__).resolve().parents[1]/'shell')
p.add_argument('--adapter',type=Path,help='private candidate native_cells.py directory')
p.add_argument('--native',type=Path,required=True)
p.add_argument('--reference-plan',action='store_true',help='same native compositor with original Python window preparation')
p.add_argument('--updates',type=int,default=200)
p.add_argument('--case',choices=('status','scroll','mixed'),default='status')
a=p.parse_args()
if not 1<=a.updates<=100000:raise SystemExit('updates must be 1–100000')
sys.path.insert(0,str(a.shell))
if a.adapter:sys.path.insert(0,str(a.adapter))
from core import Host,Window
class Reference:
    def __init__(self,lib):
        self.__dict__.update((key,value) for key,value in vars(lib).items() if key!='window_host')
lines=('Observed host: n810 · connected','Sample age: 0s','','CPU busy: 35%',
       'Load (1/5/15 min): 0.5 0.4 0.4','RAM used / total: 62 / 128 MB',
       'RAM available: 50 MB','Swap used / total: 0 / 128 MB','','Battery: 65%',
       '','WiFi wlan0: connected','USB network usb0: connected',
       'Bluetooth RFCOMM: ready','Reticulum: ready','MeshCore: ready','','↑/↓ scroll · Tab section')
h=Host(100,30,[Window('System',3,2,70,24,lines=lines)])
h.background_enabled=False;h.shadow_enabled=False;h.animate=False
h.show_clock=False;h.show_connectivity=False;h.window_opacity=.88 if a.case=='mixed' else 1
assert h.enable_native(a.native),h.native_error
if not a.reference_plan:assert hasattr(h._native.lib,'window_host'),'candidate window-host kernel unavailable'
if a.reference_plan and hasattr(h._native.lib,'window_host'):h._native.lib=Reference(h._native.lib)
h.flush(3000);expected=('native_blend' if getattr(h._native,'supports_blend',lambda *_:False)(h,h.windows) else 'native_mixed') if a.case=='mixed' else 'native'
assert h.render_backend==expected,(h.render_backend,h.render_reason)
start=time.monotonic();cpu=time.process_time();digest=hashlib.sha256();size=0
for index in range(a.updates):
    if a.case=='scroll':
        changed=tuple('23:03:%02d RX JUPITR→APRS · record %d'%(row%60,index+row) for row in range(22))
        spans=tuple((row,0,8,'accent') for row in range(22))
    else:
        changed=list(lines);changed[1]='Sample age: '+str(index%10)+'s';spans=()
    h.content('System',index,changed,spans=spans)
    output,_,_=h.flush(3000);raw=output.encode();digest.update(raw);size+=len(raw)
    assert h.render_backend==expected
elapsed=time.monotonic()-start;used=time.process_time()-cpu
print(json.dumps(dict(case=a.case,reference_plan=a.reference_plan,updates=a.updates,
    wall_seconds=elapsed,cpu_seconds=used,cpu_ms_per_update=used*1000/a.updates,
    output_bytes=size,output_sha256=digest.hexdigest(),render_backend=h.render_backend,
    native_prepares=h._native.setup_calls,row_builds=h._native.row_builds,
    library_sha256=hashlib.sha256(a.native.read_bytes()).hexdigest(),maxrss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))
