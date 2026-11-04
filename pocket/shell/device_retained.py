"""Read-only shared saved-RX adapter; original timestamp and wire provenance survive."""
from functools import lru_cache
import importlib.util
from pathlib import Path


@lru_cache(maxsize=3)
def owner(name):
    root=Path(__file__).resolve().parent
    path=root/'vendor/packet-console'/name
    spec=importlib.util.spec_from_file_location('retained_'+name.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def packets(path):
    return packet_bundle(path)[1]


def packet_bundle(path):
    path=Path(path)
    if path.stat().st_size>64*1024*1024:raise ValueError('Saved RX snapshot exceeds 64 MiB')
    history=owner('n810-frame-history.py').History.load(path)
    records=list(history.records)
    return records,decode_records(records)


def decode_records(records):
    describe=owner('n810-packet-monitor.py').describe
    result=[]
    for row in records:
        if row['direction']!='radio_to_host':continue
        raw=describe(bytes.fromhex(row['frame']))
        if raw and not raw.startswith(('Malformed','Short')):result.append(dict(row,raw=raw))
    return result


def walks(folder,call='N0CALL'):
    result=[]
    for outing in owner('n810-walk-history.py').load(folder,call):
        rows=[dict(type='session',tag=outing['name'],time=outing['start'])]
        rows.extend(dict(type='position',position=p) for p in outing['track'])
        rows.extend(dict(type='submission',probe=p) for p in outing['probes'])
        result.append(dict(file=outing['name'],files=outing['files'],rows=rows,end=outing['end']))
    return result
