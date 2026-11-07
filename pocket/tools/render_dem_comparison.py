"""Render real engine frames for desktop relief review, without changing application state."""
import argparse,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from offline_map import Renderer
from PIL import Image,ImageDraw,ImageFont

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--font',default='DejaVuSansMono.ttf')
args=parser.parse_args()
def render(enabled):
 os.environ['POCKET_DESKTOP_TERRAIN']='1' if enabled else '0'
 r=Renderer();key=('map',(47.10,-122.78),35.,180,75,True,True);r._wanted=key
 try:return r._render(key)
 finally:r.close()
def picture(frame,title):
 cw,ch=7,12;img=Image.new('RGB',(frame.width*cw,frame.height*ch+40),(18,18,18));d=ImageDraw.Draw(img);font=ImageFont.truetype(args.font,12)
 d.text((8,3),title,font=font,fill='white');d.text((8,20),frame.legend,font=font,fill='white')
 for i,(char,s) in enumerate(frame.cells):
  x=i%frame.width*cw;y=i//frame.width*ch+40;fg=tuple((s>>v)&255 for v in (40,32,24));bg=tuple((s>>v)&255 for v in (16,8,0))
  d.rectangle((x,y,x+cw-1,y+ch-1),fill=bg)
  if char=='▀':d.rectangle((x,y,x+cw-1,y+ch//2-1),fill=fg)
  elif char.strip():d.text((x,y),char,font=font,fill=fg)
 return img
out=args.output;out.mkdir(parents=True,exist_ok=True)
for enabled,name in ((False,'before'),(True,'after')):
 t=time.monotonic();frame=render(enabled);picture(frame,name.title()+' — Southern Puget Sound').save(out/(name+'.png'));print(name,frame.legend,time.monotonic()-t)
