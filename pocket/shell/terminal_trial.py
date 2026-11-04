"""Local attended-app proof from retained capture; no device or receiver owner.

Isolates only this test child's HOME to a temporary directory so an offline trial
cannot overwrite an operator's saved navigation. Normal Terminal hosting does not.
"""
import argparse,json,selectors,sys,tempfile,time,struct
from pathlib import Path
from core import Host,Window
from terminal_host import Terminal


def main():
    p=argparse.ArgumentParser();p.add_argument('--viewer',type=Path,required=True);p.add_argument('--maps',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--socket',help='optional local read-only REPLAY decoded socket');p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    value=json.loads(args.capture.read_text());value=value.get('data',value)
    with tempfile.TemporaryDirectory(prefix='legacy-aprs-test-') as temporary:
        folder=Path(temporary);history=folder/'retained.jsonl'
        rows=[dict(raw=(v.get('time','')[11:19]+' '+v['raw'])) for v in value['packets'] if v.get('raw')]
        history.write_text(''.join(json.dumps(v)+'\n' for v in rows))
        h=Host(160,48,[Window('APRS / retained capture',1,1,158,46)],animate=False)
        h.background_enabled=False;h.shadow_enabled=False;h.window_opacity=1
        selector=selectors.DefaultSelector();started=time.monotonic()
        argv=[sys.executable,str(args.viewer.resolve()),'--history',str(history),'--socket',args.socket or str(folder/'offline.sock'),'--maps',str(args.maps.resolve()),'--map-engine','next','--tui-theme','color']
        t=Terminal(h,h.windows[0].name,argv,selector,env={'HOME':str(folder)})
        def pump(seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                for key,mask in selector.select(.03):key.data.ready(mask)
                h.flush(1000000)
                if t.eof:raise RuntimeError('viewer exited: '+''.join(t.screen.display))
        try:
            pump(2)
            display='\n'.join(t.screen.display)
            assert 'Traceback' not in display and t.received>1000,display
            if args.socket:assert 'REPLAY' in display.upper(),'local replay socket did not deliver its status'
            first=time.monotonic()-started
            before=t.received;t.key('\t');pump(.2);assert t.child.poll() is None
            h.invalidate(h.windows[0].rect);h.windows[0].w=132;h.windows[0].h=40;h.invalidate(h.windows[0].rect);t.resize();pump(.5)
            assert t.size==(130,38)
            # Render retained Host cells using actual candidate font bitmaps.
            from PIL import Image,ImageDraw
            data=(Path(__file__).parent/'heard/fonts/n810-ui-512.psf').read_bytes();_,_,start,_,count,size,_,_=struct.unpack_from('<8I',data)
            glyphs={}
            for i,e in enumerate(data[start+count*size:].split(b'\xff')[:count]):
                for c in e.decode():glyphs[c]=data[start+i*size:start+(i+1)*size]
            image=Image.new('RGB',(h.width*8,h.height*16),(10,10,10));draw=ImageDraw.Draw(image)
            for i,cell in enumerate(h.front):
                if cell is None:continue
                x,y=(i%h.width)*8,(i//h.width)*16;code=cell.color
                fg=((code>>40)&255,(code>>32)&255,(code>>24)&255) if code>=1<<48 else (180,195,195)
                bg=((code>>16)&255,(code>>8)&255,code&255) if code>=1<<48 else (10,10,10)
                draw.rectangle((x,y,x+7,y+15),fill=bg)
                for yy,bits in enumerate(glyphs.get(cell.char,glyphs['?'])):
                    for xx in range(8):
                        if bits&(128>>xx):draw.point((x+xx,y+yy),fill=fg)
            image.save(args.out/'legacy-aprs.png')
            t.key('q')
            end=time.monotonic()+3
            while not t.eof and time.monotonic()<end:
                for key,mask in selector.select(.03):key.data.ready(mask)
            assert t.eof and t.child.wait(timeout=1)==0
            h.invalidate((0,0,1,1));h.flush(1000) # child Q did not close Host
            report=dict(source='local REPLAY socket + retained capture; original times, not live RF' if args.socket else 'retained capture, offline; not live RF',packets=len(rows),first_observed_seconds=first,received_bytes=t.received,patched_cells=t.patched,ready_calls=t.ready_calls,max_ready_ms=t.max_ready_ms,resize_content=list(t.size),tab_kept_child_alive=True,child_q_exit=0,host_survived=True,note='Two-second observation includes deliberate pump wait; not a startup latency benchmark. Ready timing includes parsing/dirty-cell conversion, excludes Host flush and terminal writes.')
            (args.out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
        finally:t.close();selector.close()


if __name__=='__main__':main()
