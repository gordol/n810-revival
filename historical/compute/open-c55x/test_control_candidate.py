#!/usr/bin/env python3
"""Bounded metadata/byte checks of the experimental GPL C55x control patch.

No DSP execution, arbitrary firmware inspection or Gateway-task validation.
Instruction fields come from TI SPRU374G; the original fixture is unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


def run(argv):
    p = subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=20)
    if p.returncode:
        raise RuntimeError(f'{argv[0]} exited {p.returncode}: {p.stdout}{p.stderr}')
    return p.stdout


def generated_coff(path):
    data = path.read_bytes()
    assert 22 <= len(data) <= 2*1024*1024
    def region(start,size):
        assert start >= 0 and size >= 0 and start+size <= len(data)
        return data[start:start+size]
    version,nsects,_,symptr,nsyms,opt,flags,target = struct.unpack('<HHIIIHHH',region(0,22))
    assert version==0xc2 and target==0x9c and opt in (0,28)
    assert 1 <= nsects <= 16 and nsyms <= 4096
    strings = symptr+18*nsyms
    size = struct.unpack('<I',region(strings,4))[0]
    table = region(strings,size)
    def name(raw):
        if raw[:4]==bytes(4):
            offset = struct.unpack('<I',raw[4:])[0]
            assert 4 <= offset < len(table)
            end = table.find(b'\0',offset)
            assert end >= 0
            return table[offset:end].decode('ascii')
        return raw.split(b'\0',1)[0].decode('ascii')
    sections = {}
    for i in range(nsects):
        row = struct.unpack('<8s9I2H',region(22+opt+48*i,48))
        nm,pa,va,size,offset,rp,lp,nr,nl,sflags,_,page = row
        assert nr <= 4096 and nl==0
        relocations = [struct.unpack('<IIHH',region(rp+12*j,12)) for j in range(nr)]
        sections[name(nm)] = dict(address=va,bytes=region(offset,size) if offset else b'',
                                 relocations=relocations,flags=sflags,page=page)
    symbols = {}
    i = 0
    while i < nsyms:
        raw,value,section,typ,storage,aux = struct.unpack('<8sIhHBB',region(symptr+18*i,18))
        assert i+aux < nsyms
        symbols[name(raw)] = value
        i += 1+aux
    return dict(sections=sections,symbols=symbols,flags=flags)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('workspace',type=Path,help='separate candidate workspace with source/ and build/')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--local-leaf',type=Path,default=Path(__file__).with_name('fir8_std.s'))
    args = p.parse_args()
    root,out = args.workspace.resolve(),args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    assembler,linker,dump = (root/'build'/part for part in ('gas/as-new','ld/ld-new','binutils/objdump'))
    tests = root/'source/gas/testsuite/gas/tic55x'
    instruction = re.compile(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s',re.M)
    suites = []
    for fixture in sorted(tests.glob('*.d')):
        obj = out/(fixture.stem+'.o')
        run([assembler,'-I',tests,fixture.with_suffix('.s'),'-o',obj])
        actual = run([dump,'-dr',obj])
        (out/(fixture.stem+'.dis')).write_text(actual)
        wanted,got = instruction.findall(fixture.read_text()),instruction.findall(actual)
        row = dict(name=fixture.stem,instructions=len(got),unchanged_fixture_byte_match=wanted==got)
        if fixture.stem!='program_control':
            assert wanted==got,row
        suites.append(row)
    assert len(suites)==7 and sum(r['instructions'] for r in suites if r['name']!='program_control')==1032
    control = generated_coff(out/'program_control.o')
    text = control['sections']['.text']['bytes']
    symbols = control['symbols']
    # Fixed fixture layout after relaxation; target arithmetic independently
    # follows the manual's encoded offset relative to the following instruction.
    fields = [(0,2,'l4',None),(2,3,'L8',(2,1)),(5,3,'L16',(2,1)),
              (0xf,3,'L7',(1,2)),(0x12,3,'L16',(1,2)),
              (0x19,4,'L16',(2,2)),(0x24,3,'L16',(1,2)),
              (0x2b,4,'L8',(3,1)),(0x2f,4,'L8',(3,1)),
              (0x3f,2,'pmad_l',None),(0x44,3,'pmad',(1,2))]
    checked = []
    for address,length,label,field in fields:
        code = text[address:address+length]
        if address==0:
            displacement = (int.from_bytes(code,'big')>>7)&15
        elif address==0x3f:
            displacement = code[1]&0x7f
        else:
            offset,size = field
            displacement = int.from_bytes(code[offset:offset+size],'big',signed=address!=0x44)
        expected = symbols[label]-address-length
        assert displacement==expected,(address,label,displacement,expected)
        checked.append(dict(address=address,length=length,label=label,encoded_offset=displacement))
    relocs = control['sections']['.text']['relocations']
    assert [(r[0],r[3]) for r in relocs]==[(0xa,5),(0x16,5),(0x1f,5),(0x28,5)]
    backward_source,backward_obj = out/'backward.s',out/'backward.o'
    backward_source.write_text(' .text\n_target:\n NOP\n B _target\n CALL _target\n BCC _target,AC1 > #0\n BCC _target,AR7 >= #127\n BCCU _target,AR7 >= #127\n RET\n')
    run([assembler,backward_source,'-o',backward_obj])
    backward = generated_coff(backward_obj)['sections']['.text']['bytes']
    assert backward==bytes.fromhex('20 4a7d 08fffa 0441f7 6ff87ff3 6ff97fef 4804'),backward.hex()
    branch_ranges = []
    for gap in (0,1,62,63,64,65,127,128,32766,32767,32768):
        source,obj = out/('range-'+str(gap)+'.s'),out/('range-'+str(gap)+'.o')
        source.write_text(' .text\n .global _entry\n_entry:\n B _target\n'+' NOP\n'*gap+'_target:\n RET\n')
        run([assembler,source,'-o',obj])
        script,exe = out/('range-'+str(gap)+'.ld'),out/('range-'+str(gap)+'.out')
        base = 0x1000
        script.write_text('SECTIONS { .text 0x1000 : { *(.text) } .data : { *(.data) } .bss : { *(.bss) } }\n')
        run([linker,'-T',script,'-e','_entry',obj,'-o',exe])
        result = generated_coff(exe)
        raw = result['sections']['.text']['bytes']
        if raw[0]==0x4a:
            assert gap <= 63
            prefix = b'\x4a'+bytes([gap])
        elif raw[0]==0x06:
            assert gap <= 32767
            prefix = b'\x06'+gap.to_bytes(2,'big')
        else:
            assert raw[0]==0x6a
            prefix = b'\x6a'+(base+4+gap).to_bytes(3,'big')
        expected = prefix+bytes([0x20])*gap+b'\x48\x04'
        assert result['sections']['.text']['bytes']==expected,(gap,result['sections']['.text']['bytes'][:4].hex())
        assert result['symbols']['_target']==base+len(prefix)+gap
        minimum = 2 if gap <= 63 else 3 if gap <= 32767 else 4
        branch_ranges.append(dict(gap=gap,instruction_bytes=len(prefix),linked_bytes_match=True,
                                  shortest_possible_form=len(prefix)==minimum))

    repeat_ranges = []
    for mnemonic,gaps in (('RPTBLOCAL',(0,63,64,127)),('RPTB',(0,32767,32768,65535))):
        for gap in gaps:
            source,obj = out/(mnemonic+str(gap)+'.s'),out/(mnemonic+str(gap)+'.o')
            source.write_text(' .text\n '+mnemonic+' _target\n'+' NOP\n'*gap+'_target:\n NOP\n')
            run([assembler,source,'-o',obj])
            raw = generated_coff(obj)['sections']['.text']['bytes']
            prefix = b'\x4a'+bytes([0x80|gap]) if mnemonic=='RPTBLOCAL' else b'\x0e'+gap.to_bytes(2,'big')
            assert raw==prefix+bytes([0x20])*(gap+1),(mnemonic,gap,raw[:4].hex())
            repeat_ranges.append(dict(mnemonic=mnemonic,gap=gap,bytes_match=True))
    literal_forms = {'b':('B',b'\x6a'),'call':('CALL',b'\x6c'),
                     'bcc':('BCC',b'\x68\x41'),'callcc':('CALLCC',b'\x69\x41')}
    literal_cases = []
    for name,(mnemonic,prefix) in literal_forms.items():
        for value in (0x10000,0x7fffff,0xffffff,0x1000000):
            source,obj = out/('literal-'+name+str(value)+'.s'),out/('literal-'+name+str(value)+'.o')
            operand = hex(value)+(',AC1 > #0' if name in ('bcc','callcc') else '')
            source.write_text(' .text\n '+mnemonic+' '+operand+'\n RET\n')
            process = subprocess.run([str(assembler),str(source),'-o',str(obj)],capture_output=True,text=True,timeout=20)
            row = dict(form=name,value=value,exit_code=process.returncode,messages=process.stdout+process.stderr)
            if value < 2**24:
                assert process.returncode==0,row
                assert generated_coff(obj)['sections']['.text']['bytes']==prefix+value.to_bytes(3,'big')+b'\x48\x04'
                row['bytes_match'] = True
            else:
                assert process.returncode>0,row
                row['out_of_range_literal_rejected'] = True
            literal_cases.append(row)

    forms = {'b':('B _target',b'\x6a'),'call':('CALL _target',b'\x6c'),
             'bcc':('BCC _target,AC1 > #0',b'\x68\x41'),
             'callcc':('CALLCC _target,AC1 > #0',b'\x69\x41')}
    target_source = out/'target.s'
    target_source.write_text(' .text\n .global _target\n_target:\n NOP\n RET\n')
    run([assembler,target_source,'-o',out/'target.o'])
    links,upper_address = [],[]
    for name,(line,prefix) in forms.items():
        for tail in (False,True):
            stem = name+('-tail' if tail else '-ret')
            source,obj = out/(stem+'.s'),out/(stem+'.o')
            source.write_text(' .text\n .global _entry\n .global _target\n_entry:\n '+line+'\n'+('' if tail else ' RET\n'))
            run([assembler,source,'-o',obj])
            original = generated_coff(obj)['sections']['.text']
            assert len(original['relocations'])==1 and original['relocations'][0][3]==5
            for base in (0,0x7fff,0xffff,0x123400,0xffffe0,0xfffffc,0x1000000):
                stem2 = stem+'-'+hex(base)
                script,exe = out/(stem2+'.ld'),out/(stem2+'.out')
                # Synthetic addresses for a linker test; no real device memory map.
                script.write_text('SECTIONS { .text '+hex(base)+' : { *(.text) } .data : { *(.data) } .bss : { *(.bss) } }\n')
                process = subprocess.run([str(linker),'-T',str(script),'-e','_entry',str(obj),str(out/'target.o'),'-o',str(exe)],
                                         capture_output=True,text=True,timeout=20)
                target = base+len(prefix)+3+(0 if tail else 2)
                row = dict(form=name,tail=tail,base=base,target=target,exit_code=process.returncode,
                           messages=process.stdout+process.stderr)
                if target >= 2**24:
                    row['scope'] = 'UNASSESSED: TI COFF uses upper address bits for memory pages; this is outside the verified page-zero program-address contract.'
                    upper_address.append(row)
                    continue
                assert process.returncode==0,row
                result = generated_coff(exe)
                expected = prefix+target.to_bytes(3,'big')+(b'' if tail else b'\x48\x04')+b'\x20\x48\x04'
                assert result['sections']['.text']['address']==base
                assert result['sections']['.text']['bytes']==expected,(row,result['sections']['.text']['bytes'].hex(),expected.hex())
                assert result['symbols']['_entry']==base and result['symbols']['_target']==target
                assert not result['sections']['.text']['relocations']
                row.update(bytes_match=True,symbols_match=True,text_sha256=hashlib.sha256(expected).hexdigest())
                links.append(row)
    assert len(links)==40 and len(upper_address)==16
    leaf_object = out/'fir8_std.o'
    run([assembler,args.local_leaf.resolve(),'-o',leaf_object])
    leaf = generated_coff(leaf_object)['sections']['.text']['bytes']
    assert len(leaf)==38 and hashlib.sha256(leaf).hexdigest()=='1f8d2855fe947c179598c3ed0bcffd83ba67bbdb774623b67cd78b14e79efa7c'
    caller_source,caller = out/'fir-caller.s',out/'fir-caller.o'
    caller_source.write_text(' .text\n .global _entry\n .global _n810_fir8_std\n_entry:\n CALL _n810_fir8_std\n RET\n')
    run([assembler,caller_source,'-o',caller])
    leaf_links = []
    for base in (0,0x7fff,0xffff,0x123400):
        script,exe = out/('leaf-'+hex(base)+'.ld'),out/('leaf-'+hex(base)+'.out')
        script.write_text('SECTIONS { .text '+hex(base)+' : { *(.text) } .data : { *(.data) } .bss : { *(.bss) } }\n')
        run([linker,'-T',script,'-e','_entry',caller,leaf_object,'-o',exe])
        result = generated_coff(exe)
        expected = b'\x6c'+(base+6).to_bytes(3,'big')+b'\x48\x04'+leaf
        assert result['sections']['.text']['bytes']==expected
        assert result['symbols']['_n810_fir8_std']==base+6
        leaf_links.append(dict(base=base,target=base+6,bytes_match=True,
                               text_sha256=hashlib.sha256(expected).hexdigest()))
    result = dict(status='LIMITED',hardware_execution=False,gateway_task_ready=False,
                  general_linker_verified=False,data_suites=suites,local_target_fields=checked,
                  external_rel24_records=len(relocs),linked_address_cases=links,
                  backward_branch_bytes_match=True,branch_range_cases=branch_ranges,
                  repeat_range_cases=repeat_ranges,p24_literal_cases=literal_cases,
                  upper_address_probes=upper_address,upper_address_semantics_verified=False,
                  fir_leaf_links=leaf_links,fir_leaf_source_sha256=hashlib.sha256(args.local_leaf.read_bytes()).hexdigest(),
                  interpretation='Selected control encodings and linked bytes checked. Not a general ISA/linker, firmware, ABI or hardware proof.',
                  source_sha256={str(n):hashlib.sha256((root/'source'/n).read_bytes()).hexdigest() for n in
                                 ('gas/config/tc-tic55x.c','bfd/coff-tic55x.c')})
    (out/'control-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],data_encodings=1032,local_target_fields=len(checked),
                          external_rel24_records=len(relocs),linked_address_cases=len(links),
                          backward_branch_bytes_match=True,branch_range_cases=len(branch_ranges),
                          repeat_range_cases=len(repeat_ranges),p24_literal_cases=len(literal_cases),
                          fir_leaf_links=len(leaf_links),upper_address_probes_unassessed=len(upper_address),
                          hardware_execution=False,gateway_task_ready=False),indent=2))


if __name__=='__main__':
    main()
