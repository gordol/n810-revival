"""Linked list/detail windows over the same retained contacts."""
import textwrap
from model import age


def fit(lines, width, height): return tuple(line[:width] for line in lines[:height])


class Views:
    def __init__(self, model, host):
        self.model, self.host = model, host
        self._list_key=None;self._detail_key=None
        self.offset = 0; self.scroll = 0; self.builds = {'Heard': 0, 'Details': 0}
    def update(self, now):
        model = self.model
        w = self.host.window('Heard'); width, height = max(1,w.w-2), max(1,w.h-2)
        key=(model.revision,model.selected,width,height,self.offset)
        if key!=self._list_key:
            selected = model.order.index(model.selected) if model.selected in model.order else 0
            available = max(1,height-3)
            self.offset = max(0, min(self.offset, selected))
            if selected >= self.offset+available: self.offset = selected-available+1
            lines = ['CALL         RX COUNT', '']
            spans = [(0,0,width,'toolbar')]
            for index, call in enumerate(model.order[self.offset:self.offset+available], self.offset):
                row = model.contacts[call].value
                lines.append(('> ' if call==model.selected else '  ')+f'{call:<12} {row.packets:>5}')
                if call==model.selected: spans.append((len(lines)-1,0,width,'selected'))
            if not model.order: lines.append('No heard records available')
            self._content('Heard', fit(lines,width,height), spans)
            self._list_key=(model.revision,model.selected,width,height,self.offset)
        w = self.host.window('Details'); width, height = max(1,w.w-2), max(1,w.h-2)
        ref = model.selection
        stamp=age(ref.value.last,now) if ref else ''
        key=(id(ref.value) if ref else None,width,height,self.scroll,stamp)
        if key==self._detail_key:return
        if ref:
            row = ref.value
            body = [row.call+('  * buddy annotation' if row.buddy else ''), row.name or 'No stored name', '',
                    'Last RX: '+age(row.last,now), row.last or 'Original observation time unknown',
                    'First: '+(row.first or 'unknown'), 'Dated captures: '+str(row.packets), '',
                    'Observation is not current reachability.', 'Call + SSID identifies an observed endpoint.', '']
            if row.notes: body += ['Stored notes', row.notes, '']
            body += ['Observed evidence']
            body += [kind+': '+detail+' ['+stamp+']' for kind,stamp,detail in row.evidence] or ['None recorded']
            body += ['', 'Observed used relays']
            body += [relay+' / '+str(count)+' captures / '+stamp for relay,stamp,count in row.via] or ['None recorded']
            lines = []
            for line in body: lines.extend(textwrap.wrap(line,max(1,width-2)) or [''])
            self.scroll = min(max(0,self.scroll),max(0,len(lines)-height))
            lines = lines[self.scroll:self.scroll+height]
        else: lines = ['Select a heard endpoint.', '', 'Waiting for an existing directory snapshot.']
        self._content('Details',fit(lines,width,height),[(0,0,width,'heading')])
        self._detail_key=(id(ref.value) if ref else None,width,height,self.scroll,stamp)
    def _content(self, name, lines, spans):
        w = self.host.window(name)
        if w.version != lines or w.spans != tuple(spans): self.builds[name] += 1
        self.host.content(name,lines,lines,spans)
    def select_step(self, delta):
        if self.model.step(delta): self.scroll = 0
    def click(self, x, y):
        w = self.host.window('Heard')
        if self.host.focus!=w.name or not self.host.shown(w) or w.rolled:return
        index = self.offset + y-w.y-3
        if w.x<x<w.x+w.w-1 and 0<=index<len(self.model.order) and w.y+3<=y<w.y+w.h-1:
            if self.model.select(self.model.order[index]): self.scroll=0
