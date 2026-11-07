"""Check saved 8x8 fill bytes offline; a match does not prove GPU execution."""
import argparse,json,struct
from pathlib import Path
PAGE=4096

def check(*,pixel,before,after,guard,tables,expected_tables):
    if type(pixel) is not int or not 0<=pixel<=0xffffffff:
        raise ValueError('expected pixel must be an unsigned 32-bit word')
    for name,value,length in [('before',before,PAGE),('after',after,PAGE),
                              ('guard',guard,PAGE),('tables',tables,8*PAGE),
                              ('expected tables',expected_tables,8*PAGE)]:
        if type(value) is not bytes or len(value)!=length:raise ValueError(name+' length/type mismatch')
    expected=struct.pack('<I',pixel)*64+bytes([0x3c])*(PAGE-256)
    if before!=bytes([0x3c])*PAGE:raise ValueError('initial target does not match poison pattern')
    if before==expected:raise ValueError('expected output is indistinguishable from initial target')
    if after!=expected:raise ValueError('target pixels or untouched tail mismatch')
    if guard!=bytes([0xa5])*PAGE:raise ValueError('guard page changed')
    if tables!=expected_tables:raise ValueError('page tables changed')
    return dict(status='SAVED_FILL_BYTES_MATCH_ONLY',pixels_checked=64,
                target_tail_bytes_checked=PAGE-256,guard_bytes_checked=PAGE,
                table_bytes_checked=8*PAGE,hardware_execution_verified=False)

def bounded(path,length):
    with Path(path).open('rb') as f:value=f.read(length+1)
    if len(value)!=length:raise ValueError(str(path)+' wrong length')
    return value

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pixel',type=lambda s:int(s,0),required=True)
    for name in ('before','after','guard','tables','expected-tables'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(check(pixel=a.pixel,before=bounded(a.before,PAGE),after=bounded(a.after,PAGE),
        guard=bounded(a.guard,PAGE),tables=bounded(a.tables,8*PAGE),expected_tables=bounded(a.expected_tables,8*PAGE)),indent=2))
