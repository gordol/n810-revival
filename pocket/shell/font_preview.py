"""Catalog-backed PSF bitmap previews only; never changes a terminal or kernel font."""
from pathlib import Path
import re
import struct
import sys
import os
import json
from functools import lru_cache
from app_widgets import Canvas
from paint import control_ink


class FontCatalog:
    def __init__(self,root=None):
        base=Path(__file__).resolve().parent
        candidates=(base/'vendor/fonts/choices',base.parents[1]/'console-fonts/choices')
        self.root=Path(root) if root else next((p for p in candidates if (p/'catalog.json').is_file()),candidates[0])
        self.rows=();self.error=None
        try:
            raw=(self.root/'catalog.json').read_bytes()
            if len(raw)>65536:raise ValueError('Font catalog exceeds bound')
            rows=json.loads(raw)
            if not isinstance(rows,list) or not 1<=len(rows)<=32:raise ValueError('Invalid font catalog')
            ids=set()
            for row in rows:
                if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not re.fullmatch(r'[a-z0-9-]{1,64}',row['id']) or row['id'] in ids:raise ValueError('Invalid font ID')
                ids.add(row['id'])
                if row.get('target')!='linux-vt' or row.get('capability')!='font512-unicode' or row.get('state')!='local-candidate':raise ValueError('Unsupported font target/state')
                file=row.get('file');digest=row.get('sha256')
                if not isinstance(file,str) or Path(file).name!=file or not file.endswith('.psf') or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid font asset')
                if any(type(row.get(k))!=int or row[k]<=0 for k in ('width','height','columns','rows','slots','mappings')):raise ValueError('Invalid font dimensions')
                if row['slots']!=512 or row['width']>16 or row['height']>32:raise ValueError('Unsupported font dimensions')
                if not all(isinstance(row.get(k),str) and row[k] for k in ('name','family','size')):raise ValueError('Invalid font labels')
            self.rows=tuple(rows)
        except (OSError,ValueError,TypeError,KeyError) as error:self.error=str(error)
    def selected(self,identifier):return next((row for row in self.rows if row['id']==identifier),self.rows[0] if self.rows else None)
    @lru_cache(maxsize=8)
    def glyphs(self,identifier):
        import hashlib
        row=self.selected(identifier)
        if row is None:raise ValueError('Font catalog unavailable')
        path=self.root/row['file']
        if path.stat().st_size>1024*1024:raise ValueError('Font asset exceeds bound')
        raw=path.read_bytes()
        if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Font asset hash mismatch')
        if len(raw)<32:raise ValueError('Invalid PSF header')
        magic,version,start,flags,count,size,height,width=struct.unpack_from('<8I',raw)
        if magic!=0x864ab572 or version!=0 or not 32<=start<=len(raw) or not flags&1 or count!=512 or (width,height)!=(row['width'],row['height']) or size<height*((width+7)//8) or start+count*size>len(raw):raise ValueError('Invalid PSF geometry')
        entries=raw[start+count*size:].split(b'\xff');glyphs={}
        if len(entries)<count:raise ValueError('Incomplete PSF Unicode table')
        for index,entry in enumerate(entries[:count]):
            for char in entry.split(b'\xfe')[0].decode('utf-8'):
                glyphs[char]=raw[start+index*size:start+(index+1)*size]
        if len(glyphs)!=row['mappings'] or not all(chr(code) in glyphs for code in (*range(0xe0a0,0xe0a3),*range(0xe0b0,0xe0b8))):raise ValueError('Font coverage does not match catalog')
        return row,glyphs


def terminal_font_owner():
    if sys.platform=='linux' and not os.environ.get('SSH_TTY'):
        try:
            if re.fullmatch(r'/dev/tty[0-9]+',os.ttyname(0)):return 'Physical Linux VT; unchanged'
        except OSError:pass
    return 'External terminal app; unchanged'


class FontPreview:
    def __init__(self,host,catalog=None):
        self.host=host;self.catalog=catalog or FontCatalog();self.width=76;self.height=28;self._spans=();self._layer=None;self._key=None;self._lines=()
    def row(self):return self.catalog.selected(self.host.font_preview_id)
    def read(self,key,default='Unavailable'):
        row=self.row();return str(row.get(key,default)) if row else default
    def family(self,direction):
        families=tuple(dict.fromkeys(row['family'] for row in self.catalog.rows))
        if not families:return
        current=self.row();family=families[(families.index(current['family'])+direction)%len(families)]
        choices=[row for row in self.catalog.rows if row['family']==family]
        selected=next((row for row in choices if row['size']==current['size']),choices[0]);self.host.set_preference('font_preview_id',selected['id'])
    def size(self,direction):
        current=self.row()
        if current:
            choices=[row for row in self.catalog.rows if row['family']==current['family']]
            self.host.set_preference('font_preview_id',choices[(choices.index(current)+direction)%len(choices)]['id'])
    def settings_rows(self):
        def open_preview(_):self.host.activate('Font Preview')
        return [('Font family',lambda:self.read('family'),self.family),('Font size',lambda:self.read('size'),self.size),
                ('Font preview',lambda:'Open bitmap sample' if self.row() else 'Catalog unavailable',open_preview),
                ('Font target',lambda:'Physical Linux VT' if self.row() else 'Unavailable',lambda _:None),
                ('Font status',lambda:'Preview only; apply pending',lambda _:None),
                ('Terminal font',terminal_font_owner,lambda _:None)]
    def key(self,key):
        if key in ('left','right'):self.size(-1 if key=='left' else 1);return True
        if key in ('up','down'):self.family(-1 if key=='up' else 1);return True
        return False
    def lines(self):
        key=(self.width,self.height,self.host.font_preview_id,self.host.palette,self.host.ascii)
        if key==self._key:return self._lines
        c=Canvas(self.width,self.height);c.pane(0,0,self.width,self.height,'Device font · bitmap preview',True);self._layer=None
        row=self.row()
        if not row:
            c.put(1,2,'Font catalog unavailable');c.put(1,4,self.catalog.error or 'No choices packaged')
        else:
            c.put(1,2,row['name']+' · '+row['id']);c.role(1,2,self.width-2,'heading')
            c.put(1,3,f"N810 800×480: {row['columns']} columns × {row['rows']} rows")
            c.put(1,4,f"{row['slots']} slots · {row['mappings']} Unicode mappings · 11 Powerline")
            c.put(1,5,str(row.get('fallback_slots',0))+' resized fallback glyphs · physical review pending')
            c.put(1,7,'Actual packaged bitmap · sample Aa09 + Powerline')
            try:
                row,glyphs=self.catalog.glyphs(row['id'])
                if self.host.ascii:c.put(1,9,'Bitmap needs half-block display; catalog details remain available.')
                else:
                    sample='Aa09\ue0b0\ue0b2'[:max(1,(self.width-2)//row['width'])];width=len(sample)*row['width'];height=min((row['height']+1)//2,max(0,self.height-13));cells=[]
                    color=control_ink('body',self.host.palette);fg=(color>>24)&0xffffff;bg=color&0xffffff;stride=(row['width']+7)//8
                    def pixel(x,y):
                        if y>=row['height']:return False
                        glyph=glyphs.get(sample[x//row['width']],glyphs.get('?'));column=x%row['width']
                        return bool(glyph[y*stride+column//8]&(128>>(column%8))) if glyph else False
                    for y in range(height):
                        for x in range(width):cells.append(('▀',(1<<48)|((fg if pixel(x,y*2) else bg)<<24)|(fg if pixel(x,y*2+1) else bg)))
                    if height:self._layer=(1,9,width,height,tuple(cells))
            except (OSError,ValueError,UnicodeError) as error:c.put(1,9,'Preview unavailable: '+str(error));c.role(1,9,self.width-2,'warning')
        c.put(1,self.height-3,'Preview only · no font is applied');c.role(1,self.height-3,self.width-2,'warning')
        c.put(1,self.height-2,terminal_font_owner());c.role(1,self.height-2,self.width-2,'muted')
        c.put(1,self.height-1,'↑/↓ family · ←/→ available size');c.role(1,self.height-1,self.width-2,'control')
        self._spans=c.styled_spans();self._key=key;self._lines=c.lines();return self._lines
    def spans(self):return self._spans
    def layer(self):self.lines();return self._layer
