"""Offline graft of approved artwork onto the exact selected console font.

No font loading, console ioctl, geometry change, or Unicode reassignment.
"""
import hashlib,json,struct
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE_SHA='12753ff115ad2fc254436f0e4684832a9998f1021f99a974ad1cfec6cbbc7461'
APPROVED_SHA='144268edc285ed2d65fb0abcae9bc5ef85607f32fa82f3b21d6853d86fd77284'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def decode(raw):
    magic,version,start,flags,count,size,height,width=struct.unpack_from('<8I',raw)
    if (magic,version,start,flags,count,size,height,width)!=(0x864ab572,0,32,1,512,16,16,8):
        raise ValueError('Unexpected font geometry/header')
    entries=raw[start+count*size:].split(b'\xff')
    if len(entries)!=513 or entries[-1]:raise ValueError('Invalid Unicode table')
    return [raw[start+i*size:start+(i+1)*size] for i in range(count)],entries[:-1]


def build():
    base=(HERE/'canonical-base-8x16.psf').read_bytes()
    approved=(HERE/'n810-icons-8x16.psf').read_bytes()
    if sha(base)!=BASE_SHA or sha(approved)!=APPROVED_SHA:raise ValueError('Font input identity differs')
    images,entries=decode(base);art,_=decode(approved)
    manifest=json.loads((HERE/'manifest.json').read_bytes())
    mapped={c:slot for slot,entry in enumerate(entries)
            for c in entry.split(b'\xfe')[0].decode('utf-8')}
    for row in manifest['icons']:
        slot=row['slot'];alias=chr(int(row['compatibility_alias'][2:],16))
        primary=chr(int(row['codepoint'][2:],16))
        if entries[slot] or alias in mapped:raise ValueError('Icon would overwrite an existing mapping')
        images[slot]=art[slot];entries[slot]=alias.encode('utf-8');mapped[alias]=slot
        if primary not in mapped:
            entries[slot]+=primary.encode('utf-8');mapped[primary]=slot
        row['primary_slot']=mapped[primary]
    result=base[:32]+b''.join(images)+b'\xff'.join(entries)+b'\xff'
    manifest.update(state='compatible offline candidate; not installed',profile='compact-v1',
                    width=8,height=16,slots=512,sha256=sha(result),base_sha256=BASE_SHA,
                    approved_font_sha256=APPROVED_SHA,
                    approved_source_commit='ed84e67eb2e76c10150fa085cb1682278bee4176',
                    preservation='Header, geometry, all pre-existing Unicode table entries and mapped bitmaps byte exact; only 48 previously unmapped slots changed.')
    return result,manifest


if __name__=='__main__':
    raw,manifest=build()
    (HERE/'n810-ui-icons-8x16.psf').write_bytes(raw)
    (HERE/'compatible-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(manifest['sha256'])
