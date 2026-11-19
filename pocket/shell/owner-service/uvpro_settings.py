"""Edit one reported settings field while preserving every other wire bit."""
import json
from pathlib import Path


def changed(raw, edit):
    group=edit['group'];name=edit['field']
    blocks={'settings':{22:'Settings'}, 'beacon':{50:'BSSSettings',52:'BSSSettingsV2'}}
    layout=blocks.get(group,{}).get(len(raw))
    if not layout or not isinstance(name,str) or name.startswith('_'):
        raise ValueError('Unknown settings field or radio layout')
    fields=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_bytes())[layout]
    if sum(width for _,width,_ in fields)!=8*len(raw):raise ValueError('Incomplete settings layout')
    bits=int.from_bytes(raw,'big');shift=len(raw)*8
    for key,width,kind in fields:
        shift-=width
        if key!=name:continue
        mask=(1<<width)-1
        current=(bits>>shift)&mask
        new=edit['value']
        if kind=='str':
            current=current.to_bytes(width//8,'big').split(b'\0',1)[0].decode('gbk',errors='replace')
            if not isinstance(new,str) or '\0' in new:raise ValueError('Expected text')
            encoded=new.encode('gbk')
            if len(encoded)>width//8:raise ValueError('Text exceeds radio field length')
            updated=int.from_bytes(encoded.ljust(width//8,b'\0'),'big')
        elif kind=='bool':
            current=bool(current)
            if type(new) is not bool:raise ValueError('Expected on or off')
            updated=int(new)
        else:
            if type(new) is not int or not 0<=new<=mask:raise ValueError('Expected an integer from 0 to '+str(mask))
            if key=='squelch_level' and new>9:raise ValueError('Squelch range is 0 to 9')
            updated=new
        if type(current)!=type(edit['expected']) or current!=edit['expected']:
            raise ValueError('Radio value changed. Refresh and review it again.')
        if current==new:return raw
        return ((bits&~(mask<<shift))|(updated<<shift)).to_bytes(len(raw),'big')
    raise ValueError('Field unavailable on this radio')


def transaction(edit):
    read,payload,write={'settings':(10,b'',11),'beacon':(33,b'\x02',34)}[edit['group']]
    before=yield read,payload,None
    desired=changed(before,edit)
    if desired!=before:
        reply=yield write,desired,before
        if reply:raise ValueError('Unexpected settings acknowledgement')
    verified=yield read,payload,None
    if verified!=desired:raise ValueError('Radio settings readback differs; refresh the radio')
    return dict(field=edit['field'],changed=before!=desired)
