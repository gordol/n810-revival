"""Read AppArc's installed-application catalog from private runtime storage."""
from pathlib import Path
import re
import struct

ALIASES={'chess':('ChessGenius_20036D63.exe','ChessGenius'), 'snakes':('6r45_1b.exe','Snakes')}

def applications(home=None):
    root=(Path(home) if home else Path.home())/'.local/share/symbian-private/runtime'
    catalog=root/'apps.tsv';rows=[]
    if catalog.exists():
        with catalog.open(encoding='utf-8') as stream:
            text=stream.read(262145)
        if len(text)>262144:raise ValueError('Application catalog exceeds limit')
        for line in text.splitlines():
            fields=line.split('\t')
            if len(fields)!=3:continue
            uid,path,title=fields
            if not re.fullmatch('[0-9a-f]{8}',uid):continue
            match=re.fullmatch(r'([CcEe]):\\(?:sys\\bin|system\\programs)\\([^\\/:\x00-\x1f]+\.exe)',path,re.I)
            if not match:continue
            exe=root/'data/drives'/match[1].lower()/'sys/bin'/match[2]
            if not exe.is_file() or exe.is_symlink() or not exe.resolve().is_relative_to(root.resolve()):continue
            with exe.open('rb') as stream:header=stream.read(12)
            if len(header)!=12 or struct.unpack_from('<I',header,8)[0]!=int(uid,16):continue
            title=''.join(c for c in title if c.isprintable())[:80] or exe.stem
            rows.append(dict(id=uid,title=title,path=match[1].upper()+':\\sys\\bin\\'+match[2]))
    # Migrate existing installations until their first AppArc refresh.
    if not catalog.exists():
        for alias,(filename,title) in ALIASES.items():
            p=root/'data/drives/c/sys/bin'/filename
            if p.is_file():rows.append(dict(id=alias,title=title,path='C:\\sys\\bin\\'+filename))
    return sorted({row['id']:row for row in rows}.values(),key=lambda row:row['title'].casefold())

def resolve(application,home=None):
    rows=applications(home)
    if application in ALIASES:
        filename=ALIASES[application][0].lower()
        return next((row for row in rows if row['path'].lower().endswith('\\'+filename)),None)
    return next((row for row in rows if row['id']==application),None)

def packages(home=None):
    inbox=(Path(home) if home else Path.home())/'.local/share/symbian-private/runtime/inbox'
    if not inbox.is_dir():return []
    return [dict(id='install:'+p.name,title='Install: '+p.name,path=str(p))
            for p in sorted(inbox.iterdir(),key=lambda p:p.name.casefold())
            if p.is_file() and not p.is_symlink() and re.fullmatch(r'[A-Za-z0-9 _().-]{1,160}\.sisx?',p.name,re.I)][:128]
