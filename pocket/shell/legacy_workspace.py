"""Small launch declarations for unchanged applications hosted in PTY windows."""
import json
from collections import namedtuple
from pathlib import Path
from core import Window

App=namedtuple('App','name argv desktop rect minimum icon',defaults=((10,2),''))
RESERVED={'Settings','Calendar','Terminal'}


def load(path):
    path=Path(path)
    if path.stat().st_size>32768:raise ValueError('workspace exceeds 32 KB')
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('apps'),list) or not 1<=len(data['apps'])<=12:
        raise ValueError('workspace requires version 1 and 1 to 12 apps')
    result=[];names=set(RESERVED)
    for row in data['apps']:
        if not isinstance(row,dict):raise ValueError('invalid workspace app')
        name=row['name'];argv=row['argv'];desktop=row.get('desktop',0);rect=row['rect']
        if not isinstance(name,str) or not name or len(name)>40 or any(ord(c)<32 for c in name) or name in names:raise ValueError('invalid workspace name')
        if not isinstance(argv,list) or not argv or len(argv)>64 or any(not isinstance(a,str) or '\0' in a or len(a)>4096 for a in argv):raise ValueError('invalid workspace command')
        if type(desktop) is not int or not 0<=desktop<3:raise ValueError('invalid workspace desktop')
        if not isinstance(rect,list) or len(rect)!=4 or any(type(v) is not int or not 0<=v<=4096 for v in rect) or rect[2]<12 or rect[3]<4:raise ValueError('invalid workspace geometry')
        minimum=row.get('minimum',[10,2])
        if not isinstance(minimum,list) or len(minimum)!=2 or any(type(v) is not int or not 1<=v<=4094 for v in minimum):raise ValueError('invalid app minimum')
        icon=row.get('icon','')
        if not isinstance(icon,str) or len(icon)>3 or any(ord(c)<32 for c in icon):raise ValueError('invalid app icon')
        names.add(name);result.append(App(name,tuple(argv),desktop,tuple(rect),tuple(minimum),icon))
    return tuple(result)


def windows(apps,width,height):
    result=[]
    for app in apps:
        x,y,w,h=app.rect;mw,mh=app.minimum
        w=min(width,max(w,mw+2));h=min(height,max(h,mh+2))
        result.append(Window(app.name,min(x,width-w),min(y,height-h),w,h,desktop=app.desktop))
    return result


def arrange(apps,width,height):
    """Fit usable app surfaces in columns, or use a full-size window deck."""
    for a in apps:
        if a.minimum[0]+2>width or a.minimum[1]+2>height:raise ValueError(f'{a.name} needs {a.minimum[0]} columns × {a.minimum[1]} content rows')
    result=[]
    for desktop in sorted({a.desktop for a in apps}):
        page=[a for a in apps if a.desktop==desktop]
        minimum=max(a.minimum[0]+2 for a in page)
        columns=max(1,min(len(page),(width+1)//(minimum+1)))
        groups=[[] for _ in range(columns)];heights=[0]*columns
        for app in sorted(page,key=lambda a:a.minimum[1],reverse=True):
            column=min(range(columns),key=lambda i:heights[i])
            groups[column].append(app);heights[column]+=app.minimum[1]+2+(1 if heights[column] else 0)
        gap=1 if max(heights)<=height else 0
        if any(sum(a.minimum[1]+2 for a in group)>height for group in groups):
            result.extend(Window(a.name,0,0,width,height,desktop=desktop) for a in page)
            continue
        by_name={}
        for column,group in enumerate(groups):
            group.sort(key=page.index);x=column*(width+1)//columns
            available=(column+1)*(width+1)//columns-x-1
            remaining=height-sum(a.minimum[1]+2 for a in group)-gap*(len(group)-1)
            sizes={a.name:a.minimum[1]+2 for a in group}
            # Spend spare rows on preferred sizes, retaining compact widgets.
            for app in group:
                extra=min(remaining,max(0,app.rect[3]-sizes[app.name]));sizes[app.name]+=extra;remaining-=extra
            y=0
            for app in group:
                w=min(available,max(app.rect[2],app.minimum[0]+2));h=sizes[app.name]
                by_name[app.name]=Window(app.name,x,y,w,h,desktop=desktop);y+=h+gap
        result.extend(by_name[a.name] for a in page)
    return result


def replay(sources,root,python):
    """Commands use only the private replay service and its private HOME."""
    sources=Path(sources);root=Path(root);state=root/'home/.local/state/n810-aprs'
    commands=[
        ('APRS','n810-aprs-view.py',['--socket',str(root/'aprs.sock'),'--snapshot-socket',str(root/'replay.sock'),'--maps',str(sources/'maps'),'--map-engine','next','--tui-theme','color'],[0,0,108,38]),
        ('Messages','n810-aprs-messages.py',['--socket',str(root/'aprs.sock'),'--kiss',str(root/'tx-disabled.sock'),'--store',str(state/'messages.json')],[110,0,84,22]),
        ('Nets','n810-nets.py',['--socket',str(root/'aprs.sock'),'--lead','0','--data',str(sources/'data/nets-puget-sound.json')],[110,23,84,18]),
        ('Directory','n810-aprs-directory.py',['--db',str(state/'directory.sqlite3'),'--socket',str(root/'replay.sock')],[0,40,94,18]),
        ('Services','n810-aprs-services.py',['--socket',str(root/'aprs.sock'),'--call','N0DEM'],[96,42,98,18])]
    icons={'APRS':'@','Messages':'[=]','Nets':'#','Directory':'::','Services':'<>'}
    minimums={'APRS':[64,16],'Messages':[94,22],'Nets':[65,18],'Directory':[60,14],'Services':[48,18]}
    apps=[]
    for name,script,options,rect in commands:
        if not (sources/script).is_file():raise ValueError('missing '+str(sources/script))
        apps.append(dict(name=name,argv=[python,str(sources/script),*options],desktop=0,rect=rect,minimum=minimums[name],icon=icons[name]))
    return dict(version=1,apps=apps)
