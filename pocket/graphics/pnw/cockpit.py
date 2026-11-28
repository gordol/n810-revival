"""Paint the fixed cockpit instrument faces once; their hands move in OpenGL."""
from functools import lru_cache
import math
import random


@lru_cache(maxsize=1)
def panel(jet=False):
    import os
    if os.environ.get('POCKET_TERMUX')=='1':
        import tempfile
        from pathlib import Path
        from data_paths import rainier_cache
        import hashlib
        cache=rainier_cache()
        cache.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(Path(__file__).read_bytes()).digest()
        target=cache/('jet-panel.rgba' if jet else 'cockpit-panel.rgba')
        try:
            with target.open('rb') as source:
                if source.read(len(key))==key:
                    data=source.read(1000*244*4+1)
                    if len(data)==1000*244*4:return data
        except FileNotFoundError:pass
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            folder=Path(tmp)
            data=paint_panel(jet)
            output=folder/'cached'
            output.write_bytes(key+data)
            output.replace(target)
            return data
    return paint_panel(jet)

def paint_panel(jet=False):
    from PIL import Image, ImageDraw, ImageFont
    width,height=1000,244
    art=Image.new('RGBA',(width,height))
    d=ImageDraw.Draw(art)
    rand=random.Random(172)
    grain=rand.randbytes(width*height)
    pixels=art.load()
    for x in range(width):
        u=(x-500)/500
        brow=round(12+25*u*u+17*u**6)
        for y in range(brow,height):
            depth=y-brow
            noise=(grain[y*width+x]-127)/48
            if depth<34:
                light=27+18*math.exp(-((depth-6)/7)**2)-12*depth/34
                rgb=(light*.95,light,light*.99)
            else:
                light=59+12*math.exp(-((depth-44)/15)**2)-15*y/height-8*u*u
                rgb=(light*.62,light*.69,light*.72) if jet else (light*1.04,light,light*.92)
            pixels[x,y]=tuple(int(c+noise) for c in rgb)+(255,)
    @lru_cache(None)
    def font(size):
        for name in ('DejaVuSans.ttf','/system/fonts/Roboto-Regular.ttf'):
            try:return ImageFont.truetype(name,size)
            except OSError:pass
        return ImageFont.load_default()
    ivory=(230,227,206)
    def label(x,y,text,size,color=ivory):
        d.text((x,y),text,font=font(size),fill=color,anchor='mm')
    def ellipse(x,y,r,color):
        d.ellipse((x-r,y-r,x+r,y+r),fill=color)
    def screw(x,y):
        ellipse(x,y,4,(23,24,23));ellipse(x,y-1,3,(112,110,100))
        d.line((x-2,y+1,x+2,y-2),fill=(42,42,39))
    def radial(cx,r,angle):
        a=math.radians(angle)
        return cx+r*math.sin(a),146-r*math.cos(a)
    for cx,title in ((304,'AIRSPEED'),(500,'ATTITUDE'),(696,'ALTITUDE')):
        d.rounded_rectangle((cx-79,65,cx+79,227),radius=19,fill=(29,30,28),outline=(79,78,69),width=2)
        for dx in (-67,67):
            for y in (78,214):screw(cx+dx,y)
        for r,tone in ((72,(11,12,12)),(70,(103,105,97)),(68,(52,55,54)),(65,(11,14,16))):
            ellipse(cx,146,r,tone)
        if cx==500:
            for deg in (-60,-45,-30,-20,-10,10,20,30,45,60):
                d.line((radial(cx,56,deg),radial(cx,63,deg)),fill=ivory,width=2)
        else:
            speed=cx==304
            for i in range(61 if speed else 50):
                angle=-135+270*i/60 if speed else i*7.2
                d.line((radial(cx,52 if i%5==0 else 57,angle),radial(cx,62,angle)),fill=ivory,width=2)
                if i%5==0 and (not speed or i%10==0):
                    label(*radial(cx,44,angle),str(i*(15 if jet else 5) if speed else i//5),13)
            if speed:
                if not jet:d.arc((cx-64,82,cx+64,210),-184,-39,fill=(82,158,110),width=3)
                label(cx,173,'KNOTS',9)
            else:label(cx,171,'FEET',9)
        label(cx,216,title,9,(194,192,174))
    for cx in (159,841):
        if jet:
            for r,tone in ((53,(18,22,24)),(50,(85,91,92)),(47,(12,19,21))):
                ellipse(cx,146,r,tone)
            compass=cx==159
            for j in range(36 if compass else 21):
                angle=j*10 if compass else -130+j*13
                major=j%(9 if compass else 5)==0
                d.line((radial(cx,36 if major else 40,angle),radial(cx,44,angle)),fill=ivory,width=2)
                if major:label(*radial(cx,29,angle),'NESW'[j//9] if compass else str(j*5),11)
            label(cx,210,'HEADING' if compass else 'THR %',11)
            continue
        # Adjustable eyeball air vents set into the outer panel.
        ellipse(cx,145,34,(24,25,24));ellipse(cx,144,31,(103,102,94))
        ellipse(cx,145,28,(34,36,35));ellipse(cx+2,145,22,(12,14,14))
        for j in range(-2,3):
            span=math.sqrt(20**2-(j*7)**2)
            d.line((cx-span,144+j*7,cx+span,146+j*7),fill=(74,77,73),width=3)
    return art.tobytes()
