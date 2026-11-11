# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the real desktop model with a native pixel platform; no desktop PTY."""
from pathlib import Path
import argparse,ctypes as C,importlib.util,json,os,sys,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'shell'))
from terminal import Geometry
from mbx import Renderer
from cells import style
from window import Window
DEVELOPMENT = True  # Removed by the release exporter.

class Platform:
 if DEVELOPMENT:history_capacity=128
 def __init__(self,font,library,display=None,*,frames=0,output=None,actions=(),require_gpu=True,font_mode="console",cell_renderer="gpu",diagnostics=False):
  self.diagnostics=DEVELOPMENT and diagnostics
  self.cell_renderer=cell_renderer
  self.require_gpu=require_gpu;self.font_mode=font_mode
  from presentation_text import create
  self.presentation_text=create(display,font_mode)
  self.font=font;self.library=library;self.display=display;self.limit=frames;self.output=output;self.actions=list(actions) if DEVELOPMENT else [];self.closed=False;self.frames=0;self.dirty=True;self.renderer=None;self.size=(100,30);self.report={};self.pixel_apps=[];self.compositor=None;self.gpu_context=None;self.resized=False;self.action_frame=-1
 def configure_registry(self,registry):
  if 'symbian' in registry.entries and os.environ.get('POCKET_SYMBIAN_WINDOWS')=='1':
   entry=registry.entries['symbian'];original_symbian=entry.factory
   def symbian_factory(host,**options):
    host.symbian_window=lambda application:self.open_symbian_window(host,application)
    return original_symbian(host,**options)
   registry.entries['symbian']=entry._replace(factory=symbian_factory)
  def room_factory(host,**options):
   sys.path.insert(0,str(HERE.parent/'shell/apps/surface-renderer'))
   from room_pixels import PixelRoom
   room=PixelRoom(host,Path(self.library).resolve().parent/'room-pixels.so');self.register_pixel_view(room);return room
  entry=registry.entries['surface-room'];registry.entries['surface-room']=entry._replace(factory=room_factory)
  if 'doom' in registry.entries:
   entry=registry.entries['doom'];factory=entry.factory
   def doom_factory(host,**options):
    owner=factory(host,**options)
    from doom_pixels import View
    self.register_pixel_view(View(host,owner));return owner
   registry.entries['doom']=entry._replace(factory=doom_factory)
  for identifier,entry in tuple(registry.entries.items()):
   def source_owner(host,_factory=entry.factory,_title=entry.title,**options):
    owner=_factory(host,**options)
    if callable(getattr(owner,'map_surface',None)):
     owner.set_map_presentation('semantic')
     from map_pixels import View
     self.register_pixel_view(View(host,owner,name=_title))
    return owner
   registry.entries[identifier]=entry._replace(factory=source_owner)
 def open_symbian_window(self,host,application):
  from symbian_launch import request_window
  from symbian_pixels import View
  from core import Window as DesktopWindow
  if not hasattr(self.gpu_context,'retire_retained'):raise RuntimeError('GPU window compositor unavailable')
  name=application['title']+' ['+application['id']+']'
  existing=next((w for w in host.windows if w.name==name),None)
  if existing is not None and existing.opened:host.activate(name);return
  frames,keyboard,control=request_window(application['id'])
  view=View(host,name,frames,keyboard,control)
  try:
   if existing is None:host.add_window(DesktopWindow(name,2,2,32,22,desktop=host.desktop),transient=True)
   else:existing.opened=existing.visible=True
   host.app_forms[name]=view;host.window_cleanup[name]=view.close
   self.register_pixel_view(view)
   chooser=next((w for w in host.windows if w.name=='Symbian'),None)
   if chooser is not None and chooser.opened:host.close('Symbian')
   host.activate(name)
  except BaseException:view.close();raise
 def register_pixel_view(self,view):
  # A failed app can replace its lifetime owner on Retry. The registry closes
  # that owner; presentation must replace its view too, not draw both by name.
  forget=getattr(self.display,'forget_view',None)
  if forget:
   for app in self.pixel_apps:
    if app.name==view.name:forget(app)
  self.pixel_apps[:]=[app for app in self.pixel_apps if app.name!=view.name]
  self.pixel_apps.append(view)
 def geometry(self):return Geometry(*self.size)
 def attach(self,host,panel,registry):
  self.host=host;self.panel=panel;self.registry=registry
  if os.environ.get('POCKET_SYMBIAN_WINDOWS')=='1':host.symbian_window=lambda application:self.open_symbian_window(host,application)
  self.renderer=Renderer(host,self.font,self.library,require_gpu=self.require_gpu,font_mode=self.font_mode,cell_renderer=self.cell_renderer)
  if self.renderer.size!=self.size:self.renderer.resize(*self.size)
  if self.display and hasattr(self.display,'dynamic'):
   self.display.dynamic(True);width,height=self.display.size();self.resize(width//8,height//16)
  from display_context import create
  self.gpu_context=create(self)
  host.render_context=self.gpu_context
  self.report['renderer']=self.gpu_context.renderer_description
  self.report['apps']=list(registry.entries);self.report['windows']=[w.name for w in host.windows]
 def resize(self,cols,rows):
  self.size=(max(40,min(512,cols)),max(14,min(256,rows)));self.renderer.resize(*self.size)
  if self.display and hasattr(self.display,"set_canvas"):self.display.set_canvas(self.size[0]*8,self.size[1]*16)
  self.resized=True;self.dirty=True
 def events(self):
  result=[]
  if DEVELOPMENT and self.actions and self.frames and self.action_frame!=self.frames:
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
 def compose_model(self):
  context=self.gpu_context
  if not getattr(context,'native_pixels',False):return None
  return context.prepare_model()
 def consume(self,changed,computed):
  if getattr(self.gpu_context,'native_pixels',False):return
  _,_,drawn=self.renderer.consume_composed(changed,computed);self.dirty|=bool(drawn)
 def panel_text(self,x,y,text,foreground,background):
  r=self.renderer;fg,bg,_,_=style(foreground,'5;'+str(background))
  if getattr(self.gpu_context,'native_pixels',False):
   self.dirty|=self.gpu_context.panel_text(x,y,text,fg,bg);return
  # UTF32 is text transport; glyph lookup and all pixel work remain native.
  encoded=text.encode('utf-32-le');data=C.create_string_buffer(encoded)
  if r.lib.pocket_mbx_text(r.handle,x,y,data,len(encoded)//4,r.font_codes,r.font_bits,len(r.font_codes),fg,bg):raise RuntimeError('Native panel text rejected')
  self.dirty=True
 def present(self,complete):
  transitions_ready=True
  for app in self.pixel_apps:
   prepare=getattr(app,'prepare_gpu',None)
   if prepare and not prepare(self.gpu_context):transitions_ready=False
  if not transitions_ready:return False
  visible=[app for app in self.pixel_apps if self.host.shown(self.host.window(app.name)) and not self.host.window(app.name).rolled]
  if not complete or not (self.dirty or any(app.pixel_dirty for app in visible)):return False
  from presentation_text import supported
  text=None if getattr(self.gpu_context,'native_pixels',False) else self.presentation_text
  enabled=bool(text and supported(self.host,visible,raw_capture=self.output is not None))
  if DEVELOPMENT and self.diagnostics:self.report['native_text']=dict(enabled=enabled,reason='direct native glyph runs' if getattr(self.gpu_context,'native_pixels',False) else 'native atlas' if enabled else 'complete bitmap fallback')
  for app in visible:
   if hasattr(app,'native_text'):app.native_text=enabled
  if self.renderer.defer_text(enabled):self.dirty=True
  if getattr(self.gpu_context,'native_pixels',False):
   for app in visible:
    if not app.pixel_dirty:continue
    if getattr(app,'symbian_window',False):
     x,y,w,h=self.host.bounds(self.host.window(app.name));ox,oy=self.host.origin
     self.gpu_context.damage_rect((x+ox)*8,(y+oy)*16,w*8,h*16)
    else:self.gpu_context.full_damage=True
   self.gpu_context.begin_frame()
  else:self.gpu_context.cells(enabled,self.dirty)
  self.gpu_context.compose(visible,enabled)
  if text:
   if enabled:text.stage(self.renderer,visible,self.gpu_context.image_rects)
   else:text.clear()
  self.gpu_context.present(enabled)
  for app in visible:
   completed=getattr(app,'frame_presented',None)
   if completed:completed()
  self.dirty=False;self.frames+=1
  if DEVELOPMENT and self.output:Path(self.output).write_bytes(self.gpu_context.capture())
  if DEVELOPMENT and self.diagnostics:
   self.report[self.gpu_context.report_key]=self.gpu_context.status()
   self.report['pixel_apps']={app.name:dict(frames=app.pixel_frames,jobs=app.pixel_jobs,error=getattr(app,'error',''),cell_layer=self.host.window(app.name).layer is not None) for app in self.pixel_apps}
   self.record_frame()
   self.report.update(frames=self.frames,focus=self.host.focus,opened=[w.name for w in self.host.windows if w.opened],native=True,desktop_ansi=False)
  if self.limit and self.frames>=self.limit:self.closed=True
  return True
 if DEVELOPMENT:
  def record_frame(self):
   """Bound diagnostics even when an animated desktop runs all day."""
   if not self.diagnostics:return
   errors={name:form.error for name,form in self.registry.forms.items() if form.error}
   self.report.setdefault('errors',{}).update(errors)
   self.report['menu_opened']=self.report.get('menu_opened',False) or bool(self.host.launcher_lines)
   activity=self.report.setdefault('activity',{})
   if self.host.focus in activity or len(activity)<64:activity[self.host.focus]=activity.get(self.host.focus,0)+1
   history=self.report.setdefault('history',[])
   history.append(dict(frame=self.frames,focus=self.host.focus,menu=bool(self.host.launcher_lines),size=self.size,errors=errors))
   if len(history)>self.history_capacity:
    del history[0];self.report['history_dropped']=self.report.get('history_dropped',0)+1
 def wait_timeout(self,timeout):return .016 if timeout is None else min(timeout,.016)
 def close(self):
  context=self.gpu_context
  if context:context.close();self.gpu_context=None
  if self.compositor:self.compositor.close();self.compositor=None
  if self.renderer:self.renderer.close();self.renderer=None
  if context:context.close_window()
  if self.display:self.display.close();self.display=None
 def run(self,argv):
  spec=importlib.util.spec_from_file_location('pocket_desktop_model',HERE.parent/'shell/desktop.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  try:return module.main(platform=self,argv=argv)
  finally:self.close()
if DEVELOPMENT:
 def main():
  parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--font',type=Path,required=True);parser.add_argument('--renderer-library',type=Path,required=True);parser.add_argument('--display-library',type=Path);parser.add_argument('--native-library',type=Path,required=True);parser.add_argument('--state',type=Path,required=True);parser.add_argument('--frames',type=int,default=0);parser.add_argument('--output',type=Path);parser.add_argument('--actions',type=Path);parser.add_argument('--report',type=Path)
  args,rest=parser.parse_known_args();args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
  display=Window(args.display_library) if args.display_library else None
  platform=Platform(args.font,args.renderer_library,display,frames=args.frames,output=args.output,actions=json.loads(args.actions.read_text()) if args.actions else (),diagnostics=args.report is not None)
  try:platform.run(['--shell','--session',str(args.state/'desktop.json'),'--app-state',str(args.state),'--station-db',str(args.state/'directory.sqlite3'),'--native',str(args.native_library),*rest])
  finally:
   platform.close()
   if DEVELOPMENT and (args.report):args.report.write_text(json.dumps(platform.report,indent=2)+'\n')
 if __name__=='__main__':main()
