#!/usr/bin/env python3
"""Bounded COFF2 metadata reader for these generated local objects only.

Not a firmware loader, linker, validator of arbitrary vendor firmware, or proof
of task readiness. Layout basis: recovered osso-dsp-loader coff-c55x.h.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(data):
    if not 22 <= len(data) <= 1024*1024:
        raise ValueError('object length outside bounded scope')

    def region(start, count):
        if start < 0 or count < 0 or start+count > len(data):
            raise ValueError('object region out of bounds')
        return data[start:start+count]

    version,nscns,timestamp,symptr,nsyms,opthdr,flags,target = struct.unpack('<HHIIIHHH',region(0,22))
    if version != 0xC2 or target != 0x9C or opthdr != 0 or not 1 <= nscns <= 32 or nsyms > 1024:
        raise ValueError('outside generated C55x COFF2 object scope')
    region(22,nscns*48)
    region(symptr,nsyms*18+4)
    strings = symptr+nsyms*18
    string_size = struct.unpack('<I',region(strings,4))[0]
    if string_size < 4:
        raise ValueError('invalid string table size')
    table = region(strings,string_size)

    def name(raw):
        if raw[:4] == b'\0'*4:
            offset = struct.unpack('<I',raw[4:])[0]
            if not 4 <= offset < len(table):
                raise ValueError('invalid string table offset')
            end = table.find(b'\0',offset)
            if end < 0:
                raise ValueError('unterminated name')
            return table[offset:end].decode('ascii')
        return raw.split(b'\0',1)[0].decode('ascii')

    sections = []
    for i in range(nscns):
        row = struct.unpack('<8s9I2H',region(22+48*i,48))
        nm,paddr,vaddr,size,offset,relptr,lineptr,nrel,nline,sflags,reserved,page = row
        if nrel > 16384 or nline > 16384:
            raise ValueError('section table count outside bounded scope')
        if nrel:
            region(relptr,nrel*12)
        if nline:
            raise ValueError('line tables outside proof scope')
        raw = region(offset,size) if offset else b''
        sections.append({'name':name(nm),'size_octets':size,'physical_address':paddr,
                         'virtual_address':vaddr,'flags':sflags,'memory_page':page,
                         'relocations':nrel,'raw_sha256':hashlib.sha256(raw).hexdigest()})
    symbols = []
    i = 0
    while i < nsyms:
        raw,value,section,typ,storage,aux = struct.unpack('<8sIhHBB',region(symptr+18*i,18))
        if i+1+aux > nsyms:
            raise ValueError('auxiliary symbol table overrun')
        symbols.append({'name':name(raw),'value':value,'section':section,
                        'type':typ,'storage_class':storage,'auxiliary_entries':aux})
        i += 1+aux
    return {'version':version,'target':target,'header_flags':flags,
            'header_relocation_stripped_bit':bool(flags&1),'optional_header_octets':opthdr,
            'sections':sections,'symbols':symbols,
            'legacy_loader_task_header_rejects':bool(flags&1),
            'gateway_task_ready':False,
            'scope':'metadata check of a generated numerical object; no task/firmware loading'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('object',type=Path)
    p.add_argument('output',type=Path)
    args = p.parse_args()
    if args.object.stat().st_size > 1024*1024:
        raise SystemExit('object exceeds size bound')
    data = args.object.read_bytes()
    result = inspect(data)
    # Negative fixtures exercise structural bounds on our trusted generated object.
    rejected = 0
    variants = [data[:21],data[:-1]]
    for offset,packing,value in ((2,'<H',65535),(8,'<I',0xFFFFFFFF),
                                  (12,'<I',0xFFFFFFFF),(20,'<H',0)):
        bad = bytearray(data)
        struct.pack_into(packing,bad,offset,value)
        variants.append(bytes(bad))
    for bad in variants:
        try:
            inspect(bad)
        except (ValueError,struct.error):
            rejected += 1
        else:
            raise AssertionError('malformed fixture accepted')
    result.update(object_sha256=hashlib.sha256(data).hexdigest(),malformed_fixtures_rejected=rejected)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
