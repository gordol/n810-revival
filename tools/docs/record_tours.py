#!/usr/bin/env python3
"""Record offline APRS/tmux and Pocket demonstrations from real PTY output.

Requires Pillow, ffmpeg, tmux (APRS), and the supplied public map packs.
Usage: python3 tools/docs/record_tours.py aprs --maps /path/to/map-packs
       python3 tools/docs/record_tours.py pocket
Output goes to docs/assets/demos; inspect it before updating review.json.
The 10 fps recording preserves elapsed time, using repeated frames when needed.
"""
from pathlib import Path
import argparse
import fcntl
import importlib.util
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pocket/shell/vendor/terminal'))
import pyte

class Screen(pyte.Screen):
    def report_device_status(self,mode,**kwargs):
        if not kwargs:super().report_device_status(mode)

COLORS=dict(zip(('black','red','green','brown','blue','magenta','cyan','white','brightblack','brightred','brightgreen','brightbrown','brightblue','brightmagenta','brightcyan','brightwhite'),('#000000','#cd0000','#00cd00','#cdcd00','#0000ee','#cd00cd','#00cdcd','#eeeeee','#666666','#ff5555','#55ff55','#ffff55','#5555ff','#ff55ff','#55ffff','#ffffff')))
def color(value,background=False):
    if value=='default':return '#10141a' if background else '#d8e1e8'
    return COLORS.get(value,'#'+value if len(value)==6 else '#cccccc')

def environment(directory):
    env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
    env.update(TERM='xterm-256color',COLORTERM='truecolor',PYTHONDONTWRITEBYTECODE='1',XDG_STATE_HOME=str(directory/'state'),XDG_CONFIG_HOME=str(directory/'config'),XDG_CACHE_HOME=str(directory/'cache'))
    return env

def record(command,env,name,title,cols,rows,steps,duration,directory,stop,poster_at,output=None):
    width,height=cols*10+40,rows*19+92
    font=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc' if Path('/System/Library/Fonts/Menlo.ttc').exists() else 'DejaVuSansMono.ttf',16)
    screen=Screen(cols,rows);stream=pyte.ByteStream(screen)
    master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
    process=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,cwd=ROOT,env=env,start_new_session=True);os.close(slave)
    out=Path(output) if output else ROOT/'docs/assets/demos';out.mkdir(parents=True,exist_ok=True)
    log=open(directory/'ffmpeg.log','wb')
    terminal_log=open(directory/'terminal-output.bin','wb')
    encoder=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{width}x{height}','-framerate','10','-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(out/(name+'.mp4'))],stdin=subprocess.PIPE,stderr=log)
    canvas=Image.new('RGB',(width,height),'#10141a');draw=ImageDraw.Draw(canvas);previous={};snapshots=[];frames=0;index=0;label='Start the local demonstration';start=time.monotonic();poster=False
    def send(data):os.write(master,data)
    try:
        while (elapsed:=time.monotonic()-start)<duration:
            if select.select([master],[],[],.005)[0]:
                try:data=os.read(master,1048576)
                except OSError:break
                if not data:break
                terminal_log.write(data)
                stream.feed(data)
                # Consume the queued redraw before rasterizing this sample.
                # A PTY read can stop between a clear and the following rows.
                drain_until=time.monotonic()+.05
                while time.monotonic()<drain_until and select.select([master],[],[],.002)[0]:
                    try:more=os.read(master,1048576)
                    except OSError:break
                    if not more:break
                    terminal_log.write(more);stream.feed(more)
            if index<len(steps) and elapsed>=steps[index][0]:
                if index:
                    snapshots.append({'time':round(elapsed,2),'label':label,'text':'\n'.join(screen.display)})
                    canvas.save(directory/f'step-{index:02}.png')
                _,label,action=steps[index]
                if isinstance(action,tuple) and action[0]=='resize':
                    _,columns,lines=action
                    if not (40<=columns<=cols and 14<=lines<=rows):raise ValueError('Resize exceeds the recording canvas')
                    screen.resize(lines=lines,columns=columns)
                    fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',lines,columns,0,0))
                    os.killpg(process.pid,signal.SIGWINCH)
                    canvas.paste('#10141a',(0,70,width,height));previous.clear()
                elif isinstance(action,bytes):send(action)
                elif action:action()
                index+=1
            if elapsed>=frames/10:
                draw.rectangle((0,0,width,70),fill='#10141a')
                draw.text((20,10),title,font=font,fill='#a9c9cf')
                draw.text((20,39),label,font=font,fill='#ffffff')
                for y in range(screen.lines):
                    for x in range(screen.columns):
                        c=screen.buffer[y][x]
                        if previous.get((x,y))==c:continue
                        previous[x,y]=c
                        fg,bg=color(c.fg),color(c.bg,True)
                        if c.reverse:fg,bg=bg,fg
                        xx,yy=20+x*10,72+y*19
                        # Clip glyph bearings to the terminal cell to prevent stale
                        # strokes from surviving in adjacent cells after a redraw.
                        tile=Image.new('RGB',(10,19),bg)
                        pen=ImageDraw.Draw(tile)
                        if c.data=='█':pen.rectangle((0,0,9,18),fill=fg)
                        elif c.data=='▀':pen.rectangle((0,0,9,8),fill=fg)
                        elif c.data=='▄':pen.rectangle((0,9,9,18),fill=fg)
                        elif c.data.strip():pen.text((0,-1),c.data,font=font,fill=fg)
                        canvas.paste(tile,(xx,yy))
                text='\n'.join(screen.display)
                if any(value and value.casefold() in text.casefold() for value in os.environ.get('DOCS_REJECT_TEXT','').split('|')):
                    raise RuntimeError('Excluded text appeared in a recording frame.')
                if 'Traceback (most recent call last)' in text:raise RuntimeError('Application traceback in recording; inspect local snapshots.')
                # Personal home paths are unsuitable for a documentation clip.
                if re.search(r'/Users/[^/\s]+/',text):raise RuntimeError('Personal home path in recording.')
                buffer=canvas.tobytes()
                target=int(elapsed*10)+1
                while frames<target:encoder.stdin.write(buffer);frames+=1
                if not poster and elapsed>=poster_at:
                    canvas.save(out/(name+'-poster.png'));poster=True
        snapshots.append({'time':round(time.monotonic()-start,2),'label':label,'text':'\n'.join(screen.display)})
        canvas.save(directory/'last.png')
        if process.poll() is None:
            try:send(stop)
            except OSError:pass
    finally:
        terminal_log.close()
        encoder.stdin.close();encoder.wait(timeout=30);log.close()
        deadline=time.monotonic()+3
        while process.poll() is None and time.monotonic()<deadline:
            if select.select([master],[],[],.05)[0]:
                try:os.read(master,65536)
                except OSError:break
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=4)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=4)
        os.close(master)
        (directory/'screens.json').write_text(json.dumps(snapshots,indent=2))
    if encoder.returncode:raise RuntimeError('Video encoder failed; inspect local log.')
    if elapsed<duration-.5:raise RuntimeError('Application exited before the tour completed; inspect local snapshots.')
    print(json.dumps({'video':name,'frames':frames,'seconds':frames/10,'process_exit':process.returncode,'review_directory':str(directory)}),flush=True)


def aprs(maps,directory):
    spec=importlib.util.spec_from_file_location('tmux_preview',ROOT/'tools/docs/tmux_preview.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cmd,env=module.prepare(directory,maps)
    def keys(*values):return lambda:subprocess.run(cmd+['send-keys','-t','aprs-demo:0.0',*values],env=env,check=True,capture_output=True)
    steps=[(0,'APRS map and retained packet panel',None),
           (4,'Down, Down: select an older station report',keys('Down','Down')),
           (9,'Down: select the next packet and its map marker',keys('Down')),
           (14,'x: open the selected packet in the inspector',keys('x')),
           (21,'x: close the inspector',keys('x')),
           (24,'Enter, p: focus the map and hide the packet panel',keys('Enter','p')),
           (28,'+: zoom from 80 km to 53 km',keys('+')),
           (32,'+: zoom again to 36 km',keys('+')),
           (36,'Right, Right, Up: pan the map',keys('Right','Right','Up')),
           (41,'Left, Left, Down: return to the previous center',keys('Left','Left','Down')),
           (45,'-, -: return to the 80 km overview',keys('-','-')),
           (49,'p: restore the packet panel',keys('p')),
           (53,'Ctrl-B, 1: switch to the Packets tmux window',b'\x021'),
           (58,'Ctrl-B, 2: switch to the Shell tmux window',b'\x022'),
           (62,'Ctrl-B, 0: return to the saved map workspace',b'\x020')]
    try:record(cmd+['attach-session','-t','aprs-demo'],env,'aprs-tmux-tour-20261104','APRS + tmux | public geography, fictional packets | laptop',120,44,steps,67,directory,b'\x02d',16)
    finally:subprocess.run(cmd+['kill-server'],env=env,capture_output=True)


def pocket(directory):
    command=[sys.executable,str(ROOT/'pocket/shell/launch.py'),'--state',str(directory/'session'),'--no-local-services','--no-native','--no-save','--effect','matrix']
    steps=[(0,'Matrix background with a fresh local desktop',None),
           (5,'Ctrl-], comma: find and open Calendar',b'\x1d,Calendar\r'),
           (10,'Ctrl-], Shift-2: send Calendar to desktop 2',b'\x1d@'),
           (14,'Comma: find and open Settings',b',Settings\r'),
           (20,'Ctrl-], d: open the desktop overview and window previews',b'\x1dd'),
           (27,'Tab: select another window preview',b'\t'),
           (31,'Enter: activate the selected window',b'\r'),
           (36,'Ctrl-], 3: show desktop 3 and its background',b'\x1d3'),
           (41,'b: turn the background off',b'b'),
           (45,'b: restore the Matrix background',b'b'),
           (50,'e: change the background to rain',b'e'),
           (56,'e: change the background to snow',b'e'),
           (62,'e: change the background to leaves',b'e'),
           (68,'e: change the background to flowers',b'e'),
           (74,'e: change the background to Flux',b'e'),
           (84,'d: show the window previews over Flux',b'd')]
    record(command,environment(directory),'pocket-overview-effects-20261104','Pocket overview + backgrounds | fresh local laptop session',120,40,steps,91,directory,b'q',24)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('tour',choices=('aprs','pocket'));parser.add_argument('--maps',type=Path)
    args=parser.parse_args()
    directory=Path(tempfile.mkdtemp(prefix='n810-record-'+args.tour+'-'))
    if args.tour=='aprs':
        if args.maps is None:parser.error('--maps is required for APRS')
        aprs(args.maps,directory)
    else:pocket(directory)
