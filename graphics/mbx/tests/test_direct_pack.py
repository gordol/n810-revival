"""Compile the production direct packer and compare every wire byte."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'mesa/sp_mbx_backend.h').read_text()
wire=s[s.index('struct mbx_wire_vertex'):s.index('static void mbx_fail')]
helper=s[s.index('static inline bool mbx_finite4'):s.index('static void mbx_fill_job')]
main=r'''
int main(void){
 struct mbx_color_cache cache={0};unsigned checks=0;uint32_t rng=0x8130;
 for(unsigned n=0;n<20000;++n){
  float values[3][3][4];const float (*v[3])[4]={values[0],values[1],values[2]};
  for(unsigned i=0;i<3;++i)for(unsigned a=0;a<3;++a)for(unsigned c=0;c<4;++c){
   rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;uint32_t b=rng;if((b&0x7f800000)==0x7f800000)b&=0x807fffff;memcpy(&values[i][a][c],&b,4);
  }
  unsigned slot=1+(n&1),prov=(n%3);bool smooth=n&2;
  struct mbx_wire_primitive actual,expected={.depth=1,.write=1,.func=1,.smooth=smooth};
  for(unsigned i=0;i<3;++i){memcpy(&expected.v[i].x,values[i][0],16);expected.v[i].color=mbx_color(smooth?values[i][slot]:values[prov][slot]);}
  assert(mbx_pack_direct(&actual,&cache,v,values[prov],slot,smooth));assert(!memcmp(&actual,&expected,sizeof(actual)));++checks;
  for(unsigned i=0;i<3;++i)for(unsigned c=0;c<4;++c){float old=values[i][0][c];values[i][0][c]=NAN;assert(!mbx_pack_direct(&actual,&cache,v,values[prov],slot,smooth));values[i][0][c]=old;++checks;}
  for(unsigned i=0;i<3;++i)if(smooth||i==prov)for(unsigned c=0;c<4;++c){float old=values[i][slot][c];values[i][slot][c]=INFINITY;assert(!mbx_pack_direct(&actual,&cache,v,values[prov],slot,smooth));values[i][slot][c]=old;++checks;}
 }
 printf("PASS %u direct packet equality and invalid-input rejection cases\n",checks);
}
'''
with tempfile.TemporaryDirectory(prefix='mbx-direct-pack-') as d:
 p=Path(d);(p/'test.c').write_text('#include <math.h>\n#include <stdio.h>\n#include <assert.h>\n#include "mbx_color_cache.h"\n'+wire+helper+main)
 subprocess.run(['cc','-O2','-fsanitize=address,undefined','-I'+str(root/'mesa'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
