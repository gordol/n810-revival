# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the real desktop model with a native pixel platform; no desktop PTY."""
from pathlib import Path
import argparse,ctypes as C,importlib.util,json,sys,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'shell'))
from terminal import Geometry
from mbx import Renderer
from cells import style
from window import Window
class Platform:
 def __init__(self,font,library,display=None,*,frames=0,output=None,actions=(),require_gpu=True):
  self.require_gpu=require_gpu
  self.font=font;self.library=library;self.display=display;self.limit=frames;self.output=output;self.actions=list(actions);self.closed=False;self.frames=0;self.dirty=True;self.renderer=None;self.size=(100,30);self.report={};self.pixel_apps=[];self.compositor=None;self.resized=False;self.action_frame=-1
 def configure_registry(self,registry):
  def room_factory(host,**options):
   sys.path.insert(0,str(HERE.parent/'shell/apps/surface-renderer'))
   from room_pixels import PixelRoom
   room=PixelRoom(host,Path(self.library).resolve().parent/'room-pixels.so');self.pixel_apps.append(room);return room
  entry=registry.entries['surface-room'];registry.entries['surface-room']=entry._replace(factory=room_factory)
 def geometry(self):return Geometry(*self.size)
 def attach(self,host,panel,registry):
  self.host=host;self.panel=panel;self.registry=registry
  self.renderer=Renderer(host,self.font,self.library,require_gpu=self.require_gpu)
  if self.renderer.size!=self.size:self.renderer.resize(*self.size)
  if self.display and hasattr(self.display,'dynamic'):
   self.display.dynamic(True);width,height=self.display.size();self.resize(width//8,height//16)
  self.report['renderer']=self.renderer.renderer_name
  self.report['apps']=list(registry.entries);self.report['windows']=[w.name for w in host.windows]
 def resize(self,cols,rows):
  self.size=(max(40,min(512,cols)),max(14,min(256,rows)));self.renderer.resize(*self.size)
  if self.display and hasattr(self.display,"set_canvas"):self.display.set_canvas(self.size[0]*8,self.size[1]*16)
  self.resized=True;self.dirty=True
 def events(self):
  result=[]
  if self.actions and self.frames and self.action_frame!=self.frames:
   self.action_frame=self.frames
   action=self.actions.pop(0)
   if action.get('menu'):
    hit=next(hit for panel in self.panel.panels for hit in panel.hits if hit[3]=='key:,')
    result.append(('mouse',0,hit[0],hit[1],False))
   if 'launch' in action:self.launch(action['launch'])
   if 'window' in action:self.host.activate(action['window'])
   if 'app' in action:self.registry.open(action['app'])
   if 'resize' in action:self.resize(*action['resize'])
   if 'key' in action:result.append(('key',action['key']))
  if self.display:
   for event in self.display.events():
    kind=event['action']
    if kind=='quit':self.closed=True
    elif kind=='pointer':result.append(('mouse',event['button'],event['x']//8,event['y']//16,event.get('released',False)))
    elif kind=='cancel-input':result.extend([('focus',False),('focus',True)])
    elif kind=='focus':result.append(('focus',event['focused']))
    elif kind=='key':result.append(('terminal_key',event['key'],'release' if event.get('released') else 'press',0))
    elif kind=='resize':
     self.resize(event.get('columns',event.get('width',800)//8),event.get('rows',event.get('height',480)//16))
    elif kind=='redraw':self.host.invalidate((0,0,self.host.width,self.host.height));self.dirty=True
  return result
 def consume(self,changed,computed):
  _,_,drawn=self.renderer.consume_composed(changed,computed);self.dirty|=bool(drawn)
 def panel_text(self,x,y,text,foreground,background):
  r=self.renderer;fg,bg,_,_=style(foreground,'5;'+str(background))
  # UTF32 is text transport; glyph lookup and all pixel work remain native.
  encoded=text.encode('utf-32-le');data=C.create_string_buffer(encoded)
  if r.lib.pocket_mbx_text(r.handle,x,y,data,len(encoded)//4,r.font_codes,r.font_bits,len(r.font_codes),fg,bg):raise RuntimeError('Native panel text rejected')
  self.dirty=True
 def present(self,complete):
  visible=[app for app in self.pixel_apps if self.host.shown(self.host.window(app.name)) and not self.host.window(app.name).rolled]
  if not complete or not (self.dirty or any(app.pixel_dirty for app in visible)):return False
  if self.dirty:self.renderer.finish()
  self.dirty=False;self.frames+=1;frame=self.renderer.pixels
  if visible:
   if self.compositor is None:
    from pixel_compositor import Compositor
    self.compositor=Compositor(self.host,self.renderer,Path(self.library).resolve().parent/'room-pixels.so')
   frame=bytearray(frame);self.compositor.compose(frame,visible)
  if self.display:self.display.present(frame)
  if self.output:Path(self.output).write_bytes(frame)
  self.report['pixel_apps']={app.name:dict(frames=app.pixel_frames,jobs=app.pixel_jobs,cell_layer=self.host.window(app.name).layer is not None) for app in self.pixel_apps}
  self.report.setdefault('history',[]).append(dict(frame=self.frames,focus=self.host.focus,menu=bool(self.host.launcher_lines),size=self.size,errors={name:form.error for name,form in self.registry.forms.items() if form.error}))
  self.report.update(frames=self.frames,focus=self.host.focus,opened=[w.name for w in self.host.windows if w.opened],native=True,desktop_ansi=False)
  if self.limit and self.frames>=self.limit:self.closed=True
  return True
 def wait_timeout(self,timeout):return .016 if timeout is None else min(timeout,.016)
 def close(self):
  if self.compositor:self.compositor.close();self.compositor=None
  if self.renderer:self.renderer.close();self.renderer=None
  if self.display:self.display.close();self.display=None
 def run(self,argv):
  spec=importlib.util.spec_from_file_location('pocket_desktop_model',HERE.parent/'shell/desktop.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  try:return module.main(platform=self,argv=argv)
  finally:self.close()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--font',type=Path,required=True);parser.add_argument('--renderer-library',type=Path,required=True);parser.add_argument('--display-library',type=Path);parser.add_argument('--native-library',type=Path,required=True);parser.add_argument('--state',type=Path,required=True);parser.add_argument('--frames',type=int,default=0);parser.add_argument('--output',type=Path);parser.add_argument('--actions',type=Path);parser.add_argument('--report',type=Path)
 args,rest=parser.parse_known_args();args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
 display=Window(args.display_library) if args.display_library else None
 platform=Platform(args.font,args.renderer_library,display,frames=args.frames,output=args.output,actions=json.loads(args.actions.read_text()) if args.actions else ())
 try:platform.run(['--shell','--session',str(args.state/'desktop.json'),'--app-state',str(args.state),'--station-db',str(args.state/'directory.sqlite3'),'--native',str(args.native_library),*rest])
 finally:
  platform.close()
  if args.report:args.report.write_text(json.dumps(platform.report,indent=2)+'\n')
if __name__=='__main__':main()
