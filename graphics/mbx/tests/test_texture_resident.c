#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../common/mbx_texture_resident.h"
int main(void){
 unsigned bytes=80+32*18*4+64,compact=0,expanded=0;
 unsigned char *f=calloc(1,bytes),*wire=malloc(bytes+32),*copy=malloc(bytes+32);
 struct mbx_texture_resident s={.data=malloc(MBX_WIRE_LINEAR_PAYLOAD)};struct mbx_wire_resources r;
 unsigned h[12]={0x3156474dU,9,bytes,1,400,256,0,0,0,0,0,5},t[4]={1,32*18*4,0,0};struct mbx_wire_resource d={8,32*18*4,0,(16<<16)|16};
 memcpy(f,h,48);memcpy(f+48,t,16);memcpy(f+64,&d,16);for(unsigned i=80;i<bytes;i++)f[i]=(i*13)^71;
 assert(!mbx_wire_resources_parse(f,bytes,&r));assert(!mbx_texture_resident_matches(&s,f,&r));
 assert(!mbx_texture_resident_commit(&s,f,&r));
 for(unsigned i=0;i<1000;i++){
  f[bytes-1]=(unsigned char)i;
  assert(!mbx_texture_ref_pack(&s,f,bytes,wire,bytes+32,&compact));assert(compact==176);
  memcpy(copy,wire,compact);((struct mbx_texture_ref *)copy)->session++;assert(mbx_texture_ref_expand(&s,copy,compact,bytes,&expanded));
  memcpy(copy,wire,compact);((struct mbx_texture_ref *)copy)->generation++;assert(mbx_texture_ref_expand(&s,copy,compact,bytes,&expanded));
  assert(!mbx_texture_ref_expand(&s,wire,compact,bytes,&expanded));assert(expanded==bytes&&!memcmp(f,wire,bytes));
 }
 assert(!mbx_texture_ref_pack(&s,f,bytes,wire,bytes+32,&compact));
 for(unsigned n=0;n<compact;n++){memcpy(copy,wire,compact);assert(mbx_texture_ref_expand(&s,copy,n,bytes,&expanded));}
 f[80]^=1;assert(!mbx_texture_resident_matches(&s,f,&r));assert(mbx_texture_ref_pack(&s,f,bytes,wire,bytes+32,&compact));
 assert(!mbx_texture_resident_commit(&s,f,&r));assert(s.generation==2);s.valid=0;assert(mbx_texture_ref_pack(&s,f,bytes,wire,bytes+32,&compact));
 s.generation=~0U;assert(mbx_texture_resident_commit(&s,f,&r));
 free(f);free(wire);free(copy);free(s.data);puts("texture residency: 1000 exact expansions, stale tokens/truncation/mutation/retirement rejected");
}
