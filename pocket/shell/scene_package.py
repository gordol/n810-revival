"""Versioned local scene packs: bounded JSON + packed cells, no executable data."""
import json
from pathlib import Path
import struct
import zipfile

MAX_CELLS=2097152


def save(path,metadata,cells,width,height):
    if not 1<=width<=4096 or not 1<=height<=2048 or width*height>MAX_CELLS:raise ValueError('invalid prepared dimensions')
    meta={**metadata,'format':'scenery-cells-v1','columns':width,'rows':height}
    raw=b''.join(struct.pack('!IQ',ord(cells[x,y][0]),cells[x,y][1]) for y in range(height) for x in range(width))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    import tempfile,os
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.scene-');os.close(fd)
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('scene.json',json.dumps(meta,separators=(',',':')))
            z.writestr('cells.bin',raw)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return path


def load(path):
    with zipfile.ZipFile(path) as z:
        if sorted(z.namelist())!=['cells.bin','scene.json']:raise ValueError('invalid scene pack members')
        if z.getinfo('scene.json').file_size>32768 or z.getinfo('cells.bin').file_size>MAX_CELLS*12:raise ValueError('scene pack exceeds budget')
        meta=json.loads(z.read('scene.json'));w,h=meta['columns'],meta['rows']
        if meta.get('format')!='scenery-cells-v1' or type(w) is not int or type(h) is not int or not 1<=w<=4096 or not 1<=h<=2048 or w*h>MAX_CELLS:raise ValueError('invalid scene pack dimensions')
        raw=z.read('cells.bin')
        if len(raw)!=w*h*12:raise ValueError('invalid cell data length')
        cells={}
        for i,(code,color) in enumerate(struct.iter_unpack('!IQ',raw)):
            char=chr(code)
            if not char.isprintable() or color>=1<<49:raise ValueError('invalid prepared cell')
            cells[i%w,i//w]=(char,color)
        return meta,cells


def prepare(path,width,height,preset='original',quality='compact',recipe=None):
    from scenery import Config,validate
    from landscape_detail import Nature,resolve
    from model_scene import base,view
    from scenery_geo import reference
    config=Config(preset=preset,quality=quality);appearance={}
    if recipe:
        d=json.loads(Path(recipe).read_text());config=validate(d['scenery']);appearance=d['appearance']
    n=resolve(Nature(appearance.get('season','summer'),appearance.get('show_foliage',True),appearance.get('show_animals',True),appearance.get('show_flowers',True),False,appearance.get('scene_seed',12345),appearance.get('terrain_grid',.08),tuple(config)),0)
    tick=1750 if appearance.get('light_mode')=='night' else 0
    moon=appearance.get('moon_phase','auto');shadows=appearance.get('terrain_shadows',False)
    cells=base(width,height,False,tick,1,False,moon,.005,1.65,shadows,n)
    model=view(1,False,width/(height*2),.005,1.65,n)
    return save(path,{'recipe':config._asdict(),'appearance':appearance,'nature':n._asdict(),'lighting_tick':tick,'moon_phase':moon,'camera':__import__('dataclasses').asdict(model.camera),'geographic_reference':reference(model.camera),'dem_sha256':json.loads(Path(__file__).with_name('data').joinpath('tahoma-3dep.json').read_text())['sha256'],'capabilities':'Prepared cells only: no camera movement, relighting, or procedural animation without recomputing.'},cells,width,height)


def play(path):
    import os,sys,termios,tty,selectors,signal
    from terminal import measure
    from camera_poc import ansi
    from input import Input
    meta,cells=load(path);w,h=meta['columns'],meta['rows']
    if not sys.stdin.isatty() or not sys.stdout.isatty():raise SystemExit('Run prepared playback in a terminal')
    size=measure(sys.stdout.fileno())
    if size.columns<w or size.rows<h+2:raise SystemExit(f'Pack needs at least {w}x{h+2}; prepare another size for this terminal')
    fd=sys.stdin.fileno();old=termios.tcgetattr(fd);decoder=Input();selector=selectors.DefaultSelector()
    def stop(*_):raise KeyboardInterrupt
    signals={s:signal.signal(s,stop) for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    try:
        tty.setraw(fd);selector.register(fd,selectors.EVENT_READ)
        sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J'+ansi(cells,w,h)+f'\x1b[{h+2};1HPrepared scene | Q quit');sys.stdout.flush()
        done=False
        while not done:
            events=selector.select(.1)
            data=os.read(fd,4096) if events else b''
            if events and not data:break
            done=any(e[0]=='key' and e[1] in ('q','Q','\x1b','\x03') for e in decoder.feed(data,expire=not events))
    except KeyboardInterrupt:pass
    finally:
        for s,handler in signals.items():signal.signal(s,handler)
        selector.close();termios.tcsetattr(fd,termios.TCSADRAIN,old)
        sys.stdout.write('\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l');sys.stdout.flush()
