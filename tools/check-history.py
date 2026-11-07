#!/usr/bin/env python3
"""Scan every local Git object, including unreachable objects, without printing its contents."""
import importlib.util,json,os,subprocess,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publication_check',ROOT/'tools/check-publication.py')
publication=importlib.util.module_from_spec(spec);spec.loader.exec_module(publication)
excluded=[x.casefold().encode() for x in os.environ.get('PUBLICATION_REJECT_TEXT','').split('|') if x]
process=subprocess.Popen(['git','cat-file','--batch-all-objects','--batch'],cwd=ROOT,stdout=subprocess.PIPE)
counts=Counter();errors=[]
while True:
    header=process.stdout.readline()
    if not header:break
    oid,kind,size=header.decode().split();size=int(size)
    data=process.stdout.read(size)
    if len(data)!=size or process.stdout.read(1)!=b'\n':raise SystemExit('Incomplete Git object stream')
    counts[kind]+=1
    if any(value in data.lower() for value in excluded):errors.append((oid,'excluded private text'))
    for label,pattern in publication.SECRETS.items():
        if pattern.search(data):errors.append((oid,label))
if process.wait():raise SystemExit('Git object scan failed')
if errors:
    for oid,label in errors:print(oid+': '+label+'; inspect locally',file=sys.stderr)
    raise SystemExit(1)
subprocess.run(['git','fsck','--full','--no-reflogs'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
print(json.dumps({'all_objects_scanned':sum(counts.values()),'types':dict(counts),'private_matches':0},indent=2))
