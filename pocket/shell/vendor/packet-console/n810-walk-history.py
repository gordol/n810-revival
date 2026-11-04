"""Read-only saved walking tracks and probe evidence. Never restores TX state."""
import collections
import datetime
import json
from pathlib import Path


def load(folder,call,exclude=None):
    reports=[]
    try:
        with (Path(folder)/'internet-reports.jsonl').open() as f:
            for line in f:
                try:
                    report=json.loads(line);header,payload=report['packet'].split(':',1)
                    source,route=header.split('>',1);hops=route.split(',');index=hops.index('qAR')
                    if source==call and index+1<len(hops):reports.append(dict(report,payload=payload,gate=hops[index+1]))
                except (ValueError,KeyError,TypeError):continue
    except OSError:pass
    sessions=[]
    for path in sorted(Path(folder).glob('*.jsonl'),reverse=True)[:40]:
        if path==exclude:continue
        track=collections.deque(maxlen=2000);probes=[];session={};end=''
        try:
            with path.open() as f:
                for line in f:
                    try:r=json.loads(line)
                    except ValueError:continue
                    if not isinstance(r,dict):continue
                    kind=r.get('type');end=r.get('time',end)
                    if kind=='session':session=r
                    elif kind=='position':
                        p=r.get('position')
                        if isinstance(p,dict) and all(isinstance(p.get(k),(int,float)) for k in ('lat','lon','time')):track.append(p)
                    elif kind=='submission':
                        row=r.get('probe')
                        if isinstance(row,dict) and isinstance(row.get('position'),dict):
                            saved=dict(row,session=session.get('tag',''),status='No return confirmed (saved)')
                            matching=[r for r in reports if r['payload']==row.get('payload')]
                            if matching:saved.update(internet_reports=matching,status='Internet report via '+matching[0]['gate'])
                            probes.append(saved)
                    elif kind=='repeated_copy':
                        for row in probes:
                            if row.get('number')==r.get('number'):row['return_path']=r.get('path');row['status']='Repeated copy observed'
        except OSError:continue
        if session.get('callsign')!=call or not track:continue
        sessions.append(dict(name=path.name,files=[path.name],start=session.get('time',end),end=end,track=list(track),probes=probes))
    # Consecutive armed sessions from one outing may be separated by an app restart.
    chosen=[r for r in sessions if r['probes']] or sessions
    outings=[]
    for session in reversed(chosen):
        try:gap=(datetime.datetime.fromisoformat(session['start'])-datetime.datetime.fromisoformat(outings[-1]['end'])).total_seconds() if outings else 999999
        except (ValueError,TypeError):gap=999999
        if outings and 0<=gap<=1800:
            previous=outings[-1];previous['track']=(previous['track']+session['track'])[-4000:]
            previous['probes']+=session['probes'];previous['files']+=session['files'];previous['end']=session['end']
        else:outings.append(session)
    return list(reversed(outings))[:8]
