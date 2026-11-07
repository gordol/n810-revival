"""Audit the selected elevation catalogue, with no fixed region or pack count."""
import argparse,hashlib,json,zlib
from pathlib import Path


def audit(root):
    root=Path(root);manifest=root/'elevation.json'
    document=json.loads(manifest.read_text()) if manifest.is_file() else None
    indices=[root/name for name in document['packs']] if document else sorted((root/'elevation-fine').glob('*-guarded/index.json'))
    report=[];fine_bytes=overview_bytes=0
    for path in indices:
        m=json.loads(path.read_text());levels=[(path,False)]+[(path.parent/row['index'],True) for row in m.get('overviews',())]
        total=0
        for index,is_overview in levels:
            metadata=json.loads(index.read_text());size=index.stat().st_size
            for item in metadata['tiles'].values():
                if Path(item['file']).name!=item['file']:raise ValueError('Invalid tile path')
                raw=(index.parent/item['file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Elevation checksum mismatch')
                expected=item['width']*item['height']*2;decoder=zlib.decompressobj();payload=decoder.decompress(raw,expected+1)
                if len(payload)!=expected or not decoder.eof or decoder.unused_data:raise ValueError('Elevation tile length mismatch')
                size+=len(raw)
            if is_overview:overview_bytes+=size
            else:fine_bytes+=size
            total+=size
        report.append(dict(pack=str(path.relative_to(root)),bytes=total,overviews=len(levels)-1))
    return dict(packs=len(report),bbox=document.get('bbox') if document else None,fine_bytes=fine_bytes,overview_bytes=overview_bytes,total_bytes=fine_bytes+overview_bytes,packs_detail=report)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1]/'data');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=audit(args.data)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='packs_detail'}))
