#!/usr/bin/env python3
"""Turn a validated ext4 image into an MBR miniSD image in place."""
import os, struct, sys
p=sys.argv[1]
start=2048*512
part=os.path.getsize(p)
if part != 671088640: raise SystemExit("expected 640 MiB ext4 partition")
with open(p,"r+b",buffering=0) as f:
    f.truncate(part+start)
    pos=part
    chunk=4*1024*1024
    while pos:
        n=min(chunk,pos); pos-=n; f.seek(pos); data=f.read(n); f.seek(start+pos); f.write(data)
    mbr=bytearray(512)
    mbr[440:444]=bytes.fromhex("01d00581")
    mbr[446:462]=struct.pack("<B3sB3sII",0,b"\0\0\0",0x83,b"\0\0\0",2048,part//512)
    mbr[510:512]=b"\x55\xaa"
    f.seek(0); f.write(mbr)
print(f"Assembled miniSD image with PARTUUID=8105d001-01: {p}")
